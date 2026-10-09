"""Tests des règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31).

Un concours ne s'ouvre qu'après validation de sa configuration par le responsable du
client (§6.2). Si la configuration change après cette validation, la validation ne vaut
plus : une empreinte de la configuration permet de le détecter.
"""
import pytest

from apps.commun.tests.outils import (
    configuration_complete,
    creer_categorie,
    creer_concours,
    creer_critere,
    creer_epreuve,
    creer_mission,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours import services
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Concours
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_version
from apps.utilisateurs.models import Utilisateur

Role = Utilisateur.Role
Statut = VersionCorpus.Statut


@pytest.fixture
def concours_pret_a_valider(db):
    """Un concours en brouillon, avec une configuration complète et un corpus validé."""
    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)
    concours = creer_concours(creer_mission(responsable.organisation))
    configuration_complete(concours)
    services.definir_version_corpus(concours, creer_version_validee())
    return concours, responsable


# --- Version du corpus (RM-27, RM-09) ----------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", [Statut.VALIDEE, Statut.ACTIVE])
def test_rm09_une_version_validee_ou_active_peut_etre_rattachee(statut):
    concours = creer_concours()
    version = creer_version_validee(statut=statut)

    services.definir_version_corpus(concours, version)

    concours.refresh_from_db()
    assert concours.version_corpus == version


@pytest.mark.django_db
@pytest.mark.parametrize("statut", [Statut.IMPORTEE, Statut.RETIREE])
def test_rm09_une_version_non_validee_ou_retiree_est_refusee(statut):
    concours = creer_concours()

    with pytest.raises(ConfigurationInvalideError, match="valid"):
        services.definir_version_corpus(concours, creer_version(statut=statut))

    concours.refresh_from_db()
    assert concours.version_corpus is None


@pytest.mark.django_db
def test_rm27_la_version_est_figee_apres_l_ouverture(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    services.ouvrir_concours(concours)

    with pytest.raises(ConfigurationInvalideError, match="figée"):
        services.definir_version_corpus(concours, creer_version_validee())


# --- Configuration complète --------------------------------------------------


@pytest.mark.django_db
def test_une_configuration_vide_est_incomplete():
    problemes = services.problemes_de_configuration(creer_concours())

    assert any("catégorie" in p for p in problemes)


@pytest.mark.django_db
def test_une_categorie_sans_epreuve_et_une_epreuve_sans_critere_sont_signalees():
    concours = creer_concours()
    creer_categorie(concours, nom="Sans épreuve")
    creer_epreuve(creer_categorie(concours, nom="Avec épreuve"), nom="Sans critère")

    problemes = " | ".join(services.problemes_de_configuration(concours))

    assert "Sans épreuve" in problemes
    assert "Sans critère" in problemes


@pytest.mark.django_db
def test_une_configuration_complete_n_a_aucun_probleme():
    assert services.problemes_de_configuration(configuration_complete(creer_concours())) == []


# --- Validation par le responsable client (RM-31) ----------------------------


@pytest.mark.django_db
def test_rm31_le_responsable_du_client_valide_la_configuration(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider

    services.valider_configuration(concours, responsable)

    concours.refresh_from_db()
    assert concours.configuration_validee_par == responsable
    assert concours.configuration_validee_le is not None
    assert len(concours.configuration_empreinte) == 64


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.OPERATEUR, Role.ADMINISTRATEUR])
def test_rm18_rm31_ni_l_operateur_ni_l_administrateur_ne_valident(concours_pret_a_valider, role):
    """Le prestataire exécute, le client valide (§6.2)."""
    concours, _ = concours_pret_a_valider

    with pytest.raises(ValidationRefuseeError):
        services.valider_configuration(concours, creer_utilisateur(role))

    concours.refresh_from_db()
    assert concours.configuration_validee_le is None


@pytest.mark.django_db
def test_rm20_le_responsable_d_un_autre_client_ne_valide_pas(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider
    autre_responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)

    with pytest.raises(ValidationRefuseeError):
        services.valider_configuration(concours, autre_responsable)


@pytest.mark.django_db
def test_rm31_on_ne_valide_pas_une_configuration_incomplete():
    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)
    concours = creer_concours(creer_mission(responsable.organisation))

    with pytest.raises(ConfigurationInvalideError, match="catégorie"):
        services.valider_configuration(concours, responsable)


@pytest.mark.django_db
def test_rm31_on_ne_valide_pas_sans_version_du_corpus():
    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)
    concours = configuration_complete(creer_concours(creer_mission(responsable.organisation)))

    with pytest.raises(ConfigurationInvalideError, match="corpus"):
        services.valider_configuration(concours, responsable)


# --- Ouverture (RM-27, RM-31) ------------------------------------------------


@pytest.mark.django_db
def test_rm31_ouverture_apres_validation(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)

    services.ouvrir_concours(concours)

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.OUVERT


@pytest.mark.django_db
def test_rm31_ouverture_refusee_sans_validation(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider

    with pytest.raises(ConfigurationInvalideError, match="validée"):
        services.ouvrir_concours(concours)

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.BROUILLON


@pytest.mark.django_db
def test_rm31_ouverture_refusee_si_la_configuration_a_change_apres_validation(
    concours_pret_a_valider,
):
    """La validation porte sur UNE configuration : si elle change, il faut revalider."""
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    epreuve = concours.categories.first().epreuves.first()
    creer_critere(epreuve, libelle="Critère ajouté après la validation")

    with pytest.raises(ConfigurationInvalideError, match="changé"):
        services.ouvrir_concours(concours)


@pytest.mark.django_db
def test_une_modification_sans_effet_sur_la_configuration_n_invalide_pas_la_validation(
    concours_pret_a_valider,
):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    concours.nom = "Nouveau nom du concours"
    concours.save()

    services.ouvrir_concours(concours)  # ne doit rien lever

    assert concours.etat == Concours.Etat.OUVERT


@pytest.mark.django_db
def test_revalider_apres_un_changement_permet_l_ouverture(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    creer_critere(concours.categories.first().epreuves.first(), libelle="Ajout")
    services.valider_configuration(concours, responsable)

    services.ouvrir_concours(concours)

    assert concours.etat == Concours.Etat.OUVERT


@pytest.mark.django_db
def test_rm09_ouverture_refusee_si_le_corpus_a_ete_retire_entre_temps(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    VersionCorpus.objects.filter(pk=concours.version_corpus_id).update(statut=Statut.RETIREE)

    with pytest.raises(ConfigurationInvalideError, match="corpus"):
        services.ouvrir_concours(concours)


@pytest.mark.django_db
def test_on_n_ouvre_qu_un_concours_en_brouillon(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    services.ouvrir_concours(concours)

    with pytest.raises(ConfigurationInvalideError, match="brouillon"):
        services.ouvrir_concours(concours)


# --- Empreinte de la configuration -------------------------------------------


@pytest.mark.django_db
def test_l_empreinte_change_quand_un_parametre_structurant_change(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider
    avant = services.empreinte_configuration(concours)
    epreuve = concours.categories.first().epreuves.first()

    epreuve.tirages_par_candidat = 2
    epreuve.save()

    assert services.empreinte_configuration(concours) != avant


@pytest.mark.django_db
def test_l_empreinte_est_stable_quand_rien_ne_change(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider

    assert services.empreinte_configuration(concours) == services.empreinte_configuration(concours)


# --- Critère prioritaire (§10.4) -------------------------------------------------------------


@pytest.mark.django_db
def test_la_regle_critere_prioritaire_exige_de_designer_le_critere():
    from apps.commun.tests.outils import creer_categorie, creer_concours, creer_critere, creer_epreuve
    from apps.concours import services
    from apps.concours.models import Categorie

    concours = creer_concours()
    categorie = creer_categorie(concours, regle_departage=Categorie.RegleDepartage.CRITERE_PRIORITAIRE)
    epreuve = creer_epreuve(categorie)
    creer_critere(epreuve)

    assert any("critère prioritaire" in p for p in services.problemes_de_configuration(concours))

    epreuve.critere_prioritaire = epreuve.criteres.get()
    epreuve.save()
    assert services.problemes_de_configuration(concours) == []


@pytest.mark.django_db
def test_designer_un_critere_prioritaire_change_l_empreinte_de_la_configuration():
    from apps.commun.tests.outils import creer_categorie, creer_concours, creer_critere, creer_epreuve
    from apps.concours import services

    concours = creer_concours()
    epreuve = creer_epreuve(creer_categorie(concours))
    creer_critere(epreuve)
    avant = services.empreinte_configuration(concours)

    epreuve.critere_prioritaire = epreuve.criteres.get()
    epreuve.save()

    assert services.empreinte_configuration(concours) != avant
