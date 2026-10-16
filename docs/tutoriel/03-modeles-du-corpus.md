# Chapitre 3 — Les modèles du corpus coranique

> **Étape du plan :** 0.3 · **Durée :** 2 à 3 heures · **Commits de référence :** `1886611` (VersionCorpus), `ffff712` (Sourate), `8d7ad00` (Verset) · **Résultat :** trois modèles, leurs contraintes en base de données, 39 tests verts.

## Objectif

Stocker le corpus coranique de façon **fiable** : une *version* identifiée (source, empreinte, statut), ses *sourates*, et leurs *versets*. Les règles d'intégrité sont posées **dans la base de données** : même une erreur de code ne peut pas les violer.

Deux règles absolues guident ce chapitre :

- **Règle n°1** : le texte coranique n'est jamais saisi, corrigé ni normalisé. Il vient uniquement du fichier Tanzil. Les tests n'utilisent donc **jamais** de vrais versets : des textes neutres comme `texte-de-test-1`.
- **RM-27 / §12.3** : une version validée est immuable. Ce chapitre prépare le terrain (statuts) ; le chapitre 4 applique l'immuabilité.

## Méthode (à répéter pour chaque modèle)

1. Écrire les **tests** d'abord ; les lancer ; constater qu'ils échouent.
2. Écrire le **modèle** ; `makemigrations` ; relancer : tout passe.
3. Committer.

## Étape A — Préparer l'application `coran`

```powershell
New-Item -ItemType Directory apps\coran\tests | Out-Null
New-Item -ItemType File apps\__init__.py, apps\coran\__init__.py, apps\coran\tests\__init__.py | Out-Null
```

Dans `config\settings\base.py`, deux modifications :

1. Dans `INSTALLED_APPS`, après `"channels",` ajoutez `"apps.coran",` :

```python
    "channels",
    "apps.coran",
]
```

2. Fuseau horaire des concours (Côte d'Ivoire) :

```python
TIME_ZONE = "Africa/Abidjan"
```

**Fichier `apps\coran\apps.py`**

```python
from django.apps import AppConfig


class CoranConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.coran"
    label = "coran"
    verbose_name = "Corpus coranique"
```

## Étape B — `VersionCorpus`

### B.1 Les tests d'abord

**Fichier `apps\coran\tests\test_version_corpus.py`**

```python
"""Tests du modèle VersionCorpus (cf. §12.3 : versionnement du corpus)."""
import itertools

import pytest
from django.db import IntegrityError, transaction

from apps.coran.models import VersionCorpus

_compteur = itertools.count(1)


def creer_version(**champs):
    """Crée une version de test avec une empreinte SHA-256 unique et valide."""
    n = next(_compteur)
    valeurs = {
        "version_source": "1.0",
        "nom_fichier": "quran-uthmani.xml",
        "empreinte_sha256": f"{n:064x}",
    }
    valeurs.update(champs)
    return VersionCorpus.objects.create(**valeurs)


@pytest.mark.django_db
def test_statut_initial_est_importee():
    version = creer_version()

    assert version.statut == VersionCorpus.Statut.IMPORTEE


@pytest.mark.django_db
def test_riwaya_par_defaut_est_hafs():
    version = creer_version()

    assert version.riwaya == VersionCorpus.Riwaya.HAFS


@pytest.mark.django_db
def test_empreinte_unique():
    version = creer_version()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(empreinte_sha256=version.empreinte_sha256)


@pytest.mark.django_db
@pytest.mark.parametrize("empreinte", ["abc", "g" * 64, "A" * 64, "a" * 63])
def test_empreinte_doit_etre_un_sha256_hexadecimal_minuscule(empreinte):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(empreinte_sha256=empreinte)


@pytest.mark.django_db
def test_une_seule_version_active_par_riwaya():
    creer_version(statut=VersionCorpus.Statut.ACTIVE)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(statut=VersionCorpus.Statut.ACTIVE)


@pytest.mark.django_db
def test_une_nouvelle_version_peut_etre_active_apres_retrait_de_l_ancienne():
    ancienne = creer_version(statut=VersionCorpus.Statut.ACTIVE)
    ancienne.statut = VersionCorpus.Statut.RETIREE
    ancienne.save()

    nouvelle = creer_version(statut=VersionCorpus.Statut.ACTIVE)

    assert nouvelle.statut == VersionCorpus.Statut.ACTIVE


@pytest.mark.django_db
def test_plusieurs_versions_validees_peuvent_coexister():
    creer_version(statut=VersionCorpus.Statut.VALIDEE)
    creer_version(statut=VersionCorpus.Statut.VALIDEE)

    assert VersionCorpus.objects.filter(statut=VersionCorpus.Statut.VALIDEE).count() == 2
```

```powershell
pytest apps
```

Attendu : une erreur `No module named 'apps.coran.models'`. C'est normal.

### B.2 Le modèle

**Fichier `apps\coran\models.py`**

```python
"""Modèles du corpus coranique (cf. §12 et §14 du cahier des charges).

Le texte coranique vient uniquement du fichier Tanzil importé : il n'est jamais
saisi, corrigé ni normalisé depuis l'application (règle absolue n°1).
"""
from django.db import models
from django.db.models import Q


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
```

```powershell
python manage.py makemigrations coran
python manage.py check
pytest
python manage.py migrate
```

Attendu : `0001_initial.py` créé (`Create model VersionCorpus`), puis **11 passed** (le test d'accueil et 10 nouveaux).

```powershell
git add apps config\settings\base.py
git commit -m "Corpus : application coran et modèle VersionCorpus avec ses tests"
```

**À retenir**

- `UniqueConstraint(fields=["riwaya"], condition=Q(statut="active"))` : « une seule version active par riwāya ». Avec `unique=True` sur `statut`, il n'y aurait qu'**une seule** version « validée », qu'**une seule** « retirée »... : la condition restreint l'unicité aux lignes **actives**. PostgreSQL l'implémente comme un *index unique partiel*.
- `CheckConstraint(... regex ...)` : l'empreinte doit être 64 caractères hexadécimaux en minuscules (un SHA-256).
- `condition=` remplace l'ancien `check=` depuis Django 5.1.

## Étape C — `Sourate`

### C.1 Les outils de test partagés et les tests

On sort la fabrique de versions de test dans un module commun. Créez :

**Fichier `apps\coran\tests\outils.py`**

```python
"""Fonctions utilitaires partagées par les tests de l'application coran."""
import itertools

from apps.coran.models import Sourate, VersionCorpus

_compteur_versions = itertools.count(1)
_compteur_sourates = itertools.count(1)


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
    valeurs = {
        "version": version or creer_version(),
        "numero": n,
        "nom_arabe": f"nom-arabe-de-test-{n}",
        "nom_translitteration": f"Sourate-test-{n}",
        "nombre_versets": 7,
        "type_revelation": Sourate.TypeRevelation.MECQUOISE,
        "ordre_revelation": n,
    }
    valeurs.update(champs)
    return Sourate.objects.create(**valeurs)
```

Remplacez le début de `test_version_corpus.py` (les imports, le compteur et la fonction `creer_version`) par l'import de l'outil : voici le fichier complet à ce stade.

**Fichier `apps\coran\tests\test_version_corpus.py`**

```python
"""Tests du modèle VersionCorpus (cf. §12.3 : versionnement du corpus)."""
import pytest
from django.db import IntegrityError, transaction

from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_version


@pytest.mark.django_db
def test_statut_initial_est_importee():
    version = creer_version()

    assert version.statut == VersionCorpus.Statut.IMPORTEE


@pytest.mark.django_db
def test_riwaya_par_defaut_est_hafs():
    version = creer_version()

    assert version.riwaya == VersionCorpus.Riwaya.HAFS


@pytest.mark.django_db
def test_empreinte_unique():
    version = creer_version()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(empreinte_sha256=version.empreinte_sha256)


@pytest.mark.django_db
@pytest.mark.parametrize("empreinte", ["abc", "g" * 64, "A" * 64, "a" * 63])
def test_empreinte_doit_etre_un_sha256_hexadecimal_minuscule(empreinte):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(empreinte_sha256=empreinte)


@pytest.mark.django_db
def test_une_seule_version_active_par_riwaya():
    creer_version(statut=VersionCorpus.Statut.ACTIVE)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(statut=VersionCorpus.Statut.ACTIVE)


@pytest.mark.django_db
def test_une_nouvelle_version_peut_etre_active_apres_retrait_de_l_ancienne():
    ancienne = creer_version(statut=VersionCorpus.Statut.ACTIVE)
    ancienne.statut = VersionCorpus.Statut.RETIREE
    ancienne.save()

    nouvelle = creer_version(statut=VersionCorpus.Statut.ACTIVE)

    assert nouvelle.statut == VersionCorpus.Statut.ACTIVE


@pytest.mark.django_db
def test_plusieurs_versions_validees_peuvent_coexister():
    creer_version(statut=VersionCorpus.Statut.VALIDEE)
    creer_version(statut=VersionCorpus.Statut.VALIDEE)

    assert VersionCorpus.objects.filter(statut=VersionCorpus.Statut.VALIDEE).count() == 2
```

**Fichier `apps\coran\tests\test_sourate.py`**

```python
"""Tests du modèle Sourate (cf. §12.2, §12.4 et REC-30).

Aucun texte coranique n'est saisi dans ces tests : les valeurs sont des
chaînes de test neutres.
"""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.coran.models import Sourate
from apps.coran.tests.outils import creer_sourate, creer_version


@pytest.mark.django_db
def test_numero_unique_par_version():
    version = creer_version()
    creer_sourate(version, numero=2, ordre_revelation=87)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(version, numero=2, ordre_revelation=88)


@pytest.mark.django_db
def test_meme_numero_possible_dans_deux_versions():
    creer_sourate(creer_version(), numero=2, ordre_revelation=87)
    creer_sourate(creer_version(), numero=2, ordre_revelation=87)

    assert Sourate.objects.filter(numero=2).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [0, 115])
def test_rec31_numero_de_sourate_hors_bornes_refuse(numero):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(numero=numero)


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [1, 114])
def test_numeros_limites_acceptes(numero):
    sourate = creer_sourate(numero=numero)

    assert sourate.numero == numero


@pytest.mark.django_db
def test_ordre_revelation_unique_par_version():
    version = creer_version()
    creer_sourate(version, numero=1, ordre_revelation=5)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(version, numero=2, ordre_revelation=5)


@pytest.mark.django_db
@pytest.mark.parametrize("ordre", [0, 115])
def test_ordre_revelation_hors_bornes_refuse(ordre):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(ordre_revelation=ordre)


@pytest.mark.django_db
def test_nombre_de_versets_doit_etre_au_moins_un():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(nombre_versets=0)


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [1, 9])
def test_rm_sourates_1_et_9_sans_basmala_numerotee(numero):
    """§12.4 : la sourate 9 n'a pas de basmala et celle de la sourate 1 est le verset 1:1."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(numero=numero, basmala="basmala-de-test")


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [1, 9])
def test_sourates_1_et_9_acceptees_sans_basmala(numero):
    sourate = creer_sourate(numero=numero)

    assert sourate.basmala == ""


@pytest.mark.django_db
def test_une_autre_sourate_peut_porter_une_basmala():
    sourate = creer_sourate(numero=2, basmala="basmala-de-test")

    assert sourate.basmala == "basmala-de-test"


@pytest.mark.django_db
def test_une_version_ne_peut_pas_etre_supprimee_si_elle_a_des_sourates():
    sourate = creer_sourate()

    with pytest.raises(ProtectedError):
        sourate.version.delete()
```

```powershell
pytest apps
```

Attendu : `cannot import name 'Sourate'`.

### C.2 Le modèle

**À la fin de `apps\coran\models.py`**, ajoutez la classe `Sourate` :

```python

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
```

```powershell
python manage.py makemigrations coran
python manage.py check
pytest
python manage.py migrate
```

Attendu : `0002_sourate.py`, puis **27 passed**.

```powershell
git add apps
git commit -m "Corpus : modèle Sourate avec contraintes et tests"
```

**À retenir**

- **`on_delete=PROTECT`** : supprimer une version n'emporte jamais ses sourates (jamais de cascade sur le corpus).
- **`~Q(numero__in=[1, 9]) | Q(basmala="")`** se lit : « le numéro n'est pas 1 ou 9, **ou** la basmala est vide ». Donc : une basmala remplie est **interdite** pour les sourates 1 et 9 (§12.4) ; les autres sourates peuvent en porter une.
- Pourquoi cette règle dans la **base** et pas dans une vérification Python à l'import ? Parce que **tous les chemins d'écriture passent par la base** : l'administration, un script, un `update()`, un futur développeur. Une vérification Python ne protège que le code qui l'appelle.
- **`type_revelation`** : Tanzil écrit `Meccan` / `Medinan` ; le projet stocke `mecquoise` / `medinoise`. La conversion se fait à l'import (chapitre 6).

## Étape D — `Verset`

### D.1 Les tests

Mettez à jour `apps\coran\tests\outils.py` (une fonction `creer_verset` est ajoutée) :

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
    valeurs = {
        "version": version or creer_version(),
        "numero": n,
        "nom_arabe": f"nom-arabe-de-test-{n}",
        "nom_translitteration": f"Sourate-test-{n}",
        "nombre_versets": 7,
        "type_revelation": Sourate.TypeRevelation.MECQUOISE,
        "ordre_revelation": n,
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

**Fichier `apps\coran\tests\test_verset.py`**

```python
"""Tests du modèle Verset (cf. §12.2, §12.4, REC-30 et REC-31).

Aucun texte coranique n'est saisi dans ces tests : les valeurs sont des
chaînes de test neutres.
"""
import unicodedata

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.coran.models import Verset
from apps.coran.tests.outils import creer_sourate, creer_verset


@pytest.mark.django_db
def test_numero_de_verset_unique_par_sourate():
    sourate = creer_sourate()
    creer_verset(sourate, numero=255)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_verset(sourate, numero=255)


@pytest.mark.django_db
def test_meme_numero_possible_dans_deux_sourates():
    creer_verset(creer_sourate(), numero=1)
    creer_verset(creer_sourate(), numero=1)

    assert Verset.objects.filter(numero=1).count() == 2


@pytest.mark.django_db
def test_rec31_verset_numero_zero_refuse():
    """REC-31 : « 1:0 » est refusé."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_verset(numero=0)


@pytest.mark.django_db
@pytest.mark.parametrize("texte", ["", " ", "   ", "\t", "\n"])
def test_rec30_verset_vide_refuse(texte):
    """REC-30 : absence de verset vide (y compris composé uniquement d'espaces)."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_verset(texte=texte)


@pytest.mark.django_db
def test_regle_absolue_1_texte_stocke_sans_normalisation_unicode():
    """Le texte est conservé octet pour octet : aucune normalisation Unicode (§12.2).

    « e » suivi de l'accent combinant (forme NFD) ne doit pas devenir « é » (NFC).
    """
    texte_nfd = "é texte de test "
    assert unicodedata.normalize("NFC", texte_nfd) != texte_nfd

    verset = creer_verset(texte=texte_nfd)
    verset.refresh_from_db()

    assert verset.texte == texte_nfd
    assert verset.texte.encode("utf-8") == texte_nfd.encode("utf-8")


@pytest.mark.django_db
def test_une_sourate_ne_peut_pas_etre_supprimee_si_elle_a_des_versets():
    verset = creer_verset()

    with pytest.raises(ProtectedError):
        verset.sourate.delete()


@pytest.mark.django_db
def test_versets_ordonnes_dans_l_ordre_canonique():
    sourate_2 = creer_sourate(numero=2, ordre_revelation=87)
    sourate_1 = creer_sourate(sourate_2.version, numero=1, ordre_revelation=5)
    creer_verset(sourate_2, numero=1)
    creer_verset(sourate_1, numero=3)
    creer_verset(sourate_2, numero=2)
    creer_verset(sourate_1, numero=1)

    references = [(v.sourate.numero, v.numero) for v in Verset.objects.all()]

    assert references == [(1, 1), (1, 3), (2, 1), (2, 2)]


@pytest.mark.django_db
def test_reference_au_format_sourate_verset():
    verset = creer_verset(creer_sourate(numero=2, ordre_revelation=87), numero=255)

    assert verset.reference == "2:255"
```

```powershell
pytest apps
```

Attendu : `cannot import name 'Verset'`.

### D.2 Le modèle

**À la fin de `apps\coran\models.py`**, ajoutez la classe `Verset` :

```python

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
```

```powershell
python manage.py makemigrations coran
python manage.py check
pytest
python manage.py migrate
```

Attendu : `0003_verset.py`, puis **39 passed**.

```powershell
git add apps
git commit -m "Corpus : modèle Verset avec contraintes et tests"
```

**À retenir**

- **`texte__regex=r"\S"`** : au moins un caractère non blanc. `texte != ""` laisserait passer `"   "`. La contrainte **ne modifie pas** le texte : elle refuse seulement les valeurs vides (REC-30).
- **`ordering = ["sourate__numero", "numero"]`** : l'ordre canonique (sourate puis verset). L'ordre d'insertion (`id`) ne serait pas fiable.
- **Aucune version sur `Verset`** : elle passe par `sourate.version`. Un seul endroit à tenir à jour.
- **Le test Unicode** utilise « e » plus un accent combinant (forme NFD) : une chaîne qui **changerait** si quelqu'un normalisait le texte. Le test sert de détecteur : ce qu'on écrit est exactement ce qu'on relit. Il ne tape aucun verset (règle n°1).

## Questions de compréhension

1. Pourquoi un simple `unique=True` sur `statut` ne convient-il pas pour « une seule version active par riwāya » ?
2. Pourquoi l'utilisateur `quranova` a-t-il besoin du droit `CREATEDB`, et que risqueriez-vous si les tests tournaient sur la vraie base ?
3. Pourquoi le test d'absence de normalisation Unicode utilise-t-il `e` + accent combinant plutôt qu'un vrai verset ?
4. Qu'est-ce que `PROTECT` empêche, et pourquoi est-ce important pour un corpus ?

<details>
<summary>Réponses</summary>

1. `unique=True` contraint **toutes** les lignes : il n'y aurait qu'une version par valeur de statut. Une `UniqueConstraint` avec `condition` ne contraint qu'un **sous-ensemble** (les lignes actives).
2. pytest-django crée une base temporaire `test_quranova`, applique les migrations et la supprime à la fin ; il faut donc le droit de créer des bases. Sur la vraie base, les tests créeraient et supprimeraient des données réelles.
3. Un bon test doit pouvoir échouer. « e » + accent combinant est une chaîne qui serait **modifiée** par une normalisation Unicode, donc le test détecte toute normalisation. Et la règle n°1 interdit de saisir du texte coranique, même dans un test.
4. `PROTECT` empêche de supprimer une ligne qui est référencée ailleurs. Une suppression en cascade effacerait silencieusement des sourates, puis des versets : on perdrait le texte de référence.
</details>

## Journal d'apprentissage

Notez ce qu'est une contrainte de base de données, pourquoi on la préfère à une vérification Python seule, et ce qu'apporte une contrainte conditionnelle.
