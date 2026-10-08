"""Import CSV des candidats : contrôles, détection des doublons et rapport d'erreurs (§7.3).

Principes :
- « tout ou rien » : la phase 1 lit et contrôle TOUTES les lignes sans rien écrire ; s'il y a
  une erreur, le rapport les liste toutes et la base n'est pas touchée (D21) ;
- la phase 2 (écriture) n'a lieu que si le fichier est sans erreur, dans une transaction
  verrouillant le concours ; en simulation, cette transaction est annulée à la fin ;
- le contenu est stocké tel quel : l'échappement se fait à l'affichage (REC-26).
"""
import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction

from apps.candidats.models import Candidat, Participation
from apps.candidats.services import inscrire
from apps.concours.models import Concours

DATE_MINIMALE = date(1900, 1, 1)
FORMATS_DATE = ("%d/%m/%Y", "%Y-%m-%d")
OBLIGATOIRES = ("nom", "prenom", "categorie")
FACULTATIVES = ("date_naissance", "sexe", "ville", "structure")

# En-tête normalisé (minuscules, sans accents ni séparateurs) → nom de colonne canonique.
ALIAS_COLONNES = {
    "nom": "nom",
    "prenom": "prenom",
    "prenoms": "prenom",
    "datenaissance": "date_naissance",
    "datedenaissance": "date_naissance",
    "naissance": "date_naissance",
    "sexe": "sexe",
    "genre": "sexe",
    "ville": "ville",
    "structure": "structure",
    "ecole": "structure",
    "categorie": "categorie",
}
SEXES = {"m": "M", "masculin": "M", "homme": "M", "f": "F", "feminin": "F", "femme": "F"}


@dataclass
class ErreurImport:
    ligne: int | None  # numéro physique dans le fichier (l'en-tête est la ligne 1)
    message: str


@dataclass
class InscriptionImport:
    ligne: int
    numero_candidat: int
    nom_complet: str
    categorie: str


@dataclass
class RapportImport:
    simulation: bool = False
    lignes_lues: int = 0
    erreurs: list = field(default_factory=list)
    inscriptions: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.erreurs

    def texte(self):
        if self.erreurs:
            lignes = [
                f"Ligne {e.ligne} : {e.message}" if e.ligne else e.message for e in self.erreurs
            ]
            return "\n".join(lignes)
        n = len(self.inscriptions)
        resume = f"{n} candidat{'s' if n > 1 else ''} inscrit{'s' if n > 1 else ''}."
        if self.simulation:
            resume += " Simulation : rien n'a été enregistré."
        return resume


def _normaliser(texte):
    """Minuscules, sans accents, sans espaces ni ponctuation : pour comparer des en-têtes."""
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return "".join(c for c in sans_accents.casefold() if c.isalnum())


def _decoder(octets):
    """UTF-8 (avec ou sans BOM) d'abord ; sinon cp1252, l'encodage du « CSV » d'Excel français."""
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            return octets.decode(encodage)
        except UnicodeDecodeError:
            continue
    return None


def _separateur(en_tete):
    return max(";,\t", key=en_tete.count)


def _lire_date(texte):
    for format_date in FORMATS_DATE:
        try:
            valeur = datetime.strptime(texte, format_date).date()
        except ValueError:
            continue
        if DATE_MINIMALE <= valeur <= date.today():
            return valeur
        break
    raise ValueError(f"Date de naissance invalide : « {texte} » (attendu JJ/MM/AAAA ou AAAA-MM-JJ, entre 1900 et aujourd'hui).")


def _lire_sexe(texte):
    if not texte:
        return ""
    try:
        return SEXES[_normaliser(texte)]
    except KeyError:
        raise ValueError(f"Sexe inconnu : « {texte} » (attendu M ou F).") from None


def _lire_lignes(texte, rapport):
    """Renvoie [(numéro de ligne, {colonne: valeur})] ; ajoute au rapport les erreurs de structure."""
    if not texte.strip():
        rapport.erreurs.append(ErreurImport(None, "Le fichier est vide."))
        return []
    separateur = _separateur(texte.splitlines()[0])
    lecteur = csv.reader(io.StringIO(texte, newline=""), delimiter=separateur)
    try:
        en_tete = next(lecteur)
    except StopIteration:
        rapport.erreurs.append(ErreurImport(None, "Le fichier est vide."))
        return []
    colonnes = [ALIAS_COLONNES.get(_normaliser(c)) for c in en_tete]
    for obligatoire in OBLIGATOIRES:
        if obligatoire not in colonnes:
            rapport.erreurs.append(ErreurImport(1, f"Colonne obligatoire absente : « {obligatoire} »."))
    if not rapport.ok:
        return []
    lignes = []
    for cellules in lecteur:
        if not any(c.strip() for c in cellules):
            continue  # ligne vide : ignorée
        valeurs = {}
        for colonne, cellule in zip(colonnes, cellules):
            if colonne and colonne not in valeurs:
                valeurs[colonne] = cellule.strip()
        lignes.append((lecteur.line_num, valeurs))
    if not lignes:
        rapport.erreurs.append(ErreurImport(None, "Le fichier ne contient aucune ligne de candidat."))
    return lignes


def _controler(lignes, concours, rapport):
    """Phase 1 : contrôle chaque ligne sans écrire. Renvoie le plan [(ligne, valeurs, catégorie)]."""
    categories = {c.nom.strip().casefold(): c for c in concours.categories.all()}
    limites = {n: Candidat._meta.get_field(n).max_length for n in ("nom", "prenom", "ville", "structure")}
    plan, vus = [], {}
    for numero, valeurs in lignes:
        rapport.lignes_lues += 1
        avant = len(rapport.erreurs)

        def refuser(message, numero=numero):
            rapport.erreurs.append(ErreurImport(numero, message))

        for champ in OBLIGATOIRES:
            if not valeurs.get(champ):
                refuser(f"Le champ « {champ} » est vide.")
        for champ, maximum in limites.items():
            if len(valeurs.get(champ, "")) > maximum:
                refuser(f"Le champ « {champ} » dépasse {maximum} caractères.")

        categorie = None
        if valeurs.get("categorie"):
            categorie = categories.get(valeurs["categorie"].casefold())
            if categorie is None:
                refuser(f"Catégorie inconnue dans ce concours : « {valeurs['categorie']} ».")

        naissance, sexe = None, ""
        try:
            if valeurs.get("date_naissance"):
                naissance = _lire_date(valeurs["date_naissance"])
        except ValueError as erreur:
            refuser(str(erreur))
        try:
            sexe = _lire_sexe(valeurs.get("sexe", ""))
        except ValueError as erreur:
            refuser(str(erreur))

        if len(rapport.erreurs) > avant or categorie is None:
            continue

        cle = (valeurs["nom"].casefold(), valeurs["prenom"].casefold(), naissance, categorie.pk)
        if cle in vus:
            refuser(f"Doublon : même candidat et même catégorie que la ligne {vus[cle]}.")
            continue
        vus[cle] = numero

        existant = _candidats_existants(concours.organisation_id, valeurs, naissance)
        deja = Participation.objects.filter(candidat__in=existant, categorie=categorie).first()
        if deja is not None:
            refuser(
                f"Candidat déjà inscrit dans la catégorie « {categorie.nom} » (n° {deja.numero_candidat})."
            )
            continue
        valeurs = dict(valeurs, date_naissance=naissance, sexe=sexe)
        plan.append((numero, valeurs, categorie))
    return plan


def _candidats_existants(organisation_id, valeurs, naissance):
    """Candidats du MÊME client portant ce nom, ce prénom (sans tenir compte de la casse) et cette date (RM-20)."""
    return list(
        Candidat.objects.filter(
            organisation_id=organisation_id,
            nom__iexact=valeurs["nom"],
            prenom__iexact=valeurs["prenom"],
            date_naissance=naissance,
        ).order_by("pk")
    )


def _ecrire(plan, concours, rapport):
    """Phase 2 : crée les candidats manquants et les participations, dans l'ordre du fichier."""
    crees = {}  # une même personne présente dans deux catégories n'est créée qu'une fois
    for numero, valeurs, categorie in plan:
        cle = (valeurs["nom"].casefold(), valeurs["prenom"].casefold(), valeurs["date_naissance"])
        candidat = crees.get(cle)
        if candidat is None:
            existants = _candidats_existants(concours.organisation_id, valeurs, valeurs["date_naissance"])
            candidat = existants[0] if existants else Candidat.objects.create(
                organisation_id=concours.organisation_id,
                nom=valeurs["nom"],
                prenom=valeurs["prenom"],
                date_naissance=valeurs["date_naissance"],
                sexe=valeurs["sexe"],
                ville=valeurs.get("ville", ""),
                structure=valeurs.get("structure", ""),
            )
            crees[cle] = candidat
        participation = inscrire(candidat, categorie)
        rapport.inscriptions.append(
            InscriptionImport(numero, participation.numero_candidat, candidat.nom_complet, categorie.nom)
        )


def importer_candidats(concours, chemin, *, simuler=False):
    """Importe un fichier CSV de candidats dans un concours ; renvoie un ``RapportImport``."""
    rapport = RapportImport(simulation=simuler)
    texte = _decoder(open(chemin, "rb").read())
    if texte is None:
        rapport.erreurs.append(ErreurImport(None, "Encodage du fichier non reconnu (UTF-8 ou Windows-1252 attendu)."))
        return rapport

    with transaction.atomic():
        concours = Concours.objects.select_for_update().get(pk=concours.pk)
        if concours.etat in (Concours.Etat.TERMINE, Concours.Etat.ARCHIVE):
            rapport.erreurs.append(
                ErreurImport(
                    None,
                    f"Le concours est {concours.get_etat_display().lower()} : il ne peut plus recevoir d'inscriptions.",
                )
            )
            return rapport
        lignes = _lire_lignes(texte, rapport)
        if not rapport.ok:
            return rapport
        plan = _controler(lignes, concours, rapport)
        if not rapport.ok:
            return rapport
        _ecrire(plan, concours, rapport)
        if simuler:
            transaction.set_rollback(True)
    return rapport
