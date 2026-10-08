"""Classes de base des modèles du projet.

- ``ModeleHorodate`` : clé primaire UUID (identifiants non devinables dans les URL, §13.4)
  et dates de création et de modification.
- ``ModeleDuClient`` : en plus, une ``organisation`` obligatoire. Toute table propre à un
  client en dérive (règle absolue n°3, RM-20).
"""
import uuid

from django.db import models

from apps.commun.exceptions import IncoherenceOrganisationError


class ModeleHorodate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ClientQuerySet(models.QuerySet):
    def pour_organisation(self, organisation):
        """Filtre par client : à utiliser dans toute requête qui sert un utilisateur (RM-20)."""
        return self.filter(organisation=organisation)


class ModeleDuClient(ModeleHorodate):
    """Base de toute table propre à un client.

    ``PARENTS_CLIENT`` liste les clés étrangères vers des parents qui ont eux-mêmes une
    organisation (par exemple ``("mission",)``). À l'enregistrement, l'organisation est
    recopiée du parent si elle est absente, et refusée si elle diffère.
    """

    # PROTECT : on n'efface jamais un client qui a des données.
    organisation = models.ForeignKey(
        "clients.Organisation",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    PARENTS_CLIENT = ()

    objects = ClientQuerySet.as_manager()

    class Meta:
        abstract = True

    def verifier_organisation(self):
        """Recopie l'organisation du parent si elle manque, refuse toute incohérence (RM-20)."""
        for nom in self.PARENTS_CLIENT:
            if getattr(self, f"{nom}_id") is None:
                continue
            parent = getattr(self, nom)
            if self.organisation_id is None:
                self.organisation_id = parent.organisation_id
            elif self.organisation_id != parent.organisation_id:
                raise IncoherenceOrganisationError(
                    f"{type(self).__name__} : l'organisation ({self.organisation_id}) diffère "
                    f"de celle de son parent « {nom} » ({parent.organisation_id})."
                )

    def save(self, *args, **kwargs):
        self.verifier_organisation()
        super().save(*args, **kwargs)
