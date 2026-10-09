"""Validation d'une version du corpus par le référent coranique (§12.2 points 3 à 7, §12.3 ; jalon J0, livrable L-07).

Ordre des opérations :
1. ``controles_automatiques`` : structure du corpus et aller-retour avec le fichier source (aucune transformation du texte) ;
2. ``echantillon_de_relecture`` : les versets que le référent compare au Mushaf de Médine (liste imposée par le CdC + au moins 1 % de versets tirés) ;
3. le procès-verbal (``documents``) est imprimé, relu et signé par le référent ;
4. ``valider_version`` : l'administrateur enregistre cette validation (nom du référent, date de signature) ; la version devient « validée » et figée ;
5. ``activer_version`` : elle devient la version proposée aux nouveaux concours.

Le texte coranique n'est jamais écrit ni corrigé ici : on le LIT, on le COMPARE, on le montre tel quel (règle absolue n° 1).
"""
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.coran.exceptions import CorpusImmuableError, CorpusInvalideError, ValidationCorpusRefuseeError
from apps.coran.importation import calculer_empreinte_sha256
from apps.coran.models import ValidationCorpus, Verset, VersionCorpus
from apps.utilisateurs.models import Utilisateur

DOSSIER_CORPUS = Path(settings.BASE_DIR) / "data" / "corpus"
NOMBRE_DE_SOURATES, NOMBRE_DE_VERSETS = 114, 6236
PART_DU_TIRAGE = 0.01  # §12.2 point 5 : au moins 1 % des versets

L_SOURATES = "114 sourates, numérotées de 1 à 114"
L_VERSETS = "6 236 versets"
L_METADONNEES = "nombre de versets de chaque sourate conforme aux métadonnées"
L_NUMEROTATION = "aucun verset vide, numérotation continue"
L_ALLER_RETOUR = "aller-retour : texte de la base identique au fichier source, octet par octet"

AYA = re.compile(r'<aya index="\d+" text="([^"]*)"')


@dataclass(frozen=True)
class Controle:
    libelle: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class LigneEchantillon:
    reference: str
    motif: str
    texte: str


def trouver_fichier_source(version, dossier=None):
    """Le fichier du dossier dont l'empreinte SHA-256 est celle de la version (par le contenu, jamais par le nom), ou ``None``."""
    dossier = Path(dossier or DOSSIER_CORPUS)
    for chemin in sorted(dossier.glob("*.xml")) if dossier.is_dir() else []:
        if calculer_empreinte_sha256(chemin) == version.empreinte_sha256:
            return chemin
    return None


def _versets_en_base(version):
    return list(
        Verset.objects.filter(sourate__version=version).order_by("sourate__numero", "numero")
        .values_list("sourate__numero", "numero", "texte")
    )


def controles_automatiques(version, dossier=None):
    """Les cinq contrôles automatiques du §12.2 (points 3 et 4), dans l'ordre ; chacun dit s'il est réussi et pourquoi sinon."""
    sourates = list(version.sourates.order_by("numero").values_list("numero", "nombre_versets"))
    versets = _versets_en_base(version)
    controles = []

    numeros = [n for n, _ in sourates]
    controles.append(Controle(L_SOURATES, numeros == list(range(1, NOMBRE_DE_SOURATES + 1)),
                              "" if numeros == list(range(1, NOMBRE_DE_SOURATES + 1)) else f"{len(numeros)} sourate(s) en base"))
    controles.append(Controle(L_VERSETS, len(versets) == NOMBRE_DE_VERSETS,
                              "" if len(versets) == NOMBRE_DE_VERSETS else f"{len(versets)} verset(s) en base"))

    par_sourate = {}
    for sourate, numero, texte in versets:
        par_sourate.setdefault(sourate, []).append((numero, texte))
    ecarts = [f"sourate {n} : {len(par_sourate.get(n, []))} en base, {annonces} annoncés" for n, annonces in sourates if len(par_sourate.get(n, [])) != annonces]
    controles.append(Controle(L_METADONNEES, not ecarts, " ; ".join(ecarts[:5])))

    problemes = []
    for sourate, lignes in par_sourate.items():
        if [n for n, _ in lignes] != list(range(1, len(lignes) + 1)):
            problemes.append(f"sourate {sourate} : numérotation discontinue")
        problemes += [f"{sourate}:{n} vide" for n, texte in lignes if not texte.strip()]
    controles.append(Controle(L_NUMEROTATION, not problemes, " ; ".join(problemes[:5])))

    controles.append(_aller_retour(version, versets, dossier))
    return controles


def _aller_retour(version, versets_en_base, dossier):
    fichier = trouver_fichier_source(version, dossier)
    if fichier is None:
        return Controle(L_ALLER_RETOUR, False,
                        f"Fichier source introuvable : aucun fichier .xml de {Path(dossier or DOSSIER_CORPUS)} n'a l'empreinte {version.empreinte_sha256[:16]}…")
    # Lecture indépendante de l'analyseur XML : les textes bruts du fichier, comparés dans l'ordre canonique à ceux de la base.
    textes_fichier = AYA.findall(fichier.read_bytes().decode("utf-8"))
    if len(textes_fichier) != len(versets_en_base):
        return Controle(L_ALLER_RETOUR, False, f"{len(textes_fichier)} versets dans le fichier, {len(versets_en_base)} en base")
    for (sourate, numero, texte), source in zip(versets_en_base, textes_fichier):
        if texte != source:
            return Controle(L_ALLER_RETOUR, False, f"différence au verset {sourate}:{numero}")
    return Controle(L_ALLER_RETOUR, True, f"{len(textes_fichier)} versets identiques à {fichier.name}")


def _obligatoires():
    """Les passages imposés par le CdC §12.2 point 5, avec leur motif."""
    return [
        ("sourate 1", lambda s, v: s == 1),
        ("verset 2:255 (verset du Trône)", lambda s, v: (s, v) == (2, 255)),
        ("verset 2:282 (plus long verset)", lambda s, v: (s, v) == (2, 282)),
        ("sourate 36", lambda s, v: s == 36),
        ("sourates 112 à 114", lambda s, v: s in (112, 113, 114)),
    ]


def echantillon_de_relecture(version):
    """Les versets que le référent relit : passages imposés, puis au moins 1 % de versets tirés.

    Le « tirage » est déterministe : on classe les versets restants par l'empreinte SHA-256 de « empreinte de la version | référence » et on prend
    les premiers. Ce n'est pas un enjeu de sécurité (aucun secret), et cela garantit que le procès-verbal régénéré porte exactement le même échantillon.
    """
    versets = _versets_en_base(version)
    obligatoires, restants = [], []
    for sourate, numero, texte in versets:
        motif = next((m for m, regle in _obligatoires() if regle(sourate, numero)), None)
        ligne = LigneEchantillon(f"{sourate}:{numero}", motif or "tirage", texte)
        (obligatoires if motif else restants).append((sourate, numero, ligne))
    nombre = math.ceil(PART_DU_TIRAGE * len(versets))
    classes = sorted(restants, key=lambda x: hashlib.sha256(f"{version.empreinte_sha256}|{x[2].reference}".encode()).hexdigest())[:nombre]
    return [ligne for _, _, ligne in obligatoires] + [ligne for _, _, ligne in sorted(classes, key=lambda x: (x[0], x[1]))]


def empreinte_echantillon(version, echantillon=None):
    echantillon = echantillon if echantillon is not None else echantillon_de_relecture(version)
    return hashlib.sha256((version.empreinte_sha256 + "|" + "|".join(e.reference for e in echantillon)).encode()).hexdigest()


def _verifier_administrateur(utilisateur):
    if not (getattr(utilisateur, "is_authenticated", False) and utilisateur.is_active and utilisateur.role == Utilisateur.Role.ADMINISTRATEUR):
        raise ValidationCorpusRefuseeError("Seul l'administrateur QURANOVA valide ou active une version du corpus (§12.3).")


def valider_version(version, administrateur, referent_nom, date_signature, qualite="", dossier=None):
    """Enregistre la validation d'une version « importée » par le référent coranique ; elle devient « validée » (figée, RM-27)."""
    _verifier_administrateur(administrateur)
    if VersionCorpus.objects.filter(pk=version.pk).values_list("statut", flat=True).first() != VersionCorpus.Statut.IMPORTEE:
        raise CorpusImmuableError("Seule une version « importée » peut être validée : celle-ci l'a déjà été (ou retirée).")
    if not (referent_nom or "").strip():
        raise CorpusInvalideError("Le nom du référent coranique est obligatoire : c'est lui qui signe le procès-verbal.")
    if date_signature > timezone.localdate():
        raise CorpusInvalideError("La date de signature du procès-verbal ne peut pas être dans le futur.")
    controles = controles_automatiques(version, dossier)
    echecs = [c for c in controles if not c.ok]
    if echecs:
        raise CorpusInvalideError("Contrôles automatiques non réussis : " + " ; ".join(f"{c.libelle} ({c.detail})" for c in echecs) + ".")

    with transaction.atomic():
        version.statut = VersionCorpus.Statut.VALIDEE
        version.date_validation = timezone.make_aware(datetime.combine(date_signature, time(12, 0)))
        version.save()
        validee = ValidationCorpus.objects.create(
            version=version, referent_nom=referent_nom.strip(), referent_qualite=(qualite or "").strip(), date_signature=date_signature,
            validee_par=administrateur, controles=[{"libelle": c.libelle, "ok": c.ok, "detail": c.detail} for c in controles],
            empreinte_echantillon=empreinte_echantillon(version),
        )
        journaliser("corpus.valide", auteur=administrateur, objet=version,
                    details={"referent": validee.referent_nom, "date_signature": date_signature, "empreinte": version.empreinte_sha256})
    return validee


def activer_version(version, administrateur):
    """Rend la version « active » : c'est celle proposée aux nouveaux concours (les concours existants gardent la leur)."""
    _verifier_administrateur(administrateur)
    if VersionCorpus.objects.filter(pk=version.pk).values_list("statut", flat=True).first() != VersionCorpus.Statut.VALIDEE:
        raise CorpusImmuableError("Seule une version « validée » (procès-verbal signé) peut être activée (§12.2 point 7).")
    if VersionCorpus.objects.filter(riwaya=version.riwaya, statut=VersionCorpus.Statut.ACTIVE).exclude(pk=version.pk).exists():
        raise CorpusImmuableError("Une autre version est déjà active pour cette riwāya : une seule version active à la fois.")
    with transaction.atomic():
        version.statut = VersionCorpus.Statut.ACTIVE
        version.save()
        journaliser("corpus.active", auteur=administrateur, objet=version, details={"empreinte": version.empreinte_sha256})
    return version
