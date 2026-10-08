"""Fabriques de test pour la présentation : un corpus minimal et une prestation tirée."""
import uuid

from django.utils import timezone

from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_verset, creer_version
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage
from apps.questions import services as services_questions

# Textes NEUTRES : jamais un verset (règle absolue n°1).
def texte_du_verset(sourate, verset):
    return " ".join(f"s{sourate}v{verset}m{i}" for i in range(1, 9))


def creer_corpus_de_test(sourates=((1, 7), (2, 20))):
    """Une version avec des sourates et des versets au texte neutre ; validée APRÈS l'écriture (RM-27)."""
    version = creer_version()
    for numero, nombre in sourates:
        sourate = creer_sourate(version, numero=numero, nombre_versets=nombre, ordre_revelation=numero)
        for verset in range(1, nombre + 1):
            creer_verset(sourate, numero=verset, texte=texte_du_verset(numero, verset))
    version.statut = VersionCorpus.Statut.VALIDEE
    version.date_validation = timezone.now()
    version.save()
    return version


def creer_prestation_tiree(passages=(((2, 3), (2, 5)), ((1, 1), (1, 2))), series=1, tirages=1):
    """Une prestation à l'état TIRÉ ; chaque série est composée des ``passages`` donnés (P = len(passages)).

    Renvoie ``(prestation, epreuve, version)``.
    """
    version = creer_corpus_de_test()
    epreuve = creer_epreuve_ouverte(series=0, p=len(passages), version=version, tirages_par_candidat=tirages)
    lot = services_questions.obtenir_lot(epreuve)
    toutes = []
    for _ in range(max(series, tirages)):
        questions = [
            services_questions.creer_question_passage(epreuve.organisation, version, debut, fin)
            for debut, fin in passages
        ]
        toutes.append(services_questions.composer_serie(lot, questions))
    prestation = creer_prestation(epreuve)
    for rang in range(1, tirages + 1):
        creer_tirage(prestation, toutes[rang - 1], rang=rang, id_demande=uuid.uuid4())
    Prestation.objects.filter(pk=prestation.pk).update(etat=Prestation.Etat.TIRE)
    prestation.refresh_from_db()
    return prestation, epreuve, version


def operateur_de(epreuve):
    """Un opérateur affecté à la mission du concours de l'épreuve."""
    from apps.commun.tests.outils import creer_utilisateur
    from apps.utilisateurs.models import AffectationOperateur, Utilisateur

    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return operateur


def commande(session, action, version=None, *, auteur, prestation=None, id_commande=None):
    """Envoie une commande au service avec un identifiant neuf (ou celui donné)."""
    from apps.presentation import services

    return services.appliquer_commande(
        session, id_commande or uuid.uuid4(), action, version, auteur=auteur, prestation=prestation
    )


def presentation_demarree(**options):
    """(prestation, session, operateur, état) avec la présentation préparée puis démarrée (version 2)."""
    prestation, epreuve, _ = creer_prestation_tiree(**options)
    operateur = operateur_de(epreuve)
    session = prestation.session
    commande(session, "preparer", auteur=operateur, prestation=prestation)
    resultat = commande(session, "demarrer", 1, auteur=operateur)
    return prestation, session, operateur, resultat.etat
