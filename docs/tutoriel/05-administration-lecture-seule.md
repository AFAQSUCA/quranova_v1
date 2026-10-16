# Chapitre 5 — L'administration du corpus en lecture seule

> **Étape du plan :** 0.3 (fin) · **Durée :** 45 minutes · **Commit de référence :** `569bf9f` · **Résultat :** l'interface d'administration de Django affiche le corpus, mais personne ne peut le modifier.

## Objectif

Respecter le §12.1 (« aucun compte d'organisation ne peut importer ni modifier de texte coranique ») et le §14.2 (« les données du corpus ne peuvent pas être modifiées depuis l'application »). **Même un superutilisateur** ne peut ni ajouter, ni modifier, ni supprimer : le texte vient uniquement de la commande d'import (chapitre 6).

## Étape A — Les tests d'abord

**Fichier `apps\coran\tests\test_admin.py`**

```python
"""Tests de l'administration du corpus : lecture seule pour tout le monde (§12.3).

« Aucun compte d'organisation ne peut importer ni modifier de texte coranique »
(§12.1) et « les données du corpus ne peuvent pas être modifiées depuis
l'application » (§14.2). Même un superutilisateur ne peut ni ajouter, ni modifier,
ni supprimer : le texte vient uniquement de la commande d'import.

Aucun texte coranique n'est saisi dans ces tests.
"""
import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from apps.coran.models import Sourate, Verset, VersionCorpus
from apps.coran.tests.outils import creer_verset

MODELES = [VersionCorpus, Sourate, Verset]


def _requete(utilisateur):
    requete = RequestFactory().get("/admin/")
    requete.user = utilisateur
    return requete


def _nom_url(modele, action):
    return f"admin:{modele._meta.app_label}_{modele._meta.model_name}_{action}"


@pytest.fixture
def verset(db):
    return creer_verset()


@pytest.mark.parametrize("modele", MODELES)
def test_modele_enregistre_dans_l_administration(modele):
    assert modele in admin.site._registry


@pytest.mark.django_db
@pytest.mark.parametrize("modele", MODELES)
def test_aucune_permission_d_ecriture_meme_pour_un_superutilisateur(modele, admin_user):
    modele_admin = admin.site._registry[modele]
    requete = _requete(admin_user)

    assert admin_user.is_superuser
    assert modele_admin.has_view_permission(requete) is True
    assert modele_admin.has_add_permission(requete) is False
    assert modele_admin.has_change_permission(requete) is False
    assert modele_admin.has_delete_permission(requete) is False


@pytest.mark.django_db
@pytest.mark.parametrize("modele", MODELES)
def test_la_liste_est_consultable(modele, admin_client, verset):
    reponse = admin_client.get(reverse(_nom_url(modele, "changelist")))

    assert reponse.status_code == 200


@pytest.mark.django_db
def test_la_fiche_d_un_verset_est_consultable(admin_client, verset):
    reponse = admin_client.get(reverse(_nom_url(Verset, "change"), args=[verset.pk]))

    assert reponse.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("modele", MODELES)
def test_la_page_d_ajout_est_refusee(modele, admin_client):
    reponse = admin_client.get(reverse(_nom_url(modele, "add")))

    assert reponse.status_code == 403


@pytest.mark.django_db
def test_la_modification_est_refusee_et_le_texte_reste_intact(admin_client, verset):
    texte_avant = verset.texte

    reponse = admin_client.post(
        reverse(_nom_url(Verset, "change"), args=[verset.pk]),
        {"sourate": verset.sourate_id, "numero": verset.numero, "texte": "modifie"},
    )
    verset.refresh_from_db()

    assert reponse.status_code == 403
    assert verset.texte == texte_avant


@pytest.mark.django_db
def test_la_suppression_est_refusee(admin_client, verset):
    url = reverse(_nom_url(Verset, "delete"), args=[verset.pk])

    assert admin_client.get(url).status_code == 403
    assert admin_client.post(url, {"post": "yes"}).status_code == 403
    assert Verset.objects.filter(pk=verset.pk).exists()


@pytest.mark.django_db
def test_pas_d_action_de_suppression_en_masse(admin_client, admin_user, verset):
    modele_admin = admin.site._registry[Verset]
    assert "delete_selected" not in modele_admin.get_actions(_requete(admin_user))

    admin_client.post(
        reverse(_nom_url(Verset, "changelist")),
        {"action": "delete_selected", "_selected_action": [verset.pk], "post": "yes"},
    )

    assert Verset.objects.filter(pk=verset.pk).exists()
```

Ces tests utilisent `admin_client` et `admin_user`, fournis par pytest-django. Pour qu'ils ne soient pas lents (le hachage de mot de passe de Django est volontairement coûteux), ajoutez à la **racine du projet** :

**Fichier `conftest.py`**

```python
"""Réglages communs à tous les tests (lus automatiquement par pytest)."""
import pytest


@pytest.fixture(autouse=True)
def hachage_rapide(settings):
    """Utilise un hachage de mot de passe rapide pendant les tests.

    Le hachage normal de Django est volontairement lent (protection contre le
    piratage), ce qui ralentirait chaque test qui crée un utilisateur. Ce réglage
    ne s'applique qu'aux tests, jamais au vrai serveur.
    """
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
```

```powershell
pytest apps\coran\tests\test_admin.py
```

Attendu : 16 échecs (rien n'est encore enregistré dans l'administration).

## Étape B — L'administration

**Fichier `apps\coran\admin.py`**

```python
"""Administration du corpus coranique : consultation seulement (§12.1, §12.3, §14.2).

Le texte coranique vient uniquement du fichier Tanzil, par la commande d'import.
Personne, pas même un superutilisateur, ne peut l'ajouter, le modifier ni le
supprimer depuis l'interface d'administration.
"""
from django.contrib import admin

from apps.coran.models import Sourate, Verset, VersionCorpus


class LectureSeuleAdmin(admin.ModelAdmin):
    """Base commune : on peut consulter, jamais écrire.

    Quand ``has_change_permission`` renvoie False mais que la permission de
    consultation est accordée, Django affiche la fiche en lecture seule. Retirer
    ``has_delete_permission`` supprime aussi l'action « Supprimer la sélection ».
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VersionCorpus)
class VersionCorpusAdmin(LectureSeuleAdmin):
    list_display = ("source", "version_source", "riwaya", "statut", "date_import", "date_validation")
    list_filter = ("statut", "riwaya")


@admin.register(Sourate)
class SourateAdmin(LectureSeuleAdmin):
    list_display = ("numero", "nom_translitteration", "nom_arabe", "nombre_versets", "type_revelation", "version")
    list_filter = ("version", "type_revelation")
    list_select_related = ("version",)
    search_fields = ("nom_translitteration", "nom_arabe")


@admin.register(Verset)
class VersetAdmin(LectureSeuleAdmin):
    list_display = ("reference", "sourate")
    list_filter = ("sourate__version", "sourate")
    list_select_related = ("sourate",)
    show_full_result_count = False  # évite un COUNT(*) coûteux sur 6 236 lignes par version
```

```powershell
python manage.py check
pytest apps\coran\tests\test_admin.py
```

Attendu : **16 passed**, en environ une seconde.

```powershell
git add apps conftest.py
git commit -m "Corpus : administration en lecture seule et tests"
```

## Pour comprendre

- **`has_*_permission` qui renvoie `False`** : s'applique **même au superutilisateur**. Django consulte d'abord ces méthodes.
- **Lecture seule** : si on interdit la modification mais qu'on garde la consultation, la fiche s'affiche en lecture seule ; les pages « ajouter » et « supprimer » répondent **403**. L'action « Supprimer la sélection » disparaît.
- **`list_select_related`** : évite une requête SQL par ligne pour afficher la sourate d'un verset.
- **`MD5PasswordHasher` dans `conftest.py`** : réservé aux tests ; le vrai serveur garde le hachage lent et sûr.
- Les tests **ne tapent aucun verset** : ils vérifient qu'une tentative de modification renvoie 403 et que le texte reste identique.

## Voir le résultat dans le navigateur

```powershell
python manage.py createsuperuser
python manage.py runserver
```

Ouvrez http://127.0.0.1:8000/admin/ : la section « Corpus coranique » montre les listes, **sans** bouton d'ajout ni de suppression. Les tables sont vides tant que le corpus n'est pas importé (chapitre 6).

> Au chapitre 9, le projet adopte un utilisateur personnalisé : la base de développement sera alors recréée, et vous referez `createsuperuser`.

## Questions de compréhension

1. Pourquoi retire-t-on aussi `has_delete_permission` pour supprimer l'action de suppression en masse ?
2. Pourquoi l'administration en lecture seule ne suffit-elle pas, à elle seule, à protéger le corpus ?

<details>
<summary>Réponses</summary>

1. Django n'affiche l'action « Supprimer la sélection » que si l'utilisateur a la permission de suppression ; sans elle, l'action n'est plus proposée (et un POST forgé est ignoré).
2. Elle ne protège que l'interface d'administration. Un script, la console ou un `update()` en masse contournent l'administration ; d'où la garde d'immuabilité des modèles (chapitre 4), et plus tard un déclencheur PostgreSQL.
</details>

## Journal d'apprentissage

Notez la différence entre masquer un bouton et refuser côté serveur (règle absolue n°4 : les permissions se vérifient côté serveur).
