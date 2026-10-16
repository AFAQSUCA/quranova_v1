"""Tests des règles sur les candidats : âge, consentement, inscription (§7.3, §16.2, §14.2 ; RM-28).

Aucun tirage sans consentement parental pour un mineur (règle absolue n°6) ; aucun tirage
pour une participation non admise (§14.2).
"""
from datetime import date

import pytest

from apps.candidats import services
from apps.candidats.exceptions import (
    ConsentementManquantError,
    ParticipationNonAdmiseError,
    TirageImpossibleError,
)
from apps.candidats.models import Consentement, Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_consentement,
    creer_participation,
)

Statut = Participation.Statut
DEBUT_DU_CONCOURS = date(2027, 1, 20)


def participation_nee_le(naissance, statut=Statut.ADMIS):
    """Une participation à un concours qui commence le 20 janvier 2027."""
    concours = creer_concours(date_debut=DEBUT_DU_CONCOURS, date_fin=DEBUT_DU_CONCOURS)
    categorie = creer_categorie(concours)
    candidat = creer_candidat(categorie.organisation, date_naissance=naissance)
    return creer_participation(categorie, candidat, statut=statut)


# --- Âge ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "naissance, reference, attendu",
    [
        (date(2009, 1, 20), date(2027, 1, 20), 18),  # 18 ans révolus le jour même
        (date(2009, 1, 21), date(2027, 1, 20), 17),  # il manque un jour
        (date(2010, 6, 15), date(2027, 1, 20), 16),
        (date(2000, 2, 29), date(2027, 2, 28), 26),  # naissance un 29 février
        (date(2000, 2, 29), date(2027, 3, 1), 27),
    ],
)
def test_age_a_la_date(naissance, reference, attendu):
    assert services.age_a_la_date(naissance, reference) == attendu


# --- Mineur (§16.2) ----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "naissance, attendu",
    [
        (date(2009, 1, 21), True),  # 17 ans à la date de début du concours
        (date(2009, 1, 20), False),  # 18 ans révolus le jour du début : majeur
        (date(1990, 5, 5), False),
        (None, None),  # date inconnue : on ne sait pas
    ],
)
def test_est_mineur_a_la_date_de_debut_du_concours(naissance, attendu):
    assert services.est_mineur(participation_nee_le(naissance)) is attendu


# --- Consentement requis (D13 : prudence quand la date est inconnue) ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "naissance, attendu",
    [(date(2012, 3, 3), True), (date(1990, 5, 5), False), (None, True)],
)
def test_consentement_requis_pour_un_mineur_ou_par_prudence_si_l_age_est_inconnu(naissance, attendu):
    assert services.consentement_requis(participation_nee_le(naissance)) is attendu


@pytest.mark.django_db
def test_consentement_valide_ignore_les_formulaires_retires():
    participation = participation_nee_le(date(2012, 3, 3))
    creer_consentement(
        participation, statut=Consentement.Statut.RETIRE, date_retrait=date(2027, 1, 15)
    )
    assert services.consentement_valide(participation) is None

    valide = creer_consentement(participation, version_formulaire="1.1")

    assert services.consentement_valide(participation) == valide


# --- Prêt pour le tirage (RM-28, §14.2) --------------------------------------


@pytest.mark.django_db
def test_un_majeur_admis_peut_tirer_sans_consentement():
    services.verifier_pret_pour_tirage(participation_nee_le(date(1990, 5, 5)))


@pytest.mark.django_db
@pytest.mark.parametrize("statut", [Statut.INSCRIT, Statut.RETIRE])
def test_une_participation_non_admise_ne_tire_pas(statut):
    participation = participation_nee_le(date(1990, 5, 5), statut=statut)

    with pytest.raises(ParticipationNonAdmiseError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_un_mineur_sans_consentement_ne_tire_pas():
    participation = participation_nee_le(date(2012, 3, 3))

    with pytest.raises(ConsentementManquantError, match="consentement"):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_un_mineur_dont_le_consentement_de_participation_n_est_pas_accorde_ne_tire_pas():
    """Les trois consentements sont distincts : seul le n° 1 (participation) autorise le tirage."""
    participation = participation_nee_le(date(2012, 3, 3))
    creer_consentement(
        participation,
        consentement_participation=False,
        consentement_publication_nom=True,
        consentement_image_voix=True,
    )

    with pytest.raises(ConsentementManquantError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_un_mineur_avec_consentement_de_participation_peut_tirer():
    participation = participation_nee_le(date(2012, 3, 3))
    creer_consentement(participation, consentement_participation=True)

    services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_le_retrait_du_consentement_bloque_le_tirage():
    participation = participation_nee_le(date(2012, 3, 3))
    consentement = creer_consentement(participation)
    services.verifier_pret_pour_tirage(participation)

    consentement.statut = Consentement.Statut.RETIRE
    consentement.date_retrait = date(2027, 1, 19)
    consentement.save()

    with pytest.raises(ConsentementManquantError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_date_de_naissance_inconnue_exige_le_consentement_par_prudence():
    participation = participation_nee_le(None)

    with pytest.raises(ConsentementManquantError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_les_deux_erreurs_sont_des_tirages_impossibles():
    assert issubclass(ParticipationNonAdmiseError, TirageImpossibleError)
    assert issubclass(ConsentementManquantError, TirageImpossibleError)


# --- Inscription et numérotation (§7.3) --------------------------------------


@pytest.mark.django_db
def test_le_premier_candidat_recoit_le_numero_1_puis_les_suivants_s_incrementent():
    categorie = creer_categorie()

    premiere = services.inscrire(creer_candidat(categorie.organisation), categorie)
    seconde = services.inscrire(creer_candidat(categorie.organisation), categorie)

    assert (premiere.numero_candidat, seconde.numero_candidat) == (1, 2)
    assert premiere.statut == Statut.INSCRIT
    assert premiere.concours == categorie.concours


@pytest.mark.django_db
def test_la_numerotation_est_propre_a_chaque_concours():
    categorie_a, categorie_b = creer_categorie(), creer_categorie()

    services.inscrire(creer_candidat(categorie_a.organisation), categorie_a)
    premiere_de_b = services.inscrire(creer_candidat(categorie_b.organisation), categorie_b)

    assert premiere_de_b.numero_candidat == 1


@pytest.mark.django_db
def test_la_numerotation_continue_apres_le_numero_le_plus_eleve():
    categorie = creer_categorie()
    creer_participation(categorie, numero_candidat=41)

    nouvelle = services.inscrire(creer_candidat(categorie.organisation), categorie)

    assert nouvelle.numero_candidat == 42


@pytest.mark.django_db
def test_les_numeros_ne_sont_pas_reutilises_apres_un_retrait():
    categorie = creer_categorie()
    premiere = services.inscrire(creer_candidat(categorie.organisation), categorie)
    premiere.statut = Statut.RETIRE
    premiere.save()

    suivante = services.inscrire(creer_candidat(categorie.organisation), categorie)

    assert suivante.numero_candidat == 2
