# Chapitre 11 — Jurés, codes d'accès et import CSV des candidats

> **Étape du plan :** 1.2, troisième lot (fin de l'itération 1) · **Durée :** 4 à 5 heures · **Commit de référence :** `d561fec` · **Résultat :** l'application `jury`, la commande `importer_candidats`, **52 nouveaux tests**.

## Objectif

1. **Jurés** : `Jure`, `AffectationJury` (un juré est affecté à des épreuves), `CodeAccesJure` (le code personnel avec lequel le juré se connecte sur sa tablette).
2. **Import CSV** des candidats (§7.3) : contrôle des doublons, rapport d'erreurs, simulation.

| Règle | Où elle est appliquée |
|---|---|
| **D4** : un juré n'a pas de compte Django | aucun champ `utilisateur`/`email`/`password` sur `Jure` (un test le vérifie) |
| **D5** : affectation toujours au niveau de l'épreuve | `services.affecter` crée une ligne par épreuve, qu'on vise le concours, une catégorie ou une épreuve |
| **RM-20** : séparation des clients | `PARENTS_CLIENT` sur les modèles + contrôle dans les services |
| **§7.4** : code personnel à durée limitée | `CodeAccesJure.valide_du / valide_jusqu_au`, révocation |
| **§7.3** : doublons et rapport d'erreurs | module `importation.py` |

## Décisions de ce lot

| N° | Décision |
|---|---|
| D21 | Import **tout ou rien** : toutes les lignes sont contrôlées avant toute écriture ; le rapport liste **toutes** les erreurs avec leur numéro de ligne ; `--dry-run` simule. CSV uniquement (Excel `.xlsx` demanderait la dépendance `openpyxl`, à valider d'abord). |
| D22 | Doublon = même nom + prénom (casse ignorée) + même date de naissance, **chez le même client**. Candidat existant réutilisé ; même personne dans deux catégories = un `Candidat`, deux `Participation`. |
| D23 | `CodeAccesJure` vit dans `jury` (évite une dépendance circulaire). Le code n'est **jamais stocké** : seule son empreinte HMAC-SHA256 l'est. Un seul code actif par juré et par session. |

## Étape A — Dossiers et réglages

```powershell
New-Item -ItemType Directory "apps\jury\tests" -Force | Out-Null
New-Item -ItemType File "apps\jury\__init__.py", "apps\jury\tests\__init__.py" -Force | Out-Null
New-Item -ItemType Directory "apps\candidats\management\commands" -Force | Out-Null
New-Item -ItemType File "apps\candidats\management\__init__.py", "apps\candidats\management\commands\__init__.py" -Force | Out-Null
```

Dans `config\settings\base.py`, ajoutez `"apps.jury",` à `INSTALLED_APPS` (après `apps.candidats`).

## Étape B — La fabrique de jurés

Ajoutez en haut de `apps\commun\tests\outils.py` l'import `from apps.jury.models import Jure` et cette fonction :

```python
def creer_jure(organisation=None, **champs):
    n = next(_compteur)
    valeurs = {
        "organisation": organisation or creer_organisation(),
        "nom": f"Juré{n}",
        "prenom": f"Prénom{n}",
    }
    valeurs.update(champs)
    return Jure.objects.create(**valeurs)
```

> Si votre copie diffère, le fichier de référence est `git show d561fec:apps/commun/tests/outils.py`.

## Étape C — Les tests d'abord (jurés)

**Fichier `apps\jury\tests\test_modeles.py`**

```python
"""Tests des modèles Jure, AffectationJury et CodeAccesJure (§7.4, §6.3 ; D4, D5)."""
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import (
    creer_epreuve,
    creer_jure,
    creer_organisation,
    creer_session,
)
from apps.jury.models import AffectationJury, CodeAccesJure, Jure


# --- Jure --------------------------------------------------------------------


@pytest.mark.django_db
def test_valeurs_par_defaut_d_un_jure():
    jure = creer_jure()

    assert jure.role == Jure.Role.MEMBRE
    assert jure.actif is True
    assert jure.competences == ""


@pytest.mark.django_db
def test_un_jure_n_a_pas_de_compte_django():
    """D4 : les jurés ne se connectent pas par compte, mais par un code de session (§7.4)."""
    champs = {f.name for f in Jure._meta.get_fields()}

    assert not ({"username", "password", "email", "user", "utilisateur"} & champs)


@pytest.mark.django_db
def test_nom_complet():
    assert creer_jure(nom="Traoré", prenom="Ibrahim").nom_complet == "Ibrahim Traoré"


@pytest.mark.django_db
def test_nom_et_prenom_uniques_par_organisation():
    organisation = creer_organisation()
    creer_jure(organisation, nom="Traoré", prenom="Ibrahim")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_jure(organisation, nom="Traoré", prenom="Ibrahim")
    creer_jure(creer_organisation(), nom="Traoré", prenom="Ibrahim")  # un autre client : accepté


# --- Affectation (D5 : toujours au niveau épreuve) ----------------------------


@pytest.mark.django_db
def test_un_jure_est_affecte_a_une_epreuve():
    epreuve = creer_epreuve()
    jure = creer_jure(epreuve.organisation)

    affectation = AffectationJury.objects.create(jure=jure, epreuve=epreuve)

    assert affectation in jure.affectations.all()
    assert affectation in epreuve.affectations_jury.all()


@pytest.mark.django_db
def test_un_jure_n_est_affecte_qu_une_fois_a_une_epreuve():
    epreuve = creer_epreuve()
    jure = creer_jure(epreuve.organisation)
    AffectationJury.objects.create(jure=jure, epreuve=epreuve)

    with pytest.raises(IntegrityError), transaction.atomic():
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)


@pytest.mark.django_db
def test_rm20_un_jure_d_un_autre_client_ne_peut_pas_etre_affecte():
    epreuve = creer_epreuve()
    jure_d_ailleurs = creer_jure(creer_organisation())

    with pytest.raises(IncoherenceOrganisationError):
        AffectationJury.objects.create(jure=jure_d_ailleurs, epreuve=epreuve)


@pytest.mark.django_db
def test_une_epreuve_ne_peut_pas_etre_supprimee_si_elle_a_des_jures_affectes():
    epreuve = creer_epreuve()
    AffectationJury.objects.create(jure=creer_jure(epreuve.organisation), epreuve=epreuve)

    with pytest.raises(ProtectedError):
        epreuve.delete()


# --- Code d'accès -------------------------------------------------------------


def un_code(jure, session, **champs):
    maintenant = timezone.now()
    valeurs = {
        "jure": jure,
        "session": session,
        "empreinte": "a" * 64,
        "valide_du": maintenant,
        "valide_jusqu_au": maintenant + timedelta(hours=12),
    }
    valeurs.update(champs)
    return CodeAccesJure.objects.create(**valeurs)


@pytest.mark.django_db
def test_le_code_prend_l_organisation_du_jure_et_de_la_session():
    session = creer_session()
    jure = creer_jure(session.organisation)

    assert un_code(jure, session).organisation_id == session.organisation_id


@pytest.mark.django_db
def test_rm20_un_code_ne_relie_pas_un_jure_a_la_session_d_un_autre_client():
    with pytest.raises(IncoherenceOrganisationError):
        un_code(creer_jure(creer_organisation()), creer_session())


@pytest.mark.django_db
def test_la_fin_de_validite_suit_le_debut():
    session = creer_session()
    jure = creer_jure(session.organisation)
    maintenant = timezone.now()

    with pytest.raises(IntegrityError), transaction.atomic():
        un_code(jure, session, valide_du=maintenant, valide_jusqu_au=maintenant)


@pytest.mark.django_db
def test_l_empreinte_d_un_code_est_unique():
    session = creer_session()
    un_code(creer_jure(session.organisation), session, empreinte="b" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        un_code(creer_jure(session.organisation), session, empreinte="b" * 64)


@pytest.mark.django_db
def test_un_seul_code_actif_par_jure_et_par_session():
    session = creer_session()
    jure = creer_jure(session.organisation)
    un_code(jure, session, empreinte="c" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        un_code(jure, session, empreinte="d" * 64)


@pytest.mark.django_db
def test_un_nouveau_code_est_possible_apres_la_revocation_du_precedent():
    session = creer_session()
    jure = creer_jure(session.organisation)
    un_code(jure, session, empreinte="c" * 64, revoque_le=timezone.now())

    un_code(jure, session, empreinte="d" * 64)

    assert jure.codes.count() == 2
```

**Fichier `apps\jury\tests\test_services.py`**

```python
"""Tests des règles sur les jurés : affectation et codes d'accès de session (§7.4, §6.3 ; D4, D5).

Un juré se connecte sur sa tablette avec un code personnel à usage limité à la session,
généré par l'opérateur ; aucune adresse électronique n'est exigée. Le code n'est JAMAIS
stocké en clair : seule son empreinte l'est.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_epreuve,
    creer_jure,
    creer_organisation,
    creer_session,
)
from apps.jury import services
from apps.jury.exceptions import AffectationInvalideError, CodeInvalideError
from apps.jury.models import AffectationJury, CodeAccesJure


# --- Affectation (D5) ---------------------------------------------------------


@pytest.fixture
def concours_a_deux_categories(db):
    """Un concours avec deux catégories ; la première a deux épreuves, la seconde une."""
    concours = creer_concours()
    categorie_a, categorie_b = creer_categorie(concours), creer_categorie(concours)
    epreuves = [creer_epreuve(categorie_a), creer_epreuve(categorie_a), creer_epreuve(categorie_b)]
    return concours, categorie_a, categorie_b, epreuves


@pytest.mark.django_db
def test_affecter_a_une_epreuve(concours_a_deux_categories):
    concours, _, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    creees = services.affecter(jure, epreuve=epreuves[0])

    assert [a.epreuve for a in creees] == [epreuves[0]]


@pytest.mark.django_db
def test_affecter_a_une_categorie_cree_une_ligne_par_epreuve(concours_a_deux_categories):
    concours, categorie_a, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    services.affecter(jure, categorie=categorie_a)

    assert set(jure.affectations.values_list("epreuve", flat=True)) == {epreuves[0].pk, epreuves[1].pk}


@pytest.mark.django_db
def test_affecter_a_tout_le_concours_cree_une_ligne_par_epreuve(concours_a_deux_categories):
    concours, _, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    services.affecter(jure, concours=concours)

    assert jure.affectations.count() == len(epreuves)


@pytest.mark.django_db
def test_affecter_deux_fois_est_idempotent(concours_a_deux_categories):
    concours, _, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)
    services.affecter(jure, epreuve=epreuves[0])

    creees = services.affecter(jure, concours=concours)

    assert len(creees) == len(epreuves) - 1  # seules les lignes manquantes sont créées
    assert jure.affectations.count() == len(epreuves)


@pytest.mark.django_db
def test_affecter_exige_exactement_une_portee(concours_a_deux_categories):
    concours, categorie_a, _, epreuves = concours_a_deux_categories
    jure = creer_jure(concours.organisation)

    with pytest.raises(AffectationInvalideError):
        services.affecter(jure)
    with pytest.raises(AffectationInvalideError):
        services.affecter(jure, concours=concours, categorie=categorie_a)
    assert AffectationJury.objects.count() == 0


@pytest.mark.django_db
def test_rm20_affecter_un_jure_d_un_autre_client_est_refuse(concours_a_deux_categories):
    concours, *_ = concours_a_deux_categories
    jure_d_ailleurs = creer_jure(creer_organisation())

    with pytest.raises(AffectationInvalideError, match="client"):
        services.affecter(jure_d_ailleurs, concours=concours)
    assert AffectationJury.objects.count() == 0


@pytest.mark.django_db
def test_un_jure_inactif_n_est_pas_affecte(concours_a_deux_categories):
    concours, *_ = concours_a_deux_categories
    jure = creer_jure(concours.organisation, actif=False)

    with pytest.raises(AffectationInvalideError, match="inactif"):
        services.affecter(jure, concours=concours)


# --- Génération du code -------------------------------------------------------


@pytest.fixture
def jure_et_session(db):
    session = creer_session()
    return creer_jure(session.organisation), session


@pytest.mark.django_db
def test_le_code_genere_est_court_lisible_et_sans_caracteres_ambigus(jure_et_session):
    jure, session = jure_et_session

    _, code = services.generer_code(jure, session)

    brut = code.replace("-", "")
    assert len(brut) == services.LONGUEUR_CODE
    assert set(brut) <= set(services.ALPHABET)
    assert not (set(brut) & set("01OI"))  # jamais de caractères qu'on confond sur une tablette


@pytest.mark.django_db
def test_le_code_est_affiche_en_deux_groupes(jure_et_session):
    jure, session = jure_et_session

    _, code = services.generer_code(jure, session)

    assert code[4] == "-" and len(code) == services.LONGUEUR_CODE + 1


@pytest.mark.django_db
def test_d4_le_code_n_est_jamais_stocke_en_clair(jure_et_session):
    jure, session = jure_et_session

    acces, code = services.generer_code(jure, session)

    brut = code.replace("-", "")
    valeurs_stockees = [str(v) for v in CodeAccesJure.objects.values_list("empreinte", flat=True)]
    assert acces.empreinte not in (brut, code)
    assert len(acces.empreinte) == 64
    assert all(brut not in valeur for valeur in valeurs_stockees)


@pytest.mark.django_db
def test_la_duree_de_validite_par_defaut_est_de_douze_heures(jure_et_session):
    jure, session = jure_et_session
    maintenant = timezone.now()

    acces, _ = services.generer_code(jure, session, maintenant=maintenant)

    assert acces.valide_du == maintenant
    assert acces.valide_jusqu_au == maintenant + timedelta(hours=12)


@pytest.mark.django_db
def test_deux_codes_generes_sont_differents(jure_et_session):
    jure, session = jure_et_session
    autre_jure = creer_jure(session.organisation)

    _, premier = services.generer_code(jure, session)
    _, second = services.generer_code(autre_jure, session)

    assert premier != second


@pytest.mark.django_db
def test_regenerer_un_code_revoque_l_ancien(jure_et_session):
    jure, session = jure_et_session
    ancien, ancien_code = services.generer_code(jure, session)

    nouveau, _ = services.generer_code(jure, session)

    ancien.refresh_from_db()
    assert ancien.revoque_le is not None
    assert nouveau.revoque_le is None
    with pytest.raises(CodeInvalideError):
        services.authentifier_par_code(ancien_code, session)


@pytest.mark.django_db
def test_on_ne_genere_pas_de_code_pour_un_jure_inactif(jure_et_session):
    jure, session = jure_et_session
    jure.actif = False
    jure.save()

    with pytest.raises(AffectationInvalideError, match="inactif"):
        services.generer_code(jure, session)


@pytest.mark.django_db
def test_rm20_pas_de_code_entre_un_jure_et_la_session_d_un_autre_client():
    with pytest.raises(AffectationInvalideError, match="client"):
        services.generer_code(creer_jure(creer_organisation()), creer_session())


# --- Authentification par code ------------------------------------------------


@pytest.mark.django_db
def test_un_code_valide_identifie_le_jure(jure_et_session):
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)

    acces = services.authentifier_par_code(code, session)

    assert acces.jure == jure


@pytest.mark.django_db
@pytest.mark.parametrize(
    "transformation",
    [str.lower, lambda c: c.replace("-", ""), lambda c: f"  {c}  ", lambda c: c.replace("-", " ")],
    ids=["minuscules", "sans tiret", "espaces autour", "espace au lieu du tiret"],
)
def test_la_saisie_du_code_est_tolerante(jure_et_session, transformation):
    """Sur une tablette, on tape en minuscules, avec ou sans tiret : le code reste reconnu."""
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)

    assert services.authentifier_par_code(transformation(code), session).jure == jure


@pytest.mark.django_db
def test_un_code_inconnu_est_refuse(jure_et_session):
    _, session = jure_et_session

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code("ABCD-EFGH", session)

    assert erreur.value.raison == "inconnu"


@pytest.mark.django_db
def test_un_code_d_une_autre_session_est_refuse(jure_et_session):
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)
    autre_session = creer_session(session.concours)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, autre_session)

    assert erreur.value.raison == "inconnu"


@pytest.mark.django_db
def test_un_code_expire_est_refuse(jure_et_session):
    jure, session = jure_et_session
    maintenant = timezone.now()
    _, code = services.generer_code(jure, session, maintenant=maintenant)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session, maintenant=maintenant + timedelta(hours=12, seconds=1))

    assert erreur.value.raison == "expire"


@pytest.mark.django_db
def test_un_code_pas_encore_valide_est_refuse(jure_et_session):
    jure, session = jure_et_session
    maintenant = timezone.now()
    _, code = services.generer_code(jure, session, maintenant=maintenant)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session, maintenant=maintenant - timedelta(minutes=1))

    assert erreur.value.raison == "pas_encore_valide"


@pytest.mark.django_db
def test_un_code_revoque_est_refuse(jure_et_session):
    jure, session = jure_et_session
    acces, code = services.generer_code(jure, session)
    services.revoquer_code(acces)

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session)

    assert erreur.value.raison == "revoque"


@pytest.mark.django_db
def test_un_jure_desactive_apres_coup_ne_se_connecte_plus(jure_et_session):
    jure, session = jure_et_session
    _, code = services.generer_code(jure, session)
    jure.actif = False
    jure.save()

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code(code, session)

    assert erreur.value.raison == "jure_inactif"


@pytest.mark.django_db
def test_la_derniere_utilisation_est_enregistree(jure_et_session):
    jure, session = jure_et_session
    acces, code = services.generer_code(jure, session)
    assert acces.derniere_utilisation is None

    services.authentifier_par_code(code, session)

    acces.refresh_from_db()
    assert acces.derniere_utilisation is not None


@pytest.mark.django_db
def test_le_message_d_erreur_ne_revele_pas_la_raison(jure_et_session):
    """L'écran dit seulement « code invalide » ; la raison précise reste pour le journal (§15)."""
    _, session = jure_et_session

    with pytest.raises(CodeInvalideError) as erreur:
        services.authentifier_par_code("ZZZZ-ZZZZ", session)

    assert "inconnu" not in str(erreur.value).lower()
    assert "invalide" in str(erreur.value).lower()
```

## Étape D — Le code de `jury`

**Fichier `apps\jury\apps.py`**

```python
from django.apps import AppConfig


class JuryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jury"
    label = "jury"
    verbose_name = "Jury"
```

**Fichier `apps\jury\exceptions.py`**

```python
"""Exceptions de l'application jury."""


class AffectationInvalideError(Exception):
    """Une affectation de juré ou la génération d'un code d'accès n'est pas permise (§6.3, RM-20)."""


class CodeInvalideError(Exception):
    """Un code d'accès de juré est refusé.

    Le message affiché à l'écran reste volontairement vague (il ne dit pas si le code existe) ;
    la raison précise est dans ``raison``, pour le journal d'audit.
    """

    def __init__(self, raison):
        super().__init__("Code invalide ou expiré.")
        self.raison = raison
```

**Fichier `apps\jury\models.py`**

```python
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
```

**Fichier `apps\jury\services.py`**

```python
"""Règles sur les jurés : affectation aux épreuves et codes d'accès de session (§7.4, §6.3).

Codes d'accès : 8 caractères tirés avec le module ``secrets`` dans un alphabet sans caractères
ambigus (ni 0, O, 1, I) ; affichés en deux groupes de 4 (« K7MQ-4XTR »). Seule l'empreinte
HMAC-SHA256 (clé : ``SECRET_KEY``) est stockée : un code court n'est pas assez robuste pour un
hachage lent, mais l'empreinte à clé rend la base inutilisable sans la clé, et permet de retrouver
directement l'enregistrement. Le nombre d'essais devra être limité par les vues (anti force brute).
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.concours.models import Epreuve
from apps.jury.exceptions import AffectationInvalideError, CodeInvalideError
from apps.jury.models import AffectationJury, CodeAccesJure

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 caractères, sans 0, O, 1, I
LONGUEUR_CODE = 8
DUREE_PAR_DEFAUT = timedelta(hours=12)


# --- Affectation (D5) ---------------------------------------------------------


def affecter(jure, *, concours=None, categorie=None, epreuve=None):
    """Affecte un juré à une épreuve, à toutes celles d'une catégorie, ou à tout un concours.

    Exactement une portée doit être donnée. Idempotent : les affectations déjà présentes sont
    conservées, seules les manquantes sont créées (et renvoyées).
    """
    portees = [p for p in (concours, categorie, epreuve) if p is not None]
    if len(portees) != 1:
        raise AffectationInvalideError(
            "Indiquez exactement une portée : un concours, une catégorie ou une épreuve."
        )
    if not jure.actif:
        raise AffectationInvalideError(f"Le juré {jure} est inactif : affectation impossible.")
    portee = portees[0]
    if portee.organisation_id != jure.organisation_id:
        raise AffectationInvalideError(
            "Le juré et l'épreuve appartiennent à deux clients différents (RM-20)."
        )

    if epreuve is not None:
        epreuves = [epreuve]
    elif categorie is not None:
        epreuves = list(categorie.epreuves.all())
    else:
        epreuves = list(Epreuve.objects.filter(categorie__concours=concours))

    deja = set(jure.affectations.values_list("epreuve_id", flat=True))
    creees = []
    for une_epreuve in epreuves:
        if une_epreuve.pk not in deja:
            creees.append(AffectationJury.objects.create(jure=jure, epreuve=une_epreuve))
    return creees


# --- Codes d'accès (D4) -------------------------------------------------------


def normaliser_code(saisie):
    """Majuscules, sans espace ni tiret : la saisie sur tablette est tolérante."""
    return "".join(c for c in saisie.upper() if c.isalnum())


def empreinte_du_code(code):
    """HMAC-SHA256 du code normalisé, avec la clé secrète du projet."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), normaliser_code(code).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _formater(brut):
    return f"{brut[:4]}-{brut[4:]}"


def generer_code(jure, session, maintenant=None, duree=DUREE_PAR_DEFAUT):
    """Génère un code pour un juré et une session ; révoque l'ancien code actif.

    Renvoie ``(acces, code_en_clair)``. Le code en clair n'est montré qu'ici, une seule fois
    (il sera imprimé sur la fiche du juré) : il n'est stocké nulle part.
    """
    if not jure.actif:
        raise AffectationInvalideError(f"Le juré {jure} est inactif : aucun code ne peut lui être remis.")
    if jure.organisation_id != session.organisation_id:
        raise AffectationInvalideError(
            "Le juré et la session appartiennent à deux clients différents (RM-20)."
        )
    maintenant = maintenant or timezone.now()
    with transaction.atomic():
        CodeAccesJure.objects.filter(jure=jure, session=session, revoque_le__isnull=True).update(
            revoque_le=maintenant
        )
        for _ in range(10):  # en cas de collision d'empreinte (très improbable), on retire un code
            brut = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_CODE))
            try:
                with transaction.atomic():
                    acces = CodeAccesJure.objects.create(
                        jure=jure,
                        session=session,
                        empreinte=empreinte_du_code(brut),
                        valide_du=maintenant,
                        valide_jusqu_au=maintenant + duree,
                    )
            except IntegrityError:
                continue
            return acces, _formater(brut)
    raise RuntimeError("Impossible de générer un code unique.")  # pragma: no cover


def revoquer_code(acces, maintenant=None):
    """Révoque un code : il ne permet plus de se connecter (l'enregistrement reste, pour l'audit)."""
    acces.revoque_le = maintenant or timezone.now()
    acces.save(update_fields=["revoque_le", "modifie_le"])


def authentifier_par_code(saisie, session, maintenant=None):
    """Identifie le juré qui se connecte avec un code, pour une session donnée.

    Lève ``CodeInvalideError`` (message vague, ``raison`` précise pour le journal) si le code est
    inconnu, d'une autre session, révoqué, pas encore valide, expiré, ou si le juré est inactif.
    """
    maintenant = maintenant or timezone.now()
    acces = (
        CodeAccesJure.objects.select_related("jure")
        .filter(empreinte=empreinte_du_code(saisie), session=session)
        .first()
    )
    if acces is None:
        raise CodeInvalideError("inconnu")
    if acces.revoque_le is not None:
        raise CodeInvalideError("revoque")
    if maintenant < acces.valide_du:
        raise CodeInvalideError("pas_encore_valide")
    if maintenant > acces.valide_jusqu_au:
        raise CodeInvalideError("expire")
    if not acces.jure.actif:
        raise CodeInvalideError("jure_inactif")
    acces.derniere_utilisation = maintenant
    acces.save(update_fields=["derniere_utilisation", "modifie_le"])
    return acces
```

```powershell
python manage.py makemigrations jury
python manage.py migrate
pytest apps\jury
```

Attendu : `42 passed`.

**Pourquoi seulement l'empreinte du code ?** Si la base fuit, personne ne peut se faire passer pour un juré. Le code n'a que 8 caractères : une empreinte simple (SHA-256) se casserait par force brute, d'où le **HMAC** avec la clé secrète du serveur (`SECRET_KEY`). La limitation des tentatives sera faite dans les vues (itération 4).

## Étape E — L'import CSV, tests d'abord

**Fichier `apps\candidats\tests\test_import_csv.py`**

```python
"""Tests de l'import CSV des candidats (§7.3 : contrôle des doublons et rapport d'erreurs).

Principes :
- l'import est « tout ou rien » : s'il y a une erreur, RIEN n'est enregistré, et le rapport
  les liste TOUTES (l'opérateur corrige son fichier en une fois) ;
- on peut simuler (``simuler=True``) : mêmes contrôles, même rapport, rien d'enregistré ;
- le fichier d'un client ne touche jamais les données d'un autre client (RM-20).
"""
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.candidats.importation import importer_candidats
from apps.candidats.models import Candidat, Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_organisation,
    creer_participation,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours.models import Concours
from apps.utilisateurs.models import Utilisateur

EN_TETE = ["nom", "prenom", "date_naissance", "sexe", "ville", "structure", "categorie"]


def ecrire_csv(chemin, lignes, *, separateur=";", encodage="utf-8-sig", en_tete=EN_TETE):
    """Écrit un fichier CSV de test (par défaut : UTF-8 avec BOM, séparateur « ; », comme Excel)."""
    contenu = separateur.join(en_tete) + "\n"
    contenu += "".join(separateur.join(ligne) + "\n" for ligne in lignes)
    chemin.write_bytes(contenu.encode(encodage))
    return chemin


def ligne(nom="Diallo", prenom="Awa", naissance="05/03/2010", sexe="F", ville="Abidjan",
          structure="École Test", categorie="Juniors"):
    return [nom, prenom, naissance, sexe, ville, structure, categorie]


@pytest.fixture
def concours(db):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    creer_categorie(concours, nom="Seniors")
    return concours


@pytest.fixture
def fichier(tmp_path):
    return tmp_path / "candidats.csv"


def messages(rapport):
    return " | ".join(e.message for e in rapport.erreurs)


# --- Cas nominal -------------------------------------------------------------


@pytest.mark.django_db
def test_import_de_deux_candidats(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008", "M", categorie="Seniors")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok and rapport.lignes_lues == 2
    assert Candidat.objects.count() == 2 and Participation.objects.count() == 2
    assert [(i.numero_candidat, i.categorie) for i in rapport.inscriptions] == [(1, "Juniors"), (2, "Seniors")]
    awa = Candidat.objects.get(nom="Diallo")
    assert (awa.prenom, awa.date_naissance, awa.sexe, awa.ville) == ("Awa", date(2010, 3, 5), "F", "Abidjan")
    assert awa.organisation_id == concours.organisation_id


@pytest.mark.django_db
def test_les_participations_sont_inscrites_et_numerotees_dans_l_ordre_du_fichier(concours, fichier):
    ecrire_csv(fichier, [ligne("A", "a"), ligne("B", "b"), ligne("C", "c")])

    importer_candidats(concours, fichier)

    participations = Participation.objects.filter(concours=concours).order_by("numero_candidat")
    assert [p.candidat.nom for p in participations] == ["A", "B", "C"]
    assert all(p.statut == Participation.Statut.INSCRIT for p in participations)


@pytest.mark.django_db
def test_la_numerotation_continue_apres_les_participations_existantes(concours, fichier):
    creer_participation(concours.categories.get(nom="Juniors"), numero_candidat=41)
    ecrire_csv(fichier, [ligne()])

    rapport = importer_candidats(concours, fichier)

    assert rapport.inscriptions[0].numero_candidat == 42


# --- Formats de fichier ------------------------------------------------------


@pytest.mark.django_db
def test_separateur_virgule_et_point_virgule_acceptes(concours, tmp_path):
    ecrire_csv(tmp_path / "a.csv", [ligne("Diallo", "Awa")], separateur=",")
    ecrire_csv(tmp_path / "b.csv", [ligne("Koné", "Ibrahim", "12/11/2008")], separateur=";")

    assert importer_candidats(concours, tmp_path / "a.csv").ok
    assert importer_candidats(concours, tmp_path / "b.csv").ok
    assert Candidat.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("encodage", ["utf-8", "utf-8-sig", "cp1252"])
def test_encodages_acceptes_et_accents_conserves(concours, fichier, encodage):
    """Excel français enregistre souvent en cp1252 (« CSV ANSI ») : les accents doivent survivre."""
    ecrire_csv(fichier, [ligne("Koné", "Élodie", ville="Bouaké")], encodage=encodage)

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    candidat = Candidat.objects.get()
    assert (candidat.nom, candidat.prenom, candidat.ville) == ("Koné", "Élodie", "Bouaké")


@pytest.mark.django_db
def test_en_tetes_tolerants_casse_accents_espaces_et_ordre_des_colonnes(concours, fichier):
    en_tete = ["Catégorie", "PRÉNOM", "Nom", "Date de naissance"]
    ecrire_csv(fichier, [["Juniors", "Awa", "Diallo", "05/03/2010"]], en_tete=en_tete)

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.get().nom == "Diallo"


@pytest.mark.django_db
def test_colonnes_facultatives_absentes(concours, fichier):
    ecrire_csv(fichier, [["Diallo", "Awa", "Juniors"]], en_tete=["nom", "prenom", "categorie"])

    assert importer_candidats(concours, fichier).ok
    candidat = Candidat.objects.get()
    assert candidat.date_naissance is None and candidat.sexe == "" and candidat.ville == ""


@pytest.mark.django_db
@pytest.mark.parametrize("manquante", ["nom", "prenom", "categorie"])
def test_colonne_obligatoire_manquante_refuse_tout_le_fichier(concours, fichier, manquante):
    en_tete = [c for c in EN_TETE if c != manquante]
    ecrire_csv(fichier, [[v for c, v in zip(EN_TETE, ligne()) if c != manquante]], en_tete=en_tete)

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok
    assert manquante in messages(rapport)
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_fichier_sans_aucune_ligne(concours, fichier):
    ecrire_csv(fichier, [])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "aucune ligne" in messages(rapport).lower()


@pytest.mark.django_db
def test_fichier_completement_vide(concours, fichier):
    fichier.write_bytes(b"")

    assert not importer_candidats(concours, fichier).ok


@pytest.mark.django_db
def test_les_lignes_vides_sont_ignorees(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), [";" * 6], ligne("Koné", "Ibrahim", "12/11/2008")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok and rapport.lignes_lues == 2


# --- Validation des lignes ---------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("champ, valeur", [("nom", ""), ("prenom", "  "), ("categorie", "")])
def test_champs_obligatoires_vides_refuses_avec_le_numero_de_ligne(concours, fichier, champ, valeur):
    donnees = dict(zip(EN_TETE, ligne()))
    donnees[champ] = valeur
    ecrire_csv(fichier, [ligne(), [donnees[c] for c in EN_TETE]])

    rapport = importer_candidats(concours, fichier)

    assert [e.ligne for e in rapport.erreurs] == [3]  # ligne 1 = en-tête, ligne 3 = 2e candidat
    assert champ in messages(rapport)


@pytest.mark.django_db
def test_categorie_inconnue_nommee_dans_l_erreur(concours, fichier):
    ecrire_csv(fichier, [ligne(categorie="Catégorie fantôme")])

    rapport = importer_candidats(concours, fichier)

    assert "Catégorie fantôme" in messages(rapport)
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_la_categorie_est_reconnue_sans_tenir_compte_de_la_casse(concours, fichier):
    ecrire_csv(fichier, [ligne(categorie="  juniors ")])

    assert importer_candidats(concours, fichier).ok


@pytest.mark.django_db
def test_la_categorie_d_un_autre_concours_n_est_pas_utilisee(concours, fichier):
    creer_categorie(creer_concours(), nom="Exclusive")  # n'existe pas dans NOTRE concours
    ecrire_csv(fichier, [ligne(categorie="Exclusive")])

    assert not importer_candidats(concours, fichier).ok


@pytest.mark.django_db
@pytest.mark.parametrize(
    "texte, attendu",
    [("05/03/2010", date(2010, 3, 5)), ("2010-03-05", date(2010, 3, 5)), ("", None)],
)
def test_formats_de_date_acceptes(concours, fichier, texte, attendu):
    ecrire_csv(fichier, [ligne(naissance=texte)])

    assert importer_candidats(concours, fichier).ok
    assert Candidat.objects.get().date_naissance == attendu


@pytest.mark.django_db
@pytest.mark.parametrize(
    "texte",
    [
        "31/02/2010",  # n'existe pas
        "abc",
        "2010/03/05",  # format non prévu
        "05-03-2010",
        "01/01/1850",  # trop ancien
        (timezone.now().date() + timedelta(days=1)).strftime("%d/%m/%Y"),  # dans le futur
    ],
)
def test_dates_invalides_refusees(concours, fichier, texte):
    ecrire_csv(fichier, [ligne(naissance=texte)])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "date" in messages(rapport).lower()


@pytest.mark.django_db
@pytest.mark.parametrize("texte, attendu", [("M", "M"), ("f", "F"), ("Féminin", "F"), ("masculin", "M"), ("", "")])
def test_sexe_normalise(concours, fichier, texte, attendu):
    ecrire_csv(fichier, [ligne(sexe=texte)])

    assert importer_candidats(concours, fichier).ok
    assert Candidat.objects.get().sexe == attendu


@pytest.mark.django_db
def test_sexe_inconnu_refuse(concours, fichier):
    ecrire_csv(fichier, [ligne(sexe="X")])

    assert "sexe" in messages(importer_candidats(concours, fichier)).lower()


@pytest.mark.django_db
def test_valeur_trop_longue_refusee(concours, fichier):
    ecrire_csv(fichier, [ligne(nom="N" * 101)])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "100" in messages(rapport)


@pytest.mark.django_db
def test_le_contenu_est_stocke_tel_quel_sans_etre_interprete(concours, fichier):
    """REC-26 : un nom contenant du code n'est jamais exécuté ; il est échappé à l'affichage."""
    nom_piege = "<script>alert(1)</script>"
    ecrire_csv(fichier, [ligne(nom=nom_piege)])

    assert importer_candidats(concours, fichier).ok
    assert Candidat.objects.get().nom == nom_piege


# --- Doublons ----------------------------------------------------------------


@pytest.mark.django_db
def test_doublon_dans_le_fichier_signale_les_deux_lignes(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008"), ligne("Diallo", "Awa")])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok
    erreur = rapport.erreurs[0]
    assert erreur.ligne == 4 and "doublon" in erreur.message.lower() and "2" in erreur.message


@pytest.mark.django_db
def test_doublon_sans_tenir_compte_de_la_casse(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("DIALLO", "awa")])

    assert "doublon" in messages(importer_candidats(concours, fichier)).lower()


@pytest.mark.django_db
def test_une_date_de_naissance_differente_designe_une_autre_personne(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010"), ligne("Diallo", "Awa", "17/08/2012")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok and Candidat.objects.count() == 2


@pytest.mark.django_db
def test_la_meme_personne_dans_deux_categories_est_acceptee_sans_doublon_de_candidat(concours, fichier):
    ecrire_csv(fichier, [ligne(categorie="Juniors"), ligne(categorie="Seniors")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.count() == 1 and Participation.objects.count() == 2


@pytest.mark.django_db
def test_candidat_deja_inscrit_dans_la_categorie_est_un_doublon_avec_son_numero(concours, fichier):
    categorie = concours.categories.get(nom="Juniors")
    candidat = creer_candidat(
        concours.organisation, nom="Diallo", prenom="Awa", date_naissance=date(2010, 3, 5)
    )
    creer_participation(categorie, candidat, numero_candidat=17)
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010", categorie="Juniors")])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok
    assert "déjà inscrit" in messages(rapport) and "17" in messages(rapport)
    assert Participation.objects.count() == 1


@pytest.mark.django_db
def test_un_candidat_existant_est_reutilise_pour_une_autre_categorie(concours, fichier):
    candidat = creer_candidat(
        concours.organisation, nom="Diallo", prenom="Awa", date_naissance=date(2010, 3, 5)
    )
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010", categorie="Seniors")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.count() == 1
    assert Participation.objects.get().candidat == candidat


@pytest.mark.django_db
def test_rm20_un_homonyme_d_un_autre_client_n_est_pas_reutilise(concours, fichier):
    creer_candidat(creer_organisation(), nom="Diallo", prenom="Awa", date_naissance=date(2010, 3, 5))
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.count() == 2
    assert Participation.objects.get().candidat.organisation_id == concours.organisation_id


# --- Tout ou rien, simulation, état du concours ------------------------------


@pytest.mark.django_db
def test_une_erreur_empeche_tout_l_import_et_toutes_les_erreurs_sont_listees(concours, fichier):
    ecrire_csv(
        fichier,
        [
            ligne("Valide", "Un"),
            ligne("", "Sans nom"),  # erreur ligne 3
            ligne("Valide", "Deux", categorie="Inconnue"),  # erreur ligne 4
            ligne("Valide", "Trois", naissance="31/02/2010"),  # erreur ligne 5
        ],
    )

    rapport = importer_candidats(concours, fichier)

    assert [e.ligne for e in rapport.erreurs] == [3, 4, 5]
    assert Candidat.objects.count() == 0 and Participation.objects.count() == 0
    assert rapport.inscriptions == []


@pytest.mark.django_db
def test_la_simulation_donne_le_meme_rapport_sans_rien_enregistrer(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008")])

    simulation = importer_candidats(concours, fichier, simuler=True)

    assert simulation.ok and simulation.simulation
    assert [i.numero_candidat for i in simulation.inscriptions] == [1, 2]
    assert Candidat.objects.count() == 0 and Participation.objects.count() == 0

    reel = importer_candidats(concours, fichier)
    assert [i.numero_candidat for i in reel.inscriptions] == [1, 2]
    assert Participation.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Concours.Etat.TERMINE, Concours.Etat.ARCHIVE])
def test_pas_d_import_dans_un_concours_termine_ou_archive(concours, fichier, etat):
    # D16 : un concours non brouillon exige un corpus figé et une configuration validée.
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation)
    Concours.objects.filter(pk=concours.pk).update(
        etat=etat,
        version_corpus=creer_version_validee(),
        configuration_validee_par=responsable,
        configuration_validee_le=timezone.now(),
        configuration_empreinte="a" * 64,
    )
    concours.refresh_from_db()
    ecrire_csv(fichier, [ligne()])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "inscriptions" in messages(rapport).lower()
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_le_resume_du_rapport_est_lisible(concours, fichier):
    ecrire_csv(fichier, [ligne("", "X")])

    texte = importer_candidats(concours, fichier).texte()

    assert "Ligne 2" in texte and "nom" in texte


# --- Commande ----------------------------------------------------------------


@pytest.mark.django_db
def test_commande_importer_candidats(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008")])
    sortie = StringIO()

    call_command("importer_candidats", str(concours.pk), str(fichier), stdout=sortie)

    assert Participation.objects.count() == 2
    assert "2 candidats inscrits" in sortie.getvalue()


@pytest.mark.django_db
def test_commande_dry_run(concours, fichier):
    ecrire_csv(fichier, [ligne()])
    sortie = StringIO()

    call_command("importer_candidats", str(concours.pk), str(fichier), "--dry-run", stdout=sortie)

    assert Participation.objects.count() == 0
    assert "n'a été enregistré" in sortie.getvalue()


@pytest.mark.django_db
def test_commande_affiche_toutes_les_erreurs(concours, fichier):
    ecrire_csv(fichier, [ligne("", "A"), ligne("B", "", categorie="Inconnue")])

    with pytest.raises(CommandError) as erreur:
        call_command("importer_candidats", str(concours.pk), str(fichier))

    assert "Ligne 2" in str(erreur.value) and "Ligne 3" in str(erreur.value)
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_commande_concours_ou_fichier_introuvable(concours, tmp_path):
    with pytest.raises(CommandError, match="introuvable"):
        call_command("importer_candidats", str(concours.pk), str(tmp_path / "absent.csv"))
    ecrire_csv(tmp_path / "ok.csv", [ligne()])
    with pytest.raises(CommandError, match="Concours"):
        call_command("importer_candidats", "00000000-0000-0000-0000-000000000000", str(tmp_path / "ok.csv"))
    with pytest.raises(CommandError, match="Concours"):
        call_command("importer_candidats", "pas-un-uuid", str(tmp_path / "ok.csv"))
```

```powershell
pytest apps\candidats\tests\test_import_csv.py
```

Attendu : échec (`ModuleNotFoundError: apps.candidats.importation`), voulu.

## Étape F — Le code de l'import

**Fichier `apps\candidats\importation.py`**

```python
"""Import CSV des candidats : contrôles, détection des doublons et rapport d'erreurs (§7.3).

Principes :
- « tout ou rien » : la phase 1 lit et contrôle TOUTES les lignes sans rien écrire ; s'il y a
  une erreur, le rapport les liste toutes et la base n'est pas touchée (D21) ;
- la phase 2 (écriture) n'a lieu que si le fichier est sans erreur, dans une transaction
  verrouillant le concours ; en simulation, cette transaction est annulée à la fin ;
- le contenu est stocké tel quel : l'échappement se fait à l'affichage (REC-26).
"""
import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction

from apps.candidats.models import Candidat, Participation
from apps.candidats.services import inscrire
from apps.concours.models import Concours

DATE_MINIMALE = date(1900, 1, 1)
FORMATS_DATE = ("%d/%m/%Y", "%Y-%m-%d")
OBLIGATOIRES = ("nom", "prenom", "categorie")
FACULTATIVES = ("date_naissance", "sexe", "ville", "structure")

# En-tête normalisé (minuscules, sans accents ni séparateurs) → nom de colonne canonique.
ALIAS_COLONNES = {
    "nom": "nom",
    "prenom": "prenom",
    "prenoms": "prenom",
    "datenaissance": "date_naissance",
    "datedenaissance": "date_naissance",
    "naissance": "date_naissance",
    "sexe": "sexe",
    "genre": "sexe",
    "ville": "ville",
    "structure": "structure",
    "ecole": "structure",
    "categorie": "categorie",
}
SEXES = {"m": "M", "masculin": "M", "homme": "M", "f": "F", "feminin": "F", "femme": "F"}


@dataclass
class ErreurImport:
    ligne: int | None  # numéro physique dans le fichier (l'en-tête est la ligne 1)
    message: str


@dataclass
class InscriptionImport:
    ligne: int
    numero_candidat: int
    nom_complet: str
    categorie: str


@dataclass
class RapportImport:
    simulation: bool = False
    lignes_lues: int = 0
    erreurs: list = field(default_factory=list)
    inscriptions: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.erreurs

    def texte(self):
        if self.erreurs:
            lignes = [
                f"Ligne {e.ligne} : {e.message}" if e.ligne else e.message for e in self.erreurs
            ]
            return "\n".join(lignes)
        n = len(self.inscriptions)
        resume = f"{n} candidat{'s' if n > 1 else ''} inscrit{'s' if n > 1 else ''}."
        if self.simulation:
            resume += " Simulation : rien n'a été enregistré."
        return resume


def _normaliser(texte):
    """Minuscules, sans accents, sans espaces ni ponctuation : pour comparer des en-têtes."""
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return "".join(c for c in sans_accents.casefold() if c.isalnum())


def _decoder(octets):
    """UTF-8 (avec ou sans BOM) d'abord ; sinon cp1252, l'encodage du « CSV » d'Excel français."""
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            return octets.decode(encodage)
        except UnicodeDecodeError:
            continue
    return None


def _separateur(en_tete):
    return max(";,\t", key=en_tete.count)


def _lire_date(texte):
    for format_date in FORMATS_DATE:
        try:
            valeur = datetime.strptime(texte, format_date).date()
        except ValueError:
            continue
        if DATE_MINIMALE <= valeur <= date.today():
            return valeur
        break
    raise ValueError(f"Date de naissance invalide : « {texte} » (attendu JJ/MM/AAAA ou AAAA-MM-JJ, entre 1900 et aujourd'hui).")


def _lire_sexe(texte):
    if not texte:
        return ""
    try:
        return SEXES[_normaliser(texte)]
    except KeyError:
        raise ValueError(f"Sexe inconnu : « {texte} » (attendu M ou F).") from None


def _lire_lignes(texte, rapport):
    """Renvoie [(numéro de ligne, {colonne: valeur})] ; ajoute au rapport les erreurs de structure."""
    if not texte.strip():
        rapport.erreurs.append(ErreurImport(None, "Le fichier est vide."))
        return []
    separateur = _separateur(texte.splitlines()[0])
    lecteur = csv.reader(io.StringIO(texte, newline=""), delimiter=separateur)
    try:
        en_tete = next(lecteur)
    except StopIteration:
        rapport.erreurs.append(ErreurImport(None, "Le fichier est vide."))
        return []
    colonnes = [ALIAS_COLONNES.get(_normaliser(c)) for c in en_tete]
    for obligatoire in OBLIGATOIRES:
        if obligatoire not in colonnes:
            rapport.erreurs.append(ErreurImport(1, f"Colonne obligatoire absente : « {obligatoire} »."))
    if not rapport.ok:
        return []
    lignes = []
    for cellules in lecteur:
        if not any(c.strip() for c in cellules):
            continue  # ligne vide : ignorée
        valeurs = {}
        for colonne, cellule in zip(colonnes, cellules):
            if colonne and colonne not in valeurs:
                valeurs[colonne] = cellule.strip()
        lignes.append((lecteur.line_num, valeurs))
    if not lignes:
        rapport.erreurs.append(ErreurImport(None, "Le fichier ne contient aucune ligne de candidat."))
    return lignes


def _controler(lignes, concours, rapport):
    """Phase 1 : contrôle chaque ligne sans écrire. Renvoie le plan [(ligne, valeurs, catégorie)]."""
    categories = {c.nom.strip().casefold(): c for c in concours.categories.all()}
    limites = {n: Candidat._meta.get_field(n).max_length for n in ("nom", "prenom", "ville", "structure")}
    plan, vus = [], {}
    for numero, valeurs in lignes:
        rapport.lignes_lues += 1
        avant = len(rapport.erreurs)

        def refuser(message, numero=numero):
            rapport.erreurs.append(ErreurImport(numero, message))

        for champ in OBLIGATOIRES:
            if not valeurs.get(champ):
                refuser(f"Le champ « {champ} » est vide.")
        for champ, maximum in limites.items():
            if len(valeurs.get(champ, "")) > maximum:
                refuser(f"Le champ « {champ} » dépasse {maximum} caractères.")

        categorie = None
        if valeurs.get("categorie"):
            categorie = categories.get(valeurs["categorie"].casefold())
            if categorie is None:
                refuser(f"Catégorie inconnue dans ce concours : « {valeurs['categorie']} ».")

        naissance, sexe = None, ""
        try:
            if valeurs.get("date_naissance"):
                naissance = _lire_date(valeurs["date_naissance"])
        except ValueError as erreur:
            refuser(str(erreur))
        try:
            sexe = _lire_sexe(valeurs.get("sexe", ""))
        except ValueError as erreur:
            refuser(str(erreur))

        if len(rapport.erreurs) > avant or categorie is None:
            continue

        cle = (valeurs["nom"].casefold(), valeurs["prenom"].casefold(), naissance, categorie.pk)
        if cle in vus:
            refuser(f"Doublon : même candidat et même catégorie que la ligne {vus[cle]}.")
            continue
        vus[cle] = numero

        existant = _candidats_existants(concours.organisation_id, valeurs, naissance)
        deja = Participation.objects.filter(candidat__in=existant, categorie=categorie).first()
        if deja is not None:
            refuser(
                f"Candidat déjà inscrit dans la catégorie « {categorie.nom} » (n° {deja.numero_candidat})."
            )
            continue
        valeurs = dict(valeurs, date_naissance=naissance, sexe=sexe)
        plan.append((numero, valeurs, categorie))
    return plan


def _candidats_existants(organisation_id, valeurs, naissance):
    """Candidats du MÊME client portant ce nom, ce prénom (sans tenir compte de la casse) et cette date (RM-20)."""
    return list(
        Candidat.objects.filter(
            organisation_id=organisation_id,
            nom__iexact=valeurs["nom"],
            prenom__iexact=valeurs["prenom"],
            date_naissance=naissance,
        ).order_by("pk")
    )


def _ecrire(plan, concours, rapport):
    """Phase 2 : crée les candidats manquants et les participations, dans l'ordre du fichier."""
    crees = {}  # une même personne présente dans deux catégories n'est créée qu'une fois
    for numero, valeurs, categorie in plan:
        cle = (valeurs["nom"].casefold(), valeurs["prenom"].casefold(), valeurs["date_naissance"])
        candidat = crees.get(cle)
        if candidat is None:
            existants = _candidats_existants(concours.organisation_id, valeurs, valeurs["date_naissance"])
            candidat = existants[0] if existants else Candidat.objects.create(
                organisation_id=concours.organisation_id,
                nom=valeurs["nom"],
                prenom=valeurs["prenom"],
                date_naissance=valeurs["date_naissance"],
                sexe=valeurs["sexe"],
                ville=valeurs.get("ville", ""),
                structure=valeurs.get("structure", ""),
            )
            crees[cle] = candidat
        participation = inscrire(candidat, categorie)
        rapport.inscriptions.append(
            InscriptionImport(numero, participation.numero_candidat, candidat.nom_complet, categorie.nom)
        )


def importer_candidats(concours, chemin, *, simuler=False):
    """Importe un fichier CSV de candidats dans un concours ; renvoie un ``RapportImport``."""
    rapport = RapportImport(simulation=simuler)
    texte = _decoder(open(chemin, "rb").read())
    if texte is None:
        rapport.erreurs.append(ErreurImport(None, "Encodage du fichier non reconnu (UTF-8 ou Windows-1252 attendu)."))
        return rapport

    with transaction.atomic():
        concours = Concours.objects.select_for_update().get(pk=concours.pk)
        if concours.etat in (Concours.Etat.TERMINE, Concours.Etat.ARCHIVE):
            rapport.erreurs.append(
                ErreurImport(
                    None,
                    f"Le concours est {concours.get_etat_display().lower()} : il ne peut plus recevoir d'inscriptions.",
                )
            )
            return rapport
        lignes = _lire_lignes(texte, rapport)
        if not rapport.ok:
            return rapport
        plan = _controler(lignes, concours, rapport)
        if not rapport.ok:
            return rapport
        _ecrire(plan, concours, rapport)
        if simuler:
            transaction.set_rollback(True)
    return rapport
```

**Fichier `apps\candidats\management\commands\importer_candidats.py`**

```python
"""Commande : importe un fichier CSV de candidats dans un concours (§7.3)."""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.candidats.importation import importer_candidats
from apps.concours.models import Concours


class Command(BaseCommand):
    help = (
        "Importe des candidats depuis un fichier CSV (colonnes : nom, prenom, categorie ; "
        "facultatives : date_naissance, sexe, ville, structure). Tout ou rien."
    )

    def add_arguments(self, parser):
        parser.add_argument("concours", help="Identifiant (UUID) du concours.")
        parser.add_argument("fichier", help="Chemin du fichier CSV.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Contrôle le fichier et affiche le rapport, sans rien enregistrer.",
        )

    def handle(self, *args, **options):
        try:
            concours = Concours.objects.get(pk=options["concours"])
        except (Concours.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"Concours introuvable : {options['concours']}") from None
        chemin = Path(options["fichier"])
        if not chemin.is_file():
            raise CommandError(f"Fichier introuvable : {chemin}")

        rapport = importer_candidats(concours, chemin, simuler=options["dry_run"])
        if not rapport.ok:
            raise CommandError(f"Import refusé, rien n'a été enregistré :\n{rapport.texte()}")
        self.stdout.write(self.style.SUCCESS(rapport.texte()))
```

```powershell
pytest apps\candidats
```

Attendu : `96 passed`.

## Essayer à la main

Créez un fichier `candidats.csv` (enregistré depuis Excel en « CSV UTF-8 » ou « CSV (séparateur : point-virgule) ») :

```text
nom;prenom;date_naissance;sexe;ville;structure;categorie
Diallo;Awa;05/03/2010;F;Abidjan;École Test;Juniors
```

Puis, avec l'identifiant (UUID) d'un concours existant (visible dans l'administration) :

```powershell
python manage.py importer_candidats <uuid-du-concours> candidats.csv --dry-run
python manage.py importer_candidats <uuid-du-concours> candidats.csv
```

Attendu : `1 candidat inscrit.` (et, en `--dry-run`, `Simulation : rien n'a été enregistré.`). Avec une erreur, la commande liste **toutes** les lignes fautives (« Ligne 3 : … ») et n'enregistre rien.

## Suite complète

```powershell
pytest
```

Attendu à ce stade : **379 réussis, 66 échecs** — les 66 échecs sont les tests des règles que **vous** devez écrire dans `apps\coran\services.py` (garde d'immuabilité, contrôles du corpus, traversée de sourates ; chapitres 04, 06 et 07). Les solutions repliées de ces chapitres les font tous passer.

## Questions de compréhension

1. Pourquoi l'import contrôle-t-il **toutes** les lignes avant d'écrire, plutôt que d'écrire ligne par ligne en s'arrêtant à la première erreur ?
2. Pourquoi la même personne présente dans deux catégories ne crée-t-elle qu'**un** `Candidat` mais deux `Participation` ?
3. Pourquoi un homonyme d'un autre client n'est-il jamais réutilisé ?

<details>
<summary>Réponses</summary>

1. L'opérateur corrige son fichier **en une seule fois** au lieu de relancer dix fois ; et la base n'est jamais dans un état à moitié importé (D21).
2. Le `Candidat` est la personne ; la `Participation` est son inscription à une catégorie (avec son numéro). Une contrainte d'unicité `(candidat, catégorie)` empêche seulement l'inscription en double.
3. RM-20 : les données d'un client ne doivent jamais fuiter vers un autre. Réutiliser un candidat d'une autre organisation le lierait aux deux clients.
</details>

## Journal d'apprentissage

Notez : pourquoi un code de juré n'est pas un mot de passe classique ; ce que « tout ou rien » change pour l'opérateur.

## Commit proposé

```text
Jurés, codes d'accès de session et import CSV des candidats
```
