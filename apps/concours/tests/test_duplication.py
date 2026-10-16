"""Duplication d'un concours d'une édition précédente (§7, REC-02).

Règle : la copie reprend catégories, épreuves, barèmes et séries ; elle repart en BROUILLON, sans validation de configuration,
sans candidats, sessions ni tirages. Les passages coraniques sont recréés et revérifiés dans la version du corpus de la copie (RM-23).
"""
from datetime import date

import pytest
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.candidats.models import Participation
from apps.commun.tests.outils import (
    creer_candidat, creer_categorie, creer_concours, creer_critere, creer_epreuve, creer_mission, creer_organisation,
    creer_participation, creer_session, creer_utilisateur,
)
from apps.concours import services
from apps.concours.exceptions import ConfigurationInvalideError
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_version
from apps.questions import services as services_questions
from apps.questions.models import Question, QuestionDeSerie, Serie
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def version(db):
    version = creer_version()
    for numero, versets in ((1, 7), (2, 286), (112, 4)):
        creer_sourate(version, numero=numero, nombre_versets=versets, ordre_revelation=numero)
    version.statut = VersionCorpus.Statut.VALIDEE
    version.date_validation = timezone.now()
    version.save()
    return version


@pytest.fixture
def source(version):
    """Une édition 2026 déjà passée : 2 catégories, 3 épreuves, barèmes, un critère prioritaire, des séries, et des données de passage."""
    organisation = creer_organisation()
    mission = creer_mission(organisation)
    concours = creer_concours(mission, nom="Concours régional", edition="2026", version_corpus=version)
    juniors = creer_categorie(concours, nom="Juniors", discipline=Categorie.Discipline.TAJWID, age_minimum=8, age_maximum=12,
                              effectif_prevu=40, regle_classement=Categorie.RegleClassement.TOTAL,
                              regle_departage=Categorie.RegleDepartage.CRITERE_PRIORITAIRE)
    seniors = creer_categorie(concours, nom="Seniors")
    memo = creer_epreuve(juniors, nom="Mémorisation", ordre=1, questions_par_serie=2, tirages_par_candidat=1,
                         reutilisation_autre_candidat=True, exclusion_definitive=False, affichage_scene=True,
                         mode_affichage=Epreuve.ModeAffichage.ARABE_ET_TRADUCTION, etat=Epreuve.Etat.TERMINEE)
    tajwid = creer_critere(memo, libelle="Tajwid", ordre=2, maximum=20, coefficient=2)
    creer_critere(memo, libelle="Mémorisation", ordre=1, maximum=10)
    memo.critere_prioritaire = tajwid
    memo.save()
    questions = creer_epreuve(juniors, nom="Questions", ordre=2, questions_par_serie=1, etat=Epreuve.Etat.TERMINEE)
    questions.critere_prioritaire = creer_critere(questions, libelle="Exactitude", ordre=1, maximum=10)
    questions.save()
    tilawa = creer_epreuve(seniors, nom="Tilawa", ordre=1, questions_par_serie=1, etat=Epreuve.Etat.TERMINEE)
    creer_critere(tilawa, libelle="Voix", ordre=1, maximum=10)
    lot = services_questions.obtenir_lot(memo)
    q1 = services_questions.creer_question_passage(organisation, version, (2, 142), (2, 150))
    q2 = services_questions.creer_question_passage(organisation, version, (112, 1), (112, 4))
    q3 = services_questions.creer_question_enonce(organisation, "Que signifie « Sabr » ?")
    services_questions.composer_serie(lot, [q1, q2])
    services_questions.composer_serie(lot, [q2, q3])
    # Des données de l'édition passée, qui ne doivent PAS être copiées :
    creer_session(concours)
    creer_participation(juniors, creer_candidat(organisation))
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)
    return concours, operateur


def dupliquer(concours, auteur, **champs):
    valeurs = dict(nom="Concours régional", edition="2027", date_debut=date(2027, 3, 1), date_fin=date(2027, 3, 2))
    valeurs.update(champs)
    return services.dupliquer_concours(concours, auteur=auteur, **valeurs)


@pytest.mark.django_db
def test_rec02_la_copie_reprend_categories_epreuves_baremes_et_series(source):
    concours, operateur = source

    resultat = dupliquer(concours, operateur)
    copie = resultat.concours

    assert copie.pk != concours.pk and copie.edition == "2027" and copie.organisation_id == concours.organisation_id
    assert [c.nom for c in copie.categories.order_by("nom")] == ["Juniors", "Seniors"]
    juniors = copie.categories.get(nom="Juniors")
    assert (juniors.discipline, juniors.age_minimum, juniors.age_maximum, juniors.effectif_prevu) == ("tajwid", 8, 12, 40)
    assert (juniors.regle_classement, juniors.regle_departage) == ("total", "critere_prioritaire")
    memo = juniors.epreuves.get(nom="Mémorisation")
    assert (memo.ordre, memo.questions_par_serie, memo.tirages_par_candidat) == (1, 2, 1)
    assert (memo.reutilisation_autre_candidat, memo.exclusion_definitive, memo.affichage_scene) == (True, False, True)
    assert memo.mode_affichage == Epreuve.ModeAffichage.ARABE_ET_TRADUCTION
    assert [(c.libelle, c.ordre, c.maximum, c.coefficient) for c in memo.criteres.order_by("ordre")] == [
        ("Mémorisation", 1, 10, 1), ("Tajwid", 2, 20, 2)]
    assert Epreuve.objects.filter(categorie__concours=copie).count() == 3
    assert (resultat.categories, resultat.epreuves, resultat.criteres, resultat.series) == (2, 3, 4, 2)


@pytest.mark.django_db
def test_rec02_le_critere_prioritaire_designe_un_critere_de_la_copie_pas_de_l_original(source):
    concours, operateur = source

    copie = dupliquer(concours, operateur).concours

    memo = Epreuve.objects.get(categorie__concours=copie, nom="Mémorisation")
    assert memo.critere_prioritaire.libelle == "Tajwid"
    assert memo.critere_prioritaire.epreuve_id == memo.pk  # un critère de la copie : modifier la copie ne touche pas l'original


@pytest.mark.django_db
def test_rec02_les_series_sont_recreees_avec_de_nouvelles_questions_dans_le_meme_ordre(source):
    concours, operateur = source
    originales = Question.objects.filter(organisation=concours.organisation).count()

    copie = dupliquer(concours, operateur).concours

    memo = Epreuve.objects.get(categorie__concours=copie, nom="Mémorisation")
    series = list(memo.lot.series.order_by("numero"))
    assert [s.numero for s in series] == [1, 2]
    passages = [(q.question.passage.sourate_debut, q.question.passage.verset_debut, q.question.passage.sourate_fin, q.question.passage.verset_fin)
                for q in series[0].questions_ordonnees.order_by("rang")]
    assert passages == [(2, 142, 2, 150), (112, 1, 112, 4)]
    assert [q.question.type for q in series[1].questions_ordonnees.order_by("rang")] == ["passage_coranique", "enonce"]
    assert series[1].questions_ordonnees.get(rang=2).question.enonce == "Que signifie « Sabr » ?"
    ancien_lot = Epreuve.objects.get(categorie__concours=concours, nom="Mémorisation").lot
    ids_anciens = set(QuestionDeSerie.objects.filter(serie__lot=ancien_lot).values_list("question_id", flat=True))
    ids_nouveaux = set(QuestionDeSerie.objects.filter(serie__lot=memo.lot).values_list("question_id", flat=True))
    assert not ids_anciens & ids_nouveaux  # aucune question partagée : l'original reste indépendant
    assert Question.objects.filter(organisation=concours.organisation).count() == originales + len(ids_nouveaux)


@pytest.mark.django_db
def test_rec02_la_copie_repart_en_brouillon_sans_validation_ni_donnees_de_passage(source):
    concours, operateur = source

    copie = dupliquer(concours, operateur).concours

    assert copie.etat == Concours.Etat.BROUILLON
    assert copie.configuration_validee_le is None and copie.configuration_empreinte == "" and copie.configuration_validee_par_id is None
    assert copie.sessions.count() == 0
    assert Participation.objects.filter(categorie__concours=copie).count() == 0
    assert Epreuve.objects.filter(categorie__concours=copie).exclude(etat=Epreuve.Etat.EN_PREPARATION).count() == 0
    assert (copie.date_debut, copie.date_fin) == (date(2027, 3, 1), date(2027, 3, 2))


@pytest.mark.django_db
def test_rec02_l_original_n_est_pas_modifie(source):
    concours, operateur = source
    original = (concours.etat, concours.version_corpus_id, concours.configuration_empreinte)

    dupliquer(concours, operateur)

    concours.refresh_from_db()
    assert (concours.etat, concours.version_corpus_id, concours.configuration_empreinte) == original
    assert Categorie.objects.filter(concours=concours).count() == 2
    assert Serie.objects.filter(lot__epreuve__categorie__concours=concours).count() == 2
    assert CritereNotation.objects.filter(epreuve__categorie__concours=concours).count() == 4


@pytest.mark.django_db
def test_rec02_la_copie_reprend_la_version_du_corpus_si_elle_est_encore_utilisable(source):
    concours, operateur = source

    resultat = dupliquer(concours, operateur)

    assert resultat.concours.version_corpus_id == concours.version_corpus_id
    assert resultat.avertissements == []


@pytest.mark.django_db
def test_rec02_sans_version_utilisable_la_structure_est_copiee_mais_les_passages_non(source):
    concours, operateur = source
    VersionCorpus.objects.filter(pk=concours.version_corpus_id).update(statut=VersionCorpus.Statut.RETIREE)

    resultat = dupliquer(concours, operateur)

    assert resultat.concours.version_corpus_id is None
    assert resultat.epreuves == 3 and resultat.criteres == 4
    assert resultat.series == 0 and resultat.series_ignorees == 2
    assert any("corpus" in a.lower() for a in resultat.avertissements)


@pytest.mark.django_db
def test_rec02_une_serie_sans_passage_est_copiee_meme_sans_corpus(source, version):
    concours, operateur = source
    epreuve = Epreuve.objects.get(categorie__concours=concours, nom="Questions")
    services_questions.composer_serie(services_questions.obtenir_lot(epreuve),
                                      [services_questions.creer_question_enonce(concours.organisation, "Question libre")])
    VersionCorpus.objects.filter(pk=version.pk).update(statut=VersionCorpus.Statut.RETIREE)

    resultat = dupliquer(concours, operateur)

    assert (resultat.series, resultat.series_ignorees) == (1, 2)


@pytest.mark.django_db
def test_rec02_le_nom_et_l_edition_doivent_rester_uniques(source):
    concours, operateur = source

    with pytest.raises(ConfigurationInvalideError, match="existe déjà"):
        dupliquer(concours, operateur, edition="2026")
    assert Concours.objects.filter(organisation=concours.organisation).count() == 1  # rien n'a été créé


@pytest.mark.django_db
def test_rec02_les_dates_incoherentes_sont_refusees_sans_rien_creer(source):
    concours, operateur = source

    with pytest.raises(ConfigurationInvalideError, match="date"):
        dupliquer(concours, operateur, date_debut=date(2027, 3, 5), date_fin=date(2027, 3, 1))
    assert Concours.objects.filter(organisation=concours.organisation).count() == 1


@pytest.mark.django_db
def test_rm20_la_copie_peut_aller_dans_une_autre_mission_du_meme_client_pas_d_un_autre_client(source):
    concours, operateur = source
    autre_mission = creer_mission(concours.organisation, nom="Mission 2027")
    AffectationOperateur.objects.create(mission=autre_mission, utilisateur=operateur)

    copie = dupliquer(concours, operateur, mission=autre_mission).concours
    assert copie.mission_id == autre_mission.pk

    mission_etrangere = creer_mission(creer_organisation())
    AffectationOperateur.objects.create(mission=mission_etrangere, utilisateur=operateur)
    with pytest.raises(ConfigurationInvalideError, match="client"):
        dupliquer(concours, operateur, edition="2028", mission=mission_etrangere)


@pytest.mark.django_db
def test_seul_le_personnel_du_prestataire_affecte_duplique(source):
    concours, operateur = source
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation)
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)  # opérateur non affecté à cette mission (RM-20)

    for intrus in (responsable, etranger):
        with pytest.raises(ConfigurationInvalideError, match="droit"):
            dupliquer(concours, intrus, edition="2028")
    admin = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR)
    assert dupliquer(concours, admin, edition="2029").concours.pk


@pytest.mark.django_db
def test_la_duplication_est_journalisee(source):
    concours, operateur = source

    copie = dupliquer(concours, operateur).concours

    entree = EntreeAudit.objects.filter(action="concours.duplique", objet_id=str(copie.pk)).get()
    assert entree.details["source"] == str(concours.pk) and entree.details["epreuves"] == 3


@pytest.mark.django_db
def test_la_copie_peut_etre_validee_puis_ouverte_comme_n_importe_quel_concours(source):
    concours, operateur = source
    copie = dupliquer(concours, operateur).concours
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation)

    services.valider_configuration(copie, responsable)
    services.ouvrir_concours(copie)

    copie.refresh_from_db()
    assert copie.etat == Concours.Etat.OUVERT


# --- Administration : action « Dupliquer vers une nouvelle édition » ---------------------------------------------------


def url_liste():
    from django.urls import reverse

    return reverse("admin:concours_concours_changelist")


def poster_action(client, concours, **plus):
    donnees = {"action": "dupliquer", "_selected_action": [str(concours.pk)], **plus}
    return client.post(url_liste(), donnees)


@pytest.mark.django_db
def test_l_action_ouvre_un_formulaire_prerempli_puis_cree_la_copie(client, source):
    concours, operateur = source
    operateur.is_staff = True
    operateur.save()
    client.force_login(operateur)

    page = poster_action(client, concours)
    assert page.status_code == 200 and "Dupliquer le concours" in page.content.decode()

    reponse = poster_action(client, concours, appliquer="1", nom="Concours régional", edition="2027",
                            date_debut="2027-03-01", date_fin="2027-03-02", mission=str(concours.mission_id))
    copie = Concours.objects.get(edition="2027")
    assert reponse.status_code == 302 and str(copie.pk) in reponse.url
    assert copie.etat == Concours.Etat.BROUILLON


@pytest.mark.django_db
def test_l_action_affiche_l_erreur_metier_dans_le_formulaire_sans_rien_creer(client, source):
    concours, operateur = source
    operateur.is_staff = True
    operateur.save()
    client.force_login(operateur)

    reponse = poster_action(client, concours, appliquer="1", nom="Concours régional", edition="2026",
                            date_debut="2026-03-01", date_fin="2026-03-02", mission=str(concours.mission_id))

    assert reponse.status_code == 200 and "existe déjà" in reponse.content.decode()
    assert Concours.objects.filter(organisation=concours.organisation).count() == 1


@pytest.mark.django_db
def test_le_responsable_client_n_a_pas_l_action_dupliquer(client, source):
    concours, _ = source
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation, is_staff=True)
    client.force_login(responsable)

    page = client.get(url_liste())

    assert "Dupliquer vers une nouvelle édition" not in page.content.decode()
    refus = poster_action(client, concours, appliquer="1", nom="X", edition="2030", date_debut="2030-01-01", date_fin="2030-01-02",
                          mission=str(concours.mission_id))
    assert not Concours.objects.filter(edition="2030").exists()  # même en forçant la requête, le serveur refuse
    assert refus.status_code in (200, 302)


@pytest.mark.django_db
def test_on_ne_duplique_qu_un_concours_a_la_fois(client, source):
    concours, operateur = source
    operateur.is_staff = True
    operateur.save()
    client.force_login(operateur)

    client.post(url_liste(), {"action": "dupliquer", "_selected_action": []}, follow=True)

    assert Concours.objects.filter(organisation=concours.organisation).count() == 1
