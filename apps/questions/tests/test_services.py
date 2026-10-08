"""Tests de la création d'une question à partir de références coraniques (§8.4, REC-04, REC-05)."""
import pytest
from django.utils import timezone

from apps.commun.tests.outils import creer_organisation, creer_version_validee
from apps.coran.exceptions import ReferenceInvalideError
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_version
from apps.questions import services
from apps.questions.models import PassageCoranique, Question


@pytest.fixture
def version(db):
    """Une version de corpus minimale : sourate 1 (7 versets), sourate 2 (286), sourate 3 (200)."""
    version = creer_version()  # importée : on peut y écrire ; on la valide APRÈS (RM-27 : une version validée est figée)
    for numero, versets in ((1, 7), (2, 286), (3, 200)):
        creer_sourate(version, numero=numero, nombre_versets=versets, ordre_revelation=numero)
    version.statut = VersionCorpus.Statut.VALIDEE
    version.date_validation = timezone.now()
    version.save()
    return version


@pytest.mark.django_db
def test_rec04_creation_d_une_question_a_partir_de_references(version):
    organisation = creer_organisation()

    question = services.creer_question_passage(organisation, version, (2, 142), (2, 150))

    assert question.type == Question.Type.PASSAGE_CORANIQUE
    assert question.organisation == organisation and question.version_corpus == version
    assert question.passage.libelle == "Sourate 2, versets 142 à 150"


@pytest.mark.django_db
def test_le_service_n_enregistre_aucun_texte_coranique(version):
    """Règle absolue n°1 : on stocke des références, jamais le texte des versets."""
    question = services.creer_question_passage(creer_organisation(), version, (2, 142), (2, 150))

    assert question.enonce == ""
    champs_texte = {f.name for f in PassageCoranique._meta.get_fields()}
    assert not ({"texte", "contenu"} & champs_texte)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "debut, fin, extrait",
    [
        ((200, 1), (200, 5), "sourate 200"),  # sourate inexistante
        ((2, 287), (2, 288), "286"),  # verset inexistant
        ((2, 0), (2, 5), "verset"),  # verset nul
        ((2, 150), (2, 142), "précède"),  # fin avant le début
        ((3, 1), (2, 5), "précède"),
    ],
)
def test_rec05_reference_invalide_refusee_avec_explication(version, debut, fin, extrait):
    with pytest.raises(ReferenceInvalideError, match=extrait):
        services.creer_question_passage(creer_organisation(), version, debut, fin)

    assert Question.objects.count() == 0 and PassageCoranique.objects.count() == 0


@pytest.mark.django_db
def test_une_version_sans_sourate_est_refusee():
    with pytest.raises(ReferenceInvalideError, match="aucune sourate"):
        services.creer_question_passage(creer_organisation(), creer_version_validee(), (1, 1), (1, 2))


@pytest.mark.django_db
def test_un_passage_qui_traverse_les_sourates_est_accepte_a_la_creation(version):
    question = services.creer_question_passage(creer_organisation(), version, (2, 285), (3, 10))

    assert question.passage.libelle == "Sourate 2, verset 285 à sourate 3, verset 10"


@pytest.mark.django_db
def test_creer_une_question_enonce():
    organisation = creer_organisation()

    question = services.creer_question_enonce(organisation, "  Quel est le sens de « al-Fatiha » ?  ")

    assert question.type == Question.Type.ENONCE
    assert question.enonce == "Quel est le sens de « al-Fatiha » ?"
    assert question.version_corpus is None


@pytest.mark.django_db
def test_un_enonce_vide_est_refuse():
    from apps.questions.exceptions import QuestionInvalideError

    with pytest.raises(QuestionInvalideError):
        services.creer_question_enonce(creer_organisation(), "   ")
