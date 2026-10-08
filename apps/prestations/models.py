"""Prestations (passage d'un candidat) et tirages (§8.3, §8.5, §14.1, §14.2)."""
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient
from apps.prestations.exceptions import PrestationInvalideError, TirageInvalideError


class Prestation(ModeleDuClient):
    """Le passage d'un candidat à une épreuve, dans une session (glossaire : « prestation »)."""

    PARENTS_CLIENT = ("participation", "epreuve", "session")

    class Etat(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        TIRE = "tire", "Tiré"
        EN_AFFICHAGE = "en_affichage", "En affichage"
        EN_PAUSE = "en_pause", "En pause"
        EN_NOTATION = "en_notation", "En notation"
        CLOTUREE = "cloturee", "Clôturée"
        ANNULEE = "annulee", "Annulée"

    participation = models.ForeignKey(
        "candidats.Participation", on_delete=models.PROTECT, related_name="prestations"
    )
    epreuve = models.ForeignKey("concours.Epreuve", on_delete=models.PROTECT, related_name="prestations")
    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="prestations")
    rang_passage = models.PositiveIntegerField(help_text="Rang dans l'ordre de passage de la session.")
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.EN_ATTENTE)

    class Meta:
        verbose_name = "prestation"
        verbose_name_plural = "prestations"
        ordering = ["session", "epreuve", "rang_passage"]
        constraints = [
            models.UniqueConstraint(
                fields=["participation", "epreuve"], name="prestation_unique_par_participation_et_epreuve"
            ),
            models.UniqueConstraint(
                fields=["session", "epreuve", "rang_passage"], name="prestation_rang_unique_par_session_et_epreuve"
            ),
            models.CheckConstraint(condition=Q(rang_passage__gte=1), name="prestation_rang_au_moins_1"),
        ]

    def save(self, *args, **kwargs):
        self.verifier_organisation()  # RM-20 d'abord : un autre client est une faute plus grave
        participation, epreuve, session = self.participation, self.epreuve, self.session
        if participation.categorie_id != epreuve.categorie_id:
            raise PrestationInvalideError("L'épreuve n'appartient pas à la catégorie de la participation.")
        if session.concours_id != participation.concours_id:
            raise PrestationInvalideError("La session n'appartient pas au concours de la participation.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Passage {self.rang_passage} — {self.participation.candidat}"


class Tirage(ModeleDuClient):
    """Une série attribuée à une prestation (§8.5). Jamais supprimé, jamais remplacé en silence.

    Un tirage annulé garde sa trace (motif, auteur, date) : il passe à l'état « annulé ».
    """

    PARENTS_CLIENT = ("prestation", "serie")

    class Statut(models.TextChoices):
        VALIDE = "valide", "Valide"
        ANNULE = "annule", "Annulé"

    prestation = models.ForeignKey(Prestation, on_delete=models.PROTECT, related_name="tirages")
    serie = models.ForeignKey("questions.Serie", on_delete=models.PROTECT, related_name="tirages")
    rang = models.PositiveSmallIntegerField(help_text="1 à T : numéro du tirage pour cette prestation.")
    # Identifiant unique de la demande : un second envoi (double clic, REC-07) renvoie ce tirage.
    id_demande = models.UUIDField(unique=True)
    terminal = models.CharField(max_length=100, blank=True, help_text="Terminal déclencheur.")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.VALIDE)
    motif_annulation = models.TextField(blank=True)
    annule_par = models.ForeignKey(
        "utilisateurs.Utilisateur", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    annule_le = models.DateTimeField(null=True, blank=True)
    # RM-25 : renseigné par le diaporama (itération 3) dès qu'une diapositive de la série est affichée.
    diapositive_affichee = models.BooleanField(default=False)

    class Meta:
        verbose_name = "tirage"
        verbose_name_plural = "tirages"
        ordering = ["prestation", "rang", "cree_le"]
        constraints = [
            models.UniqueConstraint(
                fields=["prestation", "rang"], condition=Q(statut="valide"), name="tirage_rang_valide_unique"
            ),
            # Jamais deux fois la même série pour un candidat dans une épreuve (RM-21).
            models.UniqueConstraint(
                fields=["prestation", "serie"], condition=Q(statut="valide"), name="tirage_serie_valide_unique"
            ),
            models.CheckConstraint(condition=Q(rang__gte=1), name="tirage_rang_au_moins_1"),
            models.CheckConstraint(
                condition=(
                    Q(statut="valide", annule_le__isnull=True, annule_par__isnull=True, motif_annulation="")
                    | (
                        Q(statut="annule", annule_le__isnull=False, annule_par__isnull=False)
                        & ~Q(motif_annulation="")
                    )
                ),
                name="tirage_annulation_coherente",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.serie.lot.epreuve_id != self.prestation.epreuve_id:
            raise TirageInvalideError("La série tirée n'appartient pas au lot de l'épreuve de la prestation.")
        if not self._state.adding:
            avant = Tirage.objects.filter(pk=self.pk).values("prestation_id", "serie_id", "rang", "id_demande").first()
            apres = {"prestation_id": self.prestation_id, "serie_id": self.serie_id, "rang": self.rang, "id_demande": self.id_demande}
            if avant != apres:
                raise TirageInvalideError("Un tirage enregistré ne peut pas être remplacé : annulez-le puis recommencez.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TirageInvalideError("Un tirage n'est jamais supprimé : il passe à l'état « annulé » (RM-25).")

    def __str__(self):
        return f"Tirage {self.rang} de {self.prestation} : {self.serie}"


class TerminalTirage(ModeleDuClient):
    """Une tablette de tirage, ouverte en mode kiosque par l'opérateur (§15.1, §8.6).

    Le terminal s'authentifie par un jeton secret (D31) dont seule l'empreinte est stockée.
    Le candidat appelé est FIXÉ PAR L'OPÉRATEUR (``prestation_appelee``) : le candidat ne choisit
    jamais son identité, et le client n'envoie jamais d'identifiant de prestation (REC-25).
    """

    PARENTS_CLIENT = ("session",)

    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="terminaux_tirage")
    nom = models.CharField(max_length=100)
    empreinte = models.CharField(max_length=64, unique=True)
    prestation_appelee = models.ForeignKey(
        Prestation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revoque_le = models.DateTimeField(null=True, blank=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "terminal de tirage"
        verbose_name_plural = "terminaux de tirage"
        ordering = ["session", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["session", "nom"], name="terminal_nom_unique_par_session"),
        ]

    def save(self, *args, **kwargs):
        self.verifier_organisation()
        if self.prestation_appelee_id is not None and self.prestation_appelee.session_id != self.session_id:
            raise PrestationInvalideError("La prestation appelée n'appartient pas à la session du terminal.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} ({self.session})"
