"""Tests des modèles Jure, AffectationJury et CodeAccesJure (§7.4, §6.3 ; D4, D5)."""
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import (
    creer_epreuve,
    creer_jure,
    creer_organisation,
    creer_session,
)
from apps.jury.models import AffectationJury, CodeAccesJure, Jure


# --- Jure --------------------------------------------------------------------


@pytest.mark.django_db
def test_valeurs_par_defaut_d_un_jure():
    jure = creer_jure()

    assert jure.role == Jure.Role.MEMBRE
    assert jure.actif is True
    assert jure.competences == ""


@pytest.mark.django_db
def test_un_jure_n_a_pas_de_compte_django():
    """D4 : les jurés ne se connectent pas par compte, mais par un code de session (§7.4)."""
    champs = {f.name for f in Jure._meta.get_fields()}

    assert not ({"username", "password", "email", "user", "utilisateur"} & champs)


@pytest.mark.django_db
def test_nom_complet():
    assert creer_jure(nom="Traoré", prenom="Ibrahim").nom_complet == "Ibrahim Traoré"


@pytest.mark.django_db
def test_nom_et_prenom_uniques_par_organisation():
    organisation = creer_organisation()
    creer_jure(organisation, nom="Traoré", prenom="Ibrahim")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_jure(organisation, nom="Traoré", prenom="Ibrahim")
    creer_jure(creer_organisation(), nom="Traoré", prenom="Ibrahim")  # un autre client : accepté


# --- Affectation (D5 : toujours au niveau épreuve) ----------------------------


@pytest.mark.django_db
def test_un_jure_est_affecte_a_une_epreuve():
    epreuve = creer_epreuve()
    jure = creer_jure(epreuve.organisation)

    affectation = AffectationJury.objects.create(jure=jure, epreuve=epreuve)

    assert affectation in jure.affectations.all()
    assert affectation in epreuve.affectations_jury.all()


@pytest.mark.django_db
def test_un_jure_n_est_affecte_qu_une_fois_a_une_epreuve():
    epreuve = creer_epreuve()
    jure = creer_jure(epreuve.organisation)
    AffectationJury.objects.create(jure=jure, epreuve=epreuve)

    with pytest.raises(IntegrityError), transaction.atomic():
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)


@pytest.mark.django_db
def test_rm20_un_jure_d_un_autre_client_ne_peut_pas_etre_affecte():
    epreuve = creer_epreuve()
    jure_d_ailleurs = creer_jure(creer_organisation())

    with pytest.raises(IncoherenceOrganisationError):
        AffectationJury.objects.create(jure=jure_d_ailleurs, epreuve=epreuve)


@pytest.mark.django_db
def test_une_epreuve_ne_peut_pas_etre_supprimee_si_elle_a_des_jures_affectes():
    epreuve = creer_epreuve()
    AffectationJury.objects.create(jure=creer_jure(epreuve.organisation), epreuve=epreuve)

    with pytest.raises(ProtectedError):
        epreuve.delete()


# --- Code d'accès -------------------------------------------------------------


def un_code(jure, session, **champs):
    maintenant = timezone.now()
    valeurs = {
        "jure": jure,
        "session": session,
        "empreinte": "a" * 64,
        "valide_du": maintenant,
        "valide_jusqu_au": maintenant + timedelta(hours=12),
    }
    valeurs.update(champs)
    return CodeAccesJure.objects.create(**valeurs)


@pytest.mark.django_db
def test_le_code_prend_l_organisation_du_jure_et_de_la_session():
    session = creer_session()
    jure = creer_jure(session.organisation)

    assert un_code(jure, session).organisation_id == session.organisation_id


@pytest.mark.django_db
def test_rm20_un_code_ne_relie_pas_un_jure_a_la_session_d_un_autre_client():
    with pytest.raises(IncoherenceOrganisationError):
        un_code(creer_jure(creer_organisation()), creer_session())


@pytest.mark.django_db
def test_la_fin_de_validite_suit_le_debut():
    session = creer_session()
    jure = creer_jure(session.organisation)
    maintenant = timezone.now()

    with pytest.raises(IntegrityError), transaction.atomic():
        un_code(jure, session, valide_du=maintenant, valide_jusqu_au=maintenant)


@pytest.mark.django_db
def test_l_empreinte_d_un_code_est_unique():
    session = creer_session()
    un_code(creer_jure(session.organisation), session, empreinte="b" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        un_code(creer_jure(session.organisation), session, empreinte="b" * 64)


@pytest.mark.django_db
def test_un_seul_code_actif_par_jure_et_par_session():
    session = creer_session()
    jure = creer_jure(session.organisation)
    un_code(jure, session, empreinte="c" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        un_code(jure, session, empreinte="d" * 64)


@pytest.mark.django_db
def test_un_nouveau_code_est_possible_apres_la_revocation_du_precedent():
    session = creer_session()
    jure = creer_jure(session.organisation)
    un_code(jure, session, empreinte="c" * 64, revoque_le=timezone.now())

    un_code(jure, session, empreinte="d" * 64)

    assert jure.codes.count() == 2

