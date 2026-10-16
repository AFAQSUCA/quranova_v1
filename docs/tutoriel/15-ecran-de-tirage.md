# Chapitre 15 — L'écran de tirage (Vue 3, Pinia, API à jeton)

> **Étape du plan :** 3.4 · **Durée :** 6 à 8 heures · **Commit de référence :** `1a0fc2f` · **Résultat :** la tablette de tirage fonctionne de bout en bout : l'opérateur appelle un candidat, le candidat appuie, la série s'affiche. **23 tests Python** (terminaux et API) et **23 tests du front**.

## Objectif

Construire le premier vrai écran temps réel du projet :

```text
Opérateur (administration)  ──appelle un candidat──►  Terminal de tirage (base de données)
                                                               ▲
Tablette (Vue 3) ──GET /api/tirage/etat/ toutes les 2 s───────┘   « qui est appelé ? »
Tablette (Vue 3) ──POST /api/tirage/ {id_demande}──► effectuer_tirage (chapitre 13) ──► « Série 4 »
```

| Règle | Où elle est appliquée |
|---|---|
| **§8.5, §15.1** : le candidat appelé est **fixé par l'opérateur** | `TerminalTirage.prestation_appelee`, `appeler_prestation` |
| **REC-25** : aucun identifiant de prestation envoyé par le client | l'API ne lit que `id_demande` ; la prestation vient du terminal authentifié |
| **REC-07** : double clic | le store ignore un 2ᵉ clic pendant l'envoi ; `id_demande` est gardé après une coupure réseau ; le serveur est idempotent |
| **RM-14** : pas de texte de verset sur l'écran du candidat | l'API ne renvoie que « Série N » ; des tests le vérifient des deux côtés |
| **§8.1** : animation purement décorative | lancée **après** la réponse du serveur, qui a déjà enregistré le tirage |
| **§16** : données personnelles | la tablette affiche le numéro et le **prénom** seulement (D34) |

## Décisions

| N° | Décision |
|---|---|
| D31 | Jeton par terminal : 256 bits, `secrets`, seule l'empreinte HMAC est stockée, révocable, transmis dans le **fragment** de l'adresse (`/tirage/#jeton`), jamais envoyé au serveur. En-tête `Authorization: Bearer`, donc sans cookie ni CSRF. |
| D32 | La tablette interroge l'état toutes les 2 secondes (WebSocket à l'itération 3). |
| D33 | Pas de références de questions sur l'écran de tirage. |
| D34 | Numéro et prénom affichés, jamais le nom de famille ni un verset. |
| D35 | Dépendances du front : `vue`, `pinia` ; `vite`, `@vitejs/plugin-vue`, `typescript` (**fixé en 5.9**, car `vue-tsc` n'est pas encore compatible avec la version 7), `vue-tsc`, `vitest`, `@vue/test-utils`, `jsdom`. |

## Partie 1 — Le côté serveur

### Étape A — Le jeton

**Fichier `apps\commun\jetons.py`**

```python
"""Jetons secrets des terminaux (tirage, commande, scène) : générés avec ``secrets``, jamais stockés.

Seule l'empreinte HMAC-SHA256 (clé : ``SECRET_KEY``) est enregistrée. Le jeton est long (256 bits) :
contrairement au code court d'un juré, il ne peut pas être deviné par essais successifs.
"""
import hashlib
import hmac
import secrets

from django.conf import settings


def fabriquer_jeton():
    return secrets.token_urlsafe(32)


def empreinte_du_jeton(jeton, contexte):
    """Empreinte du jeton pour un usage donné (``contexte`` évite de réutiliser un jeton ailleurs)."""
    message = f"{contexte}:{jeton}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()
```

### Étape B — Les modèles et les exceptions

Ajoutez à `apps\prestations\exceptions.py` les trois exceptions finales (fichier complet) :

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


class TerminalInvalideError(Exception):
    """Jeton inconnu, révoqué ou absent : le terminal n'est pas authentifié (§15)."""


class AppelInvalideError(Exception):
    """L'opérateur ne peut pas appeler cette prestation sur ce terminal (§8.5, REC-14)."""


class PasDAppelError(TirageImpossibleError):
    """Aucun candidat n'est appelé sur ce terminal : l'opérateur doit d'abord l'appeler."""
```

Ajoutez à la fin de `apps\prestations\models.py` :

**À la fin de `apps\prestations\models.py`**, ajoutez la classe `TerminalTirage` :

```python

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
```

```powershell
python manage.py makemigrations prestations
python manage.py migrate
```

### Étape C — Les tests d'abord

Ajoutez la fonction `creer_terminal_de_test` à la fin de `apps\prestations\tests\outils.py` (fichier complet) :

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


def creer_terminal_de_test(epreuve, nom="Tablette 1"):
    """Un terminal de tirage pour la session du concours de l'épreuve ; renvoie (terminal, jeton, session)."""
    from apps.prestations import terminaux

    session = creer_session(epreuve.categorie.concours)
    terminal, jeton = terminaux.creer_terminal(session, nom)
    return terminal, jeton, session
```

**Fichier `apps\prestations\tests\test_terminaux.py`**

```python
"""Tests des terminaux de tirage : jeton, appel d'un candidat par l'opérateur, état affiché (§8.6, §15 ; D31, D34)."""
import json
import uuid

import pytest
from django.utils import timezone

from apps.commun.tests.outils import creer_mission, creer_session, creer_utilisateur
from apps.prestations import terminaux
from apps.prestations.exceptions import AppelInvalideError, PasDAppelError, TerminalInvalideError
from apps.prestations.models import Prestation, TerminalTirage, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.fixture
def terminal(epreuve):
    session = creer_session(epreuve.categorie.concours)
    objet, jeton = terminaux.creer_terminal(session, "Tablette 1")
    objet.jeton_de_test = jeton
    return objet


def operateur_de(epreuve):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return operateur


def prestation_pour(epreuve, terminal, **champs):
    return creer_prestation(epreuve, session=terminal.session, **champs)


# --- Jeton (D31) ---------------------------------------------------------------


@pytest.mark.django_db
def test_d31_le_jeton_n_est_jamais_stocke_en_clair(epreuve):
    terminal, jeton = terminaux.creer_terminal(creer_session(epreuve.categorie.concours), "T")

    assert len(jeton) >= 40
    assert jeton not in terminal.empreinte and len(terminal.empreinte) == 64
    assert TerminalTirage.objects.filter(empreinte=jeton).count() == 0
    assert terminal.organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_deux_terminaux_ont_des_jetons_differents(epreuve):
    session = creer_session(epreuve.categorie.concours)

    (_, premier), (_, second) = terminaux.creer_terminal(session, "A"), terminaux.creer_terminal(session, "B")

    assert premier != second


@pytest.mark.django_db
def test_un_jeton_valide_identifie_le_terminal_et_note_l_activite(terminal):
    trouve = terminaux.authentifier_terminal(terminal.jeton_de_test)

    assert trouve == terminal
    terminal.refresh_from_db()
    assert terminal.derniere_activite is not None


@pytest.mark.django_db
@pytest.mark.parametrize("jeton", ["", None, "n-importe-quoi", "a" * 43])
def test_un_jeton_inconnu_ou_absent_est_refuse(terminal, jeton):
    with pytest.raises(TerminalInvalideError):
        terminaux.authentifier_terminal(jeton)


@pytest.mark.django_db
def test_un_terminal_revoque_est_refuse(terminal):
    terminaux.revoquer_terminal(terminal)

    with pytest.raises(TerminalInvalideError):
        terminaux.authentifier_terminal(terminal.jeton_de_test)


# --- Appel d'un candidat par l'opérateur ----------------------------------------


@pytest.mark.django_db
def test_l_operateur_appelle_un_candidat_sur_le_terminal(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)

    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))

    terminal.refresh_from_db()
    assert terminal.prestation_appelee == prestation


@pytest.mark.django_db
def test_appeler_un_autre_candidat_remplace_le_precedent(epreuve, terminal):
    operateur = operateur_de(epreuve)
    premiere, seconde = prestation_pour(epreuve, terminal), prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, premiere, operateur)

    terminaux.appeler_prestation(terminal, seconde, operateur)

    terminal.refresh_from_db()
    assert terminal.prestation_appelee == seconde


@pytest.mark.django_db
def test_rm20_un_operateur_sans_acces_a_la_mission_ne_peut_pas_appeler(epreuve, terminal):
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=creer_mission(), utilisateur=etranger)

    with pytest.raises(AppelInvalideError, match="accès"):
        terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), etranger)

    terminal.refresh_from_db()
    assert terminal.prestation_appelee is None


@pytest.mark.django_db
def test_un_responsable_client_n_appelle_pas_un_candidat(epreuve, terminal):
    responsable = creer_utilisateur(
        Utilisateur.Role.RESPONSABLE_CLIENT, organisation=epreuve.organisation
    )

    with pytest.raises(AppelInvalideError, match="prestataire"):
        terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), responsable)


@pytest.mark.django_db
def test_une_prestation_d_une_autre_session_ne_peut_pas_etre_appelee(epreuve, terminal):
    autre = creer_prestation(epreuve, session=creer_session(epreuve.categorie.concours))

    with pytest.raises(AppelInvalideError, match="session"):
        terminaux.appeler_prestation(terminal, autre, operateur_de(epreuve))


@pytest.mark.django_db
def test_seule_une_prestation_en_attente_peut_etre_appelee(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal, etat=Prestation.Etat.EN_NOTATION)

    with pytest.raises(AppelInvalideError, match="attente"):
        terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))


@pytest.mark.django_db
def test_un_terminal_revoque_ne_peut_plus_appeler(epreuve, terminal):
    terminaux.revoquer_terminal(terminal)

    with pytest.raises(AppelInvalideError, match="révoqué"):
        terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), operateur_de(epreuve))


@pytest.mark.django_db
def test_liberer_le_terminal(epreuve, terminal):
    operateur = operateur_de(epreuve)
    terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), operateur)

    terminaux.liberer_terminal(terminal)

    terminal.refresh_from_db()
    assert terminal.prestation_appelee is None


# --- Ce que voit la tablette ------------------------------------------------------


@pytest.mark.django_db
def test_l_etat_sans_appel(terminal):
    assert terminaux.etat_du_terminal(terminal) == {"terminal": "Tablette 1", "appel": None}


@pytest.mark.django_db
def test_d34_l_etat_montre_le_numero_et_le_prenom_mais_ni_le_nom_ni_aucun_verset(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))

    etat = terminaux.etat_du_terminal(terminal)

    assert etat["appel"]["numero_candidat"] == prestation.participation.numero_candidat
    assert etat["appel"]["prenom"] == prestation.participation.candidat.prenom
    assert etat["appel"]["epreuve"] == epreuve.nom
    assert etat["appel"]["tirages_prevus"] == 1 and etat["appel"]["tirages"] == []
    texte = json.dumps(etat, ensure_ascii=False)
    assert prestation.participation.candidat.nom not in texte  # RGPD : écran visible de la salle
    assert not ({"texte", "versets", "questions", "enonce"} & set(texte.replace('"', " ").split()))


@pytest.mark.django_db
def test_l_etat_apres_tirage_donne_le_libelle_de_la_serie(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))
    terminaux.tirer_pour_terminal(terminal, uuid.uuid4())

    appel = terminaux.etat_du_terminal(terminal)["appel"]

    assert appel["etat"] == "tire" and appel["peut_tirer"] is False
    assert appel["tirages"][0]["serie"].startswith("Série ")


@pytest.mark.django_db
def test_peut_tirer_tant_qu_il_reste_un_tirage(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))

    assert terminaux.etat_du_terminal(terminal)["appel"]["peut_tirer"] is True


# --- Tirage depuis le terminal ------------------------------------------------------


@pytest.mark.django_db
def test_sans_appel_le_terminal_ne_peut_pas_tirer(terminal):
    with pytest.raises(PasDAppelError):
        terminaux.tirer_pour_terminal(terminal, uuid.uuid4())

    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_le_tirage_concerne_seulement_le_candidat_appele_et_note_le_terminal(epreuve, terminal):
    appele = prestation_pour(epreuve, terminal)
    autre = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, appele, operateur_de(epreuve))

    tirage = terminaux.tirer_pour_terminal(terminal, uuid.uuid4())

    assert tirage.prestation == appele and tirage.terminal == "Tablette 1"
    assert autre.tirages.count() == 0


@pytest.mark.django_db
def test_rec07_la_meme_demande_renvoie_le_meme_tirage(epreuve, terminal):
    terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), operateur_de(epreuve))
    demande = uuid.uuid4()

    premier = terminaux.tirer_pour_terminal(terminal, demande)
    second = terminaux.tirer_pour_terminal(terminal, demande)

    assert premier == second and Tirage.objects.count() == 1
```

**Fichier `apps\prestations\tests\test_api_tirage.py`**

```python
"""Tests de l'API de l'écran de tirage (§8.5 ; REC-06, REC-07, REC-14, REC-25 ; D31, D34)."""
import json
import uuid
from datetime import date

import pytest
from django.urls import reverse

from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_participation, creer_utilisateur
from apps.prestations import terminaux
from apps.prestations.models import Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_terminal_de_test
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

URL_ETAT, URL_TIRER = reverse("prestations:api_etat"), reverse("prestations:api_tirer")


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.fixture
def poste(epreuve):
    """(épreuve, terminal, en-têtes d'authentification, opérateur)."""
    terminal, jeton, _ = creer_terminal_de_test(epreuve)
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return epreuve, terminal, {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}, operateur


def appeler(epreuve, terminal, operateur, **champs):
    prestation = creer_prestation(epreuve, session=terminal.session, **champs)
    terminaux.appeler_prestation(terminal, prestation, operateur)
    return prestation


def tirer(client, en_tetes, corps=None):
    corps = {"id_demande": str(uuid.uuid4())} if corps is None else corps
    return client.post(URL_TIRER, data=json.dumps(corps), content_type="application/json", **en_tetes)


# --- Authentification (D31) ----------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("en_tete", [{}, {"HTTP_AUTHORIZATION": "Bearer faux"}, {"HTTP_AUTHORIZATION": "Basic abc"},
                                      {"HTTP_AUTHORIZATION": "Bearer "}])
def test_sans_jeton_valide_les_deux_routes_repondent_401(client, en_tete):
    assert client.get(URL_ETAT, **en_tete).status_code == 401
    reponse = client.post(URL_TIRER, data="{}", content_type="application/json", **en_tete)
    assert reponse.status_code == 401 and reponse.json()["code"] == "terminal_inconnu"


@pytest.mark.django_db
def test_un_terminal_revoque_est_refuse(client, poste):
    _, terminal, en_tetes, _ = poste
    terminaux.revoquer_terminal(terminal)

    assert client.get(URL_ETAT, **en_tetes).status_code == 401


@pytest.mark.django_db
def test_un_compte_connecte_sans_jeton_n_a_aucun_acces(client, poste):
    """Un cookie de session (opérateur, responsable...) ne remplace pas le jeton du terminal."""
    client.force_login(creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True))

    assert client.get(URL_ETAT).status_code == 401


@pytest.mark.django_db
def test_les_methodes_non_prevues_sont_refusees(client, poste):
    _, _, en_tetes, _ = poste

    assert client.post(URL_ETAT, **en_tetes).status_code == 405
    assert client.get(URL_TIRER, **en_tetes).status_code == 405


# --- État ----------------------------------------------------------------------


@pytest.mark.django_db
def test_l_etat_sans_appel(client, poste):
    _, _, en_tetes, _ = poste

    reponse = client.get(URL_ETAT, **en_tetes)

    assert reponse.status_code == 200 and reponse.json() == {"terminal": "Tablette 1", "appel": None}
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.django_db
def test_l_etat_apres_l_appel_de_l_operateur(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    prestation = appeler(epreuve, terminal, operateur)

    appel = client.get(URL_ETAT, **en_tetes).json()["appel"]

    assert appel["prenom"] == prestation.participation.candidat.prenom
    assert appel["peut_tirer"] is True and "nom" not in appel


# --- Tirage ----------------------------------------------------------------------


@pytest.mark.django_db
def test_rec06_un_tirage_renvoie_le_libelle_de_la_serie(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)

    reponse = tirer(client, en_tetes)

    corps = reponse.json()
    assert reponse.status_code == 200
    assert corps["tirage"]["serie"].startswith("Série ") and corps["tirage"]["rang"] == 1
    assert corps["etat"]["appel"]["peut_tirer"] is False
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_rec07_deux_envois_de_la_meme_demande_ne_creent_qu_un_tirage(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)
    demande = {"id_demande": str(uuid.uuid4())}

    premier, second = tirer(client, en_tetes, demande), tirer(client, en_tetes, demande)

    assert premier.status_code == second.status_code == 200
    assert premier.json()["tirage"] == second.json()["tirage"]
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_rec25_le_client_ne_peut_pas_designer_une_autre_prestation(client, poste):
    """Même si le corps contient un identifiant de prestation, seul le candidat appelé tire."""
    epreuve, terminal, en_tetes, operateur = poste
    appelee = appeler(epreuve, terminal, operateur)
    autre = creer_prestation(epreuve, session=terminal.session)

    tirer(client, en_tetes, {"id_demande": str(uuid.uuid4()), "prestation": str(autre.pk), "prestation_id": str(autre.pk)})

    assert appelee.tirages.count() == 1 and autre.tirages.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("corps", [{}, {"id_demande": "pas-un-uuid"}, {"id_demande": 12}, {"id_demande": None}, []])
def test_requete_invalide_400(client, poste, corps):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)

    reponse = tirer(client, en_tetes, corps)

    assert reponse.status_code == 400 and reponse.json()["code"] == "requete_invalide"
    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_corps_qui_n_est_pas_du_json(client, poste):
    _, _, en_tetes, _ = poste

    reponse = client.post(URL_TIRER, data="pas du json", content_type="application/json", **en_tetes)

    assert reponse.status_code == 400


@pytest.mark.django_db
def test_sans_candidat_appele_409_pas_d_appel(client, poste):
    _, _, en_tetes, _ = poste

    reponse = tirer(client, en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "pas_d_appel"


@pytest.mark.django_db
def test_lot_epuise_409(client):
    epreuve = creer_epreuve_ouverte(series=1)
    terminal, jeton, _ = creer_terminal_de_test(epreuve)
    en_tetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}
    operateur = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR)
    appeler(epreuve, terminal, operateur)
    from apps.prestations.services import effectuer_tirage

    effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())  # un autre candidat prend l'unique série

    reponse = tirer(client, en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "lot_epuise"


@pytest.mark.django_db
def test_rm28_mineur_sans_consentement_409(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    mineur = creer_candidat(epreuve.organisation, date_naissance=date(2015, 5, 1))
    participation = creer_participation(epreuve.categorie, mineur, statut=Participation.Statut.ADMIS)
    appeler(epreuve, terminal, operateur, participation=participation)

    reponse = tirer(client, en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "consentement_manquant"
    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_la_reponse_ne_contient_aucun_texte_de_verset_ni_de_question(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)

    texte = tirer(client, en_tetes).content.decode()

    assert "Question de test" not in texte and "enonce" not in texte and "texte" not in texte


# --- Page ----------------------------------------------------------------------


@pytest.mark.django_db
def test_la_page_de_tirage_se_charge_sans_authentification(client):
    """La page est publique et vide ; toutes les données passent par l'API, protégée par le jeton."""
    reponse = client.get(reverse("prestations:ecran_tirage"))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200 and 'id="app"' in contenu and "tirage.js" in contenu
```

### Étape D — Le code

**Fichier `apps\prestations\terminaux.py`**

```python
"""Terminaux de tirage : authentification par jeton, appel d'un candidat, état affiché (§8.5, §8.6, §15).

L'opérateur FIXE le candidat appelé ; la tablette ne reçoit ni ne choisit aucune identité. Ce que la
tablette affiche (D34) : le numéro et le prénom du candidat, jamais son nom de famille (l'écran est
vu de la salle, parfois pour des mineurs, §16), et jamais le texte d'un verset (RM-14).
"""
from django.db import transaction
from django.utils import timezone

from apps.commun.jetons import empreinte_du_jeton, fabriquer_jeton
from apps.prestations import services
from apps.prestations.exceptions import AppelInvalideError, PasDAppelError, TerminalInvalideError
from apps.prestations.models import Prestation, TerminalTirage, Tirage
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

CONTEXTE_JETON = "terminal-tirage"


def creer_terminal(session, nom):
    """Crée un terminal ; renvoie ``(terminal, jeton)``. Le jeton n'est montré qu'à cet instant (D31)."""
    jeton = fabriquer_jeton()
    terminal = TerminalTirage.objects.create(
        session=session, nom=nom, empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON)
    )
    return terminal, jeton


def revoquer_terminal(terminal):
    terminal.revoque_le = timezone.now()
    terminal.prestation_appelee = None
    terminal.save(update_fields=["revoque_le", "prestation_appelee", "modifie_le"])


def authentifier_terminal(jeton):
    """Le terminal correspondant au jeton, ou ``TerminalInvalideError`` (message volontairement vague)."""
    if not jeton:
        raise TerminalInvalideError("Terminal non reconnu.")
    terminal = TerminalTirage.objects.filter(
        empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), revoque_le__isnull=True
    ).first()
    if terminal is None:
        raise TerminalInvalideError("Terminal non reconnu.")
    TerminalTirage.objects.filter(pk=terminal.pk).update(derniere_activite=timezone.now())
    terminal.refresh_from_db()
    return terminal


def appeler_prestation(terminal, prestation, operateur):
    """L'opérateur appelle un candidat sur le terminal (§8.5). Remplace l'appel précédent."""
    if operateur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        raise AppelInvalideError("Seul le personnel du prestataire peut appeler un candidat.")
    mission = prestation.epreuve.categorie.concours.mission
    if not missions_accessibles(operateur).filter(pk=mission.pk).exists():
        raise AppelInvalideError("Vous n'avez pas accès à la mission de cette prestation (RM-20).")
    with transaction.atomic():
        terminal = TerminalTirage.objects.select_for_update().get(pk=terminal.pk)
        if terminal.revoque_le is not None:
            raise AppelInvalideError("Ce terminal est révoqué.")
        if prestation.session_id != terminal.session_id:
            raise AppelInvalideError("Cette prestation n'appartient pas à la session du terminal.")
        if prestation.etat != Prestation.Etat.EN_ATTENTE:
            raise AppelInvalideError("Seule une prestation en attente peut être appelée au tirage.")
        terminal.prestation_appelee = prestation
        terminal.save(update_fields=["prestation_appelee", "modifie_le"])
    return terminal


def liberer_terminal(terminal):
    terminal.prestation_appelee = None
    terminal.save(update_fields=["prestation_appelee", "modifie_le"])


def etat_du_terminal(terminal):
    """Ce que la tablette a le droit de savoir (D34) : jamais de nom de famille, jamais de verset."""
    terminal.refresh_from_db()
    prestation = terminal.prestation_appelee
    if prestation is None:
        return {"terminal": terminal.nom, "appel": None}
    prestation = Prestation.objects.select_related("participation__candidat", "epreuve").get(pk=prestation.pk)
    tirages = list(prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang"))
    prevus = prestation.epreuve.tirages_par_candidat
    return {
        "terminal": terminal.nom,
        "appel": {
            "numero_candidat": prestation.participation.numero_candidat,
            "prenom": prestation.participation.candidat.prenom,
            "epreuve": prestation.epreuve.nom,
            "etat": prestation.etat,
            "tirages_prevus": prevus,
            "tirages": [{"rang": t.rang, "serie": t.serie.libelle} for t in tirages],
            "peut_tirer": prestation.etat == Prestation.Etat.EN_ATTENTE and len(tirages) < prevus,
        },
    }


def tirer_pour_terminal(terminal, id_demande):
    """Déclenche le tirage du candidat appelé. Le client n'indique JAMAIS la prestation (REC-25)."""
    terminal.refresh_from_db()
    if terminal.revoque_le is not None or terminal.prestation_appelee_id is None:
        raise PasDAppelError("Aucun candidat n'est appelé sur ce terminal : demandez à l'opérateur de vous appeler.")
    return services.effectuer_tirage(terminal.prestation_appelee, id_demande, terminal=terminal.nom)
```

**Fichier `apps\prestations\api.py`**

```python
"""API JSON de l'écran de tirage (§8.5, §8.6, §15.4).

Authentification : en-tête ``Authorization: Bearer <jeton>`` (D31). Aucun cookie n'est utilisé, donc
aucun CSRF n'est possible (les vues sont exemptées pour cette raison précise). Le client n'envoie
qu'un ``id_demande`` : la prestation est celle que l'opérateur a appelée sur ce terminal, jamais une
valeur fournie par le client (REC-25).
"""
import json
import uuid
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.candidats.exceptions import ConsentementManquantError, ParticipationNonAdmiseError, TirageImpossibleError
from apps.prestations import terminaux
from apps.prestations.exceptions import LotEpuiseError, PasDAppelError, TerminalInvalideError


def _reponse(donnees, statut=200):
    reponse = JsonResponse(donnees, status=statut, json_dumps_params={"ensure_ascii": False})
    reponse["Cache-Control"] = "no-store"
    return reponse


def _erreur(statut, code, message):
    return _reponse({"code": code, "message": message}, statut)


def avec_terminal(vue):
    """Authentifie le terminal par son jeton ; sinon 401 sans rien divulguer."""

    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        en_tete = request.headers.get("Authorization", "")
        jeton = en_tete[7:].strip() if en_tete.startswith("Bearer ") else ""
        try:
            terminal = terminaux.authentifier_terminal(jeton)
        except TerminalInvalideError:
            return _erreur(401, "terminal_inconnu", "Terminal non reconnu.")
        return vue(request, terminal, *args, **kwargs)

    return enveloppe


@csrf_exempt  # pas de cookie : l'authentification est l'en-tête Authorization
@require_GET
@avec_terminal
def etat(request, terminal):
    return _reponse(terminaux.etat_du_terminal(terminal))


CODES_REFUS = (
    (PasDAppelError, "pas_d_appel"),
    (LotEpuiseError, "lot_epuise"),
    (ConsentementManquantError, "consentement_manquant"),
    (ParticipationNonAdmiseError, "non_admis"),
    (TirageImpossibleError, "refuse"),
)


@csrf_exempt
@require_POST
@avec_terminal
def tirer(request, terminal):
    try:
        id_demande = uuid.UUID(str(json.loads(request.body or b"{}")["id_demande"]))
    except (ValueError, KeyError, TypeError, AttributeError):
        return _erreur(400, "requete_invalide", "Requête invalide : un identifiant de demande est attendu.")
    try:
        tirage = terminaux.tirer_pour_terminal(terminal, id_demande)
    except TirageImpossibleError as refus:
        code = next(code for classe, code in CODES_REFUS if isinstance(refus, classe))
        return _erreur(409, code, str(refus))
    return _reponse(
        {"tirage": {"rang": tirage.rang, "serie": tirage.serie.libelle}, "etat": terminaux.etat_du_terminal(terminal)}
    )
```

**Fichier `apps\prestations\urls.py`**

```python
from django.urls import path
from django.views.generic import TemplateView

from apps.prestations import api

app_name = "prestations"

urlpatterns = [
    path("tirage/", TemplateView.as_view(template_name="tirage.html"), name="ecran_tirage"),
    path("api/tirage/etat/", api.etat, name="api_etat"),
    path("api/tirage/", api.tirer, name="api_tirer"),
]
```

**Fichier `config\urls.py`**

```python
"""Routes racine du projet QURANOVA."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="accueil.html"), name="accueil"),
    path("admin/", admin.site.urls),
    path("", include("apps.prestations.urls")),
]
```

**Fichier `templates\tirage.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
  <meta name="robots" content="noindex">
  <title>QURANOVA — Tirage</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="{% static 'frontend/tirage.css' %}">
</head>
<body>
  <div id="app"></div>
  <noscript>Cet écran nécessite JavaScript.</noscript>
  <script type="module" src="{% static 'frontend/tirage.js' %}"></script>
</body>
</html>
```

### Étape E — L'administration du terminal

Ajoutez l'action « Appeler au tirage » à `PrestationAdmin` et l'administration du terminal (fichier complet), puis les exceptions `AppelInvalideError` et `TerminalInvalideError` à `ERREURS_METIER` dans `apps\commun\admin.py` :

**Fichier `apps\prestations\admin.py`**

```python
"""Administration des prestations et des tirages (§8.3, §14.2)."""
from django.contrib import admin, messages
from django.urls import reverse

from apps.commun.admin import AdminDuClient, ConsultationSeule, appliquer_action
from apps.prestations import terminaux
from apps.prestations.exceptions import AppelInvalideError
from apps.prestations.models import Prestation, TerminalTirage, Tirage


@admin.register(Prestation)
class PrestationAdmin(AdminDuClient):
    list_display = ("rang_passage", "participation", "epreuve", "session", "etat")
    list_filter = ("etat", "epreuve", "session")
    readonly_fields = ("etat",)  # l'état ne change que par les services (tirage, diaporama, notation)
    actions = ["appeler_au_tirage"]

    @admin.action(description="Appeler au tirage (terminal de la session)")
    def appeler_au_tirage(self, request, queryset):
        def appeler(prestation):
            actifs = list(prestation.session.terminaux_tirage.filter(revoque_le__isnull=True))
            if len(actifs) != 1:
                raise AppelInvalideError(
                    f"{len(actifs)} terminal(aux) actif(s) pour cette session : il en faut exactement un."
                )
            terminaux.appeler_prestation(actifs[0], prestation, request.user)

        appliquer_action(request, queryset, appeler, "candidat appelé sur le terminal de tirage")


@admin.register(Tirage)
class TirageAdmin(ConsultationSeule):
    """Un tirage ne se crée que par ``effectuer_tirage`` et ne s'annule que par ``annuler_tirage`` (§14.2)."""

    list_display = ("prestation", "serie", "rang", "statut", "terminal", "cree_le")
    list_filter = ("statut", "prestation__epreuve")


@admin.register(TerminalTirage)
class TerminalTirageAdmin(AdminDuClient):
    """Une tablette de tirage. Le jeton n'est affiché qu'une fois, à la création (D31)."""

    list_display = ("nom", "session", "prestation_appelee", "revoque_le", "derniere_activite")
    list_filter = ("session",)
    actions = ["liberer", "revoquer"]

    def get_fields(self, request, obj=None):
        return ("session", "nom") if obj is None else ("session", "nom", "prestation_appelee", "revoque_le", "derniere_activite")

    def get_readonly_fields(self, request, obj=None):
        return ("session", "nom", "prestation_appelee", "revoque_le", "derniere_activite") if obj else ()

    def has_change_permission(self, request, obj=None):
        return False if obj else super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        def creer():
            terminal, jeton = terminaux.creer_terminal(obj.session, obj.nom)
            obj.__dict__.update(terminal.__dict__)
            adresse = request.build_absolute_uri(reverse("prestations:ecran_tirage")) + "#" + jeton
            messages.warning(
                request,
                f"Terminal créé. Ouvrez cette adresse sur la tablette (elle ne sera plus affichée) : {adresse}",
            )

        self.executer_metier(request, creer)

    @admin.action(description="Libérer le terminal (retirer le candidat appelé)")
    def liberer(self, request, queryset):
        appliquer_action(request, queryset, terminaux.liberer_terminal, "terminal libéré")

    @admin.action(description="Révoquer le terminal (le jeton cesse de fonctionner)")
    def revoquer(self, request, queryset):
        appliquer_action(request, queryset, terminaux.revoquer_terminal, "terminal révoqué")
```

```powershell
pytest apps\prestations apps\commun
```

Attendu : tout passe **si vos deux règles du chapitre 13 sont écrites** ; sinon les tests qui tirent réellement une série échouent avec `NotImplementedError: TODO(human)`. C'est voulu : c'est vous qui avez la règle RM-21.

## Partie 2 — Le front : ce qu'il faut comprendre

**Un composant Vue** (`EcranTirage.vue`) est un fichier à trois parties : `<script>` (la logique), `<template>` (ce qui est affiché, avec `v-if`, `v-for`, `@click`) et le style. Il ne contient **aucune règle métier** : il affiche ce que le store lui donne et lui dit quand l'utilisateur agit.

**Un store Pinia** (`stores/tirage.ts`) est la mémoire partagée de l'écran : des `ref` (l'état), des `computed` (ce qui s'en déduit, ici la **vue** à afficher) et des fonctions (les actions). Ici la vue est **déduite de l'état du serveur** : « pas de jeton », « en attente d'appel », « prêt », « confirmation », « envoi », « résultat », « erreur ». Si la tablette est rechargée, elle reconstruit son écran depuis le serveur, sans rien perdre.

**Pourquoi l'identifiant de demande vit dans le store ?** Le candidat appuie, la connexion coupe : on ne sait pas si le serveur a tiré. Si on réessayait avec un **nouvel** identifiant, on risquerait un second tirage. On réessaie donc avec **le même**, et le serveur renvoie le tirage déjà enregistré (REC-07).

## Partie 3 — Le front : les fichiers

### Étape F — Node et les dépendances

Vérifiez Node.js (22 ou plus) :

```powershell
node -v
```

Puis, à la racine du projet :

```powershell
New-Item -ItemType Directory frontend\src\tirage\stores, frontend\src\tirage\__tests__ -Force | Out-Null
cd frontend
npm init -y
npm install vue pinia
npm install -D vite @vitejs/plugin-vue "typescript@~5.9" vue-tsc vitest @vue/test-utils jsdom
```

Remplacez ensuite le contenu de `package.json` par (les numéros de version seront ceux que `npm` aura installés ; gardez les vôtres, mais **laissez `typescript` en `~5.9`**) :

**Fichier `frontend\package.json`**

```json
{
  "name": "quranova-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "test": "vitest run",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "pinia": "^4.0.3",
    "vue": "^3.5.43"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^6.0.9",
    "@vue/test-utils": "^2.5.1",
    "jsdom": "^29.1.1",
    "typescript": "~5.9",
    "vite": "^8.3.4",
    "vitest": "^5.0.3",
    "vue-tsc": "^3.3.12"
  }
}
```

### Étape G — Réglages

**Fichier `frontend\vite.config.ts`**

```typescript
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// Le build écrit dans static/frontend/ avec des noms FIXES : le gabarit Django
// templates/tirage.html les référence directement (pas de manifeste à lire).
export default defineConfig({
  plugins: [vue()],
  base: "/static/frontend/",
  build: {
    outDir: "../static/frontend",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: "src/tirage/main.ts",
      output: {
        entryFileNames: "tirage.js",
        chunkFileNames: "tirage-[name].js",
        assetFileNames: "tirage[extname]",
      },
    },
  },
  server: {
    // En développement (npm run dev), l'API est celle de Django.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", globals: true, include: ["src/**/*.test.ts"] },
});
```

**Fichier `frontend\tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vite/client", "vitest/globals"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "vite.config.ts"]
}
```

**Fichier `frontend\src\env.d.ts`**

```typescript
/// <reference types="vite/client" />
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const composant: DefineComponent<object, object, unknown>;
  export default composant;
}
```

### Étape H — Les tests du front d'abord

**Fichier `frontend\src\tirage\__tests__\outils.ts`**

```typescript
import type { AppelEnCours, EtatTerminal } from "../types";

export function appel(champs: Partial<AppelEnCours> = {}): AppelEnCours {
  return {
    numero_candidat: 12,
    prenom: "Awa",
    epreuve: "Mémorisation",
    etat: "en_attente",
    tirages_prevus: 1,
    tirages: [],
    peut_tirer: true,
    ...champs,
  };
}

export function etat(champs: Partial<AppelEnCours> | null = {}): EtatTerminal {
  return { terminal: "Tablette 1", appel: champs === null ? null : appel(champs) };
}

export function reponseJson(corps: unknown, statut = 200): Response {
  return new Response(JSON.stringify(corps), { status: statut, headers: { "Content-Type": "application/json" } });
}

/** Un faux serveur : répond selon la route et garde la trace des appels. */
export function fauxServeur(routes: Record<string, () => Response | Promise<Response>>) {
  const appels: { chemin: string; options?: RequestInit }[] = [];
  const faux = vi.fn(async (chemin: string, options?: RequestInit) => {
    appels.push({ chemin, options });
    const route = routes[`${options?.method ?? "GET"} ${chemin}`];
    if (!route) throw new Error(`Route non prévue : ${options?.method ?? "GET"} ${chemin}`);
    return route();
  });
  vi.stubGlobal("fetch", faux);
  return { appels, faux };
}
```

**Fichier `frontend\src\tirage\__tests__\jeton.test.ts`**

```typescript
import { beforeEach, describe, expect, it } from "vitest";

import { chargerJeton, oublierJeton } from "../jeton";

describe("jeton du terminal (D31)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/tirage/");
  });

  it("lit le jeton dans le fragment, le garde et efface l'adresse", () => {
    window.history.replaceState(null, "", "/tirage/#secret-123");

    expect(chargerJeton()).toBe("secret-123");

    expect(window.location.hash).toBe("");
    expect(window.localStorage.getItem("quranova.jeton_tirage")).toBe("secret-123");
  });

  it("retrouve le jeton gardé quand l'adresse n'en contient plus", () => {
    window.localStorage.setItem("quranova.jeton_tirage", "garde");

    expect(chargerJeton()).toBe("garde");
  });

  it("renvoie null sans jeton", () => {
    expect(chargerJeton()).toBeNull();
  });

  it("oublie le jeton", () => {
    window.localStorage.setItem("quranova.jeton_tirage", "x");

    oublierJeton();

    expect(chargerJeton()).toBeNull();
  });
});
```

**Fichier `frontend\src\tirage\__tests__\store.test.ts`**

```typescript
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVALLE_INTERROGATION_MS, useTirageStore } from "../stores/tirage";
import { etat, fauxServeur, reponseJson } from "./outils";

const ETAT = "GET /api/tirage/etat/";
const TIRER = "POST /api/tirage/";

async function demarre(routes: Parameters<typeof fauxServeur>[0]) {
  window.localStorage.setItem("quranova.jeton_tirage", "jeton-test");
  const serveur = fauxServeur(routes);
  const store = useTirageStore();
  await store.demarrer();
  return { store, ...serveur };
}

describe("store de tirage", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    window.localStorage.clear();
    window.history.replaceState(null, "", "/tirage/");
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("sans jeton, le terminal n'est pas configuré et n'appelle pas le serveur", async () => {
    const serveur = fauxServeur({});
    const store = useTirageStore();

    await store.demarrer();

    expect(store.vue).toBe("sans_jeton");
    expect(serveur.faux).not.toHaveBeenCalled();
  });

  it("envoie le jeton dans l'en-tête Authorization", async () => {
    const { appels } = await demarre({ [ETAT]: () => reponseJson(etat(null)) });

    const en_tetes = appels[0]?.options?.headers as Record<string, string>;
    expect(en_tetes["Authorization"]).toBe("Bearer jeton-test");
  });

  it("attend l'appel de l'opérateur, puis propose le tirage quand un candidat est appelé", async () => {
    let courant = etat(null);
    const { store } = await demarre({ [ETAT]: () => reponseJson(courant) });
    expect(store.vue).toBe("attente_appel");

    courant = etat({});
    await vi.advanceTimersByTimeAsync(INTERVALLE_INTERROGATION_MS);

    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("demande une confirmation avant de tirer, et permet d'annuler", async () => {
    const { store } = await demarre({ [ETAT]: () => reponseJson(etat({})) });

    store.demanderConfirmation();
    expect(store.vue).toBe("confirmation");
    store.annulerConfirmation();

    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("REC-07 : deux clics rapides n'envoient qu'une seule demande", async () => {
    let appelsTirage = 0;
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: async () => {
        appelsTirage += 1;
        return reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false, etat: "tire" }),
        });
      },
    });

    await Promise.all([store.confirmerTirage(), store.confirmerTirage()]);

    expect(appelsTirage).toBe(1);
    expect(store.vue).toBe("resultat");
    store.arreter();
  });

  it("le résultat vient du serveur et ne contient que le libellé de la série", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () =>
        reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false }),
        }),
    });

    await store.confirmerTirage();

    expect(store.etat?.appel?.tirages).toEqual([{ rang: 1, serie: "Série 4" }]);
    expect(store.tirageRecent).toBe(1);
    store.arreter();
  });

  it("REC-07 : après une coupure réseau, le nouvel essai réutilise le même identifiant de demande", async () => {
    const identifiants: string[] = [];
    let coupure = true;
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: async () => {
        if (coupure) throw new TypeError("réseau coupé");
        return reponseJson({ tirage: { rang: 1, serie: "Série 2" }, etat: etat({ tirages: [{ rang: 1, serie: "Série 2" }], peut_tirer: false }) });
      },
    });
    const faux = vi.mocked(fetch);
    const originale = faux.getMockImplementation()!;
    faux.mockImplementation(async (chemin, options) => {
      if (options?.method === "POST") identifiants.push(JSON.parse(options.body as string).id_demande);
      return originale(chemin, options);
    });

    await store.confirmerTirage();
    expect(store.vue).toBe("erreur");
    expect(store.erreur?.code).toBe("reseau");

    coupure = false;
    await store.confirmerTirage();

    expect(identifiants).toHaveLength(2);
    expect(identifiants[0]).toBe(identifiants[1]);
    expect(store.vue).toBe("resultat");
    store.arreter();
  });

  it("un refus du serveur (409) affiche son message et n'impose pas de réessayer", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () => reponseJson({ code: "lot_epuise", message: "Le lot est épuisé." }, 409),
    });

    await store.confirmerTirage();

    expect(store.vue).toBe("erreur");
    expect(store.erreur).toEqual({ code: "lot_epuise", message: "Le lot est épuisé." });
    store.fermerErreur();
    await vi.advanceTimersByTimeAsync(0);
    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("un jeton refusé (401) efface le jeton et ramène à l'écran de configuration", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson({ code: "terminal_inconnu", message: "Terminal non reconnu." }, 401),
    });

    expect(store.vue).toBe("sans_jeton");
    expect(window.localStorage.getItem("quranova.jeton_tirage")).toBeNull();
  });

  it("garde le dernier état connu quand le serveur ne répond plus", async () => {
    let coupure = false;
    const { store } = await demarre({
      [ETAT]: () => {
        if (coupure) throw new TypeError("réseau coupé");
        return reponseJson(etat({}));
      },
    });
    coupure = true;

    await vi.advanceTimersByTimeAsync(INTERVALLE_INTERROGATION_MS);

    expect(store.horsLigne).toBe(true);
    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("T > 1 : après le premier tirage, le candidat peut tirer de nouveau", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({ tirages_prevus: 2, tirages: [{ rang: 1, serie: "Série 1" }], peut_tirer: true })),
    });

    expect(store.vue).toBe("resultat_partiel");
    store.arreter();
  });
});
```

**Fichier `frontend\src\tirage\__tests__\ecran.test.ts`**

```typescript
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EcranTirage from "../EcranTirage.vue";
import { INTERVALLE_INTERROGATION_MS } from "../stores/tirage";
import { etat, fauxServeur, reponseJson } from "./outils";

const ETAT = "GET /api/tirage/etat/";
const TIRER = "POST /api/tirage/";

async function monte(routes: Parameters<typeof fauxServeur>[0]) {
  window.localStorage.setItem("quranova.jeton_tirage", "jeton-test");
  const serveur = fauxServeur(routes);
  const pinia = createPinia();
  setActivePinia(pinia);
  const roue = mount(EcranTirage, { global: { plugins: [pinia] } });
  await flushPromises();
  return { roue, ...serveur };
}

describe("écran de tirage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/tirage/");
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("attend l'appel : aucun bouton de tirage", async () => {
    const { roue } = await monte({ [ETAT]: () => reponseJson(etat(null)) });

    expect(roue.text()).toContain("En attente de l'appel");
    expect(roue.find("button").exists()).toBe(false);
    roue.unmount();
  });

  it("affiche le numéro et le prénom du candidat appelé, jamais son nom", async () => {
    const { roue } = await monte({ [ETAT]: () => reponseJson(etat({})) });

    expect(roue.text()).toContain("Candidat n° 12");
    expect(roue.text()).toContain("Awa");
    roue.unmount();
  });

  it("parcours complet : bouton, confirmation, résultat « Série 4 »", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () =>
        reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false }),
        }),
    });

    await roue.get("button").trigger("click"); // « Effectuer mon tirage »
    expect(roue.text()).toContain("Confirmez-vous votre tirage ?");
    const boutons = roue.findAll("button");
    await boutons[0]!.trigger("click"); // « Oui, tirer »
    await flushPromises();

    expect(roue.get("[data-testid=serie]").text()).toBe("Série 4");
    expect(roue.find("button").exists()).toBe(false); // plus de bouton de tirage
    roue.unmount();
  });

  it("l'animation est décorative : la carte se retourne après l'arrivée du résultat", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () =>
        reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false }),
        }),
    });
    await roue.get("button").trigger("click");
    await roue.findAll("button")[0]!.trigger("click");
    await flushPromises();

    expect(roue.get(".carte").classes()).not.toContain("retournee"); // résultat connu, pas encore révélé
    await vi.advanceTimersByTimeAsync(1300);
    expect(roue.get(".carte").classes()).toContain("retournee");
    roue.unmount();
  });

  it("un écran rechargé retrouve directement le résultat, sans animation", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({ tirages: [{ rang: 1, serie: "Série 2" }], peut_tirer: false })),
    });

    expect(roue.get(".carte").classes()).toContain("retournee");
    expect(roue.get("[data-testid=serie]").text()).toBe("Série 2");
    roue.unmount();
  });

  it("affiche le message du serveur en cas de refus", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () => reponseJson({ code: "lot_epuise", message: "Le lot est épuisé : prévenez l'opérateur." }, 409),
    });
    await roue.get("button").trigger("click");
    await roue.findAll("button")[0]!.trigger("click");
    await flushPromises();

    expect(roue.get("[role=alert]").text()).toContain("Le lot est épuisé");
    roue.unmount();
  });

  it("propose « Réessayer » après une coupure réseau", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () => {
        throw new TypeError("réseau coupé");
      },
    });
    await roue.get("button").trigger("click");
    await roue.findAll("button")[0]!.trigger("click");
    await flushPromises();

    expect(roue.get("[role=alert]").text()).toContain("Connexion perdue");
    expect(roue.get("button").text()).toBe("Réessayer");
    roue.unmount();
  });

  it("n'affiche jamais de texte de verset : seul le libellé de la série est rendu", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({ tirages: [{ rang: 1, serie: "Série 7" }], peut_tirer: false })),
    });

    expect(roue.text()).not.toMatch(/[؀-ۿ]/); // aucun caractère arabe
    roue.unmount();
    void INTERVALLE_INTERROGATION_MS;
  });
});
```

```powershell
npm test
```

Attendu : échecs (les fichiers à tester n'existent pas encore). Voulu.

### Étape I — Le code du front

**Fichier `frontend\src\tirage\types.ts`**

```typescript
/** Ce que l'API de tirage renvoie (voir apps/prestations/terminaux.py). Jamais de verset (RM-14). */
export interface TirageEffectue {
  rang: number;
  serie: string;
}

export interface AppelEnCours {
  numero_candidat: number;
  prenom: string;
  epreuve: string;
  etat: string;
  tirages_prevus: number;
  tirages: TirageEffectue[];
  peut_tirer: boolean;
}

export interface EtatTerminal {
  terminal: string;
  appel: AppelEnCours | null;
}

export interface ErreurApi {
  code: string;
  message: string;
}
```

**Fichier `frontend\src\tirage\api.ts`**

```typescript
import type { ErreurApi, EtatTerminal, TirageEffectue } from "./types";

const DELAI_MAX_MS = 8000;

/** Le serveur a répondu mais refuse (401, 409, 400...). */
export class ErreurServeur extends Error {
  constructor(
    public statut: number,
    public erreur: ErreurApi,
  ) {
    super(erreur.message);
  }
}

/** Le serveur n'a pas répondu (Wi-Fi coupé, délai dépassé) : on peut réessayer. */
export class ErreurReseau extends Error {}

async function appeler(jeton: string, chemin: string, options: RequestInit = {}): Promise<unknown> {
  const controle = new AbortController();
  const minuteur = setTimeout(() => controle.abort(), DELAI_MAX_MS);
  let reponse: Response;
  try {
    reponse = await fetch(chemin, {
      ...options,
      signal: controle.signal,
      cache: "no-store",
      headers: { Authorization: `Bearer ${jeton}`, "Content-Type": "application/json" },
    });
  } catch {
    throw new ErreurReseau("Connexion au serveur impossible.");
  } finally {
    clearTimeout(minuteur);
  }
  let corps: unknown = null;
  try {
    corps = await reponse.json();
  } catch {
    // corps absent ou illisible : traité ci-dessous
  }
  if (!reponse.ok) {
    const erreur = (corps ?? {}) as Partial<ErreurApi>;
    throw new ErreurServeur(reponse.status, {
      code: erreur.code ?? "erreur_inconnue",
      message: erreur.message ?? "Erreur inattendue.",
    });
  }
  return corps;
}

export async function lireEtat(jeton: string): Promise<EtatTerminal> {
  return (await appeler(jeton, "/api/tirage/etat/")) as EtatTerminal;
}

export interface ReponseTirage {
  tirage: TirageEffectue;
  etat: EtatTerminal;
}

/** `idDemande` est généré par l'appelant et REPRIS à l'identique en cas de nouvel essai (REC-07). */
export async function demanderTirage(jeton: string, idDemande: string): Promise<ReponseTirage> {
  return (await appeler(jeton, "/api/tirage/", {
    method: "POST",
    body: JSON.stringify({ id_demande: idDemande }),
  })) as ReponseTirage;
}
```

**Fichier `frontend\src\tirage\jeton.ts`**

```typescript
const CLE = "quranova.jeton_tirage";

/**
 * Le jeton arrive dans le FRAGMENT de l'adresse (`/tirage/#jeton`) : un fragment n'est jamais envoyé
 * au serveur ni écrit dans ses journaux (D31). On le garde dans le stockage de la tablette puis on
 * efface l'adresse, pour que le jeton n'y reste pas affiché.
 */
export function chargerJeton(): string | null {
  const fragment = window.location.hash.replace(/^#/, "").trim();
  if (fragment) {
    try {
      window.localStorage.setItem(CLE, fragment);
    } catch {
      // stockage indisponible : le jeton ne vivra que le temps de la page
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return fragment;
  }
  try {
    return window.localStorage.getItem(CLE);
  } catch {
    return null;
  }
}

export function oublierJeton(): void {
  try {
    window.localStorage.removeItem(CLE);
  } catch {
    // rien à faire
  }
}
```

**Fichier `frontend\src\tirage\stores\tirage.ts`**

```typescript
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { demanderTirage, ErreurReseau, ErreurServeur, lireEtat } from "../api";
import { chargerJeton, oublierJeton } from "../jeton";
import type { ErreurApi, EtatTerminal } from "../types";

export type Vue =
  | "sans_jeton"
  | "chargement"
  | "attente_appel"
  | "pret"
  | "confirmation"
  | "envoi"
  | "resultat"
  | "resultat_partiel"
  | "erreur";

export const INTERVALLE_INTERROGATION_MS = 2000;

/**
 * L'état affiché est celui du SERVEUR (interrogé toutes les 2 secondes, D32) : si la tablette est
 * rechargée, elle retrouve le résultat. Seuls le choix « confirmer ? », l'envoi en cours et les erreurs
 * sont locaux. Le composant ne connaît pas la source des données : on pourra la remplacer par un
 * WebSocket (itération 3) sans le toucher.
 */
export const useTirageStore = defineStore("tirage", () => {
  const jeton = ref<string | null>(null);
  const etat = ref<EtatTerminal | null>(null);
  const horsLigne = ref(false);
  const confirmation = ref(false);
  const envoiEnCours = ref(false);
  const erreur = ref<ErreurApi | null>(null);
  /** Rang du tirage qui vient d'être reçu : sert uniquement à l'animation décorative. */
  const tirageRecent = ref<number | null>(null);
  // Identifiant de la demande en cours. Gardé tant que l'issue est inconnue (réseau coupé) :
  // le nouvel essai le réutilise, donc le serveur ne crée jamais deux tirages (REC-07).
  let idDemande: string | null = null;
  let minuteur: ReturnType<typeof setInterval> | null = null;

  const vue = computed<Vue>(() => {
    if (!jeton.value) return "sans_jeton";
    if (envoiEnCours.value) return "envoi";
    if (erreur.value) return "erreur";
    if (!etat.value) return "chargement";
    const appel = etat.value.appel;
    if (!appel) return "attente_appel";
    if (appel.tirages.length > 0) return appel.peut_tirer ? "resultat_partiel" : "resultat";
    return confirmation.value ? "confirmation" : "pret";
  });

  async function rafraichir(): Promise<void> {
    if (!jeton.value || envoiEnCours.value) return;
    try {
      etat.value = await lireEtat(jeton.value);
      horsLigne.value = false;
    } catch (e) {
      if (e instanceof ErreurServeur && e.statut === 401) {
        arreter();
        oublierJeton();
        jeton.value = null;
        etat.value = null;
      } else {
        horsLigne.value = true; // on garde le dernier état connu
      }
    }
  }

  async function demarrer(): Promise<void> {
    jeton.value = chargerJeton();
    if (!jeton.value) return;
    await rafraichir();
    minuteur = setInterval(() => void rafraichir(), INTERVALLE_INTERROGATION_MS);
  }

  function arreter(): void {
    if (minuteur) clearInterval(minuteur);
    minuteur = null;
  }

  function demanderConfirmation(): void {
    erreur.value = null;
    confirmation.value = true;
  }

  function annulerConfirmation(): void {
    confirmation.value = false;
  }

  async function confirmerTirage(): Promise<void> {
    if (!jeton.value || envoiEnCours.value) return; // un deuxième clic pendant l'envoi est ignoré
    envoiEnCours.value = true;
    erreur.value = null;
    confirmation.value = false;
    idDemande ??= crypto.randomUUID();
    try {
      const reponse = await demanderTirage(jeton.value, idDemande);
      etat.value = reponse.etat;
      tirageRecent.value = reponse.tirage.rang;
      idDemande = null; // issue connue : la prochaine demande (tirage suivant) aura un nouvel identifiant
    } catch (e) {
      if (e instanceof ErreurServeur) {
        idDemande = null; // refus définitif de cette demande
        if (e.statut === 401) {
          arreter();
          oublierJeton();
          jeton.value = null;
        } else {
          erreur.value = e.erreur;
        }
      } else if (e instanceof ErreurReseau) {
        // issue inconnue : on garde idDemande pour réessayer sans risque de double tirage
        erreur.value = { code: "reseau", message: "Connexion perdue. Appuyez sur « Réessayer »." };
      } else {
        throw e;
      }
    } finally {
      envoiEnCours.value = false;
    }
  }

  function fermerErreur(): void {
    erreur.value = null;
    void rafraichir();
  }

  return {
    jeton, etat, horsLigne, erreur, tirageRecent, vue,
    demarrer, arreter, rafraichir, demanderConfirmation, annulerConfirmation, confirmerTirage, fermerErreur,
  };
});
```

**Fichier `frontend\src\tirage\EcranTirage.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { useTirageStore } from "./stores/tirage";

const store = useTirageStore();

onMounted(() => void store.demarrer());
onUnmounted(() => store.arreter());

const appel = computed(() => store.etat?.appel ?? null);
const reessayable = computed(() => store.erreur?.code === "reseau");

// Animation DÉCORATIVE (§8.1) : le résultat est déjà connu et enregistré par le serveur quand on la
// lance. Elle ne décide de rien ; elle ne fait que retourner la carte.
const DUREE_ANIMATION_MS = 1200;
const reveleRang = ref<number | null>(null);
let temporisation: ReturnType<typeof setTimeout> | null = null;

watch(
  () => store.tirageRecent,
  (rang) => {
    reveleRang.value = null;
    if (temporisation) clearTimeout(temporisation);
    if (rang !== null) temporisation = setTimeout(() => (reveleRang.value = rang), DUREE_ANIMATION_MS);
  },
);

function carteRetournee(rang: number): boolean {
  // Un tirage déjà connu avant l'animation (écran rechargé) s'affiche directement.
  return store.tirageRecent !== rang || reveleRang.value === rang;
}
</script>

<template>
  <main class="ecran" :data-vue="store.vue">
    <p v-if="store.horsLigne" class="bandeau" role="status">Connexion au serveur perdue — nouvelle tentative…</p>

    <section v-if="store.vue === 'sans_jeton'" class="panneau">
      <h1>Terminal non configuré</h1>
      <p>Demandez à l'opérateur d'ouvrir l'adresse de ce terminal.</p>
    </section>

    <section v-else-if="store.vue === 'chargement'" class="panneau">
      <p>Chargement…</p>
    </section>

    <section v-else-if="store.vue === 'attente_appel'" class="panneau">
      <h1>En attente de l'appel du candidat</h1>
      <p>L'opérateur va appeler le prochain candidat.</p>
    </section>

    <section v-else-if="appel && (store.vue === 'pret' || store.vue === 'confirmation')" class="panneau">
      <p class="etiquette">Candidat n° {{ appel.numero_candidat }}</p>
      <h1>{{ appel.prenom }}</h1>
      <p>{{ appel.epreuve }}</p>
      <button v-if="store.vue === 'pret'" class="gros-bouton" type="button" @click="store.demanderConfirmation()">
        Effectuer mon tirage
      </button>
      <div v-else class="confirmation" role="alertdialog" aria-labelledby="question-confirmation">
        <p id="question-confirmation">Confirmez-vous votre tirage ?</p>
        <button class="gros-bouton" type="button" @click="store.confirmerTirage()">Oui, tirer</button>
        <button class="secondaire" type="button" @click="store.annulerConfirmation()">Annuler</button>
      </div>
    </section>

    <section v-else-if="store.vue === 'envoi'" class="panneau" aria-live="polite">
      <p class="chargement">Tirage en cours…</p>
    </section>

    <section v-else-if="appel && (store.vue === 'resultat' || store.vue === 'resultat_partiel')" class="panneau">
      <p class="etiquette">Candidat n° {{ appel.numero_candidat }}</p>
      <h1>{{ appel.prenom }}, votre tirage</h1>
      <ul class="cartes">
        <li v-for="tirage in appel.tirages" :key="tirage.rang" class="carte" :class="{ retournee: carteRetournee(tirage.rang) }">
          <span class="dos" aria-hidden="true">?</span>
          <span class="face" data-testid="serie">{{ tirage.serie }}</span>
        </li>
      </ul>
      <p v-if="store.vue === 'resultat'" class="consigne">Restez à votre place : l'opérateur lance la présentation.</p>
      <template v-else>
        <p class="consigne">Tirage {{ appel.tirages.length }} sur {{ appel.tirages_prevus }}.</p>
        <button class="gros-bouton" type="button" @click="store.demanderConfirmation()">Effectuer mon tirage suivant</button>
      </template>
    </section>

    <section v-else-if="store.vue === 'erreur' && store.erreur" class="panneau erreur" role="alert">
      <h1>Tirage impossible</h1>
      <p>{{ store.erreur.message }}</p>
      <button v-if="reessayable" class="gros-bouton" type="button" @click="store.confirmerTirage()">Réessayer</button>
      <button v-else class="secondaire" type="button" @click="store.fermerErreur()">Compris</button>
    </section>
  </main>
</template>
```

**Fichier `frontend\src\tirage\style.css`**

```css
:root { --fond: #0f3d3e; --papier: #fbf7ee; --or: #c9a227; --texte: #1d2b2b; }
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--fond); color: var(--papier);
  font-family: system-ui, "Segoe UI", sans-serif; -webkit-user-select: none; user-select: none;
  touch-action: manipulation; }
.ecran { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2rem; }
.panneau { text-align: center; max-width: 40rem; width: 100%; }
h1 { font-size: clamp(2rem, 6vw, 3.5rem); margin: .3em 0; }
.etiquette { letter-spacing: .08em; text-transform: uppercase; opacity: .8; margin: 0; }
.consigne { opacity: .85; }
.bandeau { position: fixed; top: 0; left: 0; right: 0; margin: 0; padding: .6rem; text-align: center;
  background: #8a5a00; color: #fff; font-size: 1rem; }
button { font: inherit; border: 0; cursor: pointer; border-radius: 1rem; }
button:focus-visible { outline: 4px solid #fff; outline-offset: 3px; }
.gros-bouton { background: var(--or); color: var(--texte); font-size: clamp(1.5rem, 4vw, 2.2rem); font-weight: 700;
  padding: 1.2rem 2.5rem; margin-top: 1.5rem; min-width: 16rem; min-height: 4.5rem; }
.gros-bouton:active { transform: scale(.98); }
.secondaire { background: transparent; color: var(--papier); border: 2px solid var(--papier); padding: 1rem 2rem;
  font-size: 1.3rem; margin: 1rem .5rem 0; min-height: 3.5rem; }
.confirmation { margin-top: 1rem; }
.confirmation p { font-size: 1.6rem; }
.erreur { background: #5b1d1d; padding: 2rem; border-radius: 1.5rem; }
.chargement::after { content: ""; display: inline-block; width: 1em; height: 1em; margin-left: .5em;
  border: 3px solid var(--papier); border-right-color: transparent; border-radius: 50%; animation: tourne 1s linear infinite; }
@keyframes tourne { to { transform: rotate(360deg); } }

/* Cartes retournées : décoratif seulement, le résultat est déjà enregistré par le serveur. */
.cartes { list-style: none; padding: 0; margin: 2rem 0; display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; perspective: 900px; }
.carte { position: relative; width: 14rem; height: 9rem; transform-style: preserve-3d; transition: transform .8s ease; }
.carte.retournee { transform: rotateY(180deg); }
.carte .dos, .carte .face { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  border-radius: 1rem; backface-visibility: hidden; font-size: 2.6rem; font-weight: 700; }
.carte .dos { background: var(--or); color: var(--texte); }
.carte .face { background: var(--papier); color: var(--texte); transform: rotateY(180deg); }
@media (prefers-reduced-motion: reduce) { .carte { transition: none; } .chargement::after { animation: none; } }
```

**Fichier `frontend\src\tirage\main.ts`**

```typescript
import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranTirage from "./EcranTirage.vue";
import "./style.css";

createApp(EcranTirage).use(createPinia()).mount("#app");
```

```powershell
npm test
npm run typecheck
npm run build
```

Attendu : `23 passed`, aucune erreur de types, et deux fichiers créés : `static\frontend\tirage.js` et `tirage.css`. Ce dossier n'est **pas** versionné (ajoutez `static/frontend/` à `.gitignore`) : on le reconstruit avec `npm run build`.

## Partie 4 — Voir l'écran fonctionner

1. `python manage.py runserver`, puis l'administration (chapitre 14).
2. Il vous faut un **concours en cours**, une **épreuve ouverte** avec son lot, une **session** et une **prestation** pour un candidat *admis* (voir la note du chapitre 14 sur le corpus validé).
3. **Terminaux de tirage** → *Ajouter* : choisissez la session, donnez un nom. Le message vert affiche **une seule fois** l'adresse à ouvrir sur la tablette : `http://…/tirage/#le-jeton`.
4. Ouvrez cette adresse dans un autre onglet : « En attente de l'appel du candidat ». L'adresse se vide aussitôt (le jeton est gardé par le navigateur).
5. Dans **Prestations**, cochez une prestation → action **Appeler au tirage**. En moins de 2 secondes, la tablette affiche le candidat et le bouton.
6. Appuyez, confirmez : « Série N ». Rechargez la page : le résultat est toujours là.
7. Dans **Tirages** : le tirage est enregistré avec le nom du terminal.

## Questions de compréhension

1. Pourquoi le jeton est-il dans le **fragment** (`#…`) de l'adresse et pas dans la requête (`?…`) ?
2. La tablette ne peut pas dire *quel* candidat tire. Qu'est-ce qui l'empêche d'envoyer l'identifiant d'un autre candidat ?
3. Après une coupure réseau, pourquoi le bouton « Réessayer » ne risque-t-il pas de créer un second tirage ?

<details>
<summary>Réponses</summary>

1. Un fragment n'est jamais envoyé au serveur : il n'apparaît ni dans ses journaux ni dans l'historique des intermédiaires. Une requête (`?…`) serait écrite partout.
2. L'API ne lit que `id_demande`. La prestation est celle que l'opérateur a appelée sur ce terminal, déduite du jeton authentifié ; un champ `prestation` ajouté dans la requête est ignoré (le test `test_rec25_…` le vérifie).
3. Le store garde le même `id_demande` tant que l'issue est inconnue. Le serveur, voyant un identifiant déjà enregistré, renvoie le tirage existant au lieu d'en créer un autre.
</details>

## Journal d'apprentissage

Dessinez le trajet d'un clic : du bouton jusqu'à la base de données et retour. Notez à chaque étape ce qui se passerait si la connexion coupait.

## Commit proposé

```text
Itération 2 : écran de tirage en Vue 3 et API à jeton
```
