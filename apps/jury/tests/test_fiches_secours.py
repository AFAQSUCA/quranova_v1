"""Fiches de notation de secours (§13.6, phase 4 C2) : impression la veille, puis saisie ultérieure AVEC MOTIF.

Scénario : panne simultanée des deux ordinateurs. Les jurés notent sur des fiches imprimées ; plus tard, l'opérateur les saisit en indiquant
pourquoi (motif), l'évaluation est tracée comme « saisie différée » et reste soumise aux règles habituelles (RM-16 : une note manquante n'est jamais un zéro).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_jure, creer_utilisateur
from apps.jury import fiches
from apps.jury.exceptions import EvaluationIncompleteError, EvaluationInterditeError, NoteInvalideError
from apps.jury.models import AffectationJury, Evaluation, Note
from apps.jury.tests.test_evaluations import notes_completes, poste
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_prestation, creer_tirage
from apps.resultats import documents
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

MOTIF = "Panne simultanée des deux ordinateurs à 11 h 05 : les jurés ont noté sur les fiches de secours."


@pytest.fixture
def operateur_de():
    def fabrique(prestation):
        operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
        AffectationOperateur.objects.create(mission=prestation.epreuve.categorie.concours.mission, utilisateur=operateur)
        return operateur

    return fabrique


# --- Impression -----------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_il_y_a_une_fiche_par_prestation_et_par_jure_affecte(operateur_de):
    prestation, (jure1, jure2), criteres = poste(etat=Prestation.Etat.EN_ATTENTE, jures=2)
    autre = creer_prestation(prestation.epreuve, session=prestation.session)

    html = fiches.fiches_html(prestation.session, operateur_de(prestation))

    assert html.count('class="fiche"') == 4  # 2 prestations x 2 jurés
    assert jure1.nom_complet in html and jure2.nom_complet in html
    assert f"n° {prestation.participation.numero_candidat}" in html and f"n° {autre.participation.numero_candidat}" in html


@pytest.mark.django_db
def test_chaque_fiche_porte_le_bareme_une_reference_unique_et_la_consigne_de_saisie(operateur_de):
    prestation, _, criteres = poste(etat=Prestation.Etat.EN_ATTENTE, jures=2)

    html = fiches.fiches_html(prestation.session, operateur_de(prestation))

    for critere in criteres:
        assert critere.libelle in html
    assert "/ 10" in html and "/ 5" in html and "coef" in html.lower()
    references = fiches.references(prestation.session)
    assert len(references) == 2 and len(set(references)) == 2 and all(r in html for r in references)
    assert "motif" in html.lower() and "Série tirée" in html  # la série n'est pas connue à l'impression : à écrire à la main


@pytest.mark.django_db
def test_les_fiches_n_incluent_ni_les_prestations_annulees_ni_les_jures_inactifs_ni_une_autre_session(operateur_de):
    prestation, (actif, inactif), _ = poste(etat=Prestation.Etat.EN_ATTENTE, jures=2)
    type(inactif).objects.filter(pk=inactif.pk).update(actif=False)
    creer_prestation(prestation.epreuve, session=prestation.session, etat=Prestation.Etat.ANNULEE)
    creer_prestation(prestation.epreuve)  # autre session du même concours

    html = fiches.fiches_html(prestation.session, operateur_de(prestation))

    assert html.count('class="fiche"') == 1 and inactif.nom_complet not in html


@pytest.mark.django_db
def test_une_fiche_ne_montre_aucun_resultat_ni_note(operateur_de):
    prestation, (jure,), criteres = poste(jures=1)
    from apps.jury import evaluations

    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres, (9, 8, 4)))

    html = fiches.fiches_html(prestation.session, operateur_de(prestation))

    assert "9.00" not in html and "8.00" not in html  # la fiche est vierge


@pytest.mark.django_db
def test_le_texte_saisi_est_echappe_sur_la_fiche(operateur_de):
    prestation, (jure,), _ = poste(etat=Prestation.Etat.EN_ATTENTE, jures=1)
    type(jure).objects.filter(pk=jure.pk).update(nom="<script>x</script>")

    html = fiches.fiches_html(prestation.session, operateur_de(prestation))

    assert "<script>x</script>" not in html and "&lt;script&gt;" in html


@pytest.mark.django_db
def test_l_impression_est_journalisee(operateur_de):
    prestation, _, _ = poste(etat=Prestation.Etat.EN_ATTENTE)

    fiches.fiches_html(prestation.session, operateur_de(prestation))

    assert EntreeAudit.objects.filter(action="document.fiches_secours_generees").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("nom", ["jury:fiches_secours", "jury:fiches_secours_pdf"])
def test_seul_le_personnel_affecte_imprime_les_fiches(client, operateur_de, nom):
    prestation, _, _ = poste(etat=Prestation.Etat.EN_ATTENTE)
    url = reverse(nom, args=[prestation.session.pk])
    assert client.get(url).status_code == 302  # anonyme : vers la connexion

    client.force_login(creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True))  # non affecté à cette mission (RM-20)
    assert client.get(url).status_code == 404
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation, is_staff=True))
    assert client.get(url).status_code == 404
    client.force_login(operateur_de(prestation))
    assert client.get(url).status_code in (200, 503)  # 503 : seulement si WeasyPrint manque sur la machine


# --- Saisie ultérieure ----------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_saisie_differee_cree_une_evaluation_validee_tracee_avec_son_motif(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    operateur = operateur_de(prestation)

    evaluation = fiches.saisir_fiche(operateur, jure, prestation, notes_completes(criteres, (9, "8,5", 0)), motif=MOTIF,
                                     observation="Très bonne récitation", reference="FS-001-A1B2")

    assert evaluation.statut == Evaluation.Statut.VALIDEE and evaluation.validee_le is not None
    assert (evaluation.saisie_differee, evaluation.motif_saisie_differee, evaluation.saisie_par) == (True, MOTIF, operateur)
    assert evaluation.reference_fiche == "FS-001-A1B2" and evaluation.observation == "Très bonne récitation"
    assert evaluation.series_evaluees == [prestation.tirages.first().serie.libelle]
    valeurs = {n.critere_id: n.valeur for n in evaluation.notes.all()}
    assert valeurs[criteres[1].pk] == Decimal("8.50") and valeurs[criteres[2].pk] == Decimal("0.00")  # un zéro écrit est une note (RM-16)
    assert EntreeAudit.objects.filter(action="evaluation.saisie_differee", objet_id=str(evaluation.pk)).count() == 1


@pytest.mark.django_db
def test_le_motif_est_obligatoire(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)

    for motif in ("", "   "):
        with pytest.raises(EvaluationInterditeError, match="motif"):
            fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes_completes(criteres), motif=motif)
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_rm16_une_note_manquante_sur_la_fiche_n_est_jamais_convertie_en_zero_et_rien_n_est_enregistre(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    notes = notes_completes(criteres)
    notes[str(criteres[2].pk)] = ""  # le juré n'a pas rempli ce critère

    with pytest.raises(EvaluationIncompleteError) as erreur:
        fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes, motif=MOTIF)

    assert criteres[2].libelle in str(erreur.value)
    assert not Evaluation.objects.exists() and not Note.objects.exists()


@pytest.mark.django_db
def test_une_note_hors_bareme_est_refusee(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)

    with pytest.raises(NoteInvalideError):
        fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes_completes(criteres, (11, 8, 4)), motif=MOTIF)
    assert not Evaluation.objects.exists()


@pytest.mark.django_db
def test_seul_un_jure_affecte_a_l_epreuve_a_une_fiche(operateur_de):
    prestation, _, criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    intrus = creer_jure(prestation.organisation)  # pas affecté

    with pytest.raises(EvaluationInterditeError, match="affecté"):
        fiches.saisir_fiche(operateur_de(prestation), intrus, prestation, notes_completes(criteres), motif=MOTIF)


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Prestation.Etat.EN_ATTENTE, Prestation.Etat.ANNULEE])
def test_on_ne_saisit_pas_une_fiche_pour_une_prestation_sans_tirage_valable(operateur_de, etat):
    prestation, (jure,), criteres = poste(etat=etat)

    with pytest.raises(EvaluationInterditeError, match="tirage"):
        fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes_completes(criteres), motif=MOTIF)


@pytest.mark.django_db
def test_on_ne_saisit_pas_deux_fois_la_fiche_d_un_jure(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    operateur = operateur_de(prestation)
    fiches.saisir_fiche(operateur, jure, prestation, notes_completes(criteres), motif=MOTIF)

    with pytest.raises(EvaluationInterditeError, match="déjà"):
        fiches.saisir_fiche(operateur, jure, prestation, notes_completes(criteres), motif=MOTIF)


@pytest.mark.django_db
def test_une_evaluation_en_ligne_deja_commencee_ne_peut_pas_etre_ecrasee_par_une_fiche(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    from apps.jury import evaluations

    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    with pytest.raises(EvaluationInterditeError, match="déjà"):
        fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes_completes(criteres, (1, 1, 1)), motif=MOTIF)
    assert Note.objects.filter(evaluation__jure=jure, valeur=Decimal("9")).exists()  # le brouillon en ligne n'a pas bougé


@pytest.mark.django_db
def test_seuls_le_personnel_affecte_ou_l_administrateur_saisissent(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)

    for intrus in (creer_utilisateur(Utilisateur.Role.OPERATEUR), creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation)):
        with pytest.raises(EvaluationInterditeError, match="droit"):
            fiches.saisir_fiche(intrus, jure, prestation, notes_completes(criteres), motif=MOTIF)
    assert fiches.saisir_fiche(creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR), jure, prestation, notes_completes(criteres), motif=MOTIF).pk


@pytest.mark.django_db
def test_la_prestation_est_cloturee_quand_tous_les_jures_ont_leur_fiche_saisie(operateur_de):
    prestation, (jure1, jure2), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE, jures=2)
    operateur = operateur_de(prestation)

    fiches.saisir_fiche(operateur, jure1, prestation, notes_completes(criteres), motif=MOTIF)
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_AFFICHAGE  # il manque encore un juré

    fiches.saisir_fiche(operateur, jure2, prestation, notes_completes(criteres, (7, 7, 3)), motif=MOTIF)
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.CLOTUREE
    assert EntreeAudit.objects.filter(action="prestation.cloturee").count() == 1


@pytest.mark.django_db
def test_la_saisie_differee_compte_comme_une_evaluation_validee_pour_le_classement(operateur_de):
    from apps.resultats import services as services_resultats

    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes_completes(criteres, (9, 8, 4)), motif=MOTIF)

    lignes = services_resultats.classement_provisoire(prestation.epreuve)

    assert lignes[0]["score"] == Decimal("30.00") and lignes[0]["evaluations_validees"] == 1  # 9x2 + 8x1 + 4x1


# --- Procès-verbal et administration ------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_proces_verbal_signale_les_evaluations_saisies_depuis_une_fiche(operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    fiches.saisir_fiche(operateur_de(prestation), jure, prestation, notes_completes(criteres), motif=MOTIF, reference="FS-007-ZZZZ")

    html = documents.proces_verbal(prestation.epreuve.categorie.concours)

    assert "Évaluations saisies depuis une fiche de secours" in html and MOTIF in html and "FS-007-ZZZZ" in html


@pytest.mark.django_db
def test_l_action_d_administration_saisit_une_fiche_avec_un_formulaire_adapte_au_bareme(client, operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    client.force_login(operateur_de(prestation))
    liste = reverse("admin:prestations_prestation_changelist")

    page = client.post(liste, {"action": "saisir_fiche_de_secours", "_selected_action": [str(prestation.pk)]})
    contenu = page.content.decode()
    assert page.status_code == 200 and all(f"note_{c.pk}" in contenu for c in criteres) and "motif" in contenu.lower()

    donnees = {"action": "saisir_fiche_de_secours", "_selected_action": [str(prestation.pk)], "appliquer": "1", "jure": str(jure.pk),
               "motif": MOTIF, "reference": "FS-001-A1B2", "observation": "", **{f"note_{c.pk}": v for c, v in zip(criteres, ("9", "8", "4"))}}
    reponse = client.post(liste, donnees)

    assert reponse.status_code == 302
    assert Evaluation.objects.get().saisie_differee is True


@pytest.mark.django_db
def test_l_action_affiche_l_erreur_metier_sans_rien_enregistrer(client, operateur_de):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    client.force_login(operateur_de(prestation))

    reponse = client.post(reverse("admin:prestations_prestation_changelist"), {
        "action": "saisir_fiche_de_secours", "_selected_action": [str(prestation.pk)], "appliquer": "1", "jure": str(jure.pk),
        "motif": MOTIF, f"note_{criteres[0].pk}": "9", f"note_{criteres[1].pk}": "8", f"note_{criteres[2].pk}": "",
    })

    assert reponse.status_code == 200 and criteres[2].libelle in reponse.content.decode()
    assert not Evaluation.objects.exists()
