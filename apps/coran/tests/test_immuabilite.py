"""Tests de l'immuabilité du corpus (RM-27, §12.3).

Une version validée, active ou retirée est figée : son contenu (sourates, versets)
et son identité (empreinte, fichier...) ne changent plus. Toute correction passe
par une NOUVELLE version.

Aucun texte coranique n'est saisi dans ces tests.
"""
import pytest
from django.utils import timezone

from apps.coran.exceptions import CorpusImmuableError
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_verset, creer_version

Statut = VersionCorpus.Statut
STATUTS_FIGES = [Statut.VALIDEE, Statut.ACTIVE, Statut.RETIREE]


def version_avec_contenu(statut=Statut.IMPORTEE):
    """Crée une version avec une sourate et un verset, puis fixe son statut en base.

    On utilise update() pour préparer la situation sans passer par la garde,
    qui est précisément ce que ces tests vérifient.
    """
    version = creer_version()
    sourate = creer_sourate(version)
    verset = creer_verset(sourate)
    VersionCorpus.objects.filter(pk=version.pk).update(statut=statut)
    return version, sourate, verset


# --- Contenu d'une version figée : sourates ---------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_sourate_ne_peut_pas_etre_ajoutee_a_une_version_figee(statut):
    version, _, _ = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        creer_sourate(version)


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_sourate_d_une_version_figee_ne_peut_pas_etre_modifiee(statut):
    _, sourate, _ = version_avec_contenu(statut)
    sourate.nom_translitteration = "modifie"

    with pytest.raises(CorpusImmuableError):
        sourate.save()


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_sourate_d_une_version_figee_ne_peut_pas_etre_supprimee(statut):
    _, sourate, _ = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        sourate.delete()


# --- Contenu d'une version figée : versets ----------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_verset_ne_peut_pas_etre_ajoute_a_une_version_figee(statut):
    _, sourate, _ = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        creer_verset(sourate)


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_verset_d_une_version_figee_ne_peut_pas_etre_modifie(statut):
    _, _, verset = version_avec_contenu(statut)
    verset.texte = "modifie"

    with pytest.raises(CorpusImmuableError):
        verset.save()


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_verset_d_une_version_figee_ne_peut_pas_etre_supprime(statut):
    _, _, verset = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        verset.delete()


# --- Une version importée reste modifiable ----------------------------------


@pytest.mark.django_db
def test_version_importee_reste_modifiable():
    _, sourate, verset = version_avec_contenu(Statut.IMPORTEE)

    sourate.nom_translitteration = "modifie"
    sourate.save()
    verset.texte = "modifie"
    verset.save()
    creer_verset(sourate)
    verset.delete()

    assert sourate.versets.count() == 1


# --- Pièges : déplacements et objets périmés --------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut_depart, statut_arrivee",
    [(Statut.IMPORTEE, Statut.VALIDEE), (Statut.VALIDEE, Statut.IMPORTEE)],
)
def test_rm27_verset_ne_peut_pas_traverser_la_frontiere_d_une_version_figee(
    statut_depart, statut_arrivee
):
    """Sortir d'une version figée ou entrer dans une version figée : les deux sont refusés."""
    _, _, verset = version_avec_contenu(statut_depart)
    _, sourate_arrivee, _ = version_avec_contenu(statut_arrivee)
    verset.sourate = sourate_arrivee

    with pytest.raises(CorpusImmuableError):
        verset.save()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut_depart, statut_arrivee",
    [(Statut.IMPORTEE, Statut.VALIDEE), (Statut.VALIDEE, Statut.IMPORTEE)],
)
def test_rm27_sourate_ne_peut_pas_traverser_la_frontiere_d_une_version_figee(
    statut_depart, statut_arrivee
):
    _, sourate, _ = version_avec_contenu(statut_depart)
    version_arrivee, _, _ = version_avec_contenu(statut_arrivee)
    sourate.version = version_arrivee

    with pytest.raises(CorpusImmuableError):
        sourate.save()


@pytest.mark.django_db
def test_rm27_objet_perime_en_memoire_ne_contourne_pas_la_garde():
    """La garde lit l'état réel en base, pas le statut copié dans l'objet en mémoire."""
    _, _, verset = version_avec_contenu(Statut.IMPORTEE)
    assert verset.sourate.version.statut == Statut.IMPORTEE  # copie en mémoire

    # Pendant ce temps, la version est validée ailleurs (autre processus, autre requête).
    VersionCorpus.objects.filter(pk=verset.sourate.version_id).update(
        statut=Statut.VALIDEE
    )
    verset.texte = "modifie"

    with pytest.raises(CorpusImmuableError):
        verset.save()


# --- Identité d'une version figée -------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_empreinte_d_une_version_figee_ne_peut_pas_changer(statut):
    version = creer_version(statut=statut)
    version.empreinte_sha256 = "f" * 64

    with pytest.raises(CorpusImmuableError):
        version.save()


@pytest.mark.django_db
def test_rm27_version_obsolete_en_memoire_ne_contourne_pas_la_garde():
    version = creer_version()  # importée en mémoire
    VersionCorpus.objects.filter(pk=version.pk).update(statut=Statut.VALIDEE)
    version.empreinte_sha256 = "f" * 64

    with pytest.raises(CorpusImmuableError):
        version.save()


@pytest.mark.django_db
def test_enregistrer_sans_rien_changer_reste_possible_sur_une_version_figee():
    version = creer_version(statut=Statut.VALIDEE, date_validation=timezone.now())

    version.save()

    assert VersionCorpus.objects.get(pk=version.pk).statut == Statut.VALIDEE


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_version_figee_ne_peut_pas_etre_supprimee(statut):
    version = creer_version(statut=statut)

    with pytest.raises(CorpusImmuableError):
        version.delete()


@pytest.mark.django_db
def test_version_importee_vide_peut_etre_supprimee():
    version = creer_version()

    version.delete()

    assert VersionCorpus.objects.count() == 0


# --- Transitions de statut --------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ancien, nouveau",
    [
        (Statut.IMPORTEE, Statut.VALIDEE),
        (Statut.VALIDEE, Statut.ACTIVE),
        (Statut.VALIDEE, Statut.RETIREE),
        (Statut.ACTIVE, Statut.RETIREE),
    ],
)
def test_transitions_de_statut_autorisees(ancien, nouveau):
    version = creer_version(statut=ancien, date_validation=timezone.now())

    version.statut = nouveau
    version.save()

    assert VersionCorpus.objects.get(pk=version.pk).statut == nouveau


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ancien, nouveau",
    [
        (Statut.VALIDEE, Statut.IMPORTEE),
        (Statut.ACTIVE, Statut.IMPORTEE),
        (Statut.ACTIVE, Statut.VALIDEE),
        (Statut.RETIREE, Statut.IMPORTEE),
        (Statut.RETIREE, Statut.VALIDEE),
        (Statut.RETIREE, Statut.ACTIVE),
        (Statut.IMPORTEE, Statut.ACTIVE),
        (Statut.IMPORTEE, Statut.RETIREE),
    ],
)
def test_rm27_transitions_de_statut_interdites(ancien, nouveau):
    """Surtout : revenir à « importée » dégèlerait le contenu d'une version déjà validée."""
    version = creer_version(statut=ancien, date_validation=timezone.now())
    version.statut = nouveau

    with pytest.raises(CorpusImmuableError):
        version.save()


@pytest.mark.django_db
def test_validation_sans_date_de_validation_refusee():
    """§12.2, point 7 : pas de validation sans procès-verbal du référent coranique."""
    version = creer_version()
    assert version.date_validation is None
    version.statut = Statut.VALIDEE

    with pytest.raises(CorpusImmuableError):
        version.save()
