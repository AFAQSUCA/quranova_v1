"""Fabriques de test pour les prestations et les tirages."""
import itertools
import uuid
from datetime import date

from django.utils import timezone

from apps.candidats.models import Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_epreuve,
    creer_mission,
    creer_participation,
    creer_session,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours.models import Concours, Epreuve
from apps.prestations.models import Prestation, Tirage
from apps.questions import services as services_questions
from apps.questions.tests.outils import creer_question
from apps.utilisateurs.models import Utilisateur

_rangs = itertools.count(1)


def creer_epreuve_ouverte(series=4, p=1, **champs):
    """Une épreuve OUVERTE d'un concours EN COURS, avec un lot de ``series`` séries de ``p`` questions."""
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)
    concours = creer_concours(
        creer_mission(responsable.organisation),
        etat=Concours.Etat.EN_COURS,
        version_corpus=creer_version_validee(),
        configuration_validee_par=responsable,
        configuration_validee_le=timezone.now(),
        configuration_empreinte="a" * 64,
    )
    champs.setdefault("etat", Epreuve.Etat.OUVERTE)
    epreuve = creer_epreuve(creer_categorie(concours), questions_par_serie=p, **champs)
    ajouter_series(epreuve, series)
    return epreuve


def ajouter_series(epreuve, nombre):
    """Ajoute ``nombre`` séries complètes au lot de l'épreuve ; renvoie la liste des séries créées."""
    lot = services_questions.obtenir_lot(epreuve)
    return [
        services_questions.composer_serie(
            lot, [creer_question(epreuve.organisation) for _ in range(epreuve.questions_par_serie)]
        )
        for _ in range(nombre)
    ]


def creer_prestation(epreuve, participation=None, session=None, **champs):
    """Une prestation EN_ATTENTE pour un candidat ADMIS, majeur (donc sans exigence de consentement)."""
    participation = participation or creer_participation(
        epreuve.categorie,
        creer_candidat(epreuve.organisation, date_naissance=date(1990, 1, 1)),
        statut=Participation.Statut.ADMIS,
    )
    valeurs = {
        "participation": participation,
        "epreuve": epreuve,
        "session": session or creer_session(epreuve.categorie.concours),
        "rang_passage": next(_rangs),
    }
    valeurs.update(champs)
    return Prestation.objects.create(**valeurs)


def creer_tirage(prestation, serie, **champs):
    valeurs = {"prestation": prestation, "serie": serie, "rang": 1, "id_demande": uuid.uuid4()}
    valeurs.update(champs)
    return Tirage.objects.create(**valeurs)
