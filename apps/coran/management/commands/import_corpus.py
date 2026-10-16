"""Commande : importe le corpus coranique depuis les fichiers Tanzil (§12.2)."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.coran.exceptions import CorpusDejaImporteError, CorpusInvalideError
from apps.coran.importation import importer_corpus, lire_corpus

DOSSIER_CORPUS = Path(settings.BASE_DIR) / "data" / "corpus"


class Command(BaseCommand):
    help = (
        "Importe le corpus coranique Tanzil en base, dans une version « importée ». "
        "Le texte est repris tel quel, sans aucune transformation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "fichier_texte",
            nargs="?",
            default=str(DOSSIER_CORPUS / "quran-uthmani.xml"),
            help="Fichier texte Tanzil (défaut : data/corpus/quran-uthmani.xml).",
        )
        parser.add_argument(
            "fichier_metadonnees",
            nargs="?",
            default=str(DOSSIER_CORPUS / "quran-data.xml"),
            help="Fichier de métadonnées Tanzil (défaut : data/corpus/quran-data.xml).",
        )
        parser.add_argument(
            "--version-source",
            help="Version Tanzil (sinon lue dans l'en-tête du fichier texte).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lance la lecture et les contrôles, puis annule sans rien enregistrer.",
        )

    def handle(self, *args, **options):
        for chemin in (options["fichier_texte"], options["fichier_metadonnees"]):
            if not Path(chemin).is_file():
                raise CommandError(f"Fichier introuvable : {chemin}")

        try:
            corpus = lire_corpus(
                options["fichier_texte"],
                options["fichier_metadonnees"],
                version_source=options["version_source"],
            )
            with transaction.atomic():
                version = importer_corpus(corpus)
                if options["dry_run"]:
                    transaction.set_rollback(True)
        except (CorpusInvalideError, CorpusDejaImporteError, IntegrityError) as erreur:
            raise CommandError(str(erreur)) from erreur

        nombre_versets = sum(len(s.versets) for s in corpus.sourates)
        resume = (
            f"{len(corpus.sourates)} sourates, {nombre_versets} versets, "
            f"version Tanzil {corpus.version_source}, empreinte SHA-256 {corpus.empreinte_sha256}."
        )
        if options["dry_run"]:
            self.stdout.write(f"Simulation réussie : {resume} Rien n'a été enregistré.")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Version n° {version.pk} importée (statut « importée ») : {resume}")
            )
