"""Jeu de données de la simulation de charge (REC-19) : un concours de N candidats, T terminaux, une présentation longue.

À n'exécuter que sur une base JETABLE : les données créées sont des données de charge, qui ne se suppriment pas
(le journal d'audit est en ajout seul). Dans Docker : ``docker compose down -v`` repart d'une base vide.
"""
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date

from django.test import Client
from django.utils import timezone

from apps.candidats.models import Candidat, Participation
from apps.candidats.services import inscrire
from apps.clients.models import Mission, Organisation
from apps.concours import services as services_concours
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from apps.coran.models import Verset, VersionCorpus
from apps.prestations import services as services_prestations
from apps.prestations import terminaux
from apps.prestations.models import Prestation, Terminal
from apps.questions import services as services_questions
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

# Passages de la série de présentation : de quoi faire une trentaine de diapositives à parcourir.
PASSAGES_PRESENTATION = [((2, 142), (2, 150)), ((2, 255), (2, 258))]


@dataclass
class Contexte:
    organisation: Organisation
    session: Session
    operateur: Utilisateur
    cookie_operateur: str
    prestations: list = field(default_factory=list)       # prestations à tirer (ids)
    terminaux_tirage: list = field(default_factory=list)  # [(Terminal, jeton)]
    terminaux_scene: list = field(default_factory=list)   # [(Terminal, jeton)]
    prestation_presentation: Prestation = None
    nombre_candidats: int = 0


def version_utilisable():
    versions = VersionCorpus.objects.filter(statut__in=[VersionCorpus.Statut.VALIDEE, VersionCorpus.Statut.ACTIVE])
    version = versions.order_by("-date_import").first()
    if version is None:
        raise RuntimeError(
            "Aucune version du corpus validée : importez-la (import_corpus) puis validez-la, ou lancez "
            "« creer_demo --valider-corpus-pour-test » sur cette base jetable."
        )
    return version


def preparer(nombre_candidats, nombre_terminaux_tirage, nombre_ecrans_scene, ecrire=print):
    version = version_utilisable()
    marque = secrets.token_hex(3)
    aujourd_hui = date.today()

    organisation = Organisation.objects.create(nom=f"CHARGE-TEST {marque}")
    mission = Mission.objects.create(
        organisation=organisation, nom="Charge", lieu="Simulation", date_debut=aujourd_hui, date_fin=aujourd_hui
    )
    mot_de_passe = secrets.token_urlsafe(16)
    responsable = Utilisateur.objects.create_user(
        f"charge-resp-{marque}", password=mot_de_passe, role=Utilisateur.Role.RESPONSABLE_CLIENT,
        organisation=organisation, is_staff=True,
    )
    operateur = Utilisateur.objects.create_user(
        f"charge-op-{marque}", password=mot_de_passe, role=Utilisateur.Role.OPERATEUR, is_staff=True
    )
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    concours = Concours.objects.create(
        mission=mission, nom=f"Charge {marque}", edition=str(aujourd_hui.year), date_debut=aujourd_hui, date_fin=aujourd_hui
    )
    services_concours.definir_version_corpus(concours, version)
    categorie_a = Categorie.objects.create(concours=concours, nom="Charge A")
    categorie_b = Categorie.objects.create(concours=concours, nom="Présentation")
    epreuve_a = Epreuve.objects.create(
        categorie=categorie_a, nom="Tirages", ordre=1, questions_par_serie=1, etat=Epreuve.Etat.EN_PREPARATION
    )
    epreuve_b = Epreuve.objects.create(
        categorie=categorie_b, nom="Diaporama", ordre=1, questions_par_serie=2, etat=Epreuve.Etat.EN_PREPARATION,
        reutilisation_autre_candidat=True, affichage_scene=True,  # la scène reçoit le texte : cas le plus lourd
    )
    for epreuve in (epreuve_a, epreuve_b):
        CritereNotation.objects.create(epreuve=epreuve, libelle="Mémorisation", ordre=1, maximum=10)

    ecrire(f"Création de {nombre_candidats} candidats…")
    participations = []
    for i in range(nombre_candidats):
        candidat = Candidat.objects.create(
            organisation=organisation, nom=f"Charge{i:04d}", prenom="Test", date_naissance=date(1990, 1, 1), ville="Simulation"
        )
        participation = inscrire(candidat, categorie_a)
        participation.statut = Participation.Statut.ADMIS
        participation.save(update_fields=["statut", "modifie_le"])
        participations.append(participation)
    candidat_b = Candidat.objects.create(
        organisation=organisation, nom="ChargePresentation", prenom="Test", date_naissance=date(1990, 1, 1), ville="Simulation"
    )
    participation_b = inscrire(candidat_b, categorie_b)
    participation_b.statut = Participation.Statut.ADMIS
    participation_b.save(update_fields=["statut", "modifie_le"])

    ecrire(f"Création de {nombre_candidats} séries (un verset chacune)…")
    versets = list(
        Verset.objects.filter(sourate__version=version, sourate__numero__gte=70)
        .order_by("sourate__numero", "numero").values_list("sourate__numero", "numero")[:nombre_candidats]
    )
    if len(versets) < nombre_candidats:
        raise RuntimeError(f"Le corpus ne fournit que {len(versets)} versets distincts pour {nombre_candidats} séries.")
    lot_a = services_questions.obtenir_lot(epreuve_a)
    for sourate, verset in versets:
        question = services_questions.creer_question_passage(organisation, version, (sourate, verset), (sourate, verset))
        services_questions.composer_serie(lot_a, [question])
    lot_b = services_questions.obtenir_lot(epreuve_b)
    services_questions.composer_serie(
        lot_b, [services_questions.creer_question_passage(organisation, version, d, f) for d, f in PASSAGES_PRESENTATION]
    )

    services_concours.valider_configuration(concours, responsable)
    services_concours.ouvrir_concours(concours)
    services_concours.demarrer_concours(concours)
    services_prestations.ouvrir_epreuve(epreuve_a)
    services_prestations.ouvrir_epreuve(epreuve_b)

    session = Session.objects.create(concours=concours, nom="Charge", date=aujourd_hui, lieu="Simulation")
    contexte = Contexte(
        organisation=organisation, session=session, operateur=operateur, cookie_operateur="", nombre_candidats=nombre_candidats
    )
    for i in range(nombre_terminaux_tirage):
        contexte.terminaux_tirage.append(terminaux.creer_terminal(session, f"Tirage {i + 1:02d}"))
    for i in range(nombre_ecrans_scene):
        contexte.terminaux_scene.append(terminaux.creer_terminal(session, f"Scène {i + 1:02d}", type=Terminal.Type.SCENE))
    for rang, participation in enumerate(participations, start=1):
        prestation = Prestation.objects.create(participation=participation, epreuve=epreuve_a, session=session, rang_passage=rang)
        contexte.prestations.append(prestation.pk)
    presentation = Prestation.objects.create(
        participation=participation_b, epreuve=epreuve_b, session=session, rang_passage=nombre_candidats + 1
    )
    terminal, _ = contexte.terminaux_tirage[0]
    terminaux.appeler_prestation(terminal, presentation, operateur)
    services_prestations.effectuer_tirage(presentation, uuid.uuid4(), terminal=terminal.nom)
    terminaux.liberer_terminal(terminal)
    presentation.refresh_from_db()
    contexte.prestation_presentation = presentation

    navigateur = Client()
    navigateur.force_login(operateur)
    contexte.cookie_operateur = f"sessionid={navigateur.cookies['sessionid'].value}"
    return contexte
