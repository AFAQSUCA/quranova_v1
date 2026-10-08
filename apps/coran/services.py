"""Règles métier du corpus (cf. §12.3 : versionnement et immutabilité).

Ces fonctions ne touchent pas à la base de données : elles reçoivent des
valeurs et lèvent ``CorpusImmuableError`` si l'opération est interdite.
Les modèles se chargent de lire l'état réel en base et d'appeler ces fonctions.
"""
from apps.coran.exceptions import CorpusImmuableError, ReferenceInvalideError  # noqa: F401


def verifier_transition_statut(ancien_statut, nouveau_statut, date_validation):
    """Refuse un changement de statut d'une version du corpus qui n'est pas autorisé.

    Statuts possibles : « importee », « validee », « active », « retiree ».

    TODO(human) : écrivez la règle.
    - Quelles transitions sont permises (par exemple importee -> validee) ?
    - Peut-on revenir en arrière (validee -> importee) ? Pourquoi serait-ce dangereux ?
    - Une version peut-elle devenir « validee » sans date de validation (PV du référent) ?
    Levez CorpusImmuableError avec un message explicite si la transition est refusée.
    """


def verifier_ecriture_autorisee(statut_version):
    """Refuse toute écriture sur le contenu d'une version dont le statut est figé.

    « Écriture » = création, modification ou suppression d'une sourate, d'un verset,
    ou modification des champs d'identité de la version (empreinte, fichier...).

    TODO(human) : écrivez la règle.
    - Pour quels statuts le contenu est-il figé ?
    Levez CorpusImmuableError avec un message explicite si l'écriture est refusée.
    """


def controler_corpus(corpus):
    """Contrôles automatiques du §12.2, point 3, appliqués AVANT toute écriture en base.

    ``corpus`` est un ``CorpusLu`` (cf. importation.py) : ``corpus.sourates`` est un tuple de
    ``SourateLue`` ; chacune porte ``numero``, ``nombre_versets`` (valeur déclarée par les
    métadonnées Tanzil) et ``versets`` (tuple de ``VersetLu`` avec ``numero`` et ``texte``).

    TODO(human) : écrivez les contrôles, en levant CorpusInvalideError avec un message
    explicite (quelle sourate, quel verset, quelle valeur attendue) :
    - exactement 114 sourates, numérotées de 1 à 114 sans trou ni doublon ;
    - exactement 6 236 versets au total ;
    - pour chaque sourate, le nombre de versets lus est égal à ``nombre_versets`` ;
    - dans chaque sourate, la numérotation des versets est continue (1, 2, 3, ...) ;
    - aucun verset vide (texte composé uniquement d'espaces compris).
    Vous choisissez : s'arrêter à la première erreur, ou les collecter toutes dans un seul message.
    """


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
    """Liste, dans l'ordre canonique, les références de ``debut`` à ``fin`` INCLUSES.

    ``plan`` : {numéro de sourate: nombre de versets}, dans l'ordre des sourates.
    ``debut`` et ``fin`` : couples (sourate, verset), déjà validés (ils existent et
    ``debut`` <= ``fin``). Renvoie une liste de couples, par exemple pour le plan réel :
    references_du_passage(plan, (1, 6), (2, 5)) -> [(1, 6), (1, 7), (2, 1), ..., (2, 5)]

    TODO(human) : écrivez la gestion de la traversée de sourates.
    - Un passage dans une seule sourate : de debut[1] à fin[1].
    - Un passage sur plusieurs sourates : fin de la première, sourates du milieu EN ENTIER,
      début de la dernière. Les versets sont numérotés à partir de 1 (la basmala n'est pas un
      verset numéroté, §12.4) et le plan donne le dernier verset de chaque sourate.
    - Le résultat est trié, sans doublon, et ne modifie pas ``plan``.
    """
