"""Tests des règles sur les jurés : affectation et codes d'accès de session (§7.4, §6.3 ; D4, D5).

Un juré se connecte sur sa tablette avec un code personnel à usage limité à la session,
généré par l'opérateur ; aucune adresse électronique n'est exigée. Le code n'est JAMAIS
stocké en clair : seule son empreinte l'est.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_epreuve,
    creer_jure,
    creer_organisation,
    creer_session,
)
from apps.jury import services
from apps.jury.exceptions import AffectationInvalideError, CodeInvalideError
from apps.jury.models import AffectationJury, CodeAccesJure


# --- Affectation (D5) ---------------------------------------------------------


@pytest.fixture
def concours_a_deux_categories(db):
    """Un concours avec deux catégories ; la première a deux épreuves, la seconde une."""
    concours = creer_concours()
    categorie_a, categorie_b = creer_categorie(concours), creer_categorie(concours)
    epreuves = [creer_epreuve(categorie_a), creer_epreuve(categorie_a), creer_epreuve(categorie_b)]
    return concours, categorie_a, categorie_b, epreuves


@pytest.mark.django_db
def test_affecter_a_une_epreuve(concours_a_deux_categories):
    concours, _, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    creees = services.affecter(jure, epreuve=epreuves[0])

    assert [a.epreuve for a in creees] == [epreuves[0]]


@pytest.mark.django_db
def test_affecter_a_une_categorie_cree_une_ligne_par_epreuve(concours_a_deux_categories):
    concours, categorie_a, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    services.affecter(jure, categorie=categorie_a)

    assert set(jure.affectations.values_list("epreuve", flat=True)) == {epreuves[0].pk, epreuves[1].pk}


@pytest.mark.django_db
def test_affecter_a_tout_le_concours_cree_une_ligne_par_epreuve(concours_a_deux_categories):
    concours, _, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    services.affecter(jure, concours=concours)

    assert jure.affectations.count() == len(epreuves)


@pytest.mark.django_db
def test_affecter_deux_fois_est_idempotent(concours_a_deux_categories):
    concours, _, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)
    services.affecter(jure, epreuve=epreuves[0])

    creees = services.affecter(jure, concours=concours)

    assert len(creees) == len(epreuves) - 1  # seules les lignes manquantes sont créées
    assert jure.affectations.count() == len(epreuves)


@pytest.mark.django_db
def test_affecter_exige_exactement_une_portee(concours_a_deux_categories):
    concours, categorie_a, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    with pytest.raises(AffectationInvalideError):
        services.affecter(jure)
    with pytest.raises(AffectationInvalideError):
        services.affecter(jure, concours=concours, categorie=categorie_a)
    assert AffectationJury.objects.count() == 0


@pytest.mark.django_db
def test_rm20_affecter_un_jure_d_un_autre_client_est_refuse(concours_a_deux_categories):
    concours, *_ = concours_a_deux_categories
    jure_d_ailleurs = creer_jure(creer_organisation())

    with pytest.raises(AffectationInvalideError, match="client"):
        services.affecter(jure_d_ailleurs, concours=concours)
    assert AffectationJury.objects.count() == 0


@pytest.mark.django_db
def test_un_jure_inactif_n_est_pas_affecte(concours_a_deux_categories):
    concours, *_ = concours_a_deux_categories
    jure = creer_jure(concours.organisation, actif=False)

    with pytest.raises(AffectationInvalideError, match="inactif"):
        services.affecter(jure, concours=concours)


# --- Génération du code -------------------------------------------------------


@pytest.fixture
def jure_et_session(db):
    session = creer_session()
    return creer_jure(session.organisation), session


@pytest.mark.django_db
def test_le_code_genere_est_court_lisible_et_sans_caracteres_ambigus(jure_et_session):
    jure, session = jure_et_session

    _, code = services.generer_code(jure, session)

    brut = code.replace("-", "")
    assert len(brut) == services.LONGUEUR_CODE
    assert set(brut) <= set(services.ALPHABET)
    assert not (set(brut) & set("01OI"))  # jamais de caractères qu'on confond sur une tablette


@pytest.mark.django_db
def test_le_code_est_affiche_en_deux_groupes(jure_et_session):
    jure, session = jure_et_session

    _, code = services.generer_code(jure, session)

    assert code[4] == "-" and len(code) == services.LONGUEUR_CODE + 1


@pytest.mark.django_db
def test_d4_le_code_n_est_jamais_stocke_en_clair(jure_et_session):
    jure, session = jure_et_session

    acces, code = services.generer_code(jure, session)

    brut = code.replace("-", "")
    valeurs_stockees = [str(v) for v in CodeAccesJure.objects.values_list("empreinte", flat=True)]
    assert acces.empreinte not in (brut, code)
    assert len(acces.empreinte) == 64
    assert all(brut not in valeur for valeur in valeurs_stockees)


@pytest.mark.django_db
def test_la_duree_de_validite_par_defaut_est_de_douze_heures(jure_et_session):
    jure, session = jure_et_session
    maintenant = timezone.now()

    acces, _ = services.generer_code(jure, session, maintenant=maintenant)

    assert acces.valide_du == maintenant
    assert acces.valide_jusqu_au == maintenant + timedelta(hours=12)


@pytest.mark.django_db
def test_deux_codes_generes_sont_differents(jure_et_session):
    jure, session = jure_et_session
    autre_jure = creer_jure(session.organisation)

    _, premier = services.generer_code(jure, session)
    _, second = services.generer_code(autre_jure, session)

    assert premier != second


@pytest.mark.django_db
def test_regenerer_un_code_revoque_l_ancien(jure_et_session):
    jure, session = jure_et_session
    ancien, ancien_code = services.generer_code(jure, session)

    nouveau, _ = services.generer_code(jure, session)

    ancien.refresh_from_db()
    assert ancien.revoque_le is not None
    assert nouveau.revoque_le is None
    with pytest.raises(CodeInvalideError):
        services.authentifier_par_code(ancien_code, session)


@pytest.mark.django_db
def test_on_ne_genere_pas_de_code_pour_un_jure_inactif(jure_et_session):
    jure, session = jure_et_session
    jure.actif = False
    jure.save()

    with pytest.raises(AffectationInvalideError, match="inactif"):
        services.generer_code(jure, session)


@pytest.mark.django_db
def test_rm20_pas_de_code_entre_un_jure_et_la_session_d_un_autre_client():
    with pytest.raises(AffectationInvalideError, match="client"):
        services.generer_code(creer_jure(creer_organisation()), creer_session())


# --- Authentification par code ------------------------------------------------


@pytest.mark.django_db
def test_un_code_valide_identifie_le_jure(jure_et_session):
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)

    acces = services.authentifier_par_code(code, session)

    assert acces.jure == jure


@pytest.mark.django_db
@pytest.mark.parametrize(
    "transformation",
    [str.lower, lambda c: c.replace("-", ""), lambda c: f"  {c}  ", lambda c: c.replace("-", " ")],
    ids=["minuscules", "sans tiret", "espaces autour", "espace au lieu du tiret"],
)
def test_la_saisie_du_code_est_tolerante(jure_et_session, transformation):
    """Sur une tablette, on tape en minuscules, avec ou sans tiret : le code reste reconnu."""
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)

    assert services.authentifier_par_code(transformation(code), session).jure == jure


@pytest.mark.django_db
def test_un_code_inconnu_est_refuse(jure_et_session):
    _, session = jure_et_session

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code("ABCD-EFGH", session)

    assert erreur.value.raison == "inconnu"


@pytest.mark.django_db
def test_un_code_d_une_autre_session_est_refuse(jure_et_session):
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)
    autre_session = creer_session(session.concours)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, autre_session)

    assert erreur.value.raison == "inconnu"


@pytest.mark.django_db
def test_un_code_expire_est_refuse(jure_et_session):
    jure, session = jure_et_session
    maintenant = timezone.now()
    _, code = services.generer_code(jure, session, maintenant=maintenant)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session, maintenant=maintenant + timedelta(hours=12, seconds=1))

    assert erreur.value.raison == "expire"


@pytest.mark.django_db
def test_un_code_pas_encore_valide_est_refuse(jure_et_session):
    jure, session = jure_et_session
    maintenant = timezone.now()
    _, code = services.generer_code(jure, session, maintenant=maintenant)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session, maintenant=maintenant - timedelta(minutes=1))

    assert erreur.value.raison == "pas_encore_valide"


@pytest.mark.django_db
def test_un_code_revoque_est_refuse(jure_et_session):
    jure, session = jure_et_session
    acces, code = services.generer_code(jure, session)
    services.revoquer_code(acces)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session)

    assert erreur.value.raison == "revoque"


@pytest.mark.django_db
def test_un_jure_desactive_apres_coup_ne_se_connecte_plus(jure_et_session):
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)
    jure.actif = False
    jure.save()

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session)

    assert erreur.value.raison == "jure_inactif"


@pytest.mark.django_db
def test_la_derniere_utilisation_est_enregistree(jure_et_session):
    jure, session = jure_et_session
    acces, code = services.generer_code(jure, session)
    assert acces.derniere_utilisation is None

    services.authentifier_par_code(code, session)

    acces.refresh_from_db()
    assert acces.derniere_utilisation is not None


@pytest.mark.django_db
def test_le_message_d_erreur_ne_revele_pas_la_raison(jure_et_session):
    """L'écran dit seulement « code invalide » ; la raison précise reste pour le journal (§15)."""
    _, session = jure_et_session

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code("ZZZZ-ZZZZ", session)

    assert "inconnu" not in str(erreur.value).lower()
    assert "invalide" in str(erreur.value).lower()
