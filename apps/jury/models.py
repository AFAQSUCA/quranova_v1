"""Jurés, affectations aux épreuves et codes d'accès de session (§7.4, §14.1).

Les jurés n'ont PAS de compte Django (D4) : ils se connectent sur leur tablette avec un
code personnel à usage limité à la session, généré par l'opérateur. Aucune adresse
électronique n'est exigée.
"""
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient


class Jure(ModeleDuClient):
    """Un juré désigné par le client (RM-04)."""

    class Role(models.TextChoices):
        PRESIDENT = "president", "Président du jury"
        MEMBRE = "membre", "Membre du jury"

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBRE)
    competences = models.CharField(
        max_length=200, blank=True, help_text="Catégories ou disciplines de compétence (information)."
    )
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "juré"
        verbose_name_plural = "jurés"
        ordering = ["nom", "prenom"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "nom", "prenom"], name="jure_nom_prenom_uniques_par_organisation"
            ),
        ]

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return self.nom_complet


class AffectationJury(ModeleDuClient):
    """Un juré est affecté à une épreuve : il ne note que les prestations de ses épreuves (§6.3).

    D5 : l'affectation est toujours au niveau de l'épreuve. « Affecter à tout le concours » ou
    « à une catégorie » crée simplement une ligne par épreuve (cf. services.affecter).
    """

    PARENTS_CLIENT = ("jure", "epreuve")

    jure = models.ForeignKey(Jure, on_delete=models.PROTECT, related_name="affectations")
    epreuve = models.ForeignKey(
        "concours.Epreuve", on_delete=models.PROTECT, related_name="affectations_jury"
    )

    class Meta:
        verbose_name = "affectation de juré"
        verbose_name_plural = "affectations de jurés"
        constraints = [
            models.UniqueConstraint(fields=["jure", "epreuve"], name="affectation_jury_unique"),
        ]

    def __str__(self):
        return f"{self.jure} — {self.epreuve}"


class CodeAccesJure(ModeleDuClient):
    """Code d'accès d'un juré à une session. Seule son EMPREINTE est stockée, jamais le code (D4).

    Ce modèle vit dans l'application ``jury`` et non dans ``utilisateurs`` (comme le suggère le §13.8) :
    ``concours`` dépend déjà de ``utilisateurs`` ; l'inverse créerait une dépendance circulaire.
    """

    PARENTS_CLIENT = ("jure", "session")

    jure = models.ForeignKey(Jure, on_delete=models.PROTECT, related_name="codes")
    session = models.ForeignKey(
        "concours.Session", on_delete=models.PROTECT, related_name="codes_jures"
    )
    empreinte = models.CharField(max_length=64, unique=True, help_text="HMAC-SHA256 du code.")
    valide_du = models.DateTimeField()
    valide_jusqu_au = models.DateTimeField()
    revoque_le = models.DateTimeField(null=True, blank=True)
    derniere_utilisation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "code d'accès de juré"
        verbose_name_plural = "codes d'accès de jurés"
        ordering = ["-valide_du"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valide_jusqu_au__gt=F("valide_du")), name="code_jure_fin_apres_debut"
            ),
            # Un seul code actif par juré et par session ; les codes révoqués restent (traçabilité).
            models.UniqueConstraint(
                fields=["jure", "session"],
                condition=Q(revoque_le__isnull=True),
                name="code_jure_un_seul_actif",
            ),
        ]

    def __str__(self):
        return f"Code de {self.jure} pour {self.session}"


class Evaluation(ModeleDuClient):
    """L'évaluation d'une prestation par UN juré : brouillon, puis validée (§10.2, RM-15 ; D43).

    Les notes sont enregistrées séparément par juré. Une évaluation validée ne change plus que par une
    correction approuvée (``CorrectionNote``).
    """

    PARENTS_CLIENT = ("jure", "prestation")

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDEE = "validee", "Validée"

    jure = models.ForeignKey(Jure, on_delete=models.PROTECT, related_name="evaluations")
    prestation = models.ForeignKey("prestations.Prestation", on_delete=models.PROTECT, related_name="evaluations")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    observation = models.TextField(blank=True)
    validee_le = models.DateTimeField(null=True, blank=True)
    # D43 : libellés des séries évaluées, figés à la validation (REC-11 : « le bon tirage »).
    series_evaluees = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "évaluation"
        verbose_name_plural = "évaluations"
        ordering = ["prestation", "jure"]
        constraints = [
            models.UniqueConstraint(fields=["jure", "prestation"], name="evaluation_unique_par_jure_et_prestation"),
            models.CheckConstraint(
                condition=(Q(statut="brouillon", validee_le__isnull=True) | Q(statut="validee", validee_le__isnull=False)),
                name="evaluation_validee_a_une_date",
            ),
        ]

    def __str__(self):
        return f"Évaluation de {self.jure} ({self.get_statut_display()})"


class Note(ModeleDuClient):
    """La valeur d'un critère dans une évaluation.

    RM-16 : une note MANQUANTE n'a pas de ligne ; un ZÉRO est une ligne à 0. On ne confond jamais les deux.
    """

    PARENTS_CLIENT = ("evaluation", "critere")

    evaluation = models.ForeignKey(Evaluation, on_delete=models.PROTECT, related_name="notes")
    critere = models.ForeignKey("concours.CritereNotation", on_delete=models.PROTECT, related_name="notes")
    valeur = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        verbose_name = "note"
        verbose_name_plural = "notes"
        ordering = ["evaluation", "critere__ordre"]
        constraints = [
            models.UniqueConstraint(fields=["evaluation", "critere"], name="note_unique_par_critere"),
            models.CheckConstraint(condition=Q(valeur__gte=0), name="note_positive_ou_nulle"),
        ]

    def __str__(self):
        return f"{self.critere} : {self.valeur}"


class CorrectionNote(ModeleDuClient):
    """Demande motivée de correction d'une note validée, approuvée par le responsable client (§10.2, REC-17).

    Conserve l'ancienne valeur, la nouvelle, l'auteur (le juré), l'approbateur, les dates et le motif.
    """

    PARENTS_CLIENT = ("evaluation", "critere")

    class Statut(models.TextChoices):
        DEMANDEE = "demandee", "Demandée"
        APPROUVEE = "approuvee", "Approuvée"
        REFUSEE = "refusee", "Refusée"

    evaluation = models.ForeignKey(Evaluation, on_delete=models.PROTECT, related_name="corrections")
    critere = models.ForeignKey("concours.CritereNotation", on_delete=models.PROTECT, related_name="+")
    ancienne_valeur = models.DecimalField(max_digits=6, decimal_places=2)
    nouvelle_valeur = models.DecimalField(max_digits=6, decimal_places=2)
    motif = models.TextField()
    demandee_le = models.DateTimeField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.DEMANDEE)
    traitee_par = models.ForeignKey("utilisateurs.Utilisateur", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    traitee_le = models.DateTimeField(null=True, blank=True)
    commentaire_decision = models.TextField(blank=True)

    class Meta:
        verbose_name = "correction de note"
        verbose_name_plural = "corrections de notes"
        ordering = ["demandee_le"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(statut="demandee", traitee_par__isnull=True, traitee_le__isnull=True)
                    | (~Q(statut="demandee") & Q(traitee_par__isnull=False, traitee_le__isnull=False))
                ),
                name="correction_traitee_a_un_auteur_et_une_date",
            ),
            models.UniqueConstraint(
                fields=["evaluation", "critere"], condition=Q(statut="demandee"), name="correction_une_en_attente_par_note"
            ),
        ]

    def __str__(self):
        return f"Correction {self.critere} : {self.ancienne_valeur} → {self.nouvelle_valeur} ({self.get_statut_display()})"


class ConnexionJure(ModeleDuClient):
    """Une tablette de juré connectée : un jeton long (D46), échangé contre le code court, valable autant que lui.

    Seule l'empreinte du jeton est stockée. Le jeton sert à l'API de notation et au WebSocket du diaporama.
    """

    PARENTS_CLIENT = ("acces",)

    acces = models.ForeignKey(CodeAccesJure, on_delete=models.PROTECT, related_name="connexions")
    empreinte = models.CharField(max_length=64, unique=True)
    valide_jusqu_au = models.DateTimeField()
    revoque_le = models.DateTimeField(null=True, blank=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)
    adresse = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "connexion de juré"
        verbose_name_plural = "connexions de jurés"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Connexion de {self.acces.jure}"


class TentativeCode(ModeleDuClient):
    """Un essai de code (réussi ou non), pour limiter les essais d'une même adresse (D5)."""

    PARENTS_CLIENT = ("session",)

    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="+")
    adresse = models.CharField(max_length=64)
    reussie = models.BooleanField()

    class Meta:
        verbose_name = "tentative de code"
        verbose_name_plural = "tentatives de code"
        indexes = [models.Index(fields=["adresse", "cree_le"])]
