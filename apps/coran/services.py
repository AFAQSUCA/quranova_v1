"""Règles métier du corpus (cf. §12.3 : versionnement et immutabilité).

Ces fonctions ne touchent pas à la base de données : elles reçoivent des
valeurs et lèvent ``CorpusImmuableError`` si l'opération est interdite.
Les modèles se chargent de lire l'état réel en base et d'appeler ces fonctions.
"""
from apps.coran.exceptions import CorpusImmuableError, CorpusInvalideError, ReferenceInvalideError


STATUTS_FIGES = {"validee", "active", "retiree"}

TRANSITIONS_AUTORISEES = {
    "importee": {"validee"},
    "validee": {"active", "retiree"},
    "active": {"retiree"},
    "retiree": set(),
}




NOMBRE_DE_SOURATES = 114
NOMBRE_DE_VERSETS = 6236


def verifier_transition_statut(ancien_statut, nouveau_statut, date_validation):
    """Refuse un changement de statut d'une version du corpus qui n'est pas autorisé."""
    if nouveau_statut not in TRANSITIONS_AUTORISEES.get(ancien_statut, set()):
        raise CorpusImmuableError(
            f"Transition de statut interdite : « {ancien_statut} » vers « {nouveau_statut} »."
        )
    if nouveau_statut == "validee" and date_validation is None:
        raise CorpusImmuableError(
            "Une version ne peut pas être validée sans date de validation (procès-verbal du référent)."
        )


def verifier_ecriture_autorisee(statut_version):
    """Refuse toute écriture sur le contenu d'une version dont le statut est figé."""
    if statut_version in STATUTS_FIGES:
        raise CorpusImmuableError(
            f"Version « {statut_version} » : son contenu est figé. "
            "Pour corriger, importez une nouvelle version."
        )


def controler_corpus(corpus):
    """Contrôles automatiques du §12.2, point 3 : collecte toutes les erreurs, puis les signale."""
    erreurs = []

    numeros = [s.numero for s in corpus.sourates]
    if numeros != list(range(1, NOMBRE_DE_SOURATES + 1)):
        erreurs.append(
            f"{len(numeros)} sourates lues ; attendu : les sourates 1 à {NOMBRE_DE_SOURATES}, sans trou ni doublon"
        )

    total = sum(len(s.versets) for s in corpus.sourates)
    if total != NOMBRE_DE_VERSETS:
        erreurs.append(f"{total} versets lus ; attendu : {NOMBRE_DE_VERSETS}")

    for sourate in corpus.sourates:
        lus = len(sourate.versets)
        if lus != sourate.nombre_versets:
            erreurs.append(
                f"sourate {sourate.numero} : {lus} versets lus, {sourate.nombre_versets} annoncés par les métadonnées"
            )
        if [v.numero for v in sourate.versets] != list(range(1, lus + 1)):
            erreurs.append(f"sourate {sourate.numero} : numérotation des versets discontinue ou dupliquée")
        for verset in sourate.versets:
            if not verset.texte.strip():
                erreurs.append(f"verset {sourate.numero}:{verset.numero} : texte vide")

    if erreurs:
        raise CorpusInvalideError("Corpus invalide : " + " ; ".join(erreurs) + ".")


# --- Passages coraniques (§8.4, §12.4) ------------------------------------------------
#
# Une référence est un couple (sourate, verset), par exemple (2, 255).
# Le « plan » du corpus est un dictionnaire {numéro de sourate: nombre de versets},
# dans l'ordre canonique des sourates.


def _ref(reference):
    return f"{reference[0]}:{reference[1]}"


def verifier_reference(plan, reference):
    """Refuse une référence qui n'existe pas dans le plan, avec un message explicite (REC-31)."""
    if not isinstance(reference, (tuple, list)) or len(reference) != 2:
        raise ReferenceInvalideError(
            f"Référence {reference!r} invalide : une référence est un couple (sourate, verset)."
        )
    sourate, verset = reference
    texte = _ref(reference)
    for valeur, nom in ((sourate, "sourate"), (verset, "verset")):
        if not isinstance(valeur, int) or isinstance(valeur, bool):
            raise ReferenceInvalideError(
                f"Référence {texte} invalide : le numéro de {nom} doit être un entier."
            )
    if sourate < 1:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : le numéro de sourate doit être supérieur ou égal à 1."
        )
    if sourate not in plan:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : la sourate {sourate} n'existe pas "
            f"dans cette version du corpus (sourates 1 à {max(plan)})."
        )
    if verset < 1:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : le numéro de verset doit être supérieur ou égal à 1."
        )
    if verset > plan[sourate]:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : la sourate {sourate} ne compte que "
            f"{plan[sourate]} versets (le verset {verset} n'existe pas)."
        )


def verifier_ordre_passage(debut, fin):
    """Refuse un passage dont la fin précède le début dans l'ordre canonique (§8.4, point 2).

    Un passage d'un seul verset (début = fin) est permis.
    """
    if tuple(fin) < tuple(debut):
        raise ReferenceInvalideError(
            f"Passage invalide : la fin du passage ({_ref(fin)}) précède son début ({_ref(debut)})."
        )


def references_du_passage(plan, debut, fin):
    """Liste, dans l'ordre canonique, les références de ``debut`` à ``fin`` INCLUSES."""
    (sourate_debut, verset_debut), (sourate_fin, verset_fin) = debut, fin
    references = []
    for sourate, nombre_de_versets in plan.items():
        if sourate < sourate_debut or sourate > sourate_fin:
            continue  # hors du passage
        # Première sourate : on part du verset de début ; les suivantes, du verset 1.
        premier = verset_debut if sourate == sourate_debut else 1
        # Dernière sourate : on s'arrête au verset de fin ; les précédentes, au dernier verset.
        dernier = verset_fin if sourate == sourate_fin else nombre_de_versets
        references.extend((sourate, numero) for numero in range(premier, dernier + 1))
    return references
