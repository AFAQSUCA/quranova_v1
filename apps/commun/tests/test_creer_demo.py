"""Test de la commande de démonstration (développement seulement)."""
import pytest
from django.core.management import CommandError, call_command

from apps.candidats.models import Participation
from apps.concours.models import Concours, Epreuve
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_version
from apps.prestations import services
from apps.prestations.models import Prestation, TerminalTirage
from apps.questions.models import Serie


@pytest.fixture
def corpus(db):
    version = creer_version()
    for numero in [1, 112, 113, 114, 103, 108, 105, 106, 107, 109, 110, 111]:
        creer_sourate(version, numero=numero, nombre_versets=7, ordre_revelation=numero)
    return version


@pytest.fixture
def regles_ecrites(monkeypatch):
    """Les règles de suffisance et de sélection sont à écrire par l'utilisateur : on les remplace ici."""
    monkeypatch.setattr(services, "series_necessaires", lambda epreuve, n: n * epreuve.tirages_par_candidat)


@pytest.mark.django_db
def test_la_demo_est_refusee_hors_developpement(corpus, settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="développement"):
        call_command("creer_demo", "--valider-corpus-pour-test")


@pytest.mark.django_db
def test_un_corpus_non_valide_est_refuse_sans_option(corpus, settings):
    settings.DEBUG = True

    with pytest.raises(CommandError, match="n'est pas validé"):
        call_command("creer_demo")
    assert Concours.objects.count() == 0


@pytest.mark.django_db
def test_la_demo_prepare_un_concours_pret_a_tirer(corpus, settings, regles_ecrites):
    settings.DEBUG = True

    call_command("creer_demo", "--valider-corpus-pour-test")

    concours = Concours.objects.get()
    assert concours.etat == Concours.Etat.EN_COURS
    assert Epreuve.objects.get().etat == Epreuve.Etat.OUVERTE
    assert Serie.objects.count() == 6
    assert Participation.objects.filter(statut="admis").count() == 6
    assert Prestation.objects.count() == 6 and TerminalTirage.objects.count() == 1
    corpus.refresh_from_db()
    assert corpus.statut == VersionCorpus.Statut.VALIDEE


@pytest.mark.django_db
def test_la_demo_ne_se_cree_qu_une_fois(corpus, settings, regles_ecrites):
    settings.DEBUG = True
    call_command("creer_demo", "--valider-corpus-pour-test")

    with pytest.raises(CommandError, match="existe déjà"):
        call_command("creer_demo", "--valider-corpus-pour-test")


@pytest.mark.django_db
def test_une_regle_non_ecrite_donne_un_message_clair_et_ne_laisse_rien(corpus, settings, monkeypatch):
    settings.DEBUG = True

    def non_ecrite(epreuve, nombre_candidats):
        raise NotImplementedError("TODO(human) : contrôle de suffisance du lot")

    monkeypatch.setattr(services, "series_necessaires", non_ecrite)

    with pytest.raises(CommandError, match="TODO\\(human\\)"):
        call_command("creer_demo", "--valider-corpus-pour-test")

    assert Concours.objects.count() == 0
