"""Tests des catégories, épreuves, critères et sessions (§7.2, §8.2, RM-03, RM-21)."""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_critere,
    creer_epreuve,
    creer_session,
)
from apps.concours.models import Categorie, Epreuve


# --- Catégorie ---------------------------------------------------------------


@pytest.mark.django_db
def test_la_categorie_prend_l_organisation_du_concours():
    concours = creer_concours()

    assert creer_categorie(concours).organisation_id == concours.organisation_id


@pytest.mark.django_db
def test_valeurs_par_defaut_d_une_categorie():
    categorie = creer_categorie()

    assert categorie.discipline == Categorie.Discipline.MEMORISATION
    assert categorie.regle_classement == Categorie.RegleClassement.MOYENNE
    assert categorie.regle_departage == ""  # le système n'invente jamais de règle (§10.4)
    assert categorie.age_minimum is None and categorie.age_maximum is None


@pytest.mark.django_db
def test_nom_de_categorie_unique_par_concours():
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_categorie(concours, nom="Juniors")
    creer_categorie(creer_concours(), nom="Juniors")  # un autre concours : accepté


@pytest.mark.django_db
def test_l_age_maximum_ne_peut_pas_etre_inferieur_a_l_age_minimum():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_categorie(age_minimum=15, age_maximum=10)
    assert creer_categorie(age_minimum=10, age_maximum=10).age_minimum == 10


# --- Épreuve -----------------------------------------------------------------


@pytest.mark.django_db
def test_l_epreuve_prend_l_organisation_de_sa_categorie():
    categorie = creer_categorie()

    assert creer_epreuve(categorie).organisation_id == categorie.organisation_id


@pytest.mark.django_db
def test_rm03_q_est_calcule_t_fois_p():
    epreuve = creer_epreuve(questions_par_serie=2, tirages_par_candidat=2)

    assert epreuve.questions_par_candidat == 4  # exemple du §8.2 : P = 2, T = 2


@pytest.mark.django_db
def test_valeurs_par_defaut_d_une_epreuve():
    epreuve = creer_epreuve()

    assert epreuve.tirages_par_candidat == 1  # T par défaut (§8.2)
    assert epreuve.questions_par_candidat == epreuve.questions_par_serie
    assert epreuve.mode_affichage == Epreuve.ModeAffichage.ARABE_SEUL
    assert epreuve.etat == Epreuve.Etat.EN_PREPARATION
    # Par prudence, l'écran scène est désactivé tant que l'opérateur ne l'active pas (§9.1).
    assert epreuve.affichage_scene is False


@pytest.mark.django_db
def test_rm21_reglages_de_reutilisation_par_defaut():
    epreuve = creer_epreuve()

    assert epreuve.reutilisation_autre_candidat is False
    assert epreuve.reutilisation_meme_candidat_autre_epreuve is False
    assert epreuve.exclusion_definitive is True


@pytest.mark.django_db
@pytest.mark.parametrize("champ", ["questions_par_serie", "tirages_par_candidat"])
def test_p_et_t_valent_au_moins_un(champ):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_epreuve(**{champ: 0})


@pytest.mark.django_db
def test_ordre_et_nom_d_epreuve_uniques_par_categorie():
    categorie = creer_categorie()
    creer_epreuve(categorie, nom="Récitation", ordre=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_epreuve(categorie, nom="Autre", ordre=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_epreuve(categorie, nom="Récitation", ordre=2)


@pytest.mark.django_db
def test_une_categorie_ne_peut_pas_etre_supprimee_si_elle_a_des_epreuves():
    epreuve = creer_epreuve()

    with pytest.raises(ProtectedError):
        epreuve.categorie.delete()


# --- Critère de notation (barème) --------------------------------------------


@pytest.mark.django_db
def test_le_critere_prend_l_organisation_de_son_epreuve():
    epreuve = creer_epreuve()

    assert creer_critere(epreuve).organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_coefficient_par_defaut_egal_a_un():
    assert creer_critere().coefficient == 1


@pytest.mark.django_db
@pytest.mark.parametrize("champ", ["maximum", "coefficient"])
@pytest.mark.parametrize("valeur", [0, -1])
def test_maximum_et_coefficient_strictement_positifs(champ, valeur):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_critere(**{champ: valeur})


@pytest.mark.django_db
def test_ordre_et_libelle_de_critere_uniques_par_epreuve():
    epreuve = creer_epreuve()
    creer_critere(epreuve, libelle="Mémorisation", ordre=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_critere(epreuve, libelle="Tajwid", ordre=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_critere(epreuve, libelle="Mémorisation", ordre=2)


# --- Session -----------------------------------------------------------------


@pytest.mark.django_db
def test_la_session_prend_l_organisation_du_concours():
    concours = creer_concours()

    assert creer_session(concours).organisation_id == concours.organisation_id


@pytest.mark.django_db
def test_nom_de_session_unique_par_concours():
    concours = creer_concours()
    creer_session(concours, nom="Matin")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_session(concours, nom="Matin")
