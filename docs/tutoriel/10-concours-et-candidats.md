# Chapitre 10 — Concours et candidats

> **Étape du plan :** 1.2, deuxième lot · **Durée :** 4 à 5 heures · **Commit de référence :** `28d35c3` · **Résultat :** les applications `concours` et `candidats`, leurs règles (RM-27, RM-28, RM-31) et **116 nouveaux tests**.

## Objectif

Construire le cœur de la configuration d'un concours et de ses participants :

- **`concours`** : `Concours`, `Categorie`, `Epreuve` (avec P, T, Q et les réglages de réutilisation RM-21), `CritereNotation` (le barème), `Session`.
- **`candidats`** : `Candidat`, `Participation` (l'inscription à une catégorie, avec son numéro) et `Consentement` (le consentement parental des mineurs).

Règles du cahier des charges mises en œuvre :

| Règle | Où elle est appliquée |
|---|---|
| **RM-01** : un concours appartient à une organisation | `organisation` recopiée de la mission (`ModeleDuClient`) |
| **RM-03** : Q = T × P, calculé | propriété `Epreuve.questions_par_candidat` |
| **RM-09, RM-27** : corpus validé, figé à l'ouverture | service `definir_version_corpus` + contrainte de base |
| **RM-31** : pas d'ouverture sans validation de la configuration par le responsable client | services `valider_configuration` et `ouvrir_concours` + contrainte de base |
| **RM-28** : aucun tirage pour un mineur sans consentement parental | service `verifier_pret_pour_tirage` |
| **§14.2** : aucun tirage pour une participation non admise | idem |
| **§16.2** : trois consentements distincts, non précochés ; le retrait prend effet pour l'avenir | modèle `Consentement` |

## Les décisions prises dans ce lot

| N° | Décision |
|---|---|
| D13 | **Date de naissance inconnue : le consentement est exigé par prudence** (règle absolue n°6). |
| D14 | La validation de la configuration porte sur **une configuration précise** : on en garde l'**empreinte SHA-256** et on la compare à l'ouverture. |
| D15 | `affichage_scene` est **désactivé par défaut** (§9.1). |
| D16 | Un concours non brouillon exige, **en base**, un corpus et une validation (RM-27, RM-31). |
| D17 | Numéro de candidat = plus élevé du concours + 1, **retraits compris**, sous verrou. |
| D18 | Consentement retiré = formulaire **conservé** et marqué « retiré ». |
| D19 | Format du concours : « présentiel » seulement en V1. |
| D20 | Chiffrement des fichiers (consentements, logos) repoussé à la sécurité du serveur (§15). |

Le document de conception complet, à jour, est à la fin du chapitre.

## Étape A — Les dossiers et les réglages

```powershell
foreach ($a in "concours", "candidats") {
    New-Item -ItemType Directory "apps\$a\tests" -Force | Out-Null
    New-Item -ItemType File "apps\$a\__init__.py", "apps\$a\tests\__init__.py" -Force | Out-Null
}
```

Dans `config\settings\base.py`, ajoutez les deux applications à `INSTALLED_APPS` :

```python
    "apps.commun",
    "apps.clients",
    "apps.utilisateurs",
    "apps.concours",
    "apps.candidats",
    "apps.coran",
]
```

## Étape B — Les fabriques de test

On étend le module de fabriques partagé (fichier complet à ce stade) :

**Fichier `apps\commun\tests\outils.py`**

```python
"""Fonctions utilitaires partagées par les tests des applications clients, utilisateurs, etc."""
import itertools
from datetime import date

from django.utils import timezone

from apps.candidats.models import Candidat, Consentement, Participation
from apps.clients.models import Mission, Organisation
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_version
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


def creer_version_validee(**champs):
    """Une version du corpus validée (la seule sorte que l'on peut rattacher à un concours)."""
    valeurs = {"statut": VersionCorpus.Statut.VALIDEE, "date_validation": timezone.now()}
    valeurs.update(champs)
    return creer_version(**valeurs)


def creer_concours(mission=None, **champs):
    n = next(_compteur)
    mission = mission or creer_mission()
    valeurs = {
        "mission": mission,
        "nom": f"Concours-test-{n}",
        "edition": "2027",
        "date_debut": mission.date_debut,
        "date_fin": mission.date_fin,
    }
    valeurs.update(champs)
    return Concours.objects.create(**valeurs)


def creer_categorie(concours=None, **champs):
    n = next(_compteur)
    valeurs = {"concours": concours or creer_concours(), "nom": f"Categorie-test-{n}"}
    valeurs.update(champs)
    return Categorie.objects.create(**valeurs)


def creer_epreuve(categorie=None, **champs):
    n = next(_compteur)
    valeurs = {
        "categorie": categorie or creer_categorie(),
        "nom": f"Epreuve-test-{n}",
        "ordre": n,
        "questions_par_serie": 3,
    }
    valeurs.update(champs)
    return Epreuve.objects.create(**valeurs)


def creer_critere(epreuve=None, **champs):
    n = next(_compteur)
    valeurs = {
        "epreuve": epreuve or creer_epreuve(),
        "libelle": f"Critere-test-{n}",
        "ordre": n,
        "maximum": 10,
    }
    valeurs.update(champs)
    return CritereNotation.objects.create(**valeurs)


def creer_session(concours=None, **champs):
    n = next(_compteur)
    valeurs = {
        "concours": concours or creer_concours(),
        "nom": f"Session-test-{n}",
        "date": date(2027, 1, 20),
        "lieu": "Abidjan",
    }
    valeurs.update(champs)
    return Session.objects.create(**valeurs)


def configuration_complete(concours):
    """Une catégorie, une épreuve et un critère : le minimum pour valider la configuration."""
    categorie = creer_categorie(concours)
    epreuve = creer_epreuve(categorie)
    creer_critere(epreuve)
    return concours


def creer_candidat(organisation=None, **champs):
    n = next(_compteur)
    valeurs = {
        "organisation": organisation or creer_organisation(),
        "nom": f"Nom-test-{n}",
        "prenom": f"Prenom-test-{n}",
    }
    valeurs.update(champs)
    return Candidat.objects.create(**valeurs)


def creer_participation(categorie=None, candidat=None, **champs):
    n = next(_compteur)
    categorie = categorie or creer_categorie()
    valeurs = {
        "candidat": candidat or creer_candidat(categorie.organisation),
        "concours": categorie.concours,
        "categorie": categorie,
        "numero_candidat": n,
    }
    valeurs.update(champs)
    return Participation.objects.create(**valeurs)


def creer_consentement(participation=None, **champs):
    valeurs = {
        "participation": participation or creer_participation(),
        "representant_nom": "Representant de test",
        "representant_lien": "Parent",
        "version_formulaire": "1.0",
        "date_signature": date(2027, 1, 10),
        "consentement_participation": True,
    }
    valeurs.update(champs)
    return Consentement.objects.create(**valeurs)
```

> Ce module importe les modèles des deux applications : **les tests ne se lancent qu'une fois les deux applications écrites** (étapes D et E). C'est normal : les fabriques servent à toute la suite de tests.

## Étape C — Les tests d'abord

### `concours`

**Fichier `apps\concours\tests\test_concours.py`**

```python
"""Tests du modèle Concours (§7.2, §14.1 ; RM-01, RM-27, RM-31)."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.commun.tests.outils import (
    creer_concours,
    creer_mission,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours.models import Concours
from apps.utilisateurs.models import Utilisateur

Etat = Concours.Etat


@pytest.mark.django_db
def test_etat_initial_est_brouillon_et_format_presentiel():
    concours = creer_concours()

    assert concours.etat == Etat.BROUILLON
    assert concours.format == Concours.Format.PRESENTIEL
    assert concours.version_corpus is None
    assert concours.configuration_validee_le is None


@pytest.mark.django_db
def test_rm01_le_concours_prend_l_organisation_de_sa_mission():
    mission = creer_mission()

    concours = creer_concours(mission)

    assert concours.organisation_id == mission.organisation_id


@pytest.mark.django_db
def test_une_mission_peut_regrouper_plusieurs_concours():
    mission = creer_mission()
    creer_concours(mission, nom="Concours A")
    creer_concours(mission, nom="Concours B")

    assert mission.concours.count() == 2


@pytest.mark.django_db
def test_la_date_de_fin_ne_peut_pas_preceder_la_date_de_debut():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(date_debut=date(2027, 1, 21), date_fin=date(2027, 1, 20))


@pytest.mark.django_db
def test_nom_et_edition_uniques_par_organisation():
    mission = creer_mission()
    creer_concours(mission, nom="Grand concours", edition="2027")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(mission, nom="Grand concours", edition="2027")


@pytest.mark.django_db
def test_meme_nom_possible_pour_deux_editions_ou_deux_clients():
    mission = creer_mission()
    creer_concours(mission, nom="Grand concours", edition="2027")
    creer_concours(mission, nom="Grand concours", edition="2028")
    creer_concours(creer_mission(), nom="Grand concours", edition="2027")

    assert Concours.objects.filter(nom="Grand concours").count() == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    "etat", [Etat.OUVERT, Etat.EN_COURS, Etat.SUSPENDU, Etat.TERMINE, Etat.ARCHIVE]
)
def test_rm27_rm31_un_concours_non_brouillon_exige_corpus_et_validation(etat):
    """Un concours ouvert a un corpus figé (RM-27) et une configuration validée (RM-31)."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(etat=etat)


@pytest.mark.django_db
def test_un_concours_non_brouillon_avec_corpus_et_validation_est_accepte():
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)
    mission = creer_mission(responsable.organisation)

    concours = creer_concours(
        mission,
        etat=Etat.OUVERT,
        version_corpus=creer_version_validee(),
        configuration_validee_par=responsable,
        configuration_validee_le=timezone.now(),
        configuration_empreinte="a" * 64,
    )

    assert concours.etat == Etat.OUVERT


@pytest.mark.django_db
def test_la_validation_de_configuration_est_complete_ou_absente():
    """Qui, quand et quelle configuration : les trois ensemble, ou aucun des trois."""
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(configuration_validee_par=responsable)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(configuration_validee_le=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(configuration_empreinte="a" * 64)


@pytest.mark.django_db
def test_une_mission_ne_peut_pas_etre_supprimee_si_elle_a_des_concours():
    concours = creer_concours()

    with pytest.raises(ProtectedError):
        concours.mission.delete()
```

**Fichier `apps\concours\tests\test_configuration.py`**

```python
"""Tests des catégories, épreuves, critères et sessions (§7.2, §8.2, RM-03, RM-21)."""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_critere,
    creer_epreuve,
    creer_session,
)
from apps.concours.models import Categorie, Epreuve


# --- Catégorie ---------------------------------------------------------------


@pytest.mark.django_db
def test_la_categorie_prend_l_organisation_du_concours():
    concours = creer_concours()

    assert creer_categorie(concours).organisation_id == concours.organisation_id


@pytest.mark.django_db
def test_valeurs_par_defaut_d_une_categorie():
    categorie = creer_categorie()

    assert categorie.discipline == Categorie.Discipline.MEMORISATION
    assert categorie.regle_classement == Categorie.RegleClassement.MOYENNE
    assert categorie.regle_departage == ""  # le système n'invente jamais de règle (§10.4)
    assert categorie.age_minimum is None and categorie.age_maximum is None


@pytest.mark.django_db
def test_nom_de_categorie_unique_par_concours():
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_categorie(concours, nom="Juniors")
    creer_categorie(creer_concours(), nom="Juniors")  # un autre concours : accepté


@pytest.mark.django_db
def test_l_age_maximum_ne_peut_pas_etre_inferieur_a_l_age_minimum():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_categorie(age_minimum=15, age_maximum=10)
    assert creer_categorie(age_minimum=10, age_maximum=10).age_minimum == 10


# --- Épreuve -----------------------------------------------------------------


@pytest.mark.django_db
def test_l_epreuve_prend_l_organisation_de_sa_categorie():
    categorie = creer_categorie()

    assert creer_epreuve(categorie).organisation_id == categorie.organisation_id


@pytest.mark.django_db
def test_rm03_q_est_calcule_t_fois_p():
    epreuve = creer_epreuve(questions_par_serie=2, tirages_par_candidat=2)

    assert epreuve.questions_par_candidat == 4  # exemple du §8.2 : P = 2, T = 2


@pytest.mark.django_db
def test_valeurs_par_defaut_d_une_epreuve():
    epreuve = creer_epreuve()

    assert epreuve.tirages_par_candidat == 1  # T par défaut (§8.2)
    assert epreuve.questions_par_candidat == epreuve.questions_par_serie
    assert epreuve.mode_affichage == Epreuve.ModeAffichage.ARABE_SEUL
    assert epreuve.etat == Epreuve.Etat.EN_PREPARATION
    # Par prudence, l'écran scène est désactivé tant que l'opérateur ne l'active pas (§9.1).
    assert epreuve.affichage_scene is False


@pytest.mark.django_db
def test_rm21_reglages_de_reutilisation_par_defaut():
    epreuve = creer_epreuve()

    assert epreuve.reutilisation_autre_candidat is False
    assert epreuve.reutilisation_meme_candidat_autre_epreuve is False
    assert epreuve.exclusion_definitive is True


@pytest.mark.django_db
@pytest.mark.parametrize("champ", ["questions_par_serie", "tirages_par_candidat"])
def test_p_et_t_valent_au_moins_un(champ):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_epreuve(**{champ: 0})


@pytest.mark.django_db
def test_ordre_et_nom_d_epreuve_uniques_par_categorie():
    categorie = creer_categorie()
    creer_epreuve(categorie, nom="Récitation", ordre=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_epreuve(categorie, nom="Autre", ordre=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_epreuve(categorie, nom="Récitation", ordre=2)


@pytest.mark.django_db
def test_une_categorie_ne_peut_pas_etre_supprimee_si_elle_a_des_epreuves():
    epreuve = creer_epreuve()

    with pytest.raises(ProtectedError):
        epreuve.categorie.delete()


# --- Critère de notation (barème) --------------------------------------------


@pytest.mark.django_db
def test_le_critere_prend_l_organisation_de_son_epreuve():
    epreuve = creer_epreuve()

    assert creer_critere(epreuve).organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_coefficient_par_defaut_egal_a_un():
    assert creer_critere().coefficient == 1


@pytest.mark.django_db
@pytest.mark.parametrize("champ", ["maximum", "coefficient"])
@pytest.mark.parametrize("valeur", [0, -1])
def test_maximum_et_coefficient_strictement_positifs(champ, valeur):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_critere(**{champ: valeur})


@pytest.mark.django_db
def test_ordre_et_libelle_de_critere_uniques_par_epreuve():
    epreuve = creer_epreuve()
    creer_critere(epreuve, libelle="Mémorisation", ordre=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_critere(epreuve, libelle="Tajwid", ordre=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_critere(epreuve, libelle="Mémorisation", ordre=2)


# --- Session -----------------------------------------------------------------


@pytest.mark.django_db
def test_la_session_prend_l_organisation_du_concours():
    concours = creer_concours()

    assert creer_session(concours).organisation_id == concours.organisation_id


@pytest.mark.django_db
def test_nom_de_session_unique_par_concours():
    concours = creer_concours()
    creer_session(concours, nom="Matin")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_session(concours, nom="Matin")
```

**Fichier `apps\concours\tests\test_services.py`**

```python
"""Tests des règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31).

Un concours ne s'ouvre qu'après validation de sa configuration par le responsable du
client (§6.2). Si la configuration change après cette validation, la validation ne vaut
plus : une empreinte de la configuration permet de le détecter.
"""
import pytest

from apps.commun.tests.outils import (
    configuration_complete,
    creer_categorie,
    creer_concours,
    creer_critere,
    creer_epreuve,
    creer_mission,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours import services
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Concours
from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_version
from apps.utilisateurs.models import Utilisateur

Role = Utilisateur.Role
Statut = VersionCorpus.Statut


@pytest.fixture
def concours_pret_a_valider(db):
    """Un concours en brouillon, avec une configuration complète et un corpus validé."""
    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)
    concours = creer_concours(creer_mission(responsable.organisation))
    configuration_complete(concours)
    services.definir_version_corpus(concours, creer_version_validee())
    return concours, responsable


# --- Version du corpus (RM-27, RM-09) ----------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("statut", [Statut.VALIDEE, Statut.ACTIVE])
def test_rm09_une_version_validee_ou_active_peut_etre_rattachee(statut):
    concours = creer_concours()
    version = creer_version_validee(statut=statut)

    services.definir_version_corpus(concours, version)

    concours.refresh_from_db()
    assert concours.version_corpus == version


@pytest.mark.django_db
@pytest.mark.parametrize("statut", [Statut.IMPORTEE, Statut.RETIREE])
def test_rm09_une_version_non_validee_ou_retiree_est_refusee(statut):
    concours = creer_concours()

    with pytest.raises(ConfigurationInvalideError, match="valid"):
        services.definir_version_corpus(concours, creer_version(statut=statut))

    concours.refresh_from_db()
    assert concours.version_corpus is None


@pytest.mark.django_db
def test_rm27_la_version_est_figee_apres_l_ouverture(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    services.ouvrir_concours(concours)

    with pytest.raises(ConfigurationInvalideError, match="figée"):
        services.definir_version_corpus(concours, creer_version_validee())


# --- Configuration complète --------------------------------------------------


@pytest.mark.django_db
def test_une_configuration_vide_est_incomplete():
    problemes = services.problemes_de_configuration(creer_concours())

    assert any("catégorie" in p for p in problemes)


@pytest.mark.django_db
def test_une_categorie_sans_epreuve_et_une_epreuve_sans_critere_sont_signalees():
    concours = creer_concours()
    creer_categorie(concours, nom="Sans épreuve")
    creer_epreuve(creer_categorie(concours, nom="Avec épreuve"), nom="Sans critère")

    problemes = " | ".join(services.problemes_de_configuration(concours))

    assert "Sans épreuve" in problemes
    assert "Sans critère" in problemes


@pytest.mark.django_db
def test_une_configuration_complete_n_a_aucun_probleme():
    assert services.problemes_de_configuration(configuration_complete(creer_concours())) == []


# --- Validation par le responsable client (RM-31) ----------------------------


@pytest.mark.django_db
def test_rm31_le_responsable_du_client_valide_la_configuration(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider

    services.valider_configuration(concours, responsable)

    concours.refresh_from_db()
    assert concours.configuration_validee_par == responsable
    assert concours.configuration_validee_le is not None
    assert len(concours.configuration_empreinte) == 64


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.OPERATEUR, Role.ADMINISTRATEUR])
def test_rm18_rm31_ni_l_operateur_ni_l_administrateur_ne_valident(concours_pret_a_valider, role):
    """Le prestataire exécute, le client valide (§6.2)."""
    concours, _ = concours_pret_a_valider

    with pytest.raises(ValidationRefuseeError):
        services.valider_configuration(concours, creer_utilisateur(role))

    concours.refresh_from_db()
    assert concours.configuration_validee_le is None


@pytest.mark.django_db
def test_rm20_le_responsable_d_un_autre_client_ne_valide_pas(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider
    autre_responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)

    with pytest.raises(ValidationRefuseeError):
        services.valider_configuration(concours, autre_responsable)


@pytest.mark.django_db
def test_rm31_on_ne_valide_pas_une_configuration_incomplete():
    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)
    concours = creer_concours(creer_mission(responsable.organisation))

    with pytest.raises(ConfigurationInvalideError, match="catégorie"):
        services.valider_configuration(concours, responsable)


@pytest.mark.django_db
def test_rm31_on_ne_valide_pas_sans_version_du_corpus():
    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT)
    concours = configuration_complete(creer_concours(creer_mission(responsable.organisation)))

    with pytest.raises(ConfigurationInvalideError, match="corpus"):
        services.valider_configuration(concours, responsable)


# --- Ouverture (RM-27, RM-31) ------------------------------------------------


@pytest.mark.django_db
def test_rm31_ouverture_apres_validation(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)

    services.ouvrir_concours(concours)

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.OUVERT


@pytest.mark.django_db
def test_rm31_ouverture_refusee_sans_validation(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider

    with pytest.raises(ConfigurationInvalideError, match="validée"):
        services.ouvrir_concours(concours)

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.BROUILLON


@pytest.mark.django_db
def test_rm31_ouverture_refusee_si_la_configuration_a_change_apres_validation(
    concours_pret_a_valider,
):
    """La validation porte sur UNE configuration : si elle change, il faut revalider."""
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    epreuve = concours.categories.first().epreuves.first()
    creer_critere(epreuve, libelle="Critère ajouté après la validation")

    with pytest.raises(ConfigurationInvalideError, match="changé"):
        services.ouvrir_concours(concours)


@pytest.mark.django_db
def test_une_modification_sans_effet_sur_la_configuration_n_invalide_pas_la_validation(
    concours_pret_a_valider,
):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    concours.nom = "Nouveau nom du concours"
    concours.save()

    services.ouvrir_concours(concours)  # ne doit rien lever

    assert concours.etat == Concours.Etat.OUVERT


@pytest.mark.django_db
def test_revalider_apres_un_changement_permet_l_ouverture(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    creer_critere(concours.categories.first().epreuves.first(), libelle="Ajout")
    services.valider_configuration(concours, responsable)

    services.ouvrir_concours(concours)

    assert concours.etat == Concours.Etat.OUVERT


@pytest.mark.django_db
def test_rm09_ouverture_refusee_si_le_corpus_a_ete_retire_entre_temps(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    VersionCorpus.objects.filter(pk=concours.version_corpus_id).update(statut=Statut.RETIREE)

    with pytest.raises(ConfigurationInvalideError, match="corpus"):
        services.ouvrir_concours(concours)


@pytest.mark.django_db
def test_on_n_ouvre_qu_un_concours_en_brouillon(concours_pret_a_valider):
    concours, responsable = concours_pret_a_valider
    services.valider_configuration(concours, responsable)
    services.ouvrir_concours(concours)

    with pytest.raises(ConfigurationInvalideError, match="brouillon"):
        services.ouvrir_concours(concours)


# --- Empreinte de la configuration -------------------------------------------


@pytest.mark.django_db
def test_l_empreinte_change_quand_un_parametre_structurant_change(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider
    avant = services.empreinte_configuration(concours)
    epreuve = concours.categories.first().epreuves.first()

    epreuve.tirages_par_candidat = 2
    epreuve.save()

    assert services.empreinte_configuration(concours) != avant


@pytest.mark.django_db
def test_l_empreinte_est_stable_quand_rien_ne_change(concours_pret_a_valider):
    concours, _ = concours_pret_a_valider

    assert services.empreinte_configuration(concours) == services.empreinte_configuration(concours)
```

### `candidats`

**Fichier `apps\candidats\tests\test_modeles.py`**

```python
"""Tests des modèles Candidat, Participation et Consentement (§7.3, §16.2, §14.2 ; RM-05, RM-28)."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.candidats.exceptions import ParticipationInvalideError
from apps.candidats.models import Consentement, Participation
from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_consentement,
    creer_organisation,
    creer_participation,
)


# --- Candidat ----------------------------------------------------------------


@pytest.mark.django_db
def test_champs_facultatifs_d_un_candidat_par_minimisation():
    """§7.3 / §16.1 : date de naissance, sexe, ville, structure ne sont pas obligatoires."""
    candidat = creer_candidat()

    assert candidat.date_naissance is None
    assert candidat.sexe == "" and candidat.ville == "" and candidat.structure == ""


@pytest.mark.django_db
def test_nom_complet():
    assert creer_candidat(nom="Diallo", prenom="Awa").nom_complet == "Awa Diallo"


# --- Participation -----------------------------------------------------------


@pytest.mark.django_db
def test_statut_initial_est_inscrit():
    assert creer_participation().statut == Participation.Statut.INSCRIT


@pytest.mark.django_db
def test_la_participation_prend_l_organisation_du_concours():
    categorie = creer_categorie()

    participation = creer_participation(categorie)

    assert participation.organisation_id == categorie.organisation_id


@pytest.mark.django_db
def test_numero_de_candidat_unique_par_concours():
    categorie = creer_categorie()
    creer_participation(categorie, numero_candidat=7)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_participation(categorie, numero_candidat=7)


@pytest.mark.django_db
def test_meme_numero_possible_dans_deux_concours():
    creer_participation(numero_candidat=7)
    creer_participation(numero_candidat=7)

    assert Participation.objects.filter(numero_candidat=7).count() == 2


@pytest.mark.django_db
def test_un_candidat_ne_s_inscrit_qu_une_fois_par_categorie():
    categorie = creer_categorie()
    candidat = creer_candidat(categorie.organisation)
    creer_participation(categorie, candidat)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_participation(categorie, candidat)


@pytest.mark.django_db
def test_un_candidat_peut_s_inscrire_dans_deux_categories_du_meme_concours():
    categorie_a = creer_categorie(nom="Mémorisation")
    categorie_b = creer_categorie(categorie_a.concours, nom="Tajwid")
    candidat = creer_candidat(categorie_a.organisation)

    creer_participation(categorie_a, candidat)
    creer_participation(categorie_b, candidat)

    assert candidat.participations.count() == 2


@pytest.mark.django_db
def test_la_categorie_doit_appartenir_au_concours_de_la_participation():
    categorie = creer_categorie()
    autre_concours = creer_concours(categorie.concours.mission, nom="Autre concours")

    with pytest.raises(ParticipationInvalideError):
        Participation.objects.create(
            candidat=creer_candidat(categorie.organisation),
            concours=autre_concours,
            categorie=categorie,
            numero_candidat=1,
        )


@pytest.mark.django_db
def test_rm20_un_candidat_d_un_autre_client_est_refuse():
    categorie = creer_categorie()
    candidat_d_ailleurs = creer_candidat(creer_organisation())

    with pytest.raises(IncoherenceOrganisationError):
        Participation.objects.create(
            candidat=candidat_d_ailleurs,
            concours=categorie.concours,
            categorie=categorie,
            numero_candidat=1,
        )


@pytest.mark.django_db
def test_une_organisation_ne_peut_pas_etre_supprimee_si_elle_a_des_candidats():
    candidat = creer_candidat()

    with pytest.raises(ProtectedError):
        candidat.organisation.delete()


# --- Consentement ------------------------------------------------------------


@pytest.mark.django_db
def test_les_trois_consentements_sont_distincts_et_jamais_precoches():
    """§16.2 : trois consentements non précochés ; le seul fourni par le test est celui n° 1."""
    consentement = Consentement.objects.create(
        participation=creer_participation(),
        representant_nom="Parent",
        representant_lien="Père",
        version_formulaire="1.0",
        date_signature=date(2027, 1, 10),
    )

    assert consentement.consentement_participation is False
    assert consentement.consentement_publication_nom is False
    assert consentement.consentement_image_voix is False
    assert consentement.statut == Consentement.Statut.VALIDE


@pytest.mark.django_db
def test_le_consentement_prend_l_organisation_de_la_participation():
    participation = creer_participation()

    assert creer_consentement(participation).organisation_id == participation.organisation_id


@pytest.mark.django_db
def test_un_seul_consentement_valide_par_participation():
    participation = creer_participation()
    creer_consentement(participation)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_consentement(participation, version_formulaire="1.1")


@pytest.mark.django_db
def test_un_nouveau_formulaire_est_possible_apres_le_retrait_du_precedent():
    """Le retrait prend effet pour l'avenir (§16.2) : l'ancien formulaire est conservé."""
    participation = creer_participation()
    creer_consentement(
        participation, statut=Consentement.Statut.RETIRE, date_retrait=date(2027, 1, 15)
    )

    creer_consentement(participation, version_formulaire="1.1")

    assert participation.consentements.count() == 2


@pytest.mark.django_db
def test_un_consentement_retire_a_une_date_de_retrait_et_inversement():
    participation = creer_participation()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_consentement(participation, statut=Consentement.Statut.RETIRE)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_consentement(participation, date_retrait=date(2027, 1, 15))
```

**Fichier `apps\candidats\tests\test_services.py`**

```python
"""Tests des règles sur les candidats : âge, consentement, inscription (§7.3, §16.2, §14.2 ; RM-28).

Aucun tirage sans consentement parental pour un mineur (règle absolue n°6) ; aucun tirage
pour une participation non admise (§14.2).
"""
from datetime import date

import pytest

from apps.candidats import services
from apps.candidats.exceptions import (
    ConsentementManquantError,
    ParticipationNonAdmiseError,
    TirageImpossibleError,
)
from apps.candidats.models import Consentement, Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_consentement,
    creer_participation,
)

Statut = Participation.Statut
DEBUT_DU_CONCOURS = date(2027, 1, 20)


def participation_nee_le(naissance, statut=Statut.ADMIS):
    """Une participation à un concours qui commence le 20 janvier 2027."""
    concours = creer_concours(date_debut=DEBUT_DU_CONCOURS, date_fin=DEBUT_DU_CONCOURS)
    categorie = creer_categorie(concours)
    candidat = creer_candidat(categorie.organisation, date_naissance=naissance)
    return creer_participation(categorie, candidat, statut=statut)


# --- Âge ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "naissance, reference, attendu",
    [
        (date(2009, 1, 20), date(2027, 1, 20), 18),  # 18 ans révolus le jour même
        (date(2009, 1, 21), date(2027, 1, 20), 17),  # il manque un jour
        (date(2010, 6, 15), date(2027, 1, 20), 16),
        (date(2000, 2, 29), date(2027, 2, 28), 26),  # naissance un 29 février
        (date(2000, 2, 29), date(2027, 3, 1), 27),
    ],
)
def test_age_a_la_date(naissance, reference, attendu):
    assert services.age_a_la_date(naissance, reference) == attendu


# --- Mineur (§16.2) ----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "naissance, attendu",
    [
        (date(2009, 1, 21), True),  # 17 ans à la date de début du concours
        (date(2009, 1, 20), False),  # 18 ans révolus le jour du début : majeur
        (date(1990, 5, 5), False),
        (None, None),  # date inconnue : on ne sait pas
    ],
)
def test_est_mineur_a_la_date_de_debut_du_concours(naissance, attendu):
    assert services.est_mineur(participation_nee_le(naissance)) is attendu


# --- Consentement requis (D13 : prudence quand la date est inconnue) ----------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "naissance, attendu",
    [(date(2012, 3, 3), True), (date(1990, 5, 5), False), (None, True)],
)
def test_consentement_requis_pour_un_mineur_ou_par_prudence_si_l_age_est_inconnu(naissance, attendu):
    assert services.consentement_requis(participation_nee_le(naissance)) is attendu


@pytest.mark.django_db
def test_consentement_valide_ignore_les_formulaires_retires():
    participation = participation_nee_le(date(2012, 3, 3))
    creer_consentement(
        participation, statut=Consentement.Statut.RETIRE, date_retrait=date(2027, 1, 15)
    )
    assert services.consentement_valide(participation) is None

    valide = creer_consentement(participation, version_formulaire="1.1")

    assert services.consentement_valide(participation) == valide


# --- Prêt pour le tirage (RM-28, §14.2) --------------------------------------


@pytest.mark.django_db
def test_un_majeur_admis_peut_tirer_sans_consentement():
    services.verifier_pret_pour_tirage(participation_nee_le(date(1990, 5, 5)))


@pytest.mark.django_db
@pytest.mark.parametrize("statut", [Statut.INSCRIT, Statut.RETIRE])
def test_une_participation_non_admise_ne_tire_pas(statut):
    participation = participation_nee_le(date(1990, 5, 5), statut=statut)

    with pytest.raises(ParticipationNonAdmiseError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_un_mineur_sans_consentement_ne_tire_pas():
    participation = participation_nee_le(date(2012, 3, 3))

    with pytest.raises(ConsentementManquantError, match="consentement"):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_un_mineur_dont_le_consentement_de_participation_n_est_pas_accorde_ne_tire_pas():
    """Les trois consentements sont distincts : seul le n° 1 (participation) autorise le tirage."""
    participation = participation_nee_le(date(2012, 3, 3))
    creer_consentement(
        participation,
        consentement_participation=False,
        consentement_publication_nom=True,
        consentement_image_voix=True,
    )

    with pytest.raises(ConsentementManquantError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_un_mineur_avec_consentement_de_participation_peut_tirer():
    participation = participation_nee_le(date(2012, 3, 3))
    creer_consentement(participation, consentement_participation=True)

    services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_rm28_le_retrait_du_consentement_bloque_le_tirage():
    participation = participation_nee_le(date(2012, 3, 3))
    consentement = creer_consentement(participation)
    services.verifier_pret_pour_tirage(participation)

    consentement.statut = Consentement.Statut.RETIRE
    consentement.date_retrait = date(2027, 1, 19)
    consentement.save()

    with pytest.raises(ConsentementManquantError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_date_de_naissance_inconnue_exige_le_consentement_par_prudence():
    participation = participation_nee_le(None)

    with pytest.raises(ConsentementManquantError):
        services.verifier_pret_pour_tirage(participation)


@pytest.mark.django_db
def test_les_deux_erreurs_sont_des_tirages_impossibles():
    assert issubclass(ParticipationNonAdmiseError, TirageImpossibleError)
    assert issubclass(ConsentementManquantError, TirageImpossibleError)


# --- Inscription et numérotation (§7.3) --------------------------------------


@pytest.mark.django_db
def test_le_premier_candidat_recoit_le_numero_1_puis_les_suivants_s_incrementent():
    categorie = creer_categorie()

    premiere = services.inscrire(creer_candidat(categorie.organisation), categorie)
    seconde = services.inscrire(creer_candidat(categorie.organisation), categorie)

    assert (premiere.numero_candidat, seconde.numero_candidat) == (1, 2)
    assert premiere.statut == Statut.INSCRIT
    assert premiere.concours == categorie.concours


@pytest.mark.django_db
def test_la_numerotation_est_propre_a_chaque_concours():
    categorie_a, categorie_b = creer_categorie(), creer_categorie()

    services.inscrire(creer_candidat(categorie_a.organisation), categorie_a)
    premiere_de_b = services.inscrire(creer_candidat(categorie_b.organisation), categorie_b)

    assert premiere_de_b.numero_candidat == 1


@pytest.mark.django_db
def test_la_numerotation_continue_apres_le_numero_le_plus_eleve():
    categorie = creer_categorie()
    creer_participation(categorie, numero_candidat=41)

    nouvelle = services.inscrire(creer_candidat(categorie.organisation), categorie)

    assert nouvelle.numero_candidat == 42


@pytest.mark.django_db
def test_les_numeros_ne_sont_pas_reutilises_apres_un_retrait():
    categorie = creer_categorie()
    premiere = services.inscrire(creer_candidat(categorie.organisation), categorie)
    premiere.statut = Statut.RETIRE
    premiere.save()

    suivante = services.inscrire(creer_candidat(categorie.organisation), categorie)

    assert suivante.numero_candidat == 2
```

## Étape D — Le code de `concours`

**Fichier `apps\concours\apps.py`**

```python
from django.apps import AppConfig


class ConcoursConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.concours"
    label = "concours"
    verbose_name = "Concours"
```

**Fichier `apps\concours\exceptions.py`**

```python
"""Exceptions de l'application concours."""


class ConfigurationInvalideError(Exception):
    """La configuration d'un concours est incomplète, ou l'opération demandée n'est pas permise dans cet état."""


class ValidationRefuseeError(Exception):
    """Seul le responsable du client concerné peut valider la configuration (§6.2, RM-18, RM-31)."""
```

**Fichier `apps\concours\models.py`**

```python
"""Concours, catégories, épreuves, barème et sessions (§7.2, §8.2, §14.1)."""
from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient


class Concours(ModeleDuClient):
    """Un concours (une édition) conduit pour un client, dans le cadre d'une mission."""

    PARENTS_CLIENT = ("mission",)

    class Format(models.TextChoices):
        PRESENTIEL = "presentiel", "Présentiel"  # en ligne et hybride : V2

    class Etat(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        OUVERT = "ouvert", "Ouvert"
        EN_COURS = "en_cours", "En cours"
        SUSPENDU = "suspendu", "Suspendu"
        TERMINE = "termine", "Terminé"
        ARCHIVE = "archive", "Archivé"

    mission = models.ForeignKey(
        "clients.Mission", on_delete=models.PROTECT, related_name="concours"
    )
    nom = models.CharField(max_length=200)
    edition = models.CharField(max_length=50, blank=True, help_text="Millésime ou numéro d'édition.")
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.PRESENTIEL)
    date_debut = models.DateField()
    date_fin = models.DateField()
    # RM-27 : version unique du corpus, figée à l'ouverture. Vide tant que le concours est en brouillon.
    version_corpus = models.ForeignKey(
        "coran.VersionCorpus",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="concours",
    )
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.BROUILLON)
    # RM-31 : validation de la configuration par le responsable du client (qui, quand, quelle configuration).
    configuration_validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    configuration_validee_le = models.DateTimeField(null=True, blank=True)
    configuration_empreinte = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Empreinte SHA-256 de la configuration au moment de sa validation.",
    )

    class Meta:
        verbose_name = "concours"
        verbose_name_plural = "concours"
        ordering = ["-date_debut", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "nom", "edition"], name="concours_nom_edition_uniques"
            ),
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="concours_date_fin_apres_date_debut",
            ),
            # La validation est complète ou absente : qui, quand et quelle configuration.
            models.CheckConstraint(
                condition=(
                    Q(
                        configuration_validee_par__isnull=True,
                        configuration_validee_le__isnull=True,
                        configuration_empreinte="",
                    )
                    | (
                        Q(configuration_validee_par__isnull=False, configuration_validee_le__isnull=False)
                        & ~Q(configuration_empreinte="")
                    )
                ),
                name="concours_validation_configuration_complete",
            ),
            # RM-27 et RM-31 : hors brouillon, le corpus est figé et la configuration validée.
            models.CheckConstraint(
                condition=(
                    Q(etat="brouillon")
                    | (Q(version_corpus__isnull=False) & Q(configuration_validee_le__isnull=False))
                ),
                name="concours_ouvert_exige_corpus_et_validation",
            ),
        ]

    def __str__(self):
        return f"{self.nom} {self.edition}".strip()


class Categorie(ModeleDuClient):
    """Une catégorie d'un concours : mémorisation, tajwid, tilawa, questions..."""

    PARENTS_CLIENT = ("concours",)

    class Discipline(models.TextChoices):
        MEMORISATION = "memorisation", "Mémorisation"
        TAJWID = "tajwid", "Tajwid"
        TILAWA = "tilawa", "Tilawa"
        QUESTIONS = "questions", "Questions"
        PERSONNALISEE = "personnalisee", "Personnalisée"

    class RegleClassement(models.TextChoices):
        MOYENNE = "moyenne", "Moyenne"
        TOTAL = "total", "Total"
        ELIMINATION = "elimination", "Élimination"

    class RegleDepartage(models.TextChoices):
        MOYENNE_GENERALE = "moyenne_generale", "Moyenne générale"
        CRITERE_PRIORITAIRE = "critere_prioritaire", "Critère prioritaire"
        EPREUVE_SUPPLEMENTAIRE = "epreuve_supplementaire", "Épreuve supplémentaire"
        DECISION_COMITE = "decision_comite", "Décision documentée du comité"

    concours = models.ForeignKey(Concours, on_delete=models.PROTECT, related_name="categories")
    nom = models.CharField(max_length=100)
    discipline = models.CharField(
        max_length=20, choices=Discipline.choices, default=Discipline.MEMORISATION
    )
    age_minimum = models.PositiveSmallIntegerField(null=True, blank=True)
    age_maximum = models.PositiveSmallIntegerField(null=True, blank=True)
    effectif_prevu = models.PositiveIntegerField(null=True, blank=True)
    regle_classement = models.CharField(
        max_length=20, choices=RegleClassement.choices, default=RegleClassement.MOYENNE
    )
    # Vide par défaut : le système n'invente jamais de règle de départage (§10.4).
    regle_departage = models.CharField(
        max_length=30, choices=RegleDepartage.choices, blank=True, default=""
    )

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(fields=["concours", "nom"], name="categorie_nom_unique_par_concours"),
            models.CheckConstraint(
                condition=(
                    Q(age_minimum__isnull=True)
                    | Q(age_maximum__isnull=True)
                    | Q(age_maximum__gte=F("age_minimum"))
                ),
                name="categorie_age_maximum_apres_age_minimum",
            ),
        ]

    def __str__(self):
        return self.nom


class Epreuve(ModeleDuClient):
    """Une épreuve d'une catégorie, avec ses paramètres de tirage (§8.2, RM-03, RM-21)."""

    PARENTS_CLIENT = ("categorie",)

    class ModeAffichage(models.TextChoices):
        ARABE_SEUL = "arabe_seul", "Arabe seul"
        ARABE_ET_TRADUCTION = "arabe_et_traduction", "Arabe avec traduction française"

    class Etat(models.TextChoices):
        EN_PREPARATION = "en_preparation", "En préparation"
        OUVERTE = "ouverte", "Ouverte"
        TERMINEE = "terminee", "Terminée"

    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="epreuves")
    nom = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField()
    # P : questions par série. T : tirages par candidat. Q = T x P est calculé (RM-03).
    questions_par_serie = models.PositiveSmallIntegerField(help_text="P")
    tirages_par_candidat = models.PositiveSmallIntegerField(default=1, help_text="T")
    # RM-21 : réutilisation des séries tirées.
    reutilisation_autre_candidat = models.BooleanField(default=False)
    reutilisation_meme_candidat_autre_epreuve = models.BooleanField(default=False)
    exclusion_definitive = models.BooleanField(default=True)
    mode_affichage = models.CharField(
        max_length=30, choices=ModeAffichage.choices, default=ModeAffichage.ARABE_SEUL
    )
    # Désactivé par défaut : en mémorisation, l'écran scène ne doit pas être visible du candidat (§9.1).
    affichage_scene = models.BooleanField(default=False)
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.EN_PREPARATION)

    class Meta:
        verbose_name = "épreuve"
        verbose_name_plural = "épreuves"
        ordering = ["categorie", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["categorie", "ordre"], name="epreuve_ordre_unique_par_categorie"),
            models.UniqueConstraint(fields=["categorie", "nom"], name="epreuve_nom_unique_par_categorie"),
            models.CheckConstraint(
                condition=Q(questions_par_serie__gte=1), name="epreuve_p_au_moins_1"
            ),
            models.CheckConstraint(
                condition=Q(tirages_par_candidat__gte=1), name="epreuve_t_au_moins_1"
            ),
        ]

    @property
    def questions_par_candidat(self):
        """Q = T x P (RM-03) : calculé, jamais saisi."""
        return self.tirages_par_candidat * self.questions_par_serie

    def __str__(self):
        return self.nom


class CritereNotation(ModeleDuClient):
    """Un critère du barème d'une épreuve : libellé, note maximale, coefficient (§7.2)."""

    PARENTS_CLIENT = ("epreuve",)

    epreuve = models.ForeignKey(Epreuve, on_delete=models.PROTECT, related_name="criteres")
    libelle = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField()
    maximum = models.DecimalField(max_digits=6, decimal_places=2)
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        verbose_name = "critère de notation"
        verbose_name_plural = "critères de notation"
        ordering = ["epreuve", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["epreuve", "ordre"], name="critere_ordre_unique_par_epreuve"),
            models.UniqueConstraint(fields=["epreuve", "libelle"], name="critere_libelle_unique_par_epreuve"),
            models.CheckConstraint(condition=Q(maximum__gt=0), name="critere_maximum_positif"),
            models.CheckConstraint(condition=Q(coefficient__gt=0), name="critere_coefficient_positif"),
        ]

    def __str__(self):
        return self.libelle


class Session(ModeleDuClient):
    """Une session de passage d'un concours : date, lieu, serveur de salle utilisé (§14.1)."""

    PARENTS_CLIENT = ("concours",)

    concours = models.ForeignKey(Concours, on_delete=models.PROTECT, related_name="sessions")
    nom = models.CharField(max_length=100)
    date = models.DateField()
    lieu = models.CharField(max_length=200, blank=True)
    serveur_de_salle = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "session"
        verbose_name_plural = "sessions"
        ordering = ["date", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["concours", "nom"], name="session_nom_unique_par_concours"),
        ]

    def __str__(self):
        return f"{self.nom} ({self.date})"
```

**Fichier `apps\concours\services.py`**

```python
"""Règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31)."""
import hashlib
import json

from django.utils import timezone

from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Concours
from apps.coran.models import VersionCorpus
from apps.utilisateurs.models import Utilisateur


def _statut_actuel_du_corpus(version_id):
    """Statut lu dans la base : l'objet en mémoire peut être périmé."""
    return VersionCorpus.objects.filter(pk=version_id).values_list("statut", flat=True).first()


def _verifier_version_utilisable(version_id):
    if _statut_actuel_du_corpus(version_id) not in (
        VersionCorpus.Statut.VALIDEE,
        VersionCorpus.Statut.ACTIVE,
    ):
        raise ConfigurationInvalideError(
            "Seule une version du corpus validée ou active peut être utilisée par un concours (RM-09)."
        )


def definir_version_corpus(concours, version):
    """Rattache une version du corpus au concours ; impossible après l'ouverture (RM-27)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La version du corpus est figée à l'ouverture du concours (RM-27)."
        )
    _verifier_version_utilisable(version.pk)
    concours.version_corpus = version
    concours.save(update_fields=["version_corpus", "modifie_le"])


def problemes_de_configuration(concours):
    """Liste ce qui manque pour que la configuration soit validable (vide si tout est en ordre)."""
    categories = list(concours.categories.order_by("nom"))
    if not categories:
        return ["Le concours n'a aucune catégorie."]
    problemes = []
    for categorie in categories:
        epreuves = list(categorie.epreuves.order_by("ordre"))
        if not epreuves:
            problemes.append(f"La catégorie « {categorie.nom} » n'a aucune épreuve.")
        for epreuve in epreuves:
            if not epreuve.criteres.exists():
                problemes.append(f"L'épreuve « {epreuve.nom} » n'a aucun critère de notation.")
    return problemes


def empreinte_configuration(concours):
    """Empreinte SHA-256 de la configuration : catégories, épreuves, barème et réglages de tirage.

    Sert à détecter qu'une configuration a changé APRÈS avoir été validée (RM-31).
    """
    description = []
    for categorie in concours.categories.order_by("nom"):
        epreuves = []
        for epreuve in categorie.epreuves.order_by("ordre"):
            epreuves.append(
                {
                    "nom": epreuve.nom,
                    "ordre": epreuve.ordre,
                    "P": epreuve.questions_par_serie,
                    "T": epreuve.tirages_par_candidat,
                    "reutilisation_autre_candidat": epreuve.reutilisation_autre_candidat,
                    "reutilisation_meme_candidat_autre_epreuve": (
                        epreuve.reutilisation_meme_candidat_autre_epreuve
                    ),
                    "exclusion_definitive": epreuve.exclusion_definitive,
                    "mode_affichage": epreuve.mode_affichage,
                    "affichage_scene": epreuve.affichage_scene,
                    "criteres": [
                        {
                            "libelle": critere.libelle,
                            "ordre": critere.ordre,
                            "maximum": str(critere.maximum),
                            "coefficient": str(critere.coefficient),
                        }
                        for critere in epreuve.criteres.order_by("ordre")
                    ],
                }
            )
        description.append(
            {
                "nom": categorie.nom,
                "discipline": categorie.discipline,
                "age_minimum": categorie.age_minimum,
                "age_maximum": categorie.age_maximum,
                "effectif_prevu": categorie.effectif_prevu,
                "regle_classement": categorie.regle_classement,
                "regle_departage": categorie.regle_departage,
                "epreuves": epreuves,
            }
        )
    texte = json.dumps(description, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def valider_configuration(concours, utilisateur):
    """Le responsable du client valide la configuration du concours (RM-31, §6.2).

    Le prestataire exécute, le client valide : ni l'opérateur ni l'administrateur ne peuvent le faire.
    """
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != concours.organisation_id
    ):
        raise ValidationRefuseeError(
            "Seul le responsable du client concerné peut valider la configuration du concours."
        )
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La configuration ne se valide que pour un concours en brouillon."
        )
    problemes = problemes_de_configuration(concours)
    if problemes:
        raise ConfigurationInvalideError("Configuration incomplète : " + " ".join(problemes))
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError(
            "Aucune version du corpus n'est rattachée au concours (RM-27)."
        )
    concours.configuration_validee_par = utilisateur
    concours.configuration_validee_le = timezone.now()
    concours.configuration_empreinte = empreinte_configuration(concours)
    concours.save(
        update_fields=[
            "configuration_validee_par",
            "configuration_validee_le",
            "configuration_empreinte",
            "modifie_le",
        ]
    )


def ouvrir_concours(concours):
    """Ouvre un concours : configuration validée et inchangée, corpus validé ou actif (RM-27, RM-31)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            f"Seul un concours en brouillon peut être ouvert (état actuel : {concours.get_etat_display()})."
        )
    if concours.configuration_validee_le is None:
        raise ConfigurationInvalideError(
            "La configuration n'a pas été validée par le responsable du client (RM-31)."
        )
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError("Aucune version du corpus n'est rattachée au concours.")
    _verifier_version_utilisable(concours.version_corpus_id)
    if empreinte_configuration(concours) != concours.configuration_empreinte:
        raise ConfigurationInvalideError(
            "La configuration a changé depuis sa validation : "
            "le responsable du client doit la valider de nouveau (RM-31)."
        )
    concours.etat = Concours.Etat.OUVERT
    concours.save(update_fields=["etat", "modifie_le"])
```

## Étape E — Le code de `candidats`

**Fichier `apps\candidats\apps.py`**

```python
from django.apps import AppConfig


class CandidatsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.candidats"
    label = "candidats"
    verbose_name = "Candidats"
```

**Fichier `apps\candidats\exceptions.py`**

```python
"""Exceptions de l'application candidats."""


class ParticipationInvalideError(Exception):
    """Une participation est incohérente (par exemple une catégorie qui n'est pas celle du concours)."""


class TirageImpossibleError(Exception):
    """Le tirage ne peut pas être déclenché pour cette participation (§14.2, RM-28)."""


class ParticipationNonAdmiseError(TirageImpossibleError):
    """La participation n'est pas admise : aucun tirage (§14.2)."""


class ConsentementManquantError(TirageImpossibleError):
    """Le consentement parental requis n'est pas enregistré : aucun tirage (RM-28, règle absolue n°6)."""
```

**Fichier `apps\candidats\models.py`**

```python
"""Candidats, participations et consentements parentaux (§7.3, §14.1, §16.2)."""
from django.db import models
from django.db.models import Q

from apps.candidats.exceptions import ParticipationInvalideError
from apps.commun.models import ModeleDuClient


class Candidat(ModeleDuClient):
    """Une personne inscrite par l'opérateur à partir des informations du client (RM-05).

    Minimisation (§16.1) : seuls le nom et le prénom sont obligatoires ; aucune pièce
    d'identité, aucune photographie, aucune donnée de santé.
    """

    class Sexe(models.TextChoices):
        MASCULIN = "M", "Masculin"
        FEMININ = "F", "Féminin"

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    date_naissance = models.DateField(
        null=True, blank=True, help_text="Nécessaire si la catégorie dépend de l'âge ou pour reconnaître un mineur."
    )
    sexe = models.CharField(max_length=1, choices=Sexe.choices, blank=True, default="")
    ville = models.CharField(max_length=100, blank=True)
    structure = models.CharField(max_length=200, blank=True, help_text="Structure représentée.")

    class Meta:
        verbose_name = "candidat"
        verbose_name_plural = "candidats"
        ordering = ["nom", "prenom"]

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return self.nom_complet


class Participation(ModeleDuClient):
    """L'inscription d'un candidat à une catégorie d'un concours, avec son numéro (§14.1)."""

    PARENTS_CLIENT = ("candidat", "concours", "categorie")

    class Statut(models.TextChoices):
        INSCRIT = "inscrit", "Inscrit"
        ADMIS = "admis", "Admis à concourir"
        RETIRE = "retire", "Retiré"

    candidat = models.ForeignKey(Candidat, on_delete=models.PROTECT, related_name="participations")
    concours = models.ForeignKey(
        "concours.Concours", on_delete=models.PROTECT, related_name="participations"
    )
    categorie = models.ForeignKey(
        "concours.Categorie", on_delete=models.PROTECT, related_name="participations"
    )
    numero_candidat = models.PositiveIntegerField()
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.INSCRIT)

    class Meta:
        verbose_name = "participation"
        verbose_name_plural = "participations"
        ordering = ["concours", "numero_candidat"]
        constraints = [
            models.UniqueConstraint(
                fields=["concours", "numero_candidat"], name="participation_numero_unique_par_concours"
            ),
            models.UniqueConstraint(
                fields=["candidat", "categorie"], name="participation_unique_par_categorie"
            ),
            models.CheckConstraint(
                condition=Q(numero_candidat__gte=1), name="participation_numero_au_moins_1"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.categorie.concours_id != self.concours_id:
            raise ParticipationInvalideError(
                "La catégorie de la participation n'appartient pas au concours indiqué."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"n° {self.numero_candidat} — {self.candidat}"


class Consentement(ModeleDuClient):
    """Formulaire de consentement parental d'un candidat mineur (§16.2, RM-28).

    Trois consentements distincts et jamais précochés : (1) participation et traitement
    des données, (2) publication du nom dans les classements, (3) image ou voix.
    Le retrait prend effet pour l'avenir : le formulaire est marqué « retiré » et conservé.
    Un retrait partiel se fait en retirant ce formulaire puis en en enregistrant un nouveau.
    """

    class Statut(models.TextChoices):
        VALIDE = "valide", "Valide"
        RETIRE = "retire", "Retiré"

    PARENTS_CLIENT = ("participation",)

    participation = models.ForeignKey(
        Participation, on_delete=models.PROTECT, related_name="consentements"
    )
    representant_nom = models.CharField(max_length=200)
    representant_lien = models.CharField(max_length=100, help_text="Lien avec le candidat.")
    version_formulaire = models.CharField(max_length=20)
    date_signature = models.DateField()
    consentement_participation = models.BooleanField(default=False)
    consentement_publication_nom = models.BooleanField(default=False)
    consentement_image_voix = models.BooleanField(default=False)
    # Document numérisé. Son stockage chiffré sera mis en place avec la sécurité du serveur de salle (§15).
    document = models.FileField(upload_to="consentements/", blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.VALIDE)
    date_retrait = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "consentement"
        verbose_name_plural = "consentements"
        ordering = ["participation", "-date_signature"]
        constraints = [
            # Un seul formulaire valide à la fois par participation ; les formulaires retirés restent.
            models.UniqueConstraint(
                fields=["participation"],
                condition=Q(statut="valide"),
                name="consentement_un_seul_valide_par_participation",
            ),
            models.CheckConstraint(
                condition=(
                    Q(statut="valide", date_retrait__isnull=True)
                    | Q(statut="retire", date_retrait__isnull=False)
                ),
                name="consentement_retrait_coherent",
            ),
        ]

    def __str__(self):
        return f"Consentement de {self.representant_nom} ({self.get_statut_display()})"
```

**Fichier `apps\candidats\services.py`**

```python
"""Règles sur les candidats : âge, consentement parental, numérotation (§7.3, §16.2, RM-28)."""
from django.db import transaction
from django.db.models import Max

from apps.candidats.exceptions import ConsentementManquantError, ParticipationNonAdmiseError
from apps.candidats.models import Consentement, Participation
from apps.concours.models import Concours

AGE_DE_MAJORITE = 18  # loi n° 2019-572 du 26 juin 2019 (§16.2)


def age_a_la_date(naissance, reference):
    """Âge en années révolues à la date de référence."""
    avant_anniversaire = (reference.month, reference.day) < (naissance.month, naissance.day)
    return reference.year - naissance.year - (1 if avant_anniversaire else 0)


def est_mineur(participation):
    """Vrai si le candidat a moins de 18 ans à la date de début du concours (§16.2).

    Renvoie ``None`` quand la date de naissance n'est pas connue : on ne sait pas.
    """
    naissance = participation.candidat.date_naissance
    if naissance is None:
        return None
    return age_a_la_date(naissance, participation.concours.date_debut) < AGE_DE_MAJORITE


def consentement_requis(participation):
    """Le consentement parental est requis pour un mineur, et PAR PRUDENCE si l'âge est inconnu (D13).

    Règle absolue n°6 : un mineur sans consentement ne tire pas. Mieux vaut demander la date
    de naissance (ou le consentement) que laisser passer un mineur par ignorance.
    """
    return est_mineur(participation) is not False


def consentement_valide(participation):
    """Le formulaire de consentement actuellement valide, ou ``None``."""
    return participation.consentements.filter(statut=Consentement.Statut.VALIDE).first()


def verifier_pret_pour_tirage(participation):
    """Refuse le tirage si la participation n'est pas admise (§14.2) ou si le consentement manque (RM-28)."""
    if participation.statut != Participation.Statut.ADMIS:
        raise ParticipationNonAdmiseError(
            f"La participation n° {participation.numero_candidat} n'est pas admise : aucun tirage."
        )
    if consentement_requis(participation):
        consentement = consentement_valide(participation)
        if consentement is None or not consentement.consentement_participation:
            raise ConsentementManquantError(
                "Aucun consentement parental valide pour la participation et le traitement "
                "des données : aucun tirage (RM-28)."
            )


def inscrire(candidat, categorie):
    """Inscrit un candidat à une catégorie et lui attribue le numéro suivant du concours.

    Le numéro est le plus élevé du concours plus un, retraits compris : un numéro n'est jamais réutilisé.
    Le verrou sur le concours évite que deux inscriptions simultanées reçoivent le même numéro.
    """
    with transaction.atomic():
        Concours.objects.select_for_update().get(pk=categorie.concours_id)
        dernier = Participation.objects.filter(concours_id=categorie.concours_id).aggregate(
            numero=Max("numero_candidat")
        )["numero"]
        return Participation.objects.create(
            candidat=candidat,
            concours=categorie.concours,
            categorie=categorie,
            numero_candidat=(dernier or 0) + 1,
        )
```

## Étape F — Migrations

```powershell
python manage.py check
python manage.py makemigrations concours candidats
python manage.py migrate
python manage.py makemigrations --check --dry-run
```

Attendu : `concours\migrations\0001_initial.py` (cinq modèles et leurs contraintes) et deux migrations pour `candidats` (`0001_initial` et `0002_initial` : Django sépare les clés étrangères vers `concours` quand les deux applications sont générées ensemble ; c'est sans conséquence), puis `No changes detected`.

## Étape G — Vérifier

```powershell
pytest apps\commun apps\concours apps\candidats
pytest
```

Attendu :

- les trois dossiers : **125 passed** ;
- la suite complète : **277 passed, 66 failed** si les règles des chapitres 4, 6 et 7 ne sont pas encore écrites, et **343 passed** si elles le sont.

## Étape H — Commit

```powershell
git add apps config\settings\base.py
git status
git commit -m "Étape 1.2, lot 2 : applications concours et candidats"
```

## Pour comprendre

### Les contraintes qui portent RM-27 et RM-31

Sur `Concours`, une contrainte de base dit : *« l'état est « brouillon », ou bien (une version du corpus est rattachée ET la configuration est validée) »*. Même une erreur de code ne peut donc créer un concours « ouvert » sans corpus figé ni validation du client. Une deuxième contrainte garantit que la validation est **complète ou absente** : qui, quand, et quelle configuration, les trois ensemble.

### Pourquoi une empreinte de la configuration (D14) ?

Le responsable client valide « la configuration » à un instant donné. Si l'opérateur ajoute ensuite un critère de notation, la validation ne couvre plus ce qui sera réellement utilisé. Plutôt que de bloquer toute modification (lourd), on enregistre l'**empreinte** de ce qui a été validé : à l'ouverture, on la recalcule et on la compare. Si elle diffère, on refuse et on demande une nouvelle validation. Seuls les éléments qui comptent pour le concours entrent dans l'empreinte (catégories, épreuves, barème, réglages de tirage) : renommer le concours ne l'invalide pas.

### Le prestataire exécute, le client valide (§6.2)

`valider_configuration` refuse l'opérateur, l'administrateur, un utilisateur désactivé, et un responsable d'un **autre** client. C'est la règle d'accès appliquée côté serveur (règle absolue n°4), pas un bouton masqué.

### Pourquoi `select_for_update` dans `inscrire` ?

Deux opérateurs qui inscrivent un candidat au même instant pourraient lire le même « dernier numéro » et attribuer le **même** numéro. Le verrou sur la ligne du concours force la seconde inscription à attendre la première. (La contrainte d'unicité refuserait aussi le doublon, mais avec une erreur au lieu d'un numéro correct.)

### Le mineur et la prudence (D13)

Le cahier des charges collecte la date de naissance « si la catégorie dépend de l'âge » (minimisation). Mais la règle absolue n°6 interdit un tirage pour un mineur sans consentement. Quand la date est inconnue, on **ne sait pas** : on choisit le côté sûr et on exige le consentement, jusqu'à ce que l'opérateur renseigne la date de naissance. Si le produit préfère l'autre arbitrage, il suffit de changer la fonction `consentement_requis`.

### Trois consentements distincts

Seul le consentement n° 1 (**participation et traitement des données**) autorise le tirage. Les deux autres (publication du nom, image ou voix) conditionnent l'affichage public, pas la participation. Le test `test_rm28_un_mineur_dont_le_consentement_de_participation_n_est_pas_accorde_ne_tire_pas` le vérifie : accorder les consentements 2 et 3 sans le 1 ne suffit pas.

## Questions de compréhension

1. Pourquoi mettre RM-27 et RM-31 dans une **contrainte de base** en plus des services ?
2. Que se passe-t-il si l'opérateur modifie un critère de notation après la validation par le responsable client ?
3. Pourquoi un numéro de candidat n'est-il jamais réutilisé après un retrait ?
4. Pourquoi le consentement n° 1 est-il le seul à conditionner le tirage ?

<details>
<summary>Réponses</summary>

1. Un service n'est appliqué que si le code l'appelle. Une contrainte s'applique à **tous** les chemins d'écriture (administration, script, import, erreur d'un futur développeur). Les deux se complètent : le service donne un message clair, la contrainte est le filet de sécurité.
2. L'empreinte recalculée à l'ouverture diffère de celle enregistrée : `ouvrir_concours` refuse avec « La configuration a changé depuis sa validation » et le responsable client doit valider de nouveau.
3. Des documents déjà imprimés ou communiqués (fiches de notation, ordre de passage) portent ce numéro ; le réattribuer à un autre candidat créerait des confusions sur les notes.
4. Le consentement n° 1 porte sur la participation et le traitement des données : sans lui, on n'a pas le droit de traiter les données du mineur, donc de le faire concourir. Les consentements 2 et 3 portent sur des usages facultatifs (nom dans les classements, image ou voix).
</details>

## Le document de conception, à jour

À ce stade, `docs\conception\modele-de-donnees.md` contient aussi les décisions D13 à D20 :

**Fichier `docs\conception\modele-de-donnees.md`**

```markdown
# Modèle de données V1 — décisions de conception (phase 1)

Ce document fige le modèle de données de la V1. Il complète le §14 du cahier des charges
(`docs/cdc/14-modele-de-donnees-previsionnel.md`) et en précise les choix. Il est la référence
de l'étape 1.2 (« Modèles, application par application »).

## 1. Décisions confirmées

| N° | Décision | Conséquence |
|---|---|---|
| D1 | **Utilisateur Django personnalisé** dès maintenant (`AUTH_USER_MODEL = "utilisateurs.Utilisateur"`) | à faire avant toute table qui référence l'utilisateur ; la base de développement est recréée |
| D2 | **UUID comme clé primaire** de toutes les tables client | identifiants non devinables dans les URL (§13.4) |
| D3 | **`organisation` recopiée sur toutes les tables client**, avec test de cohérence parent-enfant | règle absolue n°3 ; classe abstraite `ModeleDuClient` |
| D4 | Jurés **hors comptes Django** : code de session haché, pas d'e-mail | §7.4 |
| D5 | Affectation d'un juré **toujours au niveau épreuve** | l'interface sait « affecter à tout le concours » en créant les lignes |
| D6 | Diapositives **stockées** à la préparation de l'affichage | l'état de présentation n'est qu'un pointeur ; reprise simple (§13.5) |
| D7 | Journal d'audit **simple** en V1, colonne d'empreinte chaînée prévue mais vide | autorisé par le §24 |
| D8 | Barème : **critères seulement** en V1 | pénalités et bonus si un règlement les exige |
| D9 | Départage : **règle de classement sur la catégorie** ; décision manuelle documentée plus tard | §10.4 |
| D10 | Une mission regroupe un ou plusieurs concours ; un concours appartient à une mission | |
| D11 | `Traduction` / `TraductionVerset` à l'itération 3 (diaporama) | |
| D12 | `Incident` rattaché au concours, et à la prestation si elle existe | |

## 2. Principes communs

- Toute table propre à un client : `organisation` non nulle, indexée, `on_delete=PROTECT`, filtrée par `.pour_organisation(...)`.
- Si une table a un parent client (par exemple une affectation et sa mission), l'`organisation` de l'enfant **doit** être celle du parent : elle est recopiée automatiquement et refusée si elle diffère.
- `cree_le` et `modifie_le` sur toutes les tables.
- Aucune suppression en cascade d'une donnée de concours : on archive.
- Ce qui se déduit d'une autre table n'est pas stocké : Q = T × P, disponibilité d'une série (déduite des tirages), classement provisoire (calculé), candidat mineur (déduit de la date de naissance).

## 3. Catalogue des modèles par application

| Application | Modèles | Itération du planning |
|---|---|---|
| `commun` | `ModeleHorodate`, `ModeleDuClient` (classes abstraites, gestionnaire filtré) | 1 |
| `clients` | `Organisation`, `Mission` | 1 |
| `utilisateurs` | `Utilisateur`, `AffectationOperateur`, `CodeAccesJure` | 1 |
| `concours` | `Concours`, `Categorie`, `Epreuve`, `CritereNotation`, `Session` | 1 |
| `candidats` | `Candidat`, `Participation`, `Consentement` | 1 |
| `jury` | `Jure`, `AffectationJury` (itération 1) ; `Evaluation`, `NoteCritere`, `CorrectionEvaluation` (itération 4) | 1 et 4 |
| `questions` | `PassageCoranique`, `Question`, `Lot`, `Serie`, `SerieQuestion` | 2 |
| `prestations` | `Prestation`, `Tirage`, `Incident` | 2 |
| `presentation` | `Diapositive`, `EtatPresentation`, `EvenementPresentation` | 3 |
| `resultats` | `Classement`, `LigneClassement`, `DocumentResultat` | 4 |
| `audit` | `JournalAudit` | 4 |
| `coran` | `VersionCorpus`, `Sourate`, `Verset` (fait) ; `Traduction`, `TraductionVerset` | 0 et 3 |

## 4. Ce que garantit la base de données et ce que garantit le code

| Règle | Où |
|---|---|
| Un seul tirage valide par `(prestation, rang)` ; une série n'est jamais tirée deux fois par un même candidat dans une épreuve ; identifiant de demande unique | base de données |
| Numéro de participation unique par concours ; une évaluation par juré et par prestation | base de données |
| Dates cohérentes (fin ≥ début), couleurs au format `#RRGGBB`, rôle et organisation cohérents | base de données |
| Réutilisation des séries (RM-21) | service, dans une transaction avec verrou sur le lot (règle absolue n°2) |
| Série de P questions exactement, suffisance du lot (RM-22, RM-24) | service, à l'ouverture de l'épreuve |
| Une note ne dépasse pas le maximum du critère | service (la règle croise deux tables) |
| Organisation de l'enfant = organisation du parent | modèle (`save()`), avec tests |

## 5. Points délicats à garder en tête

1. Une trentaine de modèles : l'ordre d'implémentation suit les itérations du planning.
2. `organisation` répétée : sûre, mais exige le test de cohérence parent-enfant.
3. RM-21 est la règle la plus délicate du projet (trois réglages combinables) : elle est écrite par l'utilisateur.
4. Les paramètres structurants sont verrouillés quand le concours est en cours (§7.2) : un mécanisme de modification exceptionnelle, motivée et tracée, reste à concevoir à l'itération 1.

## 6. Décisions complémentaires (étape 1.2, deuxième lot : concours et candidats)

| N° | Décision | Pourquoi |
|---|---|---|
| D13 | **Date de naissance inconnue : le consentement parental est exigé par prudence.** `est_mineur` renvoie « inconnu » (`None`), et `consentement_requis` le traite comme un mineur. | règle absolue n°6 : mieux vaut demander la date de naissance (ou le consentement) que laisser passer un mineur. Réversible en changeant une seule fonction. |
| D14 | **La validation de la configuration porte sur une configuration précise** : une empreinte SHA-256 des catégories, épreuves, barème et réglages de tirage est enregistrée à la validation, et comparée à l'ouverture. | RM-31 : si la configuration change après validation, le responsable client doit la valider de nouveau. |
| D15 | `affichage_scene` est **désactivé par défaut** sur une épreuve. | §9.1 : en mémorisation, l'écran scène ne doit pas être visible du candidat ; l'opérateur l'active volontairement. |
| D16 | **Un concours non brouillon exige, en base de données**, une version du corpus et une configuration validée. | RM-27 et RM-31 appliquées par une contrainte, pas seulement par du code. |
| D17 | **Numéro de candidat** : plus élevé du concours plus un, retraits compris, sous verrou sur le concours. Un numéro n'est jamais réutilisé. | évite deux inscriptions simultanées avec le même numéro, et toute ambiguïté sur les documents déjà imprimés. |
| D18 | **Consentement retiré = formulaire conservé et marqué « retiré »** ; un retrait partiel se fait en retirant le formulaire puis en en enregistrant un nouveau. Un seul formulaire valide par participation. | §16.2 : le retrait prend effet pour l'avenir et l'historique reste. |
| D19 | `Format` du concours : seul « présentiel » en V1. | en ligne et hybride sont en V2 (§5.2). |
| D20 | Le stockage **chiffré** des formulaires de consentement et des logos est repoussé à la sécurité du serveur de salle (§15). Le champ fichier existe déjà. | |

### Ce qui reste hors de ce lot

- `Jure` et `AffectationJury`, `CodeAccesJure` : lot suivant de l'itération 1 (avec l'import CSV des candidats).
- Le verrouillage des paramètres structurants quand le concours est « en cours » (§7.2), avec modification exceptionnelle motivée et tracée : à concevoir avec le journal d'audit.
- Les lots, séries et questions (itération 2), les tirages (itération 2), etc.
```

## Journal d'apprentissage

Notez : ce qu'est une empreinte de configuration et pourquoi on la compare à l'ouverture ; la différence entre une règle dans un service et une règle dans une contrainte ; pourquoi on protège un mineur par défaut quand son âge est inconnu.

## Et ensuite ?

Le prochain lot de l'étape 1.2 ajoute les **jurés** (`Jure`, `AffectationJury`, `CodeAccesJure`) et l'**import CSV des candidats** (avec contrôle des doublons et rapport d'erreurs, §7.3), ce qui termine l'itération 1 du planning (clients, concours, candidats, jurés).
