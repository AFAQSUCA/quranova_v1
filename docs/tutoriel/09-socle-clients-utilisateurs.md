# Chapitre 9 — Le socle : classes de base, clients, utilisateurs et rôles

> **Étape du plan :** 1.2, premier lot · **Durée :** 3 heures · **Commit de référence :** `9299052` · **Résultat :** trois applications (`commun`, `clients`, `utilisateurs`), un utilisateur Django personnalisé avec des rôles, la séparation des clients appliquée par construction, **41 nouveaux tests**.

## Objectif

Poser les fondations de toutes les tables de la V1 :

1. **`commun`** : deux classes de base. `ModeleHorodate` (clé primaire **UUID**, dates de création et de modification) et `ModeleDuClient` (en plus, une `organisation` **obligatoire**). Toute table propre à un client en dérive : c'est la **règle absolue n°3** (séparation des clients, RM-20) appliquée *par construction*.
2. **`clients`** : `Organisation` (le client) et `Mission`.
3. **`utilisateurs`** : l'`Utilisateur` personnalisé avec ses **rôles**, et l'`AffectationOperateur` (un opérateur n'accède qu'aux missions qui lui sont affectées, §6.3).

Décisions appliquées : **D1** (utilisateur personnalisé), **D2** (UUID), **D3** (`organisation` recopiée partout, avec test de cohérence parent-enfant).

> **D1 est irréversible en pratique** : `AUTH_USER_MODEL` doit être fixé **avant** la première migration d'un projet. Votre base de développement a déjà été migrée avec l'utilisateur par défaut de Django : il faut la **recréer** (étape C). Vous perdez seulement des données de test, car le corpus se réimporte en une commande.

## Étape A — Créer les dossiers

```powershell
foreach ($a in "commun", "clients", "utilisateurs") {
    New-Item -ItemType Directory "apps\$a\tests" -Force | Out-Null
    New-Item -ItemType File "apps\$a\__init__.py", "apps\$a\tests\__init__.py" -Force | Out-Null
}
```

## Étape B — Les réglages

Dans `config\settings\base.py` :

1. Dans `INSTALLED_APPS`, remplacez `"apps.coran",` par les quatre applications (l'ordre n'a pas d'importance fonctionnelle, mais celui-ci est lisible) :

```python
    "channels",
    "apps.commun",
    "apps.clients",
    "apps.utilisateurs",
    "apps.coran",
]
```

2. À la fin du fichier, après `DEFAULT_AUTO_FIELD` :

```python
# Utilisateur personnalisé (rôles, organisation) : à fixer AVANT la première migration d'un projet.
AUTH_USER_MODEL = "utilisateurs.Utilisateur"

# Fichiers téléversés (logos des clients, formulaires de consentement...). Jamais versionnés.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
```

3. Ajoutez une ligne à la fin de `.gitignore` :

```text
media/
```

## Étape C — Les tests d'abord

Les tests s'appuient sur de petites fabriques :

**Fichier `apps\commun\tests\outils.py`**

```python
"""Fonctions utilitaires partagées par les tests des applications clients, utilisateurs, etc."""
import itertools
from datetime import date

from apps.clients.models import Mission, Organisation
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
```

**Les classes de base** : ce test vérifie que *toute* table client, présente ou future, respecte la règle n°3. Il s'enrichira tout seul à chaque nouveau modèle.

**Fichier `apps\commun\tests\test_modele_du_client.py`**

```python
"""Tests des classes de base : séparation des clients (règle absolue n°3, RM-20, §13.4)."""
import uuid

import pytest
from django.apps import apps
from django.db import models

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.models import ModeleDuClient, ModeleHorodate
from apps.commun.tests.outils import creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs.models import AffectationOperateur


def modeles_du_client():
    return [m for m in apps.get_models() if issubclass(m, ModeleDuClient)]


def test_il_existe_au_moins_un_modele_du_client():
    assert modeles_du_client(), "Aucun modèle ne dérive de ModeleDuClient : le test ci-dessous serait vide."


@pytest.mark.parametrize("modele", modeles_du_client(), ids=lambda m: m.__name__)
def test_regle_3_toute_table_client_a_une_organisation_obligatoire_indexee_et_protegee(modele):
    champ = modele._meta.get_field("organisation")

    assert champ.many_to_one
    assert champ.related_model._meta.label == "clients.Organisation"
    assert champ.null is False
    assert champ.db_index is True
    assert champ.remote_field.on_delete is models.PROTECT


@pytest.mark.parametrize("modele", modeles_du_client(), ids=lambda m: m.__name__)
def test_toute_table_client_a_une_cle_primaire_uuid_et_des_horodatages(modele):
    assert issubclass(modele, ModeleHorodate)
    assert isinstance(modele._meta.pk, models.UUIDField)
    assert {"cree_le", "modifie_le"} <= {f.name for f in modele._meta.get_fields()}


@pytest.mark.django_db
def test_la_cle_primaire_est_un_uuid_genere_automatiquement():
    mission = creer_mission()

    assert isinstance(mission.pk, uuid.UUID)


@pytest.mark.django_db
def test_rm20_pour_organisation_ne_renvoie_que_les_donnees_du_client():
    organisation_a, organisation_b = creer_organisation(), creer_organisation()
    mission_a = creer_mission(organisation_a)
    creer_mission(organisation_b)

    resultat = type(mission_a).objects.pour_organisation(organisation_a)

    assert list(resultat) == [mission_a]


@pytest.mark.django_db
def test_organisation_deduite_du_parent_quand_elle_est_absente():
    mission = creer_mission()
    operateur = creer_utilisateur()

    affectation = AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    assert affectation.organisation_id == mission.organisation_id


@pytest.mark.django_db
def test_organisation_incoherente_avec_le_parent_refusee():
    """Une affectation d'une mission du client A ne peut pas être rangée dans le client B."""
    mission = creer_mission()
    autre_organisation = creer_organisation()
    operateur = creer_utilisateur()

    with pytest.raises(IncoherenceOrganisationError):
        AffectationOperateur.objects.create(
            mission=mission, utilisateur=operateur, organisation=autre_organisation
        )
```

**Fichier `apps\clients\tests\test_organisation.py`**

```python
"""Tests du modèle Organisation (§7.1, §14.1)."""
import pytest
from django.db import DataError, IntegrityError, transaction
from django.db.models import ProtectedError

from apps.clients.models import Organisation
from apps.commun.tests.outils import creer_mission, creer_organisation


@pytest.mark.django_db
def test_statut_initial_est_actif():
    assert creer_organisation().statut == Organisation.Statut.ACTIF


@pytest.mark.django_db
def test_le_nom_d_une_organisation_est_unique():
    creer_organisation(nom="Association Test")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_organisation(nom="Association Test")


@pytest.mark.django_db
@pytest.mark.parametrize("couleur", ["", "#0A7B5C", "#ffffff"])
def test_couleurs_valides_acceptees(couleur):
    organisation = creer_organisation(couleur_principale=couleur, couleur_secondaire=couleur)

    assert organisation.couleur_principale == couleur


@pytest.mark.django_db
@pytest.mark.parametrize("couleur", ["rouge", "#12345", "#GGGGGG", "123456", "#1234567"])
def test_couleurs_invalides_refusees_par_la_base(couleur):
    # Trop longue : refusée par la colonne (DataError) ; mal formée : par la contrainte (IntegrityError).
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        creer_organisation(couleur_principale=couleur)


@pytest.mark.django_db
def test_une_organisation_ne_peut_pas_etre_supprimee_si_elle_a_des_missions():
    mission = creer_mission()

    with pytest.raises(ProtectedError):
        mission.organisation.delete()
```

**Fichier `apps\clients\tests\test_mission.py`**

```python
"""Tests du modèle Mission (§14.1, §22)."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.clients.models import Mission
from apps.commun.tests.outils import creer_mission


@pytest.mark.django_db
def test_statut_initial_est_en_preparation():
    assert creer_mission().statut == Mission.Statut.EN_PREPARATION


@pytest.mark.django_db
def test_une_mission_d_un_seul_jour_est_acceptee():
    mission = creer_mission(date_debut=date(2027, 1, 20), date_fin=date(2027, 1, 20))

    assert mission.date_debut == mission.date_fin


@pytest.mark.django_db
def test_la_date_de_fin_ne_peut_pas_preceder_la_date_de_debut():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_mission(date_debut=date(2027, 1, 21), date_fin=date(2027, 1, 20))
```

**Fichier `apps\utilisateurs\tests\test_utilisateur.py`**

```python
"""Tests du modèle Utilisateur personnalisé et de ses rôles (§6.1, D1)."""
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.commun.tests.outils import creer_organisation, creer_utilisateur
from apps.utilisateurs.models import Utilisateur

Role = Utilisateur.Role


def test_le_modele_utilisateur_du_projet_est_personnalise():
    assert settings.AUTH_USER_MODEL == "utilisateurs.Utilisateur"
    assert get_user_model() is Utilisateur


@pytest.mark.django_db
def test_la_cle_primaire_de_l_utilisateur_est_un_uuid():
    assert isinstance(creer_utilisateur().pk, uuid.UUID)


@pytest.mark.django_db
def test_un_responsable_client_a_une_organisation():
    organisation = creer_organisation()

    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT, organisation)

    assert responsable.organisation == organisation


@pytest.mark.django_db
def test_un_responsable_client_sans_organisation_est_refuse():
    with pytest.raises(IntegrityError), transaction.atomic():
        Utilisateur.objects.create_user(
            username="sans-organisation", password="x", role=Role.RESPONSABLE_CLIENT
        )


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.OPERATEUR, Role.ADMINISTRATEUR])
def test_un_utilisateur_du_prestataire_n_a_pas_d_organisation(role):
    assert creer_utilisateur(role).organisation is None

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_utilisateur(role, organisation=creer_organisation())


@pytest.mark.django_db
def test_le_role_par_defaut_est_operateur():
    utilisateur = Utilisateur.objects.create_user(username="par-defaut", password="x")

    assert utilisateur.role == Role.OPERATEUR


@pytest.mark.django_db
def test_un_superutilisateur_est_administrateur():
    superutilisateur = Utilisateur.objects.create_superuser(
        username="chef", email="chef@example.org", password="x"
    )

    assert superutilisateur.role == Role.ADMINISTRATEUR
    assert superutilisateur.is_superuser and superutilisateur.is_staff
```

**Fichier `apps\utilisateurs\tests\test_affectation.py`**

```python
"""Tests de l'affectation d'un opérateur à une mission (§6.3, §14.1)."""
import pytest
from django.db import IntegrityError, transaction

from apps.commun.tests.outils import creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs.exceptions import AffectationInvalideError
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

Role = Utilisateur.Role


@pytest.mark.django_db
def test_un_operateur_peut_etre_affecte_a_une_mission():
    mission, operateur = creer_mission(), creer_utilisateur(Role.OPERATEUR)

    affectation = AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    assert affectation in mission.affectations.all()


@pytest.mark.django_db
def test_un_operateur_n_est_affecte_qu_une_fois_a_une_mission():
    mission, operateur = creer_mission(), creer_utilisateur(Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    with pytest.raises(IntegrityError), transaction.atomic():
        AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.ADMINISTRATEUR, Role.RESPONSABLE_CLIENT])
def test_seul_un_operateur_peut_etre_affecte_a_une_mission(role):
    mission = creer_mission()
    utilisateur = creer_utilisateur(role, creer_organisation() if role == Role.RESPONSABLE_CLIENT else None)

    with pytest.raises(AffectationInvalideError):
        AffectationOperateur.objects.create(mission=mission, utilisateur=utilisateur)

    assert AffectationOperateur.objects.count() == 0
```

**Fichier `apps\utilisateurs\tests\test_acces_missions.py`**

```python
"""Tests des règles d'accès aux missions (§6.3, REC-29, RM-20).

Un opérateur n'accède qu'aux missions qui lui sont affectées ; un responsable client
n'accède qu'aux missions de son organisation ; l'administrateur accède à toutes.
"""
import pytest
from django.contrib.auth.models import AnonymousUser

from apps.commun.tests.outils import creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs import services
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

Role = Utilisateur.Role


@pytest.fixture
def deux_clients(db):
    """Deux clients (A et B), chacun avec une mission."""
    organisation_a, organisation_b = creer_organisation(), creer_organisation()
    return {
        "organisation_a": organisation_a,
        "organisation_b": organisation_b,
        "mission_a": creer_mission(organisation_a),
        "mission_b": creer_mission(organisation_b),
    }


def test_rec29_un_operateur_n_accede_qu_aux_missions_qui_lui_sont_affectees(deux_clients):
    operateur = creer_utilisateur(Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=deux_clients["mission_a"], utilisateur=operateur)

    accessibles = services.missions_accessibles(operateur)

    assert list(accessibles) == [deux_clients["mission_a"]]


def test_rec29_un_operateur_sans_affectation_n_accede_a_rien(deux_clients):
    assert list(services.missions_accessibles(creer_utilisateur(Role.OPERATEUR))) == []


def test_rec29_un_responsable_client_n_accede_qu_aux_missions_de_son_organisation(deux_clients):
    responsable_a = creer_utilisateur(Role.RESPONSABLE_CLIENT, deux_clients["organisation_a"])

    accessibles = services.missions_accessibles(responsable_a)

    assert list(accessibles) == [deux_clients["mission_a"]]


def test_l_administrateur_accede_a_toutes_les_missions(deux_clients):
    administrateur = creer_utilisateur(Role.ADMINISTRATEUR)

    assert set(services.missions_accessibles(administrateur)) == {
        deux_clients["mission_a"],
        deux_clients["mission_b"],
    }


def test_un_utilisateur_desactive_n_accede_a_rien(deux_clients):
    administrateur = creer_utilisateur(Role.ADMINISTRATEUR, is_active=False)

    assert list(services.missions_accessibles(administrateur)) == []


def test_un_visiteur_anonyme_n_accede_a_rien(deux_clients):
    assert list(services.missions_accessibles(AnonymousUser())) == []
```

À ce stade, `pytest apps\commun apps\clients apps\utilisateurs` échoue (modèles introuvables) : c'est normal.

## Étape D — Le code

### `commun`

**Fichier `apps\commun\apps.py`**

```python
from django.apps import AppConfig


class CommunConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.commun"
    label = "commun"
    verbose_name = "Éléments communs"
```

**Fichier `apps\commun\exceptions.py`**

```python
"""Exceptions partagées par toutes les applications."""


class IncoherenceOrganisationError(Exception):
    """L'organisation d'une donnée diffère de celle de son parent (règle absolue n°3, RM-20)."""
```

**Fichier `apps\commun\models.py`**

```python
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

    def save(self, *args, **kwargs):
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
        super().save(*args, **kwargs)
```

### `clients`

**Fichier `apps\clients\apps.py`**

```python
from django.apps import AppConfig


class ClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.clients"
    label = "clients"
    verbose_name = "Clients"
```

**Fichier `apps\clients\models.py`**

```python
"""Clients du prestataire et leurs missions (§7.1, §14.1)."""
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient, ModeleHorodate

# Une couleur est vide (aucune personnalisation) ou au format « #RRGGBB ».
FORMAT_COULEUR = r"^(#[0-9A-Fa-f]{6})?$"


class Organisation(ModeleHorodate):
    """Un client du prestataire (association, école coranique, mosquée...).

    C'est la seule table client SANS clé ``organisation`` : elle est l'organisation.
    """

    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        ARCHIVE = "archive", "Archivé"

    nom = models.CharField(max_length=200, unique=True)
    logo = models.FileField(upload_to="logos/", blank=True)
    couleur_principale = models.CharField(max_length=7, blank=True, default="")
    couleur_secondaire = models.CharField(max_length=7, blank=True, default="")
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=50, blank=True)
    courriel = models.EmailField(blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.ACTIF)

    class Meta:
        verbose_name = "organisation"
        verbose_name_plural = "organisations"
        ordering = ["nom"]
        constraints = [
            models.CheckConstraint(
                condition=Q(couleur_principale__regex=FORMAT_COULEUR),
                name="organisation_couleur_principale_valide",
            ),
            models.CheckConstraint(
                condition=Q(couleur_secondaire__regex=FORMAT_COULEUR),
                name="organisation_couleur_secondaire_valide",
            ),
        ]

    def __str__(self):
        return self.nom


class Mission(ModeleDuClient):
    """Une prestation du prestataire chez un client : lieu, dates, formule (§14.1, §22)."""

    class Statut(models.TextChoices):
        EN_PREPARATION = "en_preparation", "En préparation"
        EN_COURS = "en_cours", "En cours"
        TERMINEE = "terminee", "Terminée"
        ARCHIVEE = "archivee", "Archivée"

    nom = models.CharField(max_length=200)
    lieu = models.CharField(max_length=200)
    date_debut = models.DateField()
    date_fin = models.DateField()
    formule = models.CharField(max_length=100, blank=True, help_text="Formule commerciale retenue.")
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.EN_PREPARATION
    )

    class Meta:
        verbose_name = "mission"
        verbose_name_plural = "missions"
        ordering = ["-date_debut"]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="mission_date_fin_apres_date_debut",
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.organisation})"
```

### `utilisateurs`

**Fichier `apps\utilisateurs\apps.py`**

```python
from django.apps import AppConfig


class UtilisateursConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.utilisateurs"
    label = "utilisateurs"
    verbose_name = "Utilisateurs"
```

**Fichier `apps\utilisateurs\exceptions.py`**

```python
"""Exceptions de l'application utilisateurs."""


class AffectationInvalideError(Exception):
    """Une affectation d'opérateur à une mission viole une règle d'accès (§6.3)."""
```

**Fichier `apps\utilisateurs\models.py`**

```python
"""Comptes du prestataire et du client, et affectation des opérateurs aux missions (§6, §14.1).

Les jurés n'ont PAS de compte : ils se connectent par un code de session (§7.4).
"""
import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient
from apps.utilisateurs.exceptions import AffectationInvalideError


class GestionnaireUtilisateur(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Un superutilisateur Django est l'administrateur QURANOVA.
        extra_fields.setdefault("role", self.model.Role.ADMINISTRATEUR)
        return super().create_superuser(username, email, password, **extra_fields)


class Utilisateur(AbstractUser):
    """Compte nominatif : administrateur ou opérateur (prestataire), responsable client."""

    class Role(models.TextChoices):
        ADMINISTRATEUR = "administrateur", "Administrateur QURANOVA"
        OPERATEUR = "operateur", "Opérateur"
        RESPONSABLE_CLIENT = "responsable_client", "Responsable client"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.OPERATEUR)
    # Renseignée pour un responsable client, vide pour le personnel du prestataire.
    organisation = models.ForeignKey(
        "clients.Organisation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="utilisateurs",
    )

    objects = GestionnaireUtilisateur()

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        constraints = [
            # Un responsable client appartient à un client ; le personnel du prestataire à aucun.
            models.CheckConstraint(
                condition=(
                    Q(role="responsable_client", organisation__isnull=False)
                    | (~Q(role="responsable_client") & Q(organisation__isnull=True))
                ),
                name="utilisateur_role_et_organisation_coherents",
            ),
        ]


class AffectationOperateur(ModeleDuClient):
    """Un opérateur est affecté à une mission : il n'accède qu'aux missions affectées (§6.3)."""

    PARENTS_CLIENT = ("mission",)

    mission = models.ForeignKey(
        "clients.Mission", on_delete=models.PROTECT, related_name="affectations"
    )
    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="affectations"
    )

    class Meta:
        verbose_name = "affectation d'opérateur"
        verbose_name_plural = "affectations d'opérateurs"
        constraints = [
            models.UniqueConstraint(
                fields=["mission", "utilisateur"], name="affectation_unique_par_mission"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.utilisateur.role != Utilisateur.Role.OPERATEUR:
            raise AffectationInvalideError(
                f"Seul un opérateur peut être affecté à une mission (rôle : {self.utilisateur.role})."
            )
        super().save(*args, **kwargs)
```

**Fichier `apps\utilisateurs\services.py`**

```python
"""Règles d'accès aux données selon le rôle (§6.3, REC-29, RM-20)."""
from apps.clients.models import Mission
from apps.utilisateurs.models import Utilisateur


def missions_accessibles(utilisateur):
    """Renvoie les missions auxquelles ``utilisateur`` a le droit d'accéder.

    - administrateur : toutes (chaque accès devra être journalisé, cf. audit) ;
    - responsable client : celles de son organisation ;
    - opérateur : celles qui lui sont affectées ;
    - utilisateur désactivé ou anonyme : aucune.
    """
    if not getattr(utilisateur, "is_authenticated", False) or not utilisateur.is_active:
        return Mission.objects.none()
    if utilisateur.role == Utilisateur.Role.ADMINISTRATEUR:
        return Mission.objects.all()
    if utilisateur.role == Utilisateur.Role.RESPONSABLE_CLIENT:
        return Mission.objects.pour_organisation(utilisateur.organisation)
    if utilisateur.role == Utilisateur.Role.OPERATEUR:
        return Mission.objects.filter(affectations__utilisateur=utilisateur)
    return Mission.objects.none()
```

## Étape E — Migrations et recréation de la base de développement

Créez les migrations **d'abord** (la base actuelle est encore celle d'avant) :

```powershell
python manage.py makemigrations clients utilisateurs
```

Attendu : `clients\migrations\0001_initial.py` (`Organisation`, `Mission`) et `utilisateurs\migrations\0001_initial.py` (`Utilisateur`, `AffectationOperateur`, contraintes).

Puis recréez la base de développement. Si vous essayez `migrate` sans le faire, Django répond `InconsistentMigrationHistory: Migration admin.0001_initial is applied before its dependency utilisateurs.0001_initial` : l'administration a déjà été installée avec l'ancien utilisateur.

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
& $psql -U postgres -c "DROP DATABASE quranova;"
& $psql -U postgres -c "CREATE DATABASE quranova OWNER quranova;"
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py import_corpus
python manage.py createsuperuser
```

Attendu : `migrate` applique toutes les migrations, `No changes detected`, l'import du corpus réussit (si vous avez écrit `controler_corpus`, sinon il passe sans contrôle), et `createsuperuser` crée un compte dont le rôle est **administrateur** (le gestionnaire `GestionnaireUtilisateur` s'en charge).

## Étape F — Vérifier

```powershell
python manage.py check
pytest apps\commun apps\clients apps\utilisateurs
pytest
```

Attendu :

- les trois applications : **41 passed** ;
- la suite complète : **161 passed, 66 failed** si vous n'avez pas écrit les règles des chapitres 4, 6 et 7, et **227 passed** si vous les avez toutes écrites.

## Étape G — Commit

```powershell
git add apps config\settings\base.py .gitignore
git status
git commit -m "Socle : classes de base, clients, utilisateurs et rôles"
```

Vérifiez que `.env`, `.venv` et `media\` n'apparaissent pas.

## Pour comprendre

### `ModeleDuClient` : la séparation des clients par construction

- **`organisation`** est obligatoire, **indexée** (toute clé étrangère l'est), et en **`PROTECT`** : on n'efface pas un client qui a des données.
- **`related_name="%(app_label)s_%(class)s_set"`** : chaque modèle fils a son propre nom de relation inverse ; sans cela, deux modèles dérivés se télescoperaient.
- **`pour_organisation(...)`** : la méthode à utiliser dans **toute** requête qui sert un utilisateur.
- **`PARENTS_CLIENT`** : si une table a un parent qui porte déjà une organisation (par exemple une affectation et sa mission), `save()` **recopie** l'organisation du parent si elle est absente, et **refuse** (`IncoherenceOrganisationError`) si elle diffère. Une affectation de la mission du client A ne peut donc jamais être rangée chez le client B.
- Le test paramétré `test_regle_3_...` parcourt **tous** les modèles qui dérivent de `ModeleDuClient` : un oubli futur est détecté automatiquement.

### `Utilisateur`

- **Un seul modèle, trois rôles** : `administrateur`, `operateur`, `responsable_client`. Le rôle `superviseur` viendra en V2.
- **Contrainte de base** : un responsable client **a** une organisation ; un administrateur ou un opérateur **n'en a pas**. La condition se lit : *(rôle = responsable_client ET organisation renseignée) OU (rôle ≠ responsable_client ET organisation vide)*.
- **Les jurés n'ont pas de compte** (D4) : ils se connecteront par un code de session, sans e-mail (§7.4). Ils auront leur propre modèle à l'itération 1.

### `missions_accessibles`

C'est la règle d'accès du §6.3, testée par **REC-29** : un opérateur affecté au client A n'accède pas aux données du client B. Un utilisateur désactivé ou anonyme n'accède à rien. L'administrateur accède à tout (chaque accès devra être journalisé : le journal d'audit viendra à l'itération 4).

> **Rappel (règle absolue n°4)** : les permissions se vérifient **côté serveur**, à chaque vue et à chaque message WebSocket. Cette fonction sera appelée par les futures vues.

### Pourquoi des UUID comme clés primaires ?

Les identifiants apparaissent dans les URL. Avec des entiers (`/missions/12/`), un utilisateur peut essayer `/missions/13/` (attaque dite IDOR, REC-25). Un UUID n'est pas devinable ; ce n'est pas une protection suffisante à lui seul (le contrôle d'accès reste indispensable), mais c'est une défense supplémentaire.

## Questions de compréhension

1. Pourquoi `ModeleDuClient` recopie-t-il l'organisation du parent, plutôt que de la laisser à la charge de chaque développeur ?
2. Pourquoi la contrainte « rôle et organisation cohérents » est-elle dans la base de données et pas seulement dans l'interface ?
3. Pourquoi un UUID n'est-il pas une protection suffisante contre l'accès aux données d'un autre client ?

<details>
<summary>Réponses</summary>

1. Ce qui dépend de la discipline de chacun finit par être oublié. En le mettant dans la classe de base, on le garantit pour toutes les tables, présentes et futures, et le test paramétré le vérifie.
2. Une contrainte de base s'applique à **tous** les chemins d'écriture (administration, scripts, imports, erreurs de code). Une vérification dans l'interface ne protège que ce formulaire.
3. Un UUID rend l'identifiant difficile à **deviner**, mais quelqu'un qui obtient un lien (par exemple dans un courriel transféré) pourrait l'utiliser. Le contrôle d'accès côté serveur (`missions_accessibles`, filtre par organisation) reste la vraie protection.
</details>

## Journal d'apprentissage

Notez : à quoi sert `ModeleDuClient`, ce que fait `pour_organisation`, et pourquoi on a recréé la base de développement.

## Et ensuite ?

Le prochain lot de l'étape 1.2 ajoute les applications `concours` (concours, catégories, épreuves, critères, sessions) et `candidats` (candidats, participations, consentements), toujours sur le même modèle : tests d'abord, puis code, puis commit.
