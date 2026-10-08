"""Modèles du corpus coranique (cf. §12 et §14 du cahier des charges).

Le texte coranique vient uniquement du fichier Tanzil importé : il n'est jamais
saisi, corrigé ni normalisé depuis l'application (règle absolue n°1).
"""
from django.db import models
from django.db.models import Q

from apps.coran import services


class VersionCorpus(models.Model):
    """Une version identifiée du corpus : source, empreinte, statut (§12.3).

    Une fois validée, une version est immuable (RM-27) : toute correction
    donne lieu à une nouvelle version, jamais à une modification de l'ancienne.
    """

    class Riwaya(models.TextChoices):
        HAFS = "hafs", "Hafs ʿan ʿĀṣim"

    class Statut(models.TextChoices):
        IMPORTEE = "importee", "Importée"
        VALIDEE = "validee", "Validée"
        ACTIVE = "active", "Active"
        RETIREE = "retiree", "Retirée"

    source = models.CharField(max_length=100, default="Tanzil")
    version_source = models.CharField(
        max_length=50,
        help_text="Version indiquée dans l'en-tête du fichier Tanzil.",
    )
    riwaya = models.CharField(
        max_length=20, choices=Riwaya.choices, default=Riwaya.HAFS
    )
    nom_fichier = models.CharField(max_length=255)
    empreinte_sha256 = models.CharField(
        max_length=64,
        unique=True,
        help_text="Empreinte SHA-256 du fichier source (64 caractères hexadécimaux).",
    )
    date_import = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.IMPORTEE
    )
    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date du procès-verbal de validation du référent coranique.",
    )

    class Meta:
        verbose_name = "version du corpus"
        verbose_name_plural = "versions du corpus"
        ordering = ["-date_import"]
        constraints = [
            # Au plus une version active par riwāya (§12.3 : activation pour
            # les nouveaux concours ; les anciens gardent leur version).
            models.UniqueConstraint(
                fields=["riwaya"],
                condition=Q(statut="active"),
                name="une_seule_version_active_par_riwaya",
            ),
            # SHA-256 = 64 caractères hexadécimaux en minuscules.
            models.CheckConstraint(
                condition=Q(empreinte_sha256__regex=r"^[0-9a-f]{64}$"),
                name="empreinte_sha256_valide",
            ),
        ]

    def __str__(self):
        return f"{self.source} {self.version_source} ({self.get_riwaya_display()}) — {self.get_statut_display()}"

    # Champs qui identifient le fichier source : ils ne changent plus une fois la version figée.
    CHAMPS_FIGES = (
        "source",
        "version_source",
        "riwaya",
        "nom_fichier",
        "empreinte_sha256",
        "date_import",
        "date_validation",
    )

    def save(self, *args, **kwargs):
        # On compare à l'état RÉEL en base, jamais à l'objet en mémoire (il peut être périmé).
        ancien = VersionCorpus.objects.filter(pk=self.pk).first() if self.pk else None
        if ancien is not None:
            if ancien.statut != self.statut:
                services.verifier_transition_statut(
                    ancien.statut, self.statut, self.date_validation
                )
            if any(getattr(ancien, c) != getattr(self, c) for c in self.CHAMPS_FIGES):
                services.verifier_ecriture_autorisee(ancien.statut)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        statut = (
            VersionCorpus.objects.filter(pk=self.pk).values_list("statut", flat=True).first()
        )
        if statut is not None:
            services.verifier_ecriture_autorisee(statut)
        return super().delete(*args, **kwargs)


def _verifier_versions_modifiables(version_ids):
    """Vérifie, sur l'état réel en base, que toutes ces versions acceptent des écritures."""
    statuts = VersionCorpus.objects.filter(pk__in=version_ids).values_list(
        "statut", flat=True
    )
    for statut in statuts:
        services.verifier_ecriture_autorisee(statut)


def _verifier_sourates_modifiables(sourate_ids):
    """Même vérification, à partir des sourates (donc des versions dont elles dépendent)."""
    version_ids = Sourate.objects.filter(pk__in=sourate_ids).values_list(
        "version_id", flat=True
    )
    _verifier_versions_modifiables(set(version_ids))


class Sourate(models.Model):
    """Une sourate d'une version du corpus, avec ses métadonnées Tanzil (§12.1, §12.4).

    Les valeurs viennent des fichiers Tanzil importés ; elles ne sont jamais
    saisies à la main. Le contenu d'une version validée est immuable (RM-27).
    """

    class TypeRevelation(models.TextChoices):
        MECQUOISE = "mecquoise", "Mecquoise"
        MEDINOISE = "medinoise", "Médinoise"

    # PROTECT : supprimer une version ne doit jamais emporter ses sourates.
    version = models.ForeignKey(
        VersionCorpus, on_delete=models.PROTECT, related_name="sourates"
    )
    numero = models.PositiveSmallIntegerField(help_text="Numéro de 1 à 114.")
    nom_arabe = models.CharField(max_length=100)
    nom_translitteration = models.CharField(
        max_length=100,
        help_text="Translittération de Tanzil (la forme française usuelle sera validée par le référent).",
    )
    nombre_versets = models.PositiveSmallIntegerField(
        help_text="Nombre de versets déclaré par les métadonnées Tanzil."
    )
    type_revelation = models.CharField(max_length=20, choices=TypeRevelation.choices)
    ordre_revelation = models.PositiveSmallIntegerField(
        help_text="Rang dans l'ordre de révélation, de 1 à 114."
    )
    basmala = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Basmala de tête, reprise telle quelle de l'attribut « bismillah » "
            "du verset 1. Vide pour les sourates 1 et 9 (§12.4)."
        ),
    )

    class Meta:
        verbose_name = "sourate"
        verbose_name_plural = "sourates"
        ordering = ["version", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "numero"], name="sourate_numero_unique_par_version"
            ),
            models.UniqueConstraint(
                fields=["version", "ordre_revelation"],
                name="sourate_ordre_revelation_unique_par_version",
            ),
            models.CheckConstraint(
                condition=Q(numero__range=(1, 114)), name="sourate_numero_entre_1_et_114"
            ),
            models.CheckConstraint(
                condition=Q(ordre_revelation__range=(1, 114)),
                name="sourate_ordre_revelation_entre_1_et_114",
            ),
            models.CheckConstraint(
                condition=Q(nombre_versets__gte=1),
                name="sourate_au_moins_un_verset",
            ),
            # §12.4 : pas de basmala séparée pour la sourate 1 (c'est le verset 1:1)
            # ni pour la sourate 9 (qui n'en comporte pas).
            models.CheckConstraint(
                condition=~Q(numero__in=[1, 9]) | Q(basmala=""),
                name="sourates_1_et_9_sans_basmala",
            ),
        ]

    def __str__(self):
        return f"{self.numero}. {self.nom_translitteration}"

    def save(self, *args, **kwargs):
        # Version actuelle ET version précédente en base (si on déplace la sourate).
        version_ids = {self.version_id}
        if self.pk:
            ancienne = (
                Sourate.objects.filter(pk=self.pk).values_list("version_id", flat=True).first()
            )
            if ancienne is not None:
                version_ids.add(ancienne)
        _verifier_versions_modifiables(version_ids)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        version_id = (
            Sourate.objects.filter(pk=self.pk).values_list("version_id", flat=True).first()
        )
        if version_id is not None:
            _verifier_versions_modifiables({version_id})
        return super().delete(*args, **kwargs)


class Verset(models.Model):
    """Un verset d'une sourate : son texte exact, tel que fourni par Tanzil (§12.2).

    Règle absolue n°1 : le texte n'est jamais saisi, corrigé ni normalisé
    (aucune normalisation Unicode, aucune suppression de diacritiques).
    Il est stocké tel quel, en UTF-8, et sa version est celle de sa sourate.
    """

    # PROTECT : supprimer une sourate ne doit jamais emporter ses versets.
    sourate = models.ForeignKey(
        Sourate, on_delete=models.PROTECT, related_name="versets"
    )
    numero = models.PositiveSmallIntegerField(
        help_text="Numéro du verset dans sa sourate, à partir de 1."
    )
    texte = models.TextField(
        help_text="Texte exact du verset, repris du fichier Tanzil sans aucune transformation."
    )

    class Meta:
        verbose_name = "verset"
        verbose_name_plural = "versets"
        # Ordre canonique : numéro de sourate, puis numéro de verset.
        ordering = ["sourate__numero", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["sourate", "numero"], name="verset_numero_unique_par_sourate"
            ),
            models.CheckConstraint(
                condition=Q(numero__gte=1), name="verset_numero_au_moins_1"
            ),
            # REC-30 : aucun verset vide (au moins un caractère non blanc).
            models.CheckConstraint(
                condition=Q(texte__regex=r"\S"), name="verset_texte_non_vide"
            ),
        ]

    @property
    def reference(self):
        """Référence « sourate:verset » (ex. 2:255), cf. §12.4."""
        return f"{self.sourate.numero}:{self.numero}"

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        # Sourate actuelle ET sourate précédente en base (si on déplace le verset).
        sourate_ids = {self.sourate_id}
        if self.pk:
            ancienne = (
                Verset.objects.filter(pk=self.pk).values_list("sourate_id", flat=True).first()
            )
            if ancienne is not None:
                sourate_ids.add(ancienne)
        _verifier_sourates_modifiables(sourate_ids)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        sourate_id = (
            Verset.objects.filter(pk=self.pk).values_list("sourate_id", flat=True).first()
        )
        if sourate_id is not None:
            _verifier_sourates_modifiables({sourate_id})
        return super().delete(*args, **kwargs)
