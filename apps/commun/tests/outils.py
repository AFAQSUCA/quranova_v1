"""Fonctions utilitaires partagées par les tests des applications clients, utilisateurs, etc."""
import itertools
from datetime import date

from django.utils import timezone

from apps.candidats.models import Candidat, Consentement, Participation
from apps.clients.models import Mission, Organisation
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_version
from apps.jury.models import Jure
from apps.utilisateurs.models import Utilisateur

_compteur = itertools.count(1)


def creer_organisation(**champs):
    n = next(_compteur)
    valeurs = {"nom": f"Organisation-test-{n}"}
    valeurs.update(champs)
    return Organisation.objects.create(**valeurs)


def creer_mission(organisation=None, **champs):
    n = next(_compteur)
    valeurs = {
        "organisation": organisation or creer_organisation(),
        "nom": f"Mission-test-{n}",
        "lieu": "Abidjan",
        "date_debut": date(2027, 1, 20),
        "date_fin": date(2027, 1, 21),
    }
    valeurs.update(champs)
    return Mission.objects.create(**valeurs)


def creer_utilisateur(role=Utilisateur.Role.OPERATEUR, organisation=None, **champs):
    """Crée un utilisateur de test ; un responsable client reçoit une organisation s'il n'en a pas."""
    n = next(_compteur)
    if role == Utilisateur.Role.RESPONSABLE_CLIENT and organisation is None:
        organisation = creer_organisation()
    return Utilisateur.objects.create_user(
        username=f"utilisateur-test-{n}",
        password="mot-de-passe-de-test",
        role=role,
        organisation=organisation,
        **champs,
    )


def creer_version_validee(**champs):
    """Une version du corpus validée (la seule sorte que l'on peut rattacher à un concours)."""
    valeurs = {"statut": VersionCorpus.Statut.VALIDEE, "date_validation": timezone.now()}
    valeurs.update(champs)
    return creer_version(**valeurs)


def creer_concours(mission=None, **champs):
    n = next(_compteur)
    mission = mission or creer_mission()
    valeurs = {
        "mission": mission,
        "nom": f"Concours-test-{n}",
        "edition": "2027",
        "date_debut": mission.date_debut,
        "date_fin": mission.date_fin,
    }
    valeurs.update(champs)
    return Concours.objects.create(**valeurs)


def creer_categorie(concours=None, **champs):
    n = next(_compteur)
    valeurs = {"concours": concours or creer_concours(), "nom": f"Categorie-test-{n}"}
    valeurs.update(champs)
    return Categorie.objects.create(**valeurs)


def creer_epreuve(categorie=None, **champs):
    n = next(_compteur)
    valeurs = {
        "categorie": categorie or creer_categorie(),
        "nom": f"Epreuve-test-{n}",
        "ordre": n,
        "questions_par_serie": 3,
    }
    valeurs.update(champs)
    return Epreuve.objects.create(**valeurs)


def creer_critere(epreuve=None, **champs):
    n = next(_compteur)
    valeurs = {
        "epreuve": epreuve or creer_epreuve(),
        "libelle": f"Critere-test-{n}",
        "ordre": n,
        "maximum": 10,
    }
    valeurs.update(champs)
    return CritereNotation.objects.create(**valeurs)


def creer_session(concours=None, **champs):
    n = next(_compteur)
    valeurs = {
        "concours": concours or creer_concours(),
        "nom": f"Session-test-{n}",
        "date": date(2027, 1, 20),
        "lieu": "Abidjan",
    }
    valeurs.update(champs)
    return Session.objects.create(**valeurs)


def configuration_complete(concours):
    """Une catégorie, une épreuve et un critère : le minimum pour valider la configuration."""
    categorie = creer_categorie(concours)
    epreuve = creer_epreuve(categorie)
    creer_critere(epreuve)
    return concours


def creer_candidat(organisation=None, **champs):
    n = next(_compteur)
    valeurs = {
        "organisation": organisation or creer_organisation(),
        "nom": f"Nom-test-{n}",
        "prenom": f"Prenom-test-{n}",
    }
    valeurs.update(champs)
    return Candidat.objects.create(**valeurs)


def creer_participation(categorie=None, candidat=None, **champs):
    n = next(_compteur)
    categorie = categorie or creer_categorie()
    valeurs = {
        "candidat": candidat or creer_candidat(categorie.organisation),
        "concours": categorie.concours,
        "categorie": categorie,
        "numero_candidat": n,
    }
    valeurs.update(champs)
    return Participation.objects.create(**valeurs)


def creer_consentement(participation=None, **champs):
    valeurs = {
        "participation": participation or creer_participation(),
        "representant_nom": "Representant de test",
        "representant_lien": "Parent",
        "version_formulaire": "1.0",
        "date_signature": date(2027, 1, 10),
        "consentement_participation": True,
    }
    valeurs.update(champs)
    return Consentement.objects.create(**valeurs)


def creer_jure(organisation=None, **champs):
    n = next(_compteur)
    valeurs = {
        "organisation": organisation or creer_organisation(),
        "nom": f"Jure-nom-test-{n}",
        "prenom": f"Jure-prenom-test-{n}",
    }
    valeurs.update(champs)
    return Jure.objects.create(**valeurs)
