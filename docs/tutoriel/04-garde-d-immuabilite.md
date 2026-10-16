# Chapitre 4 — Une version validée ne change plus (garde d'immuabilité)

> **Étape du plan :** 0.3 (suite) · **Durée :** 2 heures · **Commit de référence :** `6a515f4` · **Résultat :** les modèles du corpus refusent toute écriture sur une version figée.

## Objectif

Appliquer **RM-27** et le §12.3 : *une version validée est immuable ; toute correction donne lieu à une nouvelle version*. Ce chapitre contient **deux règles que vous écrivez vous-même** (`TODO(human)`).

## Le principe

- Les **modèles** (`save()` et `delete()`) lisent l'état **réel en base** et appellent deux fonctions de règles.
- Les **règles** sont dans `apps\coran\services.py`, sans accès à la base : elles reçoivent des valeurs et lèvent `CorpusImmuableError`.

### Les pièges (que les tests vérifient)

1. **Objet périmé en mémoire** : un verset peut croire que sa version est « importée » alors qu'elle a été validée entre-temps. La garde lit donc le statut **dans la base**, pas dans `verset.sourate.version.statut`.
2. **Déplacement** : changer un verset de sourate (ou une sourate de version), c'est sortir d'une version et entrer dans une autre. Il faut vérifier **l'ancien et le nouveau parent**.
3. **Retour en arrière** : repasser de « validée » à « importée » dégèlerait le contenu. D'où le contrôle des transitions.
4. **Identité de la version** : l'empreinte, le fichier et la date de validation ne changent plus une fois la version figée.

### Limite connue

`QuerySet.update()`, `bulk_create()` et `QuerySet.delete()` **contournent** `save()` et `delete()`. Un déclencheur PostgreSQL (niveau 3) fermera plus tard cette porte. En attendant, la garde protège contre les erreurs de code courantes.

## Étape A — L'exception et les règles vides

**Fichier `apps\coran\exceptions.py`**

```python
"""Exceptions de l'application coran."""


class CorpusImmuableError(Exception):
    """Une écriture est refusée parce qu'elle violerait l'immuabilité du corpus (RM-27, §12.3)."""
```

**Fichier `apps\coran\services.py`**

```python
"""Règles métier du corpus (cf. §12.3 : versionnement et immutabilité).

Ces fonctions ne touchent pas à la base de données : elles reçoivent des
valeurs et lèvent ``CorpusImmuableError`` si l'opération est interdite.
Les modèles se chargent de lire l'état réel en base et d'appeler ces fonctions.
"""
from apps.coran.exceptions import CorpusImmuableError  # noqa: F401  (à utiliser ci-dessous)


def verifier_transition_statut(ancien_statut, nouveau_statut, date_validation):
    """Refuse un changement de statut d'une version du corpus qui n'est pas autorisé.

    Statuts possibles : « importee », « validee », « active », « retiree ».

    TODO(human) : écrivez la règle.
    - Quelles transitions sont permises (par exemple importee -> validee) ?
    - Peut-on revenir en arrière (validee -> importee) ? Pourquoi serait-ce dangereux ?
    - Une version peut-elle devenir « validee » sans date de validation (PV du référent) ?
    Levez CorpusImmuableError avec un message explicite si la transition est refusée.
    """


def verifier_ecriture_autorisee(statut_version):
    """Refuse toute écriture sur le contenu d'une version dont le statut est figé.

    « Écriture » = création, modification ou suppression d'une sourate, d'un verset,
    ou modification des champs d'identité de la version (empreinte, fichier...).

    TODO(human) : écrivez la règle.
    - Pour quels statuts le contenu est-il figé ?
    Levez CorpusImmuableError avec un message explicite si l'écriture est refusée.
    """
```

Tant que les deux fonctions sont vides, elles ne refusent rien : les anciens tests continuent de passer.

## Étape B — Les tests (à écrire avant la plomberie)

Mettez à jour `apps\coran\tests\outils.py` (le numéro de sourate par défaut reste entre 1 et 114) :

**Fichier `apps\coran\tests\outils.py`**

```python
"""Fonctions utilitaires partagées par les tests de l'application coran."""
import itertools

from apps.coran.models import Sourate, Verset, VersionCorpus

_compteur_versions = itertools.count(1)
_compteur_sourates = itertools.count(1)
_compteur_versets = itertools.count(1)


def creer_version(**champs):
    """Crée une version de test avec une empreinte SHA-256 unique et valide."""
    n = next(_compteur_versions)
    valeurs = {
        "version_source": "1.0",
        "nom_fichier": "quran-uthmani.xml",
        "empreinte_sha256": f"{n:064x}",
    }
    valeurs.update(champs)
    return VersionCorpus.objects.create(**valeurs)


def creer_sourate(version=None, **champs):
    """Crée une sourate de test ; numéro et ordre de révélation sont uniques par défaut."""
    n = next(_compteur_sourates)
    rang = (n - 1) % 114 + 1  # reste entre 1 et 114 même après de nombreux tests
    valeurs = {
        "version": version or creer_version(),
        "numero": rang,
        "nom_arabe": f"nom-arabe-de-test-{n}",
        "nom_translitteration": f"Sourate-test-{n}",
        "nombre_versets": 7,
        "type_revelation": Sourate.TypeRevelation.MECQUOISE,
        "ordre_revelation": rang,
    }
    valeurs.update(champs)
    return Sourate.objects.create(**valeurs)


def creer_verset(sourate=None, **champs):
    """Crée un verset de test ; le numéro est unique par défaut et le texte est neutre."""
    n = next(_compteur_versets)
    valeurs = {
        "sourate": sourate or creer_sourate(),
        "numero": n,
        "texte": f"texte-de-test-{n}",
    }
    valeurs.update(champs)
    return Verset.objects.create(**valeurs)
```

**Fichier `apps\coran\tests\test_immuabilite.py`**

```python
"""Tests de l'immuabilité du corpus (RM-27, §12.3).

Une version validée, active ou retirée est figée : son contenu (sourates, versets)
et son identité (empreinte, fichier...) ne changent plus. Toute correction passe
par une NOUVELLE version.

Aucun texte coranique n'est saisi dans ces tests.
"""
import pytest
from django.utils import timezone

from apps.coran.exceptions import CorpusImmuableError
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_verset, creer_version

Statut = VersionCorpus.Statut
STATUTS_FIGES = [Statut.VALIDEE, Statut.ACTIVE, Statut.RETIREE]


def version_avec_contenu(statut=Statut.IMPORTEE):
    """Crée une version avec une sourate et un verset, puis fixe son statut en base.

    On utilise update() pour préparer la situation sans passer par la garde,
    qui est précisément ce que ces tests vérifient.
    """
    version = creer_version()
    sourate = creer_sourate(version)
    verset = creer_verset(sourate)
    VersionCorpus.objects.filter(pk=version.pk).update(statut=statut)
    return version, sourate, verset


# --- Contenu d'une version figée : sourates ---------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_sourate_ne_peut_pas_etre_ajoutee_a_une_version_figee(statut):
    version, _, _ = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        creer_sourate(version)


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_sourate_d_une_version_figee_ne_peut_pas_etre_modifiee(statut):
    _, sourate, _ = version_avec_contenu(statut)
    sourate.nom_translitteration = "modifie"

    with pytest.raises(CorpusImmuableError):
        sourate.save()


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_sourate_d_une_version_figee_ne_peut_pas_etre_supprimee(statut):
    _, sourate, _ = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        sourate.delete()


# --- Contenu d'une version figée : versets ----------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_verset_ne_peut_pas_etre_ajoute_a_une_version_figee(statut):
    _, sourate, _ = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        creer_verset(sourate)


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_verset_d_une_version_figee_ne_peut_pas_etre_modifie(statut):
    _, _, verset = version_avec_contenu(statut)
    verset.texte = "modifie"

    with pytest.raises(CorpusImmuableError):
        verset.save()


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_verset_d_une_version_figee_ne_peut_pas_etre_supprime(statut):
    _, _, verset = version_avec_contenu(statut)

    with pytest.raises(CorpusImmuableError):
        verset.delete()


# --- Une version importée reste modifiable ----------------------------------


@pytest.mark.django_db
def test_version_importee_reste_modifiable():
    _, sourate, verset = version_avec_contenu(Statut.IMPORTEE)

    sourate.nom_translitteration = "modifie"
    sourate.save()
    verset.texte = "modifie"
    verset.save()
    creer_verset(sourate)
    verset.delete()

    assert sourate.versets.count() == 1


# --- Pièges : déplacements et objets périmés --------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut_depart, statut_arrivee",
    [(Statut.IMPORTEE, Statut.VALIDEE), (Statut.VALIDEE, Statut.IMPORTEE)],
)
def test_rm27_verset_ne_peut_pas_traverser_la_frontiere_d_une_version_figee(
    statut_depart, statut_arrivee
):
    """Sortir d'une version figée ou entrer dans une version figée : les deux sont refusés."""
    _, _, verset = version_avec_contenu(statut_depart)
    _, sourate_arrivee, _ = version_avec_contenu(statut_arrivee)
    verset.sourate = sourate_arrivee

    with pytest.raises(CorpusImmuableError):
        verset.save()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut_depart, statut_arrivee",
    [(Statut.IMPORTEE, Statut.VALIDEE), (Statut.VALIDEE, Statut.IMPORTEE)],
)
def test_rm27_sourate_ne_peut_pas_traverser_la_frontiere_d_une_version_figee(
    statut_depart, statut_arrivee
):
    _, sourate, _ = version_avec_contenu(statut_depart)
    version_arrivee, _, _ = version_avec_contenu(statut_arrivee)
    sourate.version = version_arrivee

    with pytest.raises(CorpusImmuableError):
        sourate.save()


@pytest.mark.django_db
def test_rm27_objet_perime_en_memoire_ne_contourne_pas_la_garde():
    """La garde lit l'état réel en base, pas le statut copié dans l'objet en mémoire."""
    _, _, verset = version_avec_contenu(Statut.IMPORTEE)
    assert verset.sourate.version.statut == Statut.IMPORTEE  # copie en mémoire

    # Pendant ce temps, la version est validée ailleurs (autre processus, autre requête).
    VersionCorpus.objects.filter(pk=verset.sourate.version_id).update(
        statut=Statut.VALIDEE
    )
    verset.texte = "modifie"

    with pytest.raises(CorpusImmuableError):
        verset.save()


# --- Identité d'une version figée -------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_empreinte_d_une_version_figee_ne_peut_pas_changer(statut):
    version = creer_version(statut=statut)
    version.empreinte_sha256 = "f" * 64

    with pytest.raises(CorpusImmuableError):
        version.save()


@pytest.mark.django_db
def test_rm27_version_obsolete_en_memoire_ne_contourne_pas_la_garde():
    version = creer_version()  # importée en mémoire
    VersionCorpus.objects.filter(pk=version.pk).update(statut=Statut.VALIDEE)
    version.empreinte_sha256 = "f" * 64

    with pytest.raises(CorpusImmuableError):
        version.save()


@pytest.mark.django_db
def test_enregistrer_sans_rien_changer_reste_possible_sur_une_version_figee():
    version = creer_version(statut=Statut.VALIDEE, date_validation=timezone.now())

    version.save()

    assert VersionCorpus.objects.get(pk=version.pk).statut == Statut.VALIDEE


@pytest.mark.django_db
@pytest.mark.parametrize("statut", STATUTS_FIGES)
def test_rm27_version_figee_ne_peut_pas_etre_supprimee(statut):
    version = creer_version(statut=statut)

    with pytest.raises(CorpusImmuableError):
        version.delete()


@pytest.mark.django_db
def test_version_importee_vide_peut_etre_supprimee():
    version = creer_version()

    version.delete()

    assert VersionCorpus.objects.count() == 0


# --- Transitions de statut --------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ancien, nouveau",
    [
        (Statut.IMPORTEE, Statut.VALIDEE),
        (Statut.VALIDEE, Statut.ACTIVE),
        (Statut.VALIDEE, Statut.RETIREE),
        (Statut.ACTIVE, Statut.RETIREE),
    ],
)
def test_transitions_de_statut_autorisees(ancien, nouveau):
    version = creer_version(statut=ancien, date_validation=timezone.now())

    version.statut = nouveau
    version.save()

    assert VersionCorpus.objects.get(pk=version.pk).statut == nouveau


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ancien, nouveau",
    [
        (Statut.VALIDEE, Statut.IMPORTEE),
        (Statut.ACTIVE, Statut.IMPORTEE),
        (Statut.ACTIVE, Statut.VALIDEE),
        (Statut.RETIREE, Statut.IMPORTEE),
        (Statut.RETIREE, Statut.VALIDEE),
        (Statut.RETIREE, Statut.ACTIVE),
        (Statut.IMPORTEE, Statut.ACTIVE),
        (Statut.IMPORTEE, Statut.RETIREE),
    ],
)
def test_rm27_transitions_de_statut_interdites(ancien, nouveau):
    """Surtout : revenir à « importée » dégèlerait le contenu d'une version déjà validée."""
    version = creer_version(statut=ancien, date_validation=timezone.now())
    version.statut = nouveau

    with pytest.raises(CorpusImmuableError):
        version.save()


@pytest.mark.django_db
def test_validation_sans_date_de_validation_refusee():
    """§12.2, point 7 : pas de validation sans procès-verbal du référent coranique."""
    version = creer_version()
    assert version.date_validation is None
    version.statut = Statut.VALIDEE

    with pytest.raises(CorpusImmuableError):
        version.save()
```

## Étape C — La plomberie dans les modèles

Remplacez `apps\coran\models.py` par ce fichier complet (les trois modèles, avec `save()` et `delete()` gardés) :

**Fichier `apps\coran\models.py`**

```python
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
```

Aucun champ n'a changé : `python manage.py makemigrations --check --dry-run` doit répondre `No changes detected`.

## Étape D — Constater l'état « rouge »

```powershell
pytest -q
```

Attendu : **39 failed, 46 passed**. Les 39 échecs sont tous dans `test_immuabilite.py` : ils attendent vos règles. Les 46 autres passent (les 39 anciens tests et 7 tests de la garde où « rien n'est interdit »).

## Étape E — À vous : écrire les deux règles (`TODO(human)`)

Dans `apps\coran\services.py`, écrivez le corps de :

- `verifier_transition_statut(ancien_statut, nouveau_statut, date_validation)` ;
- `verifier_ecriture_autorisee(statut_version)`.

Les tests dessinent la règle :

- **Quatre** transitions sont autorisées : importée → validée, validée → active, validée → retirée, active → retirée. Les **huit** autres sont interdites (surtout tout retour vers « importée »).
- Passer à « validée » **exige** une `date_validation` (le procès-verbal du référent coranique, §12.2 point 7).
- Trois statuts sont **figés** : validée, active, retirée.

**Indice :** pensez à un dictionnaire qui associe chaque statut à l'ensemble des statuts qu'il peut atteindre, puis testez `nouveau in ...`.

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
# Dans apps/coran/services.py, remplacez les deux fonctions vides par :

STATUTS_FIGES = {"validee", "active", "retiree"}

# Pour chaque statut : les statuts que l'on a le droit d'atteindre ensuite.
TRANSITIONS_AUTORISEES = {
    "importee": {"validee"},
    "validee": {"active", "retiree"},
    "active": {"retiree"},
    "retiree": set(),
}


def verifier_transition_statut(ancien_statut, nouveau_statut, date_validation):
    """Refuse un changement de statut d'une version du corpus qui n'est pas autorisé."""
    if nouveau_statut not in TRANSITIONS_AUTORISEES.get(ancien_statut, set()):
        raise CorpusImmuableError(
            f"Transition de statut interdite : « {ancien_statut} » vers « {nouveau_statut} »."
        )
    if nouveau_statut == "validee" and date_validation is None:
        raise CorpusImmuableError(
            "Une version ne peut pas être validée sans date de validation (procès-verbal du référent)."
        )


def verifier_ecriture_autorisee(statut_version):
    """Refuse toute écriture sur le contenu d'une version dont le statut est figé."""
    if statut_version in STATUTS_FIGES:
        raise CorpusImmuableError(
            f"Version « {statut_version} » : son contenu est figé. "
            "Pour corriger, importez une nouvelle version."
        )
```

</details>

```powershell
pytest apps\coran\tests\test_immuabilite.py
pytest
```

Attendu : **85 passed**.

```powershell
git add apps
git commit -m "Corpus : garde d'immuabilité des versions validées"
```

## Questions de compréhension

1. Pourquoi une version doit-elle passer par « validée » avant de devenir « active » ?
2. Dans `save()`, pourquoi lit-on le statut dans la **base** plutôt que dans `self.sourate.version.statut` ?
3. Pourquoi les règles sont-elles dans `services.py` (sans base de données) et la plomberie dans les modèles ?

<details>
<summary>Réponses</summary>

1. Parce que la validation est l'acte du référent coranique (procès-verbal) qui atteste que le texte est exact. Activer une version non validée ferait servir en concours un texte que personne n'a certifié.
2. L'objet en mémoire peut être périmé : un autre processus a pu valider la version entre-temps. Seule la base dit la vérité à l'instant de l'écriture.
3. Une règle pure est testable sans base, donc rapidement, et ne dépend d'aucun modèle (pas d'import circulaire). Le modèle sait *quand* appeler la règle ; le service sait *quoi* décider.
</details>

## Journal d'apprentissage

Expliquez, avec vos mots, pourquoi on ne corrige jamais un verset directement en base, et la procédure correcte (nouvelle version, validation du référent, activation pour les nouveaux concours).
