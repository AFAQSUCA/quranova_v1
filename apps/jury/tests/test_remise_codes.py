"""Remise des codes d'accès aux jurés (§7.4, J-1 du guide de l'opérateur) : le code en clair n'est montré qu'une fois, à l'écran."""
import pytest
from django.urls import reverse

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_jure, creer_session, creer_utilisateur
from apps.jury import services
from apps.jury.exceptions import AffectationInvalideError, CodeInvalideError
from apps.jury.models import AffectationJury, CodeAccesJure
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def salle(db):
    epreuve = creer_epreuve_ouverte(series=1)
    session = creer_prestation(epreuve).session
    jures = [creer_jure(epreuve.organisation) for _ in range(2)]
    for jure in jures:
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return session, jures, operateur


def test_chaque_jure_recoit_un_code_distinct_qui_ouvre_sa_session(salle):
    session, jures, operateur = salle

    remis = services.remettre_codes(operateur, jures, session)

    assert [j for j, _ in remis] == jures and len({code for _, code in remis}) == 2
    for jure, code in remis:
        assert services.authentifier_par_code(code, session).jure == jure


def test_un_nouveau_code_revoque_l_ancien(salle):
    session, jures, operateur = salle
    (_, ancien), = services.remettre_codes(operateur, jures[:1], session)

    services.remettre_codes(operateur, jures[:1], session)

    with pytest.raises(CodeInvalideError):
        services.authentifier_par_code(ancien, session)


def test_le_journal_ne_contient_jamais_le_code_en_clair(salle):
    session, jures, operateur = salle

    remis = services.remettre_codes(operateur, jures, session)

    assert EntreeAudit.objects.filter(action="jury.codes_remis").count() == 1
    journal = " ".join(str(e.details) for e in EntreeAudit.objects.all())
    assert all(code not in journal for _, code in remis)


def test_seul_le_personnel_affecte_remet_des_codes(salle):
    session, jures, _ = salle

    for intrus in (creer_utilisateur(Utilisateur.Role.OPERATEUR), creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=session.organisation)):
        with pytest.raises(AffectationInvalideError, match="droit"):
            services.remettre_codes(intrus, jures, session)
    assert not CodeAccesJure.objects.exists()


def test_un_jure_sans_affectation_dans_le_concours_ne_recoit_pas_de_code(salle):
    session, _, operateur = salle
    sans_epreuve = creer_jure(session.organisation)

    with pytest.raises(AffectationInvalideError, match="affecté"):
        services.remettre_codes(operateur, [sans_epreuve], session)


def test_l_action_d_administration_affiche_les_codes_une_seule_fois(client, salle):
    session, jures, operateur = salle
    client.force_login(operateur)
    liste = reverse("admin:jury_jure_changelist")
    selection = [str(j.pk) for j in jures]

    formulaire = client.post(liste, {"action": "remettre_les_codes", "_selected_action": selection})
    assert formulaire.status_code == 200 and str(session.pk) in formulaire.content.decode()

    reponse = client.post(liste, {"action": "remettre_les_codes", "_selected_action": selection, "appliquer": "1", "session": str(session.pk)})
    page = reponse.content.decode()
    assert reponse.status_code == 200 and all(j.nom_complet in page for j in jures) and "une seule fois" in page
    assert "no-store" in reponse["Cache-Control"]
    assert CodeAccesJure.objects.filter(session=session).count() == 2


def test_le_responsable_client_ne_peut_pas_remettre_de_codes_meme_en_forcant_la_requete(client, salle):
    session, jures, _ = salle
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=session.organisation, is_staff=True))

    client.post(reverse("admin:jury_jure_changelist"), {"action": "remettre_les_codes", "_selected_action": [str(jures[0].pk)], "appliquer": "1", "session": str(session.pk)})

    assert not CodeAccesJure.objects.exists()
