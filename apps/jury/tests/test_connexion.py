"""Tests de la connexion des jurés : code contre jeton, limitation des essais (D4, D5, D46)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_jure, creer_session
from apps.jury import connexion, services
from apps.jury.exceptions import CodeInvalideError, JetonInvalideError, TropDEssaisError
from apps.jury.models import ConnexionJure


@pytest.fixture
def poste(db):
    session = creer_session()
    jure = creer_jure(session.organisation)
    acces, code = services.generer_code(jure, session)
    return session, jure, acces, code


@pytest.mark.django_db
def test_un_code_valide_donne_un_jeton_long_non_stocke_en_clair(poste):
    session, jure, acces, code = poste

    conn, jeton = connexion.ouvrir_connexion(code, session, "10.0.0.5")

    assert len(jeton) >= 40 and conn.empreinte != jeton and len(conn.empreinte) == 64
    assert conn.acces == acces and conn.organisation_id == session.organisation_id
    assert conn.valide_jusqu_au == acces.valide_jusqu_au  # D46
    assert not ConnexionJure.objects.filter(empreinte=jeton).exists()


@pytest.mark.django_db
def test_le_jeton_identifie_le_jure_et_note_l_activite(poste):
    session, jure, _, code = poste
    conn, jeton = connexion.ouvrir_connexion(code, session)

    trouvee = connexion.authentifier_jeton(jeton, session)

    assert trouvee.acces.jure == jure
    conn.refresh_from_db()
    assert conn.derniere_activite is not None


@pytest.mark.django_db
@pytest.mark.parametrize("jeton", ["", None, "faux", "a" * 43])
def test_un_jeton_inconnu_est_refuse(poste, jeton):
    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, poste[0])


@pytest.mark.django_db
def test_d46_le_jeton_expire_avec_le_code(poste):
    session, _, acces, code = poste
    _, jeton = connexion.ouvrir_connexion(code, session)

    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, session, maintenant=acces.valide_jusqu_au + timedelta(seconds=1))


@pytest.mark.django_db
def test_un_code_revoque_ou_un_jure_desactive_invalide_le_jeton(poste):
    session, jure, acces, code = poste
    _, jeton = connexion.ouvrir_connexion(code, session)
    services.revoquer_code(acces)
    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, session)

    session2 = creer_session()
    jure2 = creer_jure(session2.organisation)
    _, code2 = services.generer_code(jure2, session2)
    _, jeton2 = connexion.ouvrir_connexion(code2, session2)
    jure2.actif = False
    jure2.save()
    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton2, session2)


@pytest.mark.django_db
def test_un_jeton_d_une_autre_session_est_refuse(poste):
    session, _, _, code = poste
    _, jeton = connexion.ouvrir_connexion(code, session)

    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, creer_session(session.concours))


@pytest.mark.django_db
def test_la_connexion_peut_etre_revoquee(poste):
    session, _, _, code = poste
    conn, jeton = connexion.ouvrir_connexion(code, session)

    connexion.revoquer_connexion(conn)

    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, session)


@pytest.mark.django_db
def test_d5_apres_cinq_codes_faux_l_adresse_est_bloquee_meme_avec_le_bon_code(poste):
    session, _, _, code = poste
    for _ in range(5):
        with pytest.raises(CodeInvalideError):
            connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")

    with pytest.raises(TropDEssaisError) as erreur:
        connexion.ouvrir_connexion(code, session, "10.0.0.9")

    assert 0 < erreur.value.attente_secondes <= 300


@pytest.mark.django_db
def test_le_blocage_ne_touche_pas_une_autre_adresse_et_se_leve_apres_la_fenetre(poste):
    session, _, _, code = poste
    for _ in range(5):
        with pytest.raises(CodeInvalideError):
            connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")

    connexion.ouvrir_connexion(code, session, "10.0.0.10")  # autre tablette : acceptée
    plus_tard = timezone.now() + timedelta(minutes=6)
    conn, _ = connexion.ouvrir_connexion(code, session, "10.0.0.9", maintenant=plus_tard)  # fenêtre écoulée

    assert conn.adresse == "10.0.0.9"


@pytest.mark.django_db
def test_quatre_codes_faux_ne_bloquent_pas(poste):
    session, _, _, code = poste
    for _ in range(4):
        with pytest.raises(CodeInvalideError):
            connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")

    connexion.ouvrir_connexion(code, session, "10.0.0.9")


@pytest.mark.django_db
def test_les_connexions_reussies_et_les_echecs_sont_journalises_sans_le_code(poste):
    session, jure, _, code = poste
    with pytest.raises(CodeInvalideError):
        connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")
    connexion.ouvrir_connexion(code, session, "10.0.0.9")

    echec = EntreeAudit.objects.get(action="jury.connexion_echouee")
    reussie = EntreeAudit.objects.get(action="jury.connexion")
    assert echec.details["raison"] == "inconnu" and echec.terminal == "10.0.0.9"
    assert reussie.auteur_libelle == f"juré {jure.nom_complet}"
    assert "ZZZZ" not in str(echec.details) and code.replace("-", "") not in str(reussie.details)
