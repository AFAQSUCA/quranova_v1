"""L'exemple calculé à la main (tests/test_calcul.py), reconstruit avec de vrais modèles."""
from datetime import date

from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_critere, creer_jure, creer_participation
from apps.jury import evaluations
from apps.jury.models import AffectationJury
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage

NOTES = {
    "A": [(9, 8, 4), (8, 9, 5), (10, 7, 4)],
    "B": [(9, 9, 5), (9, 8, 4), (8, 8, 4)],
    "C": [(7, 7, 3), (8, 8, 4), (6, 6, 3)],
    "E": [(9, 8, 4), (9, 8, 4), (9, 8, 4)],
    "D": [(9, 8, 4), (9, 7, 5)],  # le 3e juré n'a pas validé
}


def construire_exemple(regle_classement="moyenne", regle_departage="", critere_prioritaire=0):
    """Renvoie ``(epreuve, participations{A..E}, jurés, critères)`` avec les évaluations VALIDÉES de l'exemple."""
    epreuve = creer_epreuve_ouverte(series=1)
    categorie = epreuve.categorie
    categorie.regle_classement, categorie.regle_departage = regle_classement, regle_departage
    categorie.save()
    criteres = [creer_critere(epreuve, maximum=m, coefficient=c, libelle=l) for l, m, c in
                (("Mémorisation", 10, 2), ("Tajwid", 10, 1), ("Voix", 5, 1))]
    if regle_departage == "critere_prioritaire":
        epreuve.critere_prioritaire = criteres[critere_prioritaire]
        epreuve.save()
    jures = [creer_jure(epreuve.organisation) for _ in range(3)]
    for jure in jures:
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)
    participations = {}
    for nom, notes_par_jure in NOTES.items():
        participation = creer_participation(
            categorie, creer_candidat(epreuve.organisation, nom=f"Candidat-{nom}", prenom=nom, date_naissance=date(1990, 1, 1)), statut=Participation.Statut.ADMIS
        )
        participations[nom] = participation
        prestation = creer_prestation(epreuve, participation=participation, etat=Prestation.Etat.EN_NOTATION)
        creer_tirage(prestation, epreuve.lot.series.first())
        for jure, valeurs in zip(jures, notes_par_jure):
            evaluations.enregistrer_brouillon(jure, prestation, {str(c.pk): v for c, v in zip(criteres, valeurs)})
            evaluations.valider_evaluation(jure, prestation)
    return epreuve, participations, jures, criteres
