# Chapitre 17 — L'état de présentation et les commandes (itération 3, étape 3b)

> **Commit de référence :** `c63d1dc` · **Durée :** 5 à 6 heures · **Résultat :** les modèles `EtatPresentation` et `CommandePresentation`, le service `appliquer_commande` (versionné, idempotent, sérialisé), l'instantané projeté par rôle, le `Terminal` généralisé, et **une règle à écrire par vous** : les **transitions**.

## Objectif

Le serveur **détient** l'état du diaporama (règle absolue n°7). Chaque commande porte un identifiant unique et la version attendue (RM-30) :

| Règle | Où elle est appliquée |
|---|---|
| **RM-30** : commande obsolète ou déjà traitée rejetée | `appliquer_commande` : version comparée sous verrou ; identifiant unique en base |
| **REC-24** : deux « suivante » simultanées → une seule appliquée | verrou de session + version ; test avec deux threads |
| **RM-11** : rien n'avance sans l'opérateur ; la pause bloque | **vous** : `appliquer_transition` |
| **§9.3** : le retour en arrière est journalisé | `CommandePresentation` journalise TOUTES les commandes |
| **RM-25** : tirage marqué dès qu'un verset est affiché | `_synchroniser_prestation` |
| **RM-14, D15** : le texte ne va qu'aux écrans autorisés | `construire_instantane` (projection côté serveur) |
| **D37** : un terminal de scène a son jeton | `Terminal` avec un type « tirage » ou « scène » |

## Étape A — Le terminal généralisé (D37)

`TerminalTirage` devient `Terminal` (champ `type` : `tirage` ou `scene`). La migration **renomme** le modèle sans perdre les terminaux existants.

Dans tout le code, remplacez `TerminalTirage` par `Terminal` et `terminaux_tirage` par `terminaux` (modèle, administration, tests). Le jeton d'une scène n'ouvre pas l'API de tirage, ni l'inverse : le type fait partie de l'authentification.

**À la fin de `apps\prestations\models.py`**, ajoutez la classe `Terminal` :

```python

class Terminal(ModeleDuClient):
    """Un terminal de la salle : tablette de tirage ou écran de scène (§15.1, §8.6, §9.4 ; D31, D37).

    Le terminal s'authentifie par un jeton secret (D31) dont seule l'empreinte est stockée.
    Le candidat appelé est FIXÉ PAR L'OPÉRATEUR (``prestation_appelee``) : le candidat ne choisit
    jamais son identité, et le client n'envoie jamais d'identifiant de prestation (REC-25).
    """

    PARENTS_CLIENT = ("session",)

    class Type(models.TextChoices):
        TIRAGE = "tirage", "Tablette de tirage"
        SCENE = "scene", "Écran de scène"

    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="terminaux")
    nom = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.TIRAGE)
    empreinte = models.CharField(max_length=64, unique=True)
    prestation_appelee = models.ForeignKey(
        Prestation, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revoque_le = models.DateTimeField(null=True, blank=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "terminal"
        verbose_name_plural = "terminaux"
        ordering = ["session", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["session", "nom"], name="terminal_nom_unique_par_session"),
            # Seule une tablette de tirage a un candidat « appelé » : l'écran de scène suit la session.
            models.CheckConstraint(
                condition=Q(type="tirage") | Q(prestation_appelee__isnull=True),
                name="terminal_appel_reserve_au_tirage",
            ),
        ]

    def save(self, *args, **kwargs):
        self.verifier_organisation()
        if self.prestation_appelee_id is not None and self.prestation_appelee.session_id != self.session_id:
            raise PrestationInvalideError("La prestation appelée n'appartient pas à la session du terminal.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} ({self.session})"
```

**Fichier `apps\prestations\migrations\0003_terminal.py`**

```python
"""D37 : ``TerminalTirage`` devient ``Terminal`` (types « tirage » et « scène »), sans perdre les terminaux existants."""
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("concours", "0001_initial"),
        ("prestations", "0002_terminaltirage"),
    ]

    operations = [
        migrations.RenameModel(old_name="TerminalTirage", new_name="Terminal"),
        migrations.AlterModelOptions(
            name="terminal",
            options={
                "ordering": ["session", "nom"],
                "verbose_name": "terminal",
                "verbose_name_plural": "terminaux",
            },
        ),
        migrations.AlterField(
            model_name="terminal",
            name="session",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT, related_name="terminaux", to="concours.session"
            ),
        ),
        migrations.AddField(
            model_name="terminal",
            name="type",
            field=models.CharField(
                choices=[("tirage", "Tablette de tirage"), ("scene", "Écran de scène")],
                default="tirage",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="terminal",
            constraint=models.CheckConstraint(
                condition=Q(type="tirage") | Q(prestation_appelee__isnull=True),
                name="terminal_appel_reserve_au_tirage",
            ),
        ),
    ]
```

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
from apps.prestations.models import Prestation, Terminal, Tirage
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

CONTEXTE_JETON = "terminal-tirage"


def creer_terminal(session, nom, type=Terminal.Type.TIRAGE):
    """Crée un terminal ; renvoie ``(terminal, jeton)``. Le jeton n'est montré qu'à cet instant (D31)."""
    jeton = fabriquer_jeton()
    terminal = Terminal.objects.create(
        session=session, nom=nom, type=type, empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON)
    )
    return terminal, jeton


def revoquer_terminal(terminal):
    terminal.revoque_le = timezone.now()
    terminal.prestation_appelee = None
    terminal.save(update_fields=["revoque_le", "prestation_appelee", "modifie_le"])


def authentifier_terminal(jeton, type=Terminal.Type.TIRAGE):
    """Le terminal de ce ``type`` correspondant au jeton, ou ``TerminalInvalideError`` (message vague).

    Le type fait partie de l'authentification : le jeton d'une scène ne donne aucun accès à l'API de tirage,
    ni l'inverse (REC-14).
    """
    if not jeton:
        raise TerminalInvalideError("Terminal non reconnu.")
    terminal = Terminal.objects.filter(
        empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), type=type, revoque_le__isnull=True
    ).first()
    if terminal is None:
        raise TerminalInvalideError("Terminal non reconnu.")
    Terminal.objects.filter(pk=terminal.pk).update(derniere_activite=timezone.now())
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
        terminal = Terminal.objects.select_for_update().get(pk=terminal.pk)
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

```powershell
python manage.py migrate
```

## Étape B — Les modèles

**Fichier `apps\presentation\models.py`**

```python
"""État de présentation d'une prestation et journal des commandes (§9.3, §13.5, RM-30)."""
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient


class EtatPresentation(ModeleDuClient):
    """L'état du diaporama d'une prestation. C'est le SERVEUR qui le détient (règle absolue n°7).

    ``version`` croît à chaque changement ; une commande n'est appliquée que si elle porte la version
    courante (RM-30). ``plan`` ne contient que des références, figées à « Préparer l'affichage » (D39).
    """

    PARENTS_CLIENT = ("prestation", "session")

    class Phase(models.TextChoices):
        PREPAREE = "preparee", "Préparée"
        AFFICHAGE = "affichage", "En affichage"
        PAUSE = "pause", "En pause"
        TERMINEE = "terminee", "Terminée"

    prestation = models.OneToOneField("prestations.Prestation", on_delete=models.PROTECT, related_name="presentation")
    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="presentations")
    active = models.BooleanField(default=False, help_text="La présentation suivie par les écrans de la session (D41).")
    version = models.PositiveIntegerField(default=1)
    phase = models.CharField(max_length=10, choices=Phase.choices, default=Phase.PREPAREE)
    index = models.PositiveIntegerField(null=True, blank=True, help_text="Diapositive courante (0 = la première).")
    rejeu = models.PositiveIntegerField(default=0, help_text="Incrémenté par « Réafficher la diapositive ».")
    plan = models.JSONField(default=list)

    class Meta:
        verbose_name = "état de présentation"
        verbose_name_plural = "états de présentation"
        constraints = [
            # Une seule présentation active par session (D41).
            models.UniqueConstraint(fields=["session"], condition=Q(active=True), name="presentation_une_active_par_session"),
            models.CheckConstraint(condition=Q(version__gte=1), name="presentation_version_au_moins_1"),
            models.CheckConstraint(
                condition=(Q(phase="preparee", index__isnull=True) | (~Q(phase="preparee") & Q(index__isnull=False))),
                name="presentation_index_selon_la_phase",
            ),
        ]

    def __str__(self):
        return f"Présentation de {self.prestation} (v{self.version}, {self.get_phase_display()})"


class CommandePresentation(ModeleDuClient):
    """Journal des commandes reçues : appliquées OU rejetées, avec leur auteur (§9.3, §15.2).

    L'identifiant de commande, unique, est ce qui rend une commande rejouable sans effet (RM-30).
    Le retour à la diapositive précédente y est donc toujours tracé.
    """

    PARENTS_CLIENT = ("session",)

    class Statut(models.TextChoices):
        APPLIQUEE = "appliquee", "Appliquée"
        REJETEE = "rejetee", "Rejetée"

    id_commande = models.UUIDField(unique=True)
    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="commandes_presentation")
    prestation = models.ForeignKey(
        "prestations.Prestation", null=True, blank=True, on_delete=models.PROTECT, related_name="commandes_presentation"
    )
    action = models.CharField(max_length=20)
    version_attendue = models.PositiveIntegerField(null=True, blank=True)
    version_apres = models.PositiveIntegerField(null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    raison = models.CharField(max_length=40, blank=True)
    auteur = models.ForeignKey("utilisateurs.Utilisateur", null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "commande de présentation"
        verbose_name_plural = "commandes de présentation"
        ordering = ["cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(statut="appliquee", raison="") | (Q(statut="rejetee") & ~Q(raison=""))),
                name="commande_raison_si_rejetee",
            ),
        ]

    def __str__(self):
        return f"{self.action} ({self.get_statut_display()})"
```

```powershell
python manage.py makemigrations presentation
python manage.py migrate
```

## Étape C — Les transitions : les tests d'abord, puis **votre** règle

La fonction est **pure** : position et action en entrée, nouvelle position (ou refus) en sortie. Elle ne touche ni la base ni le réseau, donc elle se teste sans rien d'autre.

**Fichier `apps\presentation\tests\test_transitions.py`**

```python
"""Tests des transitions de la présentation (§9.3, RM-10, RM-11) — fonction à écrire par vous."""
import pytest

from apps.presentation.exceptions import TransitionInterditeError
from apps.presentation.transitions import AFFICHAGE, PAUSE, PREPAREE, TERMINEE, Position, appliquer_transition

TOTAL = 5  # diapositives 0 à 4


def p(phase, index=None, rejeu=0):
    return Position(phase, index, rejeu)


@pytest.mark.parametrize(
    "avant, action, apres",
    [
        (p(PREPAREE), "demarrer", p(AFFICHAGE, 0)),
        (p(AFFICHAGE, 0), "suivante", p(AFFICHAGE, 1)),
        (p(AFFICHAGE, 3), "suivante", p(AFFICHAGE, 4)),
        (p(AFFICHAGE, 4), "precedente", p(AFFICHAGE, 3)),
        (p(AFFICHAGE, 1), "precedente", p(AFFICHAGE, 0)),
        (p(AFFICHAGE, 2), "pause", p(PAUSE, 2)),
        (p(PAUSE, 2), "reprendre", p(AFFICHAGE, 2)),
        (p(AFFICHAGE, 2, rejeu=1), "reafficher", p(AFFICHAGE, 2, rejeu=2)),
        (p(AFFICHAGE, 4), "terminer", p(TERMINEE, 4)),
        (p(AFFICHAGE, 1), "terminer", p(TERMINEE, 1)),  # fin anticipée (incident) possible
        (p(PAUSE, 3), "terminer", p(TERMINEE, 3)),
    ],
)
def test_transitions_autorisees(avant, action, apres):
    assert appliquer_transition(avant, TOTAL, action) == apres


@pytest.mark.parametrize(
    "avant, action",
    [
        (p(PREPAREE), "suivante"),  # RM-11 : rien n'avance avant « démarrer »
        (p(PREPAREE), "precedente"),
        (p(PREPAREE), "pause"),
        (p(PREPAREE), "terminer"),
        (p(AFFICHAGE, 4), "suivante"),  # jamais au-delà de la dernière diapositive
        (p(AFFICHAGE, 0), "precedente"),  # pas de retour avant la première
        (p(AFFICHAGE, 0), "demarrer"),  # déjà démarrée
        (p(AFFICHAGE, 1), "reprendre"),  # ce n'est pas en pause
        (p(PAUSE, 2), "suivante"),  # la pause bloque l'avancement (§9.3)
        (p(PAUSE, 2), "precedente"),
        (p(PAUSE, 2), "pause"),
        (p(PAUSE, 2), "reafficher"),
        (p(PAUSE, 2), "demarrer"),
        (p(TERMINEE, 4), "suivante"),
        (p(TERMINEE, 4), "precedente"),
        (p(TERMINEE, 4), "reprendre"),
        (p(TERMINEE, 4), "terminer"),
        (p(TERMINEE, 4), "reafficher"),
        (p(AFFICHAGE, 2), "preparer"),  # « préparer » crée l'état : ce n'est pas une transition
        (p(AFFICHAGE, 2), "n_importe_quoi"),
        (p(AFFICHAGE, 2), ""),
    ],
)
def test_transitions_interdites_avec_un_message(avant, action):
    with pytest.raises(TransitionInterditeError) as erreur:
        appliquer_transition(avant, TOTAL, action)

    assert str(erreur.value)  # un message explicite pour l'opérateur


def test_une_presentation_d_une_seule_diapositive():
    debut = appliquer_transition(p(PREPAREE), 1, "demarrer")

    assert debut == p(AFFICHAGE, 0)
    with pytest.raises(TransitionInterditeError):
        appliquer_transition(debut, 1, "suivante")
    assert appliquer_transition(debut, 1, "terminer") == p(TERMINEE, 0)


def test_la_position_recue_n_est_jamais_modifiee():
    avant = p(AFFICHAGE, 2)

    appliquer_transition(avant, TOTAL, "suivante")

    assert avant == p(AFFICHAGE, 2)


def test_parcours_complet_de_la_premiere_a_la_derniere_diapositive():
    position = appliquer_transition(p(PREPAREE), TOTAL, "demarrer")
    for attendu in range(1, TOTAL):
        position = appliquer_transition(position, TOTAL, "suivante")
        assert position.index == attendu

    assert appliquer_transition(position, TOTAL, "terminer").phase == TERMINEE
```

**Fichier `apps\presentation\transitions.py`**

```python
"""Transitions de l'état de présentation (§9.3, RM-10, RM-11).

Fonction PURE : elle ne touche ni la base ni le réseau. Elle reçoit la position courante et l'action, et
renvoie la nouvelle position, ou refuse. Le service ``appliquer_commande`` se charge du reste (verrou,
version, journal).
"""
from dataclasses import dataclass

from apps.presentation.exceptions import TransitionInterditeError  # noqa: F401

PREPAREE, AFFICHAGE, PAUSE, TERMINEE = "preparee", "affichage", "pause", "terminee"
ACTIONS = ("demarrer", "suivante", "precedente", "pause", "reprendre", "reafficher", "terminer")


@dataclass(frozen=True)
class Position:
    """Où en est la présentation : sa phase, la diapositive courante (``None`` si rien n'est affiché), le rejeu."""

    phase: str
    index: int | None = None
    rejeu: int = 0


def appliquer_transition(position, total, action):
    """Renvoie la ``Position`` après ``action``, ou lève ``TransitionInterditeError`` avec un message clair.

    TODO(human) : écrivez la règle. ``total`` est le nombre de diapositives du plan (les index vont de 0 à
    total - 1). Contrat (voir ``test_transitions.py``) :
    - ``demarrer`` : « préparée » -> « en affichage », à la diapositive 0 ;
    - ``suivante`` : seulement « en affichage » ; avance d'une diapositive ; INTERDITE à la dernière
      (l'opérateur doit « terminer ») : jamais de défilement automatique, jamais au-delà de la fin ;
    - ``precedente`` : seulement « en affichage » et pas à la première diapositive ; recule d'une ;
    - ``pause`` : « en affichage » -> « en pause » (même diapositive) ; ``reprendre`` : l'inverse ;
    - ``reafficher`` : seulement « en affichage » ; même diapositive, ``rejeu`` augmente de 1 ;
    - ``terminer`` : « en affichage » ou « en pause » -> « terminée » (la diapositive courante est conservée) ;
    - tout le reste est interdit, y compris toute action sur une présentation « terminée » et l'action
      « preparer » (qui n'est pas une transition : elle crée l'état) ou une action inconnue.
    La position reçue n'est jamais modifiée (``Position`` est figée) : renvoyez-en une nouvelle.
    """
    raise NotImplementedError("TODO(human) : transitions de la présentation (voir la docstring)")
```

```powershell
pytest apps\presentation\tests\test_transitions.py
```

Avant : `35 failed`. Après : `35 passed`.

**Indice :** traitez d'abord les cas qui interdisent tout (présentation terminée), puis `demarrer`, puis ce qui est permis en pause, et enfin ce qui n'est permis qu'en affichage. Pensez à la **dernière** diapositive : on n'avance pas au-delà, on « termine ».

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
# Dans apps/presentation/transitions.py, remplacez le corps de appliquer_transition (et ajoutez « replace » à l'import de dataclasses : from dataclasses import dataclass, replace) par :

def appliquer_transition(position, total, action):
    """Renvoie la ``Position`` après ``action``, ou lève ``TransitionInterditeError`` avec un message clair.

    TODO(human) : écrivez la règle. ``total`` est le nombre de diapositives du plan (les index vont de 0 à
    total - 1). Contrat (voir ``test_transitions.py``) :
    - ``demarrer`` : « préparée » -> « en affichage », à la diapositive 0 ;
    - ``suivante`` : seulement « en affichage » ; avance d'une diapositive ; INTERDITE à la dernière
      (l'opérateur doit « terminer ») : jamais de défilement automatique, jamais au-delà de la fin ;
    - ``precedente`` : seulement « en affichage » et pas à la première diapositive ; recule d'une ;
    - ``pause`` : « en affichage » -> « en pause » (même diapositive) ; ``reprendre`` : l'inverse ;
    - ``reafficher`` : seulement « en affichage » ; même diapositive, ``rejeu`` augmente de 1 ;
    - ``terminer`` : « en affichage » ou « en pause » -> « terminée » (la diapositive courante est conservée) ;
    - tout le reste est interdit, y compris toute action sur une présentation « terminée » et l'action
      « preparer » (qui n'est pas une transition : elle crée l'état) ou une action inconnue.
    La position reçue n'est jamais modifiée (``Position`` est figée) : renvoyez-en une nouvelle.
    """
    phase, index = position.phase, position.index
    if phase == TERMINEE:
        raise TransitionInterditeError("La présentation est terminée : plus aucune commande n'est possible.")
    if action == "demarrer":
        if phase != PREPAREE:
            raise TransitionInterditeError("La présentation est déjà démarrée.")
        return Position(AFFICHAGE, 0, position.rejeu)
    if phase == PREPAREE:
        raise TransitionInterditeError("La présentation n'est pas démarrée : utilisez « Démarrer ».")
    if action == "reprendre":
        if phase != PAUSE:
            raise TransitionInterditeError("La présentation n'est pas en pause.")
        return replace(position, phase=AFFICHAGE)
    if action == "terminer":
        return replace(position, phase=TERMINEE)  # depuis l'affichage ou la pause
    if phase == PAUSE:
        raise TransitionInterditeError("La présentation est en pause : reprenez avant de continuer.")
    # À partir d'ici, la phase est « affichage ».
    if action == "suivante":
        if index >= total - 1:
            raise TransitionInterditeError("C'est la dernière diapositive : utilisez « Terminer la prestation ».")
        return replace(position, index=index + 1)
    if action == "precedente":
        if index <= 0:
            raise TransitionInterditeError("C'est déjà la première diapositive.")
        return replace(position, index=index - 1)
    if action == "pause":
        return replace(position, phase=PAUSE)
    if action == "reafficher":
        return replace(position, rejeu=position.rejeu + 1)
    raise TransitionInterditeError(f"Action inconnue ou non permise ici : « {action} ».")
```

</details>

## Étape D — Le service des commandes et l'instantané

**Fichier `apps\presentation\tests\test_commandes.py`**

```python
"""Tests des commandes de présentation (§9.3, §13.5 ; RM-30, RM-25 ; REC-14, REC-24)."""
import threading
import uuid

import pytest
from django.db import connection

from apps.commun.tests.outils import creer_session, creer_utilisateur
from apps.prestations.models import Prestation, Tirage
from apps.presentation import services
from apps.presentation.models import CommandePresentation, EtatPresentation
from apps.presentation.tests.outils import commande, creer_prestation_tiree, operateur_de, presentation_demarree
from apps.utilisateurs.models import Utilisateur


@pytest.fixture
def tiree(db):
    prestation, epreuve, _ = creer_prestation_tiree()
    return prestation, prestation.session, operateur_de(epreuve)


# --- Préparer ------------------------------------------------------------------


@pytest.mark.django_db
def test_preparer_cree_l_etat_actif_en_version_1(tiree):
    prestation, session, operateur = tiree

    resultat = commande(session, "preparer", auteur=operateur, prestation=prestation)

    assert (resultat.statut, resultat.version) == ("appliquee", 1)
    etat = EtatPresentation.objects.get()
    assert etat.active and etat.phase == "preparee" and etat.index is None
    assert len(etat.plan) == 10  # 2 questions : intercalaires, 5 versets, fins de question, fin de série
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.TIRE  # rien n'est encore affiché


@pytest.mark.django_db
def test_preparer_exige_une_prestation_tiree(tiree):
    prestation, session, operateur = tiree
    Prestation.objects.filter(pk=prestation.pk).update(etat=Prestation.Etat.EN_ATTENTE)
    prestation.refresh_from_db()

    resultat = commande(session, "preparer", auteur=operateur, prestation=prestation)

    assert (resultat.statut, resultat.raison) == ("rejetee", "transition_interdite")
    assert EtatPresentation.objects.count() == 0


@pytest.mark.django_db
def test_preparer_refuse_une_prestation_d_une_autre_session(tiree):
    prestation, session, operateur = tiree
    autre_session = creer_session(session.concours)

    resultat = commande(autre_session, "preparer", auteur=operateur, prestation=prestation)

    assert resultat.statut == "rejetee"


@pytest.mark.django_db
def test_d41_on_ne_prepare_pas_une_autre_prestation_pendant_un_affichage():
    prestation, session, operateur, _ = presentation_demarree()
    prestation2, epreuve, _ = creer_prestation_tiree()  # autre prestation, autre concours : on la rattache à la session
    Prestation.objects.filter(pk=prestation2.pk).update(session=session)

    resultat = commande(session, "preparer", auteur=operateur, prestation=prestation2)

    assert (resultat.statut, resultat.raison) == ("rejetee", "transition_interdite")


# --- Parcours ------------------------------------------------------------------


@pytest.mark.django_db
def test_le_parcours_complet_met_a_jour_la_prestation():
    prestation, session, operateur, etat = presentation_demarree()
    assert (etat.version, etat.phase, etat.index) == (2, "affichage", 0)
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_AFFICHAGE

    assert commande(session, "pause", 2, auteur=operateur).etat.phase == "pause"
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_PAUSE
    assert commande(session, "reprendre", 3, auteur=operateur).version == 4
    suivante = commande(session, "suivante", 4, auteur=operateur)
    assert (suivante.statut, suivante.etat.index, suivante.version) == ("appliquee", 1, 5)
    termine = commande(session, "terminer", 5, auteur=operateur)
    prestation.refresh_from_db()
    assert termine.etat.phase == "terminee" and prestation.etat == Prestation.Etat.EN_NOTATION
    assert commande(session, "suivante", 6, auteur=operateur).raison == "transition_interdite"


@pytest.mark.django_db
def test_rm11_rien_n_avance_tout_seul_et_la_pause_bloque():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "pause", 2, auteur=operateur)

    resultat = commande(session, "suivante", 3, auteur=operateur)

    assert (resultat.statut, resultat.raison) == ("rejetee", "transition_interdite")
    assert EtatPresentation.objects.get().index == 0


@pytest.mark.django_db
def test_reafficher_rejoue_la_diapositive_sans_la_changer():
    prestation, session, operateur, _ = presentation_demarree()

    resultat = commande(session, "reafficher", 2, auteur=operateur)

    assert (resultat.etat.index, resultat.etat.rejeu, resultat.version) == (0, 1, 3)


# --- RM-30 : version, idempotence ------------------------------------------------


@pytest.mark.django_db
def test_rm30_une_commande_avec_une_version_obsolete_est_rejetee_et_ne_change_rien():
    prestation, session, operateur, _ = presentation_demarree()

    resultat = commande(session, "suivante", 1, auteur=operateur)  # la version courante est 2

    assert (resultat.statut, resultat.raison, resultat.version) == ("rejetee", "version_obsolete", 2)
    assert EtatPresentation.objects.get().index == 0


@pytest.mark.django_db
def test_rec24_deux_suivante_avec_la_meme_version_une_seule_est_appliquee():
    prestation, session, operateur, _ = presentation_demarree()

    premiere = commande(session, "suivante", 2, auteur=operateur)
    seconde = commande(session, "suivante", 2, auteur=operateur)  # double clic : même version attendue

    assert premiere.statut == "appliquee" and seconde.statut == "rejetee"
    assert seconde.raison == "version_obsolete" and seconde.version == 3
    assert EtatPresentation.objects.get().index == 1  # une seule diapositive franchie


@pytest.mark.django_db
def test_rm30_une_commande_rejouee_n_est_jamais_appliquee_deux_fois():
    prestation, session, operateur, _ = presentation_demarree()
    identifiant = uuid.uuid4()
    premiere = commande(session, "suivante", 2, auteur=operateur, id_commande=identifiant)

    rejeu = commande(session, "suivante", 2, auteur=operateur, id_commande=identifiant)

    assert (premiere.statut, rejeu.statut, rejeu.version) == ("appliquee", "deja_traitee", 3)
    assert EtatPresentation.objects.get().index == 1
    assert CommandePresentation.objects.filter(id_commande=identifiant).count() == 1


@pytest.mark.django_db
def test_une_commande_rejetee_rejouee_donne_la_meme_reponse():
    prestation, session, operateur, _ = presentation_demarree()
    identifiant = uuid.uuid4()
    commande(session, "suivante", 1, auteur=operateur, id_commande=identifiant)

    rejeu = commande(session, "suivante", 1, auteur=operateur, id_commande=identifiant)

    assert (rejeu.statut, rejeu.raison) == ("rejetee", "version_obsolete")


@pytest.mark.django_db
def test_un_identifiant_de_commande_d_une_autre_session_est_refuse():
    prestation, session, operateur, _ = presentation_demarree()
    identifiant = uuid.uuid4()
    commande(session, "suivante", 2, auteur=operateur, id_commande=identifiant)
    autre_session = creer_session(session.concours)

    resultat = commande(autre_session, "suivante", 3, auteur=operateur, id_commande=identifiant)

    assert (resultat.statut, resultat.raison) == ("rejetee", "non_autorise")


@pytest.mark.django_db(transaction=True)
def test_rec24_deux_commandes_simultanees_une_seule_est_appliquee():
    prestation, session, operateur, _ = presentation_demarree()
    barriere = threading.Barrier(2)
    resultats = []

    def envoyer():
        try:
            barriere.wait()
            resultats.append(commande(session, "suivante", 2, auteur=operateur))
        finally:
            connection.close()

    fils = [threading.Thread(target=envoyer) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert sorted(r.statut for r in resultats) == ["appliquee", "rejetee"]
    assert EtatPresentation.objects.get().index == 1


# --- Permissions (REC-14) --------------------------------------------------------


@pytest.mark.django_db
def test_rec14_un_responsable_client_ne_commande_pas(tiree):
    prestation, session, _ = tiree
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=session.organisation)

    resultat = commande(session, "preparer", auteur=responsable, prestation=prestation)

    assert (resultat.statut, resultat.raison) == ("rejetee", "non_autorise")
    assert EtatPresentation.objects.count() == 0


@pytest.mark.django_db
def test_rm20_un_operateur_sans_acces_a_la_mission_ne_commande_pas(tiree):
    from apps.clients.models import Mission  # noqa: F401
    from apps.commun.tests.outils import creer_mission
    from apps.utilisateurs.models import AffectationOperateur

    prestation, session, _ = tiree
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=creer_mission(), utilisateur=etranger)

    resultat = commande(session, "preparer", auteur=etranger, prestation=prestation)

    assert (resultat.statut, resultat.raison) == ("rejetee", "non_autorise")


@pytest.mark.django_db
def test_un_utilisateur_anonyme_ne_commande_pas(tiree):
    from django.contrib.auth.models import AnonymousUser

    prestation, session, _ = tiree

    assert commande(session, "preparer", auteur=AnonymousUser(), prestation=prestation).raison == "non_autorise"


@pytest.mark.django_db
def test_une_action_inconnue_est_rejetee():
    prestation, session, operateur, _ = presentation_demarree()

    resultat = commande(session, "exploser", 2, auteur=operateur)

    assert (resultat.statut, resultat.raison) == ("rejetee", "commande_inconnue")


@pytest.mark.django_db
def test_sans_presentation_active_les_commandes_sont_rejetees(tiree):
    _, session, operateur = tiree

    assert commande(session, "demarrer", 0, auteur=operateur).raison == "transition_interdite"


# --- Journal ----------------------------------------------------------------------


@pytest.mark.django_db
def test_toute_commande_est_journalisee_avec_son_auteur_et_le_retour_en_arriere_aussi():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)
    precedente = commande(session, "precedente", 3, auteur=operateur)
    commande(session, "suivante", 1, auteur=operateur)  # rejetée : version obsolète

    journal = list(CommandePresentation.objects.order_by("cree_le").values_list("action", "statut", "raison"))

    assert ("precedente", "appliquee", "") in journal
    assert ("suivante", "rejetee", "version_obsolete") in journal
    assert precedente.etat.index == 0
    assert set(CommandePresentation.objects.values_list("auteur", flat=True)) == {operateur.pk}


# --- RM-25 : diapositive affichée ---------------------------------------------------


@pytest.mark.django_db
def test_rm25_le_tirage_est_marque_des_qu_un_verset_est_affiche():
    prestation, session, operateur, _ = presentation_demarree()
    tirage = Tirage.objects.get(prestation=prestation)
    assert tirage.diapositive_affichee is False  # l'intercalaire ne compte pas

    commande(session, "suivante", 2, auteur=operateur)  # diapositive 1 : premier verset

    tirage.refresh_from_db()
    assert tirage.diapositive_affichee is True
```

**Fichier `apps\presentation\tests\test_instantane.py`**

```python
"""Tests de l'instantané et de sa projection par rôle (protocole §3.1 ; RM-14, D15)."""
import pytest

from apps.concours.models import Epreuve
from apps.presentation import instantane
from apps.presentation.tests.outils import commande, creer_prestation_tiree, operateur_de, presentation_demarree, texte_du_verset


def avancer(session, operateur, version, n):
    for i in range(n):
        version = commande(session, "suivante", version + i, auteur=operateur).version - i
    return version


@pytest.mark.django_db
def test_sans_presentation_active(db):
    from apps.commun.tests.outils import creer_session

    message = instantane.construire_instantane(creer_session(), "operateur")

    assert message["prestation"] is None and message["version"] == 0 and message["diapositive"] is None


@pytest.mark.django_db
def test_presentation_preparee_pas_encore_de_diapositive():
    prestation, epreuve, _ = creer_prestation_tiree()
    operateur = operateur_de(epreuve)
    commande(prestation.session, "preparer", auteur=operateur, prestation=prestation)

    message = instantane.construire_instantane(prestation.session, "operateur")

    assert (message["phase"], message["version"], message["diapositive"]) == ("preparee", 1, None)
    assert message["prestation"]["candidat"] == {
        "numero": prestation.participation.numero_candidat, "prenom": prestation.participation.candidat.prenom,
    }
    assert message["prestation"]["serie"] == "Série 1" and message["instantane"] is True


@pytest.mark.django_db
def test_l_intercalaire_ne_contient_jamais_de_texte_coranique():
    prestation, session, operateur, _ = presentation_demarree()  # diapositive 0 : intercalaire

    message = instantane.construire_instantane(session, "operateur")

    diapositive = message["diapositive"]
    assert diapositive["type"] == "intercalaire_question" and "texte" not in diapositive
    assert diapositive["question"] == {"rang": 1, "total": 2, "libelle": "Sourate 2, versets 3 à 5"}
    assert (diapositive["index"], diapositive["total"]) == (0, 10)


@pytest.mark.django_db
def test_l_operateur_recoit_le_texte_du_corpus_et_la_reference():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)

    diapositive = instantane.construire_instantane(session, "operateur")["diapositive"]

    assert diapositive["type"] == "verset" and diapositive["reference"] == "2:3"
    assert diapositive["segment"] == {"rang": 1, "total": 1}
    assert diapositive["texte"] == texte_du_verset(2, 3)


@pytest.mark.django_db
def test_d15_la_scene_ne_recoit_pas_le_texte_si_l_epreuve_ne_l_affiche_pas():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)
    assert prestation.epreuve.affichage_scene is False  # défaut (D15)

    diapositive = instantane.construire_instantane(session, "scene")["diapositive"]

    assert diapositive["type"] == "verset" and "texte" not in diapositive


@pytest.mark.django_db
def test_la_scene_recoit_le_texte_quand_l_epreuve_l_affiche():
    prestation, session, operateur, _ = presentation_demarree()
    Epreuve.objects.filter(pk=prestation.epreuve_id).update(affichage_scene=True)
    commande(session, "suivante", 2, auteur=operateur)

    diapositive = instantane.construire_instantane(session, "scene")["diapositive"]

    assert diapositive["texte"] == texte_du_verset(2, 3)


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["candidat", "jury", "tirage", ""])
def test_rm14_aucun_autre_role_ne_recoit_de_texte(role):
    prestation, session, operateur, _ = presentation_demarree()
    Epreuve.objects.filter(pk=prestation.epreuve_id).update(affichage_scene=True)
    commande(session, "suivante", 2, auteur=operateur)

    diapositive = instantane.construire_instantane(session, role)["diapositive"]

    assert "texte" not in diapositive


@pytest.mark.django_db
def test_le_rejeu_et_la_version_sont_dans_l_instantane():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "reafficher", 2, auteur=operateur)

    message = instantane.construire_instantane(session, "operateur", instantane=False)

    assert (message["version"], message["rejeu"], message["instantane"]) == (3, 1, False)
```

**Fichier `apps\presentation\services.py`**

```python
"""Commandes de présentation : versionnées, idempotentes, sérialisées (§9.3, §13.5, RM-30 ; REC-24).

Le serveur détient l'état. Une commande n'est appliquée que si elle porte la version courante ; une commande
déjà reçue (même identifiant) n'est jamais appliquée deux fois ; toutes les commandes d'une session passent
sous un verrou : deux « diapositive suivante » simultanées donnent UNE seule application.
"""
from dataclasses import dataclass

from django.db import transaction

from apps.prestations.models import Prestation, Tirage
from apps.presentation import diapositives
from apps.presentation.exceptions import PlanImpossibleError, TransitionInterditeError
from apps.presentation.models import CommandePresentation, EtatPresentation
from apps.presentation.transitions import ACTIONS, Position, appliquer_transition
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

ETATS_PRESTATION = {
    "demarrer": Prestation.Etat.EN_AFFICHAGE,
    "reprendre": Prestation.Etat.EN_AFFICHAGE,
    "pause": Prestation.Etat.EN_PAUSE,
    "terminer": Prestation.Etat.EN_NOTATION,
}
TYPES_AVEC_TEXTE = ("verset", "enonce")


@dataclass
class Resultat:
    """Ce que le serveur répond à une commande (protocole §3.2) : ``statut``, ``raison``, ``version``."""

    statut: str  # « appliquee », « deja_traitee » ou « rejetee »
    version: int
    raison: str = ""
    etat: EtatPresentation | None = None


def peut_commander(utilisateur, session):
    """Seul le personnel du prestataire affecté à la mission commande le diaporama (§6.2, REC-14, RM-20)."""
    if not getattr(utilisateur, "is_authenticated", False) or not utilisateur.is_active:
        return False
    if utilisateur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        return False
    return missions_accessibles(utilisateur).filter(pk=session.concours.mission_id).exists()


def etat_actif(session):
    return EtatPresentation.objects.filter(session=session, active=True).first()


def _version_courante(session):
    actif = etat_actif(session)
    return actif.version if actif else 0


def _journaliser(session, id_commande, action, version_attendue, auteur, statut, raison="", version_apres=None, prestation=None):
    CommandePresentation.objects.create(
        id_commande=id_commande, session=session, prestation=prestation, action=action,
        version_attendue=version_attendue, version_apres=version_apres, statut=statut, raison=raison, auteur=auteur,
    )


def _deja_traitee(session, id_commande):
    """Réponse à une commande déjà reçue, ou ``None`` si elle est nouvelle (idempotence, RM-30)."""
    ancienne = CommandePresentation.objects.filter(id_commande=id_commande).first()
    if ancienne is None:
        return None
    if ancienne.session_id != session.pk:
        return Resultat("rejetee", _version_courante(session), "non_autorise")
    if ancienne.statut == CommandePresentation.Statut.APPLIQUEE:
        return Resultat("deja_traitee", ancienne.version_apres)
    return Resultat("rejetee", _version_courante(session), ancienne.raison)


def appliquer_commande(session, id_commande, action, version_attendue=None, *, auteur, prestation=None):
    """Applique une commande d'affichage et renvoie un ``Resultat``. Ne lève pas pour un refus métier."""
    if not peut_commander(auteur, session):
        return Resultat("rejetee", _version_courante(session), "non_autorise")
    deja = _deja_traitee(session, id_commande)
    if deja is not None:
        return deja

    with transaction.atomic():
        # Verrou de session : toutes les commandes d'une session sont sérialisées (§13.5, REC-24).
        type(session).objects.select_for_update().get(pk=session.pk)
        deja = _deja_traitee(session, id_commande)  # une commande identique a pu passer pendant l'attente
        if deja is not None:
            return deja

        def rejeter(raison):
            _journaliser(session, id_commande, action, version_attendue, auteur,
                         CommandePresentation.Statut.REJETEE, raison, prestation=prestation)
            return Resultat("rejetee", _version_courante(session), raison)

        if action == "preparer":
            return _preparer(session, id_commande, auteur, prestation, rejeter)
        if action not in ACTIONS:
            return rejeter("commande_inconnue")
        etat = etat_actif(session)
        if etat is None:
            return rejeter("transition_interdite")
        if version_attendue != etat.version:
            return rejeter("version_obsolete")
        try:
            position = appliquer_transition(Position(etat.phase, etat.index, etat.rejeu), len(etat.plan), action)
        except TransitionInterditeError:
            return rejeter("transition_interdite")

        etat.phase, etat.index, etat.rejeu = position.phase, position.index, position.rejeu
        etat.version += 1
        etat.save(update_fields=["phase", "index", "rejeu", "version", "modifie_le"])
        _synchroniser_prestation(etat, action)
        _journaliser(session, id_commande, action, version_attendue, auteur,
                     CommandePresentation.Statut.APPLIQUEE, version_apres=etat.version, prestation=etat.prestation)
        return Resultat("appliquee", etat.version, etat=etat)


def _preparer(session, id_commande, auteur, prestation, rejeter):
    """« Préparer l'affichage » : la prestation devient la présentation active de la session (D39, D41)."""
    if prestation is None or prestation.session_id != session.pk:
        return rejeter("transition_interdite")
    actif = etat_actif(session)
    if actif is not None and actif.phase in (EtatPresentation.Phase.AFFICHAGE, EtatPresentation.Phase.PAUSE):
        return rejeter("transition_interdite")  # il faut terminer la présentation en cours
    prestation = Prestation.objects.select_for_update().get(pk=prestation.pk)
    if prestation.etat != Prestation.Etat.TIRE:
        return rejeter("transition_interdite")  # seule une prestation tirée se présente
    try:
        plan = diapositives.construire_plan(prestation)
    except PlanImpossibleError:
        return rejeter("transition_interdite")

    if actif is not None:
        actif.active = False
        actif.save(update_fields=["active", "modifie_le"])
    etat = EtatPresentation.objects.filter(prestation=prestation).first()
    if etat is None:
        etat = EtatPresentation(prestation=prestation, session=session, version=1)
    else:
        etat.version += 1
    etat.active, etat.phase, etat.index, etat.rejeu, etat.plan = True, EtatPresentation.Phase.PREPAREE, None, 0, plan
    etat.save()
    _journaliser(session, id_commande, "preparer", None, auteur,
                 CommandePresentation.Statut.APPLIQUEE, version_apres=etat.version, prestation=prestation)
    return Resultat("appliquee", etat.version, etat=etat)


def _synchroniser_prestation(etat, action):
    """Répercute la commande sur la prestation (§8.3) et sur le tirage dont une diapositive est affichée (RM-25)."""
    prestation = etat.prestation
    nouvel_etat = ETATS_PRESTATION.get(action)
    if nouvel_etat is not None and prestation.etat != nouvel_etat:
        prestation.etat = nouvel_etat
        prestation.save(update_fields=["etat", "modifie_le"])
    if etat.phase == EtatPresentation.Phase.AFFICHAGE and etat.index is not None:
        diapositive = etat.plan[etat.index]
        if diapositive["type"] in TYPES_AVEC_TEXTE:
            # Dès qu'un verset (ou un énoncé) d'une série est affiché, son tirage ne peut plus être réintégré.
            Tirage.objects.filter(prestation=prestation, serie_id=diapositive["serie_id"]).update(diapositive_affichee=True)
```

**Fichier `apps\presentation\instantane.py`**

```python
"""Instantané de l'état de présentation envoyé aux écrans (protocole §3.1), projeté selon le rôle (RM-14).

La projection est faite ICI, côté serveur, avant tout envoi : un écran non autorisé ne reçoit jamais le texte.
"""
from apps.presentation import diapositives
from apps.presentation.services import etat_actif

OPERATEUR, SCENE = "operateur", "scene"


def texte_autorise(role, epreuve):
    """L'opérateur voit toujours le texte ; la scène seulement si l'épreuve l'a activé (D15)."""
    return role == OPERATEUR or (role == SCENE and epreuve.affichage_scene)


def construire_instantane(session, role, *, instantane=True):
    """Le dictionnaire de ``type: "etat"`` pour la session, tel que défini dans le protocole."""
    etat = etat_actif(session)
    message = {"type": "etat", "instantane": instantane, "session": str(session.pk)}
    if etat is None:
        return {**message, "prestation": None, "version": 0, "phase": None, "rejeu": 0, "diapositive": None}

    prestation = etat.prestation
    participation = prestation.participation
    message.update(
        prestation={
            "id": str(prestation.pk),
            "candidat": {"numero": participation.numero_candidat, "prenom": participation.candidat.prenom},
            "epreuve": prestation.epreuve.nom,
            "serie": " · ".join(dict.fromkeys(d["serie"] for d in etat.plan)),
        },
        version=etat.version,
        phase=etat.phase,
        rejeu=etat.rejeu,
        diapositive=None,
    )
    if etat.index is not None:
        brute = etat.plan[etat.index]
        diapositive = {"index": brute["index"], "total": brute["total"], "type": brute["type"]}
        if brute["type"] != "fin_serie":
            diapositive["question"] = {
                "rang": brute["question_rang"], "total": brute["question_total"], "libelle": brute["libelle"],
            }
        if brute["type"] == "verset":
            diapositive["reference"] = brute["reference"]
            diapositive["segment"] = {"rang": brute["segment_rang"], "total": brute["segment_total"]}
        if brute["type"] in ("verset", "enonce") and texte_autorise(role, prestation.epreuve):
            diapositive["texte"] = diapositives.texte_de(brute)
        message["diapositive"] = diapositive
    return message
```

```powershell
pytest apps\presentation
```

Attendu (avec vos règles écrites) : **tout passe**, y compris le test à **deux threads** qui envoie deux « suivante » simultanés : un seul est appliqué.

## Pourquoi un verrou **et** une version ?

La **version** détecte qu'une commande s'appuie sur un état périmé (le double clic de la ligne 2 arrive avec la version 17 alors que l'état est déjà en 18). Le **verrou** garantit que deux commandes réellement simultanées passent l'une après l'autre : sans lui, elles liraient toutes deux « version 17 » et seraient toutes deux appliquées.

## Questions de compréhension

1. Une commande rejetée est-elle journalisée ? Pourquoi ?
2. Qu'arrive-t-il si l'écran renvoie la même commande (même `id`) après une coupure ?
3. Pourquoi la scène ne reçoit-elle pas le texte quand `affichage_scene` est faux, alors que le serveur le connaît ?

<details>
<summary>Réponses</summary>

1. Oui : pour la trace (qui a tenté quoi) et pour que le renvoi d'une commande rejetée donne la même réponse.
2. Le serveur reconnaît l'identifiant et répond `deja_traitee` avec la version obtenue : la commande n'est pas appliquée deux fois, aucune commande n'est perdue.
3. La projection se fait **côté serveur** avant l'envoi : masquer un champ côté navigateur ne protégerait rien (règle absolue n°4).
</details>

## Journal d'apprentissage

Décrivez, pour chaque cas du tableau des transitions que vous avez choisi d'interdire, le problème que cela évite pendant un concours.

## Commit proposé

```text
Itération 3 : état de présentation, commandes versionnées et idempotentes
```
