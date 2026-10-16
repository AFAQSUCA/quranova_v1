# Chapitre 13 — Prestations, tirage et annulation (itération 2, suite)

> **Étape du plan :** 3.2 à 3.3 · **Durée :** 5 à 6 heures · **Commit de référence :** `55fbf60` · **Résultat :** l'application `prestations` (`Prestation`, `Tirage`), le service `effectuer_tirage`, l'ouverture d'épreuve (RM-24), l'annulation (RM-25) et **75 tests**, dont **deux règles à écrire par vous**.

## Objectif

Faire tirer une série à un candidat, de façon **sûre** (deux candidats simultanés ne reçoivent jamais la même série), **idempotente** (un double clic ne crée qu'un tirage) et **traçable** (un tirage annulé reste visible).

| Règle | Où elle est appliquée |
|---|---|
| **RM-07, §8.5** : tirage côté serveur, enregistré avant confirmation | `effectuer_tirage` (transaction, `secrets.choice`) |
| **Règle absolue n°2** : `secrets` + `select_for_update` sur le lot + idempotence | `effectuer_tirage`, `id_demande` unique en base |
| **RM-21** : réutilisation des séries | **vous** : `series_admissibles` |
| **RM-24 / §8.2** : lot suffisant avant l'ouverture | **vous** : `series_necessaires` ; `ouvrir_epreuve` |
| **RM-22** : séries de P questions | `ouvrir_epreuve` via `series_incompletes` |
| **RM-25** : annulation avec trace ; série réintégrée si rien n'a été affiché | `annuler_tirage` + `series_admissibles` |
| **RM-28** : pas de tirage pour un mineur sans consentement | `verifier_pret_pour_tirage` (chapitre 10) |
| **§14.2** : un tirage validé n'est jamais remplacé en silence | `Tirage.save` / `Tirage.delete` |

## Pourquoi un verrou sur le lot ?

Les séries disponibles sont **calculées** (décision D2). Sans verrou, deux candidats qui tirent en même temps lisent tous deux « série 4 disponible » et la reçoivent tous les deux. Avec `select_for_update` sur le lot, le second tirage **attend** la fin du premier, puis relit les tirages enregistrés et ne voit plus la série 4. Le verrou transforme deux lectures simultanées en deux lectures successives. Le test `test_concurrence.py` le prouve avec deux threads.

Le **double clic** (REC-07) est une autre question : il se règle avec `id_demande`, unique en base. Le second envoi trouve le tirage déjà enregistré et le renvoie.

## Décisions de ce lot

| N° | Décision |
|---|---|
| D25 | Tirage possible seulement si le concours est « en cours » et l'épreuve « ouverte ». |
| D26 | Annulation : motif, auteur et date obligatoires ; tirage jamais supprimé. `diapositive_affichee` est porté par le **tirage**. |
| D27 | Un tirage annulé dont une diapositive a été affichée compte comme un tirage valide pour l'exclusion (à confirmer avec le CDC §8.5). |
| D28 | `id_demande` unique ; une demande annulée n'est pas rejouable ; avec T > 1 la prestation reste « en attente » jusqu'au T-ième tirage. |

## Étape A — Dossiers et réglages

```powershell
New-Item -ItemType Directory "apps\prestations\tests" -Force | Out-Null
New-Item -ItemType File "apps\prestations\__init__.py", "apps\prestations\tests\__init__.py" -Force | Out-Null
```

Dans `config\settings\base.py`, ajoutez `"apps.prestations",` à `INSTALLED_APPS` (après `apps.questions`).

Dans `apps\commun\models.py`, la méthode `save` de `ModeleDuClient` est découpée : le contrôle d'organisation devient une méthode `verifier_organisation`, appelée par `save`. Une prestation l'appelle **avant** ses propres contrôles, pour qu'une donnée d'un autre client soit toujours signalée comme telle (RM-20).

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
```

## Étape B — Les modèles

Les fabriques d'abord, puis les tests des modèles, puis les modèles.

**Fichier `apps\prestations\tests\outils.py`**

```python
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
```

**Fichier `apps\prestations\tests\test_modeles.py`**

```python
"""Tests des modèles Prestation et Tirage (§8.3, §14.1, §14.2 ; RM-20, RM-25)."""
import uuid

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_organisation,
    creer_participation,
    creer_session,
    creer_utilisateur,
)
from apps.prestations.exceptions import PrestationInvalideError, TirageInvalideError
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import ajouter_series, creer_epreuve_ouverte, creer_prestation, creer_tirage


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=3)


# --- Prestation --------------------------------------------------------------


@pytest.mark.django_db
def test_une_prestation_est_en_attente_par_defaut_et_prend_l_organisation(epreuve):
    prestation = creer_prestation(epreuve)

    assert prestation.etat == Prestation.Etat.EN_ATTENTE
    assert prestation.organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_une_prestation_par_participation_et_par_epreuve(epreuve):
    prestation = creer_prestation(epreuve)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_prestation(epreuve, participation=prestation.participation)


@pytest.mark.django_db
def test_le_rang_de_passage_est_unique_par_session_et_par_epreuve(epreuve):
    premiere = creer_prestation(epreuve, rang_passage=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_prestation(epreuve, session=premiere.session, rang_passage=1)


@pytest.mark.django_db
def test_l_epreuve_doit_etre_celle_de_la_categorie_de_la_participation(epreuve):
    autre_categorie = creer_categorie(epreuve.categorie.concours)
    participation = creer_participation(autre_categorie)

    with pytest.raises(PrestationInvalideError, match="catégorie"):
        creer_prestation(epreuve, participation=participation)


@pytest.mark.django_db
def test_la_session_doit_etre_celle_du_concours(epreuve):
    autre_concours_du_meme_client = creer_concours(epreuve.categorie.concours.mission)

    with pytest.raises(PrestationInvalideError, match="session"):
        creer_prestation(epreuve, session=creer_session(autre_concours_du_meme_client))


@pytest.mark.django_db
def test_rm20_une_participation_d_un_autre_client_est_refusee(epreuve):
    participation = creer_participation()

    with pytest.raises(IncoherenceOrganisationError):
        creer_prestation(epreuve, participation=participation)


# --- Tirage ------------------------------------------------------------------


@pytest.mark.django_db
def test_un_tirage_valide_par_defaut(epreuve):
    prestation = creer_prestation(epreuve)
    serie = epreuve.lot.series.first()

    tirage = creer_tirage(prestation, serie)

    assert tirage.statut == Tirage.Statut.VALIDE
    assert tirage.diapositive_affichee is False
    assert tirage.organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_la_serie_doit_appartenir_au_lot_de_l_epreuve(epreuve):
    autre_epreuve = creer_epreuve_ouverte(series=1)
    prestation = creer_prestation(epreuve)

    with pytest.raises(TirageInvalideError, match="lot"):
        creer_tirage(prestation, autre_epreuve.lot.series.first())


@pytest.mark.django_db
def test_l_identifiant_de_demande_est_unique(epreuve):
    serie1, serie2, _ = epreuve.lot.series.all()
    identifiant = uuid.uuid4()
    creer_tirage(creer_prestation(epreuve), serie1, id_demande=identifiant)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(creer_prestation(epreuve), serie2, id_demande=identifiant)


@pytest.mark.django_db
def test_rm21_jamais_deux_fois_la_meme_serie_pour_un_candidat(epreuve):
    prestation = creer_prestation(epreuve)
    serie = epreuve.lot.series.first()
    creer_tirage(prestation, serie, rang=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(prestation, serie, rang=2)


@pytest.mark.django_db
def test_un_seul_tirage_valide_par_rang(epreuve):
    prestation = creer_prestation(epreuve)
    serie1, serie2, _ = epreuve.lot.series.all()
    creer_tirage(prestation, serie1, rang=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(prestation, serie2, rang=1)


@pytest.mark.django_db
def test_un_tirage_annule_libere_le_rang_et_garde_la_trace(epreuve):
    prestation = creer_prestation(epreuve)
    serie1, serie2, _ = epreuve.lot.series.all()
    operateur = creer_utilisateur()
    creer_tirage(
        prestation, serie1, rang=1, statut=Tirage.Statut.ANNULE,
        motif_annulation="Erreur d'appel", annule_par=operateur, annule_le=timezone.now(),
    )

    creer_tirage(prestation, serie2, rang=1)

    assert prestation.tirages.count() == 2


@pytest.mark.django_db
def test_rm25_l_annulation_exige_motif_auteur_et_date(epreuve):
    prestation = creer_prestation(epreuve)
    serie = epreuve.lot.series.first()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(prestation, serie, statut=Tirage.Statut.ANNULE)
    with pytest.raises(IntegrityError), transaction.atomic():  # motif vide
        creer_tirage(
            prestation, serie, statut=Tirage.Statut.ANNULE,
            annule_par=creer_utilisateur(), annule_le=timezone.now(),
        )


@pytest.mark.django_db
def test_un_tirage_valide_ne_porte_pas_de_motif_d_annulation(epreuve):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(creer_prestation(epreuve), epreuve.lot.series.first(), motif_annulation="x")


@pytest.mark.django_db
def test_un_tirage_n_est_jamais_supprime(epreuve):
    tirage = creer_tirage(creer_prestation(epreuve), epreuve.lot.series.first())

    with pytest.raises(TirageInvalideError, match="annulé"):
        tirage.delete()
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_un_tirage_enregistre_ne_peut_pas_etre_remplace_en_silence(epreuve):
    tirage = creer_tirage(creer_prestation(epreuve), epreuve.lot.series.first())
    tirage.serie = epreuve.lot.series.last()

    with pytest.raises(TirageInvalideError, match="remplacé"):
        tirage.save()


@pytest.mark.django_db
def test_une_serie_tiree_ne_peut_pas_etre_supprimee(epreuve):
    serie = epreuve.lot.series.first()
    creer_tirage(creer_prestation(epreuve), serie)

    with pytest.raises(ProtectedError):
        serie.delete()
```

**Fichier `apps\prestations\apps.py`**

```python
from django.apps import AppConfig


class PrestationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.prestations"
    label = "prestations"
    verbose_name = "Prestations"
```

**Fichier `apps\prestations\exceptions.py`**

```python
"""Erreurs de l'application prestations."""
from apps.candidats.exceptions import TirageImpossibleError


class PrestationInvalideError(Exception):
    """Une prestation incohérente (participation, épreuve ou session qui ne vont pas ensemble)."""


class TirageInvalideError(Exception):
    """Un tirage incohérent, ou une tentative de modifier un tirage enregistré (§14.2)."""


class TirageRefuseError(TirageImpossibleError):
    """Le tirage est refusé : état du concours, de l'épreuve ou de la prestation, ou quota atteint (§8.5)."""


class LotEpuiseError(TirageImpossibleError):
    """Aucune série admissible : le tirage est bloqué, l'opérateur doit compléter le lot (RM-21)."""


class OuvertureEpreuveRefuseeError(Exception):
    """L'épreuve ne peut pas être ouverte : lot absent, séries incomplètes ou insuffisantes (RM-22, RM-24)."""


class AnnulationInvalideError(Exception):
    """L'annulation d'un tirage est refusée (RM-25)."""
```

**Fichier `apps\prestations\models.py`**

```python
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
        return f"Prestation n° {self.rang_passage} — {self.participation}"


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
```

```powershell
python manage.py makemigrations prestations
python manage.py migrate
pytest apps\prestations\tests\test_modeles.py
```

Attendu : `17 passed`.

## Étape C — Les tests des règles

**Fichier `apps\prestations\tests\test_rm21_selection.py`**

```python
"""Tests de la sélection des séries admissibles (RM-21, RM-25) — règle à écrire par vous.

Les trois paramètres de RM-21 sont portés par l'épreuve :
- RM-21.a ``reutilisation_autre_candidat`` (défaut : non) ;
- RM-21.b ``reutilisation_meme_candidat_autre_epreuve`` (défaut : non) ;
- RM-21.c ``exclusion_definitive`` (déduite : oui si a et b sont « non »).
Quelle que soit la configuration, un candidat ne reçoit jamais deux fois la même série dans une épreuve.
"""
import pytest
from django.utils import timezone

from apps.commun.tests.outils import creer_utilisateur
from apps.prestations import services
from apps.prestations.models import Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage


def annule(prestation, serie, *, affichee):
    return creer_tirage(
        prestation, serie, statut=Tirage.Statut.ANNULE, motif_annulation="Incident",
        annule_par=creer_utilisateur(), annule_le=timezone.now(), diapositive_affichee=affichee,
    )


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.mark.django_db
def test_rm21_toutes_les_series_sont_admissibles_au_depart_dans_l_ordre(epreuve):
    admissibles = services.series_admissibles(creer_prestation(epreuve))

    assert [s.numero for s in admissibles] == [1, 2, 3, 4]


@pytest.mark.django_db
def test_rm21_serie_exclue_apres_tirage_pour_les_autres_candidats_par_defaut(epreuve):
    premiere = epreuve.lot.series.get(numero=2)
    creer_tirage(creer_prestation(epreuve), premiere)

    admissibles = services.series_admissibles(creer_prestation(epreuve))

    assert [s.numero for s in admissibles] == [1, 3, 4]


@pytest.mark.django_db
def test_rm21a_reattribution_a_un_autre_candidat_si_autorisee():
    epreuve = creer_epreuve_ouverte(series=4, reutilisation_autre_candidat=True)
    creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get(numero=2))

    admissibles = services.series_admissibles(creer_prestation(epreuve))

    assert [s.numero for s in admissibles] == [1, 2, 3, 4]


@pytest.mark.django_db
@pytest.mark.parametrize("reattribution", [False, True])
def test_rm21_jamais_deux_fois_la_meme_serie_pour_un_candidat(reattribution):
    epreuve = creer_epreuve_ouverte(series=3, reutilisation_autre_candidat=reattribution, tirages_par_candidat=2)
    prestation = creer_prestation(epreuve)
    creer_tirage(prestation, epreuve.lot.series.get(numero=1), rang=1)

    admissibles = services.series_admissibles(prestation)

    assert 1 not in [s.numero for s in admissibles]


@pytest.mark.django_db
def test_rm21b_sans_effet_tant_qu_un_lot_n_est_pas_partage():
    """D24 : un lot par épreuve ; le paramètre RM-21.b ne change donc rien pour l'instant."""
    standard = creer_epreuve_ouverte(series=3)
    permissive = creer_epreuve_ouverte(series=3, reutilisation_meme_candidat_autre_epreuve=True)
    for epreuve in (standard, permissive):
        creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get(numero=1))

    resultats = [
        [s.numero for s in services.series_admissibles(creer_prestation(e))] for e in (standard, permissive)
    ]

    assert resultats[0] == resultats[1] == [2, 3]


@pytest.mark.django_db
def test_rm25_serie_reintegree_si_le_tirage_annule_n_a_rien_affiche(epreuve):
    prestation = creer_prestation(epreuve)
    annule(prestation, epreuve.lot.series.get(numero=1), affichee=False)

    for candidat in (prestation, creer_prestation(epreuve)):
        assert 1 in [s.numero for s in services.series_admissibles(candidat)]


@pytest.mark.django_db
def test_rm25_serie_exclue_si_le_tirage_annule_a_deja_affiche_une_diapositive(epreuve):
    prestation = creer_prestation(epreuve)
    annule(prestation, epreuve.lot.series.get(numero=1), affichee=True)

    for candidat in (prestation, creer_prestation(epreuve)):
        assert 1 not in [s.numero for s in services.series_admissibles(candidat)]


@pytest.mark.django_db
def test_rm25_avec_reattribution_la_serie_affichee_puis_annulee_reste_exclue_pour_le_meme_candidat():
    """D27 : le candidat a vu la série ; il ne la reçoit pas de nouveau, les autres le peuvent."""
    epreuve = creer_epreuve_ouverte(series=3, reutilisation_autre_candidat=True)
    prestation = creer_prestation(epreuve)
    annule(prestation, epreuve.lot.series.get(numero=1), affichee=True)

    assert 1 not in [s.numero for s in services.series_admissibles(prestation)]
    assert 1 in [s.numero for s in services.series_admissibles(creer_prestation(epreuve))]


@pytest.mark.django_db
def test_rm21_lot_epuise_liste_vide():
    epreuve = creer_epreuve_ouverte(series=1)
    creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get())

    assert services.series_admissibles(creer_prestation(epreuve)) == []


@pytest.mark.django_db
def test_les_tirages_d_une_autre_epreuve_n_ont_aucun_effet(epreuve):
    autre = creer_epreuve_ouverte(series=2)
    creer_tirage(creer_prestation(autre), autre.lot.series.get(numero=1))

    assert len(services.series_admissibles(creer_prestation(epreuve))) == 4
```

**Fichier `apps\prestations\tests\test_rm24_suffisance.py`**

```python
"""Tests du contrôle de suffisance du lot (§8.2, RM-24) et de l'ouverture d'une épreuve.

``series_necessaires`` est la règle à écrire par vous ; le reste est testé à travers elle.
"""
import pytest

from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_participation
from apps.concours.models import Epreuve
from apps.prestations import services
from apps.prestations.exceptions import OuvertureEpreuveRefuseeError
from apps.prestations.tests.outils import ajouter_series, creer_epreuve_ouverte
from apps.questions.models import QuestionDeSerie, Serie
from apps.questions.tests.outils import creer_question


@pytest.mark.django_db
@pytest.mark.parametrize(
    "n, t, reattribution, attendu",
    [
        (10, 1, False, 10),  # exclusion définitive : S >= N x T
        (10, 2, False, 20),
        (1, 1, False, 1),
        (10, 1, True, 1),  # réattribution : S >= T
        (10, 3, True, 3),
        (0, 2, True, 2),
    ],
)
def test_rm24_series_necessaires(n, t, reattribution, attendu):
    epreuve = creer_epreuve_ouverte(series=0, tirages_par_candidat=t, reutilisation_autre_candidat=reattribution)

    assert services.series_necessaires(epreuve, n) == attendu


@pytest.mark.django_db
def test_rm24_sans_candidat_et_sans_reattribution_aucune_serie_n_est_necessaire():
    assert services.series_necessaires(creer_epreuve_ouverte(series=0), 0) == 0


def inscrits_admis(epreuve, n):
    for _ in range(n):
        creer_participation(
            epreuve.categorie, creer_candidat(epreuve.organisation), statut=Participation.Statut.ADMIS
        )


def en_preparation(series, admis, **champs):
    epreuve = creer_epreuve_ouverte(series=series, etat=Epreuve.Etat.EN_PREPARATION, **champs)
    inscrits_admis(epreuve, admis)
    return epreuve


@pytest.mark.django_db
def test_rm24_series_manquantes_compte_les_admis_seulement():
    epreuve = en_preparation(series=3, admis=5)
    creer_participation(epreuve.categorie)  # inscrit, non admis : ne compte pas

    assert services.series_manquantes(epreuve) == 2  # 5 admis x 1 tirage - 3 séries


@pytest.mark.django_db
def test_rm24_ouverture_bloquee_lot_insuffisant_avec_le_nombre_de_series_manquantes():
    epreuve = en_preparation(series=3, admis=5)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="2 série"):
        services.ouvrir_epreuve(epreuve)

    epreuve.refresh_from_db()
    assert epreuve.etat == Epreuve.Etat.EN_PREPARATION


@pytest.mark.django_db
def test_rm24_ouverture_possible_quand_le_lot_suffit():
    epreuve = en_preparation(series=5, admis=5)

    services.ouvrir_epreuve(epreuve)

    epreuve.refresh_from_db()
    assert epreuve.etat == Epreuve.Etat.OUVERTE


@pytest.mark.django_db
def test_rm24_la_reattribution_reduit_le_besoin():
    epreuve = en_preparation(series=1, admis=5, reutilisation_autre_candidat=True)

    services.ouvrir_epreuve(epreuve)

    epreuve.refresh_from_db()
    assert epreuve.etat == Epreuve.Etat.OUVERTE


@pytest.mark.django_db
def test_rm22_ouverture_bloquee_si_une_serie_est_incomplete():
    epreuve = en_preparation(series=5, admis=1)
    bancale = Serie.objects.create(lot=epreuve.lot, numero=99)
    for rang in (1, 2):  # P = 1 dans cette épreuve : deux questions, c'est une de trop
        QuestionDeSerie.objects.create(serie=bancale, question=creer_question(epreuve.organisation), rang=rang)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="99"):
        services.ouvrir_epreuve(epreuve)


@pytest.mark.django_db
def test_ouverture_bloquee_sans_lot_ou_sans_serie():
    epreuve = creer_epreuve_ouverte(series=0, etat=Epreuve.Etat.EN_PREPARATION)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="aucune série"):
        services.ouvrir_epreuve(epreuve)


@pytest.mark.django_db
def test_une_epreuve_deja_ouverte_ne_s_ouvre_pas_deux_fois():
    epreuve = creer_epreuve_ouverte(series=2)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="préparation"):
        services.ouvrir_epreuve(epreuve)
```

**Fichier `apps\prestations\tests\test_tirage.py`**

```python
"""Tests du service de tirage (§8.5 ; RM-07, RM-21, RM-28 ; REC-06, REC-07)."""
import uuid
from datetime import date

import pytest

from apps.candidats.exceptions import ConsentementManquantError, ParticipationNonAdmiseError, TirageImpossibleError
from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_consentement, creer_participation
from apps.concours.models import Concours, Epreuve
from apps.prestations import services
from apps.prestations.exceptions import LotEpuiseError, TirageRefuseError
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.mark.django_db
def test_rec06_un_seul_tirage_valide_est_enregistre(epreuve):
    prestation = creer_prestation(epreuve)

    tirage = services.effectuer_tirage(prestation, uuid.uuid4(), terminal="tablette-1")

    assert Tirage.objects.count() == 1
    assert tirage.statut == Tirage.Statut.VALIDE and tirage.rang == 1 and tirage.terminal == "tablette-1"
    assert tirage.serie.lot.epreuve == epreuve
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.TIRE


@pytest.mark.django_db
def test_rec07_double_clic_aucun_double_tirage(epreuve):
    prestation = creer_prestation(epreuve)
    demande = uuid.uuid4()

    premier = services.effectuer_tirage(prestation, demande)
    second = services.effectuer_tirage(prestation, demande)

    assert premier == second and Tirage.objects.count() == 1


@pytest.mark.django_db
def test_un_identifiant_de_demande_ne_sert_pas_pour_une_autre_prestation(epreuve):
    demande = uuid.uuid4()
    services.effectuer_tirage(creer_prestation(epreuve), demande)

    with pytest.raises(TirageImpossibleError, match="autre prestation"):
        services.effectuer_tirage(creer_prestation(epreuve), demande)
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_le_tirage_choisit_avec_le_module_secrets(epreuve, monkeypatch):
    appels = []

    def faux_choice(sequence):
        appels.append(list(sequence))
        return sequence[-1]

    monkeypatch.setattr(services.secrets, "choice", faux_choice)

    tirage = services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())

    assert [s.numero for s in appels[0]] == [1, 2, 3, 4] and tirage.serie.numero == 4


@pytest.mark.django_db
def test_deux_candidats_ne_recoivent_pas_la_meme_serie_par_defaut():
    epreuve = creer_epreuve_ouverte(series=3)

    series = [services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4()).serie for _ in range(3)]

    assert len(set(series)) == 3


@pytest.mark.django_db
def test_lot_epuise_le_tirage_est_bloque_sans_rien_enregistrer():
    epreuve = creer_epreuve_ouverte(series=1)
    services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())
    prestation = creer_prestation(epreuve)

    with pytest.raises(LotEpuiseError, match="compléter"):
        services.effectuer_tirage(prestation, uuid.uuid4())

    assert Tirage.objects.count() == 1
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_ATTENTE


@pytest.mark.django_db
def test_plusieurs_tirages_par_candidat():
    epreuve = creer_epreuve_ouverte(series=5, tirages_par_candidat=2)
    prestation = creer_prestation(epreuve)

    premier = services.effectuer_tirage(prestation, uuid.uuid4())
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_ATTENTE  # il reste un tirage à faire
    second = services.effectuer_tirage(prestation, uuid.uuid4())

    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.TIRE
    assert (premier.rang, second.rang) == (1, 2) and premier.serie != second.serie
    with pytest.raises(TirageRefuseError):
        services.effectuer_tirage(prestation, uuid.uuid4())
    assert Tirage.objects.count() == 2


@pytest.mark.django_db
def test_rm28_un_mineur_sans_consentement_ne_tire_pas(epreuve):
    mineur = creer_candidat(epreuve.organisation, date_naissance=date(2015, 5, 1))
    participation = creer_participation(epreuve.categorie, mineur, statut=Participation.Statut.ADMIS)
    prestation = creer_prestation(epreuve, participation=participation)

    with pytest.raises(ConsentementManquantError):
        services.effectuer_tirage(prestation, uuid.uuid4())

    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_rm28_un_mineur_avec_consentement_tire(epreuve):
    mineur = creer_candidat(epreuve.organisation, date_naissance=date(2015, 5, 1))
    participation = creer_participation(epreuve.categorie, mineur, statut=Participation.Statut.ADMIS)
    creer_consentement(participation)

    tirage = services.effectuer_tirage(creer_prestation(epreuve, participation=participation), uuid.uuid4())

    assert tirage.statut == Tirage.Statut.VALIDE


@pytest.mark.django_db
def test_une_participation_non_admise_ne_tire_pas(epreuve):
    participation = creer_participation(
        epreuve.categorie, creer_candidat(epreuve.organisation, date_naissance=date(1990, 1, 1))
    )  # statut « inscrit »

    with pytest.raises(ParticipationNonAdmiseError):
        services.effectuer_tirage(creer_prestation(epreuve, participation=participation), uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Concours.Etat.OUVERT, Concours.Etat.SUSPENDU, Concours.Etat.TERMINE])
def test_d25_pas_de_tirage_si_le_concours_n_est_pas_en_cours(epreuve, etat):
    Concours.objects.filter(pk=epreuve.categorie.concours_id).update(etat=etat)

    with pytest.raises(TirageRefuseError, match="concours"):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Epreuve.Etat.EN_PREPARATION, Epreuve.Etat.TERMINEE])
def test_d25_pas_de_tirage_si_l_epreuve_n_est_pas_ouverte(epreuve, etat):
    Epreuve.objects.filter(pk=epreuve.pk).update(etat=etat)

    with pytest.raises(TirageRefuseError, match="épreuve"):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Prestation.Etat.EN_NOTATION, Prestation.Etat.CLOTUREE, Prestation.Etat.ANNULEE])
def test_pas_de_tirage_si_la_prestation_n_est_pas_en_attente(epreuve, etat):
    prestation = creer_prestation(epreuve, etat=etat)

    with pytest.raises(TirageRefuseError, match="attente"):
        services.effectuer_tirage(prestation, uuid.uuid4())


@pytest.mark.django_db
def test_epreuve_sans_lot_le_tirage_est_bloque():
    epreuve = creer_epreuve_ouverte(series=0)

    with pytest.raises(LotEpuiseError):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())
```

**Fichier `apps\prestations\tests\test_annulation.py`**

```python
"""Tests de l'annulation d'un tirage (RM-25, §8.5, D26)."""
import uuid

import pytest

from apps.commun.tests.outils import creer_utilisateur
from apps.prestations import services
from apps.prestations.exceptions import AnnulationInvalideError, LotEpuiseError
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import Utilisateur


@pytest.fixture
def tirage(db):
    epreuve = creer_epreuve_ouverte(series=1)
    return services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())


@pytest.mark.django_db
def test_rm25_le_tirage_annule_garde_sa_trace(tirage):
    operateur = creer_utilisateur()

    annule = services.annuler_tirage(tirage, operateur, "  Erreur d'appel du candidat  ")

    assert Tirage.objects.count() == 1
    assert annule.statut == Tirage.Statut.ANNULE
    assert annule.motif_annulation == "Erreur d'appel du candidat"
    assert annule.annule_par == operateur and annule.annule_le is not None
    assert annule.serie == tirage.serie


@pytest.mark.django_db
def test_la_prestation_redevient_en_attente(tirage):
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident")

    tirage.prestation.refresh_from_db()
    assert tirage.prestation.etat == Prestation.Etat.EN_ATTENTE


@pytest.mark.django_db
def test_rm25_serie_reintegree_si_aucune_diapositive_affichee(tirage):
    """Lot d'une seule série : après annulation, le nouveau tirage peut la recevoir de nouveau."""
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident technique")

    nouveau = services.effectuer_tirage(tirage.prestation, uuid.uuid4())

    assert nouveau.serie == tirage.serie and nouveau.id != tirage.id
    assert Tirage.objects.count() == 2


@pytest.mark.django_db
def test_rm25_serie_exclue_si_une_diapositive_a_ete_affichee(tirage):
    Tirage.objects.filter(pk=tirage.pk).update(diapositive_affichee=True)
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident pendant l'affichage")

    with pytest.raises(LotEpuiseError):
        services.effectuer_tirage(tirage.prestation, uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("motif", ["", "   ", None])
def test_le_motif_est_obligatoire(tirage, motif):
    with pytest.raises(AnnulationInvalideError, match="motif"):
        services.annuler_tirage(tirage, creer_utilisateur(), motif)

    tirage.refresh_from_db()
    assert tirage.statut == Tirage.Statut.VALIDE


@pytest.mark.django_db
def test_un_responsable_client_ne_peut_pas_annuler(tirage):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)

    with pytest.raises(AnnulationInvalideError, match="prestataire"):
        services.annuler_tirage(tirage, responsable, "Je n'aime pas ma série")


@pytest.mark.django_db
def test_on_n_annule_pas_deux_fois(tirage):
    operateur = creer_utilisateur()
    services.annuler_tirage(tirage, operateur, "Incident")

    with pytest.raises(AnnulationInvalideError, match="déjà annulé"):
        services.annuler_tirage(tirage, operateur, "Encore")


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Prestation.Etat.EN_NOTATION, Prestation.Etat.CLOTUREE])
def test_pas_d_annulation_une_fois_en_notation(tirage, etat):
    Prestation.objects.filter(pk=tirage.prestation_id).update(etat=etat)

    with pytest.raises(AnnulationInvalideError, match="notation"):
        services.annuler_tirage(tirage, creer_utilisateur(), "Trop tard")


@pytest.mark.django_db
def test_la_demande_d_un_tirage_annule_n_est_pas_rejouable(tirage):
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident")

    with pytest.raises(Exception, match="annulé"):
        services.effectuer_tirage(tirage.prestation, tirage.id_demande)
```

**Fichier `apps\prestations\tests\test_concurrence.py`**

```python
"""Test de concurrence du tirage : le verrou sur le lot sérialise les tirages (règle absolue n°2).

Nécessite une vraie base PostgreSQL et de vraies transactions (``transaction=True``).
"""
import threading
import uuid

import pytest
from django.db import connection

from apps.prestations import services
from apps.prestations.exceptions import LotEpuiseError
from apps.prestations.models import Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation


def lancer_en_parallele(taches):
    """Exécute chaque tâche dans son thread, démarrage simultané ; renvoie les résultats ou exceptions."""
    barriere = threading.Barrier(len(taches))
    resultats = [None] * len(taches)

    def executer(i, tache):
        try:
            barriere.wait()
            resultats[i] = tache()
        except Exception as erreur:  # noqa: BLE001 - on veut observer l'erreur, quelle qu'elle soit
            resultats[i] = erreur
        finally:
            connection.close()

    threads = [threading.Thread(target=executer, args=(i, t)) for i, t in enumerate(taches)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultats


@pytest.mark.django_db(transaction=True)
def test_deux_tirages_simultanes_sur_un_lot_d_une_serie_un_seul_reussit():
    epreuve = creer_epreuve_ouverte(series=1)
    prestations = [creer_prestation(epreuve), creer_prestation(epreuve)]

    resultats = lancer_en_parallele(
        [lambda p=p: services.effectuer_tirage(p, uuid.uuid4()) for p in prestations]
    )

    reussis = [r for r in resultats if isinstance(r, Tirage)]
    refuses = [r for r in resultats if isinstance(r, LotEpuiseError)]
    assert len(reussis) == 1 and len(refuses) == 1
    assert Tirage.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_rec07_deux_clics_simultanes_avec_la_meme_demande_creent_un_seul_tirage():
    epreuve = creer_epreuve_ouverte(series=3)
    prestation = creer_prestation(epreuve)
    demande = uuid.uuid4()

    resultats = lancer_en_parallele([lambda: services.effectuer_tirage(prestation, demande) for _ in range(2)])

    assert all(isinstance(r, Tirage) for r in resultats), resultats
    assert resultats[0].pk == resultats[1].pk
    assert Tirage.objects.count() == 1
```

## Étape D — Le service, avec **deux règles à écrire par vous**

Voici `services.py` tel qu'il est dans le dépôt : tout est écrit **sauf** `series_admissibles` et `series_necessaires` (marquées `TODO(human)`).

**Fichier `apps\prestations\services.py`**

```python
"""Tirage au sort des séries, ouverture des épreuves et annulation des tirages (§8, RM-21 à RM-28).

Règle absolue n°2 : le tirage se fait côté serveur, avec le module ``secrets``, dans une
transaction qui verrouille le lot (``select_for_update``), et il est idempotent grâce à
l'identifiant de demande.
"""
import secrets

from django.db import transaction
from django.utils import timezone

from apps.candidats.models import Participation
from apps.candidats.services import verifier_pret_pour_tirage
from apps.concours.models import Concours, Epreuve
from apps.prestations.exceptions import (
    AnnulationInvalideError,
    LotEpuiseError,
    OuvertureEpreuveRefuseeError,
    TirageRefuseError,
)
from apps.candidats.exceptions import TirageImpossibleError
from apps.prestations.models import Prestation, Tirage
from apps.questions.models import Lot
from apps.questions.services import series_incompletes
from apps.utilisateurs.models import Utilisateur


# --- Règles métier à écrire par vous (TODO(human)) ---------------------------


def series_admissibles(prestation):
    """Les séries que cette prestation peut encore tirer, triées par numéro (RM-21, RM-25).

    TODO(human) : écrivez la règle. Entrées utiles : ``prestation.epreuve`` (champs
    ``reutilisation_autre_candidat`` = RM-21.a), son lot (``epreuve.lot.series``) et les tirages
    de ces séries (``Tirage``, champs ``statut``, ``prestation``, ``diapositive_affichee``).

    Contrat attendu (voir ``test_rm21_selection.py``) :
    - un tirage VALIDE rend sa série indisponible pour le MÊME candidat, toujours ;
    - pour les AUTRES candidats, la série est indisponible sauf si RM-21.a est vrai ;
    - un tirage ANNULÉ compte comme un tirage valide si une diapositive a été affichée
      (``diapositive_affichee``), sinon il est ignoré : la série est réintégrée (RM-25) ;
    - le résultat est une liste de ``Serie`` (vide si le lot est épuisé).
    RM-21.b (autre épreuve) est sans effet tant qu'un lot n'est pas partagé (D24).
    """
    raise NotImplementedError("TODO(human) : règle RM-21 (voir la docstring)")


def series_necessaires(epreuve, nombre_candidats):
    """Nombre minimal de séries que le lot doit contenir pour servir tous les tirages (§8.2, RM-24).

    TODO(human) : écrivez la règle. ``nombre_candidats`` est N (participations admises).
    - si une série tirée est exclue pour tous les candidats (RM-21.a faux) : S >= N x T ;
    - si une série peut être réattribuée à d'autres candidats (RM-21.a vrai) : S >= T.
    T est ``epreuve.tirages_par_candidat``. Renvoyez le S minimal (un entier).
    """
    raise NotImplementedError("TODO(human) : contrôle de suffisance du lot (voir la docstring)")


# --- Ouverture d'une épreuve (RM-22, RM-24) ----------------------------------


def series_manquantes(epreuve):
    """Combien de séries faut-il encore ajouter au lot (0 si le lot suffit) ?"""
    admis = Participation.objects.filter(
        categorie_id=epreuve.categorie_id, statut=Participation.Statut.ADMIS
    ).count()
    lot = Lot.objects.filter(epreuve=epreuve).first()
    presentes = lot.series.count() if lot else 0
    return max(0, series_necessaires(epreuve, admis) - presentes)


def ouvrir_epreuve(epreuve):
    """Ouvre l'épreuve si son lot est complet et suffisant, sinon explique ce qui manque (RM-24)."""
    with transaction.atomic():
        epreuve = Epreuve.objects.select_for_update().get(pk=epreuve.pk)
        if epreuve.etat != Epreuve.Etat.EN_PREPARATION:
            raise OuvertureEpreuveRefuseeError(f"L'épreuve « {epreuve.nom} » n'est pas en préparation.")
        lot = Lot.objects.filter(epreuve=epreuve).first()
        if lot is None or not lot.series.exists():
            raise OuvertureEpreuveRefuseeError(f"L'épreuve « {epreuve.nom} » n'a aucune série.")
        incompletes = series_incompletes(lot)
        if incompletes:
            numeros = ", ".join(str(s.numero) for s in incompletes)
            raise OuvertureEpreuveRefuseeError(
                f"Séries incomplètes (RM-22) : {numeros}. Chaque série doit contenir "
                f"exactement {epreuve.questions_par_serie} questions."
            )
        manque = series_manquantes(epreuve)
        if manque:
            raise OuvertureEpreuveRefuseeError(
                f"Lot insuffisant (RM-24) : il manque {manque} série(s) pour servir tous les tirages prévus."
            )
        epreuve.etat = Epreuve.Etat.OUVERTE
        epreuve.save(update_fields=["etat", "modifie_le"])
    return epreuve


# --- Tirage (§8.5) -----------------------------------------------------------


def _rejouer(tirage, prestation):
    """Une demande déjà traitée renvoie son tirage (REC-07) ; jamais celui d'une autre prestation."""
    if tirage.prestation_id != prestation.pk:
        raise TirageImpossibleError("Cet identifiant de demande appartient à une autre prestation.")
    if tirage.statut != Tirage.Statut.VALIDE:
        raise TirageImpossibleError("Ce tirage a été annulé : utilisez une nouvelle demande.")
    return tirage


def effectuer_tirage(prestation, id_demande, *, terminal=""):
    """Attribue une série à la prestation (§8.5, RM-07, RM-21, RM-28) et renvoie le ``Tirage``.

    Idempotent : un second appel avec le même ``id_demande`` renvoie le tirage déjà enregistré.
    Le verrou sur le lot sérialise les tirages : deux candidats simultanés ne reçoivent pas la
    même série, et la série est enregistrée AVANT toute communication du résultat.
    """
    deja = Tirage.objects.filter(id_demande=id_demande).first()
    if deja is not None:
        return _rejouer(deja, prestation)

    with transaction.atomic():
        lot = Lot.objects.select_for_update().filter(epreuve_id=prestation.epreuve_id).first()
        if lot is None:
            raise LotEpuiseError("Cette épreuve n'a pas de lot : complétez-le avant tout tirage.")
        # Rechargé sous verrou : un tirage simultané de la même demande a pu être enregistré.
        deja = Tirage.objects.filter(id_demande=id_demande).first()
        if deja is not None:
            return _rejouer(deja, prestation)
        prestation = (
            Prestation.objects.select_for_update()
            .select_related("participation__candidat", "participation__concours", "epreuve__categorie__concours")
            .get(pk=prestation.pk)
        )
        epreuve = prestation.epreuve

        if epreuve.categorie.concours.etat != Concours.Etat.EN_COURS:
            raise TirageRefuseError("Le concours n'est pas en cours : aucun tirage.")
        if epreuve.etat != Epreuve.Etat.OUVERTE:
            raise TirageRefuseError("L'épreuve n'est pas ouverte : aucun tirage.")
        if prestation.etat != Prestation.Etat.EN_ATTENTE:
            raise TirageRefuseError("La prestation n'est pas en attente : aucun tirage.")
        deja_tires = prestation.tirages.filter(statut=Tirage.Statut.VALIDE).count()
        if deja_tires >= epreuve.tirages_par_candidat:
            raise TirageRefuseError(f"Les {epreuve.tirages_par_candidat} tirage(s) prévus sont déjà effectués.")
        verifier_pret_pour_tirage(prestation.participation)  # admission et consentement (RM-28)

        admissibles = series_admissibles(prestation)
        if not admissibles:
            raise LotEpuiseError("Le lot est épuisé : l'opérateur doit le compléter avant de poursuivre.")
        serie = secrets.choice(admissibles)  # générateur cryptographiquement sûr (règle n°2)

        tirage = Tirage.objects.create(
            prestation=prestation, serie=serie, rang=deja_tires + 1, id_demande=id_demande, terminal=terminal
        )
        if deja_tires + 1 >= epreuve.tirages_par_candidat:
            prestation.etat = Prestation.Etat.TIRE
            prestation.save(update_fields=["etat", "modifie_le"])
    return tirage


# --- Annulation (RM-25) ------------------------------------------------------

ETATS_ANNULABLES = (
    Prestation.Etat.EN_ATTENTE,
    Prestation.Etat.TIRE,
    Prestation.Etat.EN_AFFICHAGE,
    Prestation.Etat.EN_PAUSE,
)


def annuler_tirage(tirage, auteur, motif, *, maintenant=None):
    """Annule un tirage : il est conservé avec son motif et son auteur (RM-25), jamais supprimé.

    La série redevient admissible seulement si aucune de ses diapositives n'a été affichée :
    c'est ``series_admissibles`` qui l'applique, d'après ``diapositive_affichee``.
    """
    motif = (motif or "").strip()
    if not motif:
        raise AnnulationInvalideError("Un motif est obligatoire pour annuler un tirage.")
    if auteur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        raise AnnulationInvalideError("Seul le personnel du prestataire peut annuler un tirage.")

    with transaction.atomic():
        Lot.objects.select_for_update().get(epreuve_id=tirage.prestation.epreuve_id)
        tirage = Tirage.objects.select_related("prestation").get(pk=tirage.pk)
        if tirage.statut != Tirage.Statut.VALIDE:
            raise AnnulationInvalideError("Ce tirage est déjà annulé.")
        prestation = Prestation.objects.select_for_update().get(pk=tirage.prestation_id)
        if prestation.etat not in ETATS_ANNULABLES:
            raise AnnulationInvalideError("La prestation est en notation ou terminée : le tirage ne peut plus être annulé.")
        tirage.statut = Tirage.Statut.ANNULE
        tirage.motif_annulation = motif
        tirage.annule_par = auteur
        tirage.annule_le = maintenant or timezone.now()
        tirage.save()
        # Il manque désormais un tirage valide : la prestation attend de nouveau son tirage.
        prestation.etat = Prestation.Etat.EN_ATTENTE
        prestation.save(update_fields=["etat", "modifie_le"])
    return tirage
```

### À vous : `series_necessaires` (§8.2, RM-24)

Écrivez le nombre minimal de séries que le lot doit contenir : **S ≥ N × T** si une série tirée est exclue pour tous, **S ≥ T** si elle peut être réattribuée. Testez avec :

```powershell
pytest apps\prestations\tests\test_rm24_suffisance.py
```

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
    if epreuve.reutilisation_autre_candidat:
        return epreuve.tirages_par_candidat
    return nombre_candidats * epreuve.tirages_par_candidat
```

</details>

### À vous : `series_admissibles` (RM-21, RM-25)

Écrivez la liste des séries qu'une prestation peut encore tirer, en lisant les trois paramètres de RM-21 et les tirages déjà faits. **Indice :** construisez d'abord l'ensemble des séries *exclues* (celles que le candidat a déjà reçues, puis celles que tout le monde a reçues si la réattribution est interdite), puis retirez-les du lot. Pour RM-25, un tirage annulé ne compte que si `diapositive_affichee` est vrai.

```powershell
pytest apps\prestations\tests\test_rm21_selection.py
```

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
    epreuve = prestation.epreuve
    lot = epreuve.lot
    # Les tirages qui « comptent » : valides, ou annulés alors qu'une diapositive avait été affichée (RM-25).
    comptent = Tirage.objects.filter(serie__lot=lot).filter(
        Q(statut=Tirage.Statut.VALIDE) | Q(statut=Tirage.Statut.ANNULE, diapositive_affichee=True)
    )
    # Jamais deux fois la même série pour le même candidat dans une épreuve.
    exclues = set(comptent.filter(prestation=prestation).values_list("serie_id", flat=True))
    if not epreuve.reutilisation_autre_candidat:
        # RM-21.a faux : une série tirée est exclue pour tous.
        exclues |= set(comptent.values_list("serie_id", flat=True))
    return list(lot.series.exclude(pk__in=exclues).order_by("numero"))
```

</details>

> Cette solution utilise `Q` : ajoutez `from django.db.models import Q` en haut de `services.py`.

## Résultat attendu

```powershell
pytest apps\prestations
```

Avec vos deux règles : **75 passed**. Sans elles, 45 tests échouent (tirage, ouverture, annulation en dépendent). Suite complète : **513 réussis** si vous avez aussi écrit les règles du corpus (chapitres 04, 06 et 07).

## Questions de compréhension

1. `effectuer_tirage` cherche l'`id_demande` **avant** la transaction, puis **dans** la transaction. Pourquoi les deux ?
2. Pourquoi `Tirage.delete()` lève-t-il une erreur au lieu de laisser faire ?
3. Avec T = 2, pourquoi la prestation reste-t-elle « en attente » après le premier tirage ?

<details>
<summary>Réponses</summary>

1. Avant : chemin rapide, sans verrou, pour le cas courant d'un double clic déjà traité. Dans la transaction : deux requêtes simultanées avec la même demande passent toutes deux le premier contrôle ; la seconde, bloquée sur le verrou, doit relire pour trouver le tirage que la première vient d'enregistrer.
2. Un tirage est une preuve du déroulement du concours (RM-25, §14.2) : on l'annule avec motif et auteur, on ne le fait pas disparaître. (Un `QuerySet.delete()` contournerait cette garde : les contraintes `PROTECT` sur la série et la prestation restent la protection de dernier recours.)
3. Parce que §8.5 n'autorise le tirage qu'à l'état EN_ATTENTE, et qu'il reste un tirage à faire ; l'état passe à TIRÉ seulement quand les T tirages sont faits.
</details>

## Journal d'apprentissage

Expliquez avec vos mots pourquoi un verrou est nécessaire alors que la contrainte d'unicité `(prestation, série)` existe déjà en base.

## Commit proposé

```text
Itération 2 : tirage, ouverture d'épreuve et annulation (RM-21, RM-24, RM-25)
```
