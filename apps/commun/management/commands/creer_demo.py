"""Commande : prépare un jeu de données de démonstration pour essayer l'application (développement seulement).

Crée un client, une mission, un concours configuré (une catégorie, une épreuve, un barème), des
candidats admis, un lot de séries composées de VRAIS passages du corpus importé (références seulement :
le texte n'est jamais copié), puis valide, ouvre et démarre le concours, ouvre l'épreuve, et prépare
une session, un terminal de tirage et les prestations. Il ne reste qu'à appeler un candidat.

Refuse de s'exécuter hors développement (DEBUG), car il crée des comptes aux mots de passe connus.
"""
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.candidats.models import Candidat, Participation
from apps.candidats.services import inscrire
from apps.clients.models import Mission, Organisation
from apps.concours import services as services_concours
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from apps.coran.models import VersionCorpus
from apps.prestations import services as services_prestations
from apps.prestations import terminaux
from apps.prestations.models import Prestation
from apps.questions import services as services_questions
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

NOM_ORGANISATION = "Association Démo"
MOT_DE_PASSE = "demo-12345"
NOMBRE_CANDIDATS = 6
# Passages courts de la fin du Coran : 12 passages = 6 séries de 2 questions (un candidat par série, RM-24).
PASSAGES = [
    ((1, 1), (1, 7)), ((112, 1), (112, 4)), ((113, 1), (113, 5)), ((114, 1), (114, 6)),
    ((103, 1), (103, 3)), ((108, 1), (108, 3)), ((105, 1), (105, 5)), ((106, 1), (106, 4)),
    ((107, 1), (107, 7)), ((109, 1), (109, 6)), ((110, 1), (110, 3)), ((111, 1), (111, 5)),
]
PRENOMS = ["Awa", "Ibrahim", "Fatima", "Moussa", "Khadija", "Souleymane"]
NOMS = ["Diallo", "Koné", "Traoré", "Ouattara", "Bamba", "Coulibaly"]


class Command(BaseCommand):
    help = "Prépare des données de démonstration (développement seulement)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--valider-corpus-pour-test",
            action="store_true",
            help="Marque la version importée comme « validée » pour l'essai. ATTENTION : ce n'est PAS la "
            "validation du référent coranique (jalon J0).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Commande réservée au développement (DEBUG doit être vrai).")
        if Organisation.objects.filter(nom=NOM_ORGANISATION).exists():
            raise CommandError(f"La démonstration existe déjà (« {NOM_ORGANISATION} »). Rien n'a été modifié.")
        version = self._choisir_version(options["valider_corpus_pour_test"])

        try:
            with transaction.atomic():
                resultat = self._creer(version)
        except NotImplementedError as regle:
            raise CommandError(
                f"{regle}\nCette règle est à écrire par vous (voir le chapitre 13 du tutoriel). "
                "Rien n'a été enregistré : relancez la commande après l'avoir écrite."
            ) from None
        self._afficher(resultat)

    def _choisir_version(self, valider):
        versions = VersionCorpus.objects.exclude(statut=VersionCorpus.Statut.RETIREE)
        utilisable = versions.filter(
            statut__in=[VersionCorpus.Statut.VALIDEE, VersionCorpus.Statut.ACTIVE]
        ).order_by("-date_import").first()
        if utilisable:
            return utilisable
        importee = versions.order_by("-date_import").first()
        if importee is None:
            raise CommandError("Aucun corpus : lancez d'abord « python manage.py import_corpus ».")
        if not valider:
            raise CommandError(
                "Le corpus importé n'est pas validé (RM-09). Pour un simple essai en local, relancez avec "
                "--valider-corpus-pour-test (ce n'est pas la validation du référent coranique)."
            )
        importee.statut = VersionCorpus.Statut.VALIDEE
        importee.date_validation = timezone.now()
        importee.save()
        self.stdout.write(self.style.WARNING("Corpus marqué « validé » POUR L'ESSAI (pas de validation du référent)."))
        return importee

    def _creer(self, version):
        organisation = Organisation.objects.create(nom=NOM_ORGANISATION)
        mission = Mission.objects.create(
            organisation=organisation, nom="Mission démo", lieu="Abidjan",
            date_debut=date.today(), date_fin=date.today(),
        )
        responsable = Utilisateur.objects.create_user(
            "responsable", password=MOT_DE_PASSE, role=Utilisateur.Role.RESPONSABLE_CLIENT,
            organisation=organisation, is_staff=True,
        )
        operateur = Utilisateur.objects.create_user(
            "operateur", password=MOT_DE_PASSE, role=Utilisateur.Role.OPERATEUR, is_staff=True,
        )
        AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

        concours = Concours.objects.create(
            mission=mission, nom="Concours démo", edition=str(date.today().year),
            date_debut=date.today(), date_fin=date.today(),
        )
        services_concours.definir_version_corpus(concours, version)
        categorie = Categorie.objects.create(concours=concours, nom="Juniors")
        epreuve = Epreuve.objects.create(
            categorie=categorie, nom="Mémorisation", ordre=1, questions_par_serie=2,
            etat=Epreuve.Etat.EN_PREPARATION,
        )
        CritereNotation.objects.create(epreuve=epreuve, libelle="Mémorisation", ordre=1, maximum=10)
        CritereNotation.objects.create(epreuve=epreuve, libelle="Tajwid", ordre=2, maximum=10)

        participations = []
        for i in range(NOMBRE_CANDIDATS):
            candidat = Candidat.objects.create(
                organisation=organisation, nom=NOMS[i], prenom=PRENOMS[i],
                date_naissance=date(1990 + i, 5, 1), ville="Abidjan",
            )
            participation = inscrire(candidat, categorie)
            participation.statut = Participation.Statut.ADMIS
            participation.save(update_fields=["statut", "modifie_le"])
            participations.append(participation)

        lot = services_questions.obtenir_lot(epreuve)
        questions = [
            services_questions.creer_question_passage(organisation, version, debut, fin)
            for debut, fin in PASSAGES
        ]
        for i in range(0, len(questions), 2):
            services_questions.composer_serie(lot, questions[i : i + 2])

        services_concours.valider_configuration(concours, responsable)
        services_concours.ouvrir_concours(concours)
        services_concours.demarrer_concours(concours)
        services_prestations.ouvrir_epreuve(epreuve)

        session = Session.objects.create(concours=concours, nom="Session 1", date=date.today(), lieu="Salle principale")
        terminal, jeton = terminaux.creer_terminal(session, "Tablette 1")
        for rang, participation in enumerate(participations, start=1):
            Prestation.objects.create(participation=participation, epreuve=epreuve, session=session, rang_passage=rang)
        return {"terminal": terminal, "jeton": jeton, "concours": concours}

    def _afficher(self, resultat):
        self.stdout.write(self.style.SUCCESS("Démonstration prête."))
        self.stdout.write(f"  Comptes : « operateur » et « responsable » (mot de passe : {MOT_DE_PASSE}).")
        self.stdout.write(f"  Concours : {resultat['concours']} (en cours, épreuve ouverte, {NOMBRE_CANDIDATS} candidats admis).")
        self.stdout.write("  Écran de tirage, à ouvrir sur la tablette (jeton affiché une seule fois) :")
        self.stdout.write(self.style.WARNING(f"    http://127.0.0.1:8000/tirage/#{resultat['jeton']}"))
        self.stdout.write("  Ensuite : /admin/ → Prestations → cocher une prestation → « Appeler au tirage ».")
