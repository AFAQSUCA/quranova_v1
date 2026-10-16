# Chapitre 21 — Les évaluations des jurés et leur connexion (itération 4, étapes 4b et 4c)

> **Commit de référence :** `47061de` · **Durée :** 8 à 10 heures · **Résultat :** les jurés notent (brouillon, validation, clôture, corrections approuvées), se connectent avec leur code, et reçoivent le diaporama. **85 tests**.

## Objectif

| Règle | Où elle est appliquée |
|---|---|
| **RM-15** : chaque juré note séparément, seulement ses épreuves | `Evaluation` (juré × prestation), `_verifier_droit_de_noter` |
| **RM-16, REC-12** : une note manquante n'est jamais un zéro | pas de ligne `Note` = manquante ; `0` = une ligne à 0 ; validation refusée si incomplète |
| **§8.3** : saisie dès l'affichage, validation après « Terminer » | `ETATS_DE_SAISIE`, `valider_evaluation` |
| **§14.2** : une évaluation ne se valide que par son juré | `valider_evaluation(jure, prestation)` n'agit que sur l'évaluation de ce juré |
| **REC-17, §10.2** : correction motivée, approuvée par le responsable client | `CorrectionNote`, `demander_correction`, `traiter_correction` |
| **D5** : limitation des essais de code | `ouvrir_connexion` : 5 échecs / 5 minutes / adresse |
| **D46** : jeton long valable autant que le code | `ConnexionJure` |
| **D44** : le juré reçoit le texte, ne commande jamais | rôle `jury` du WebSocket |
| **REC-25** : jamais d'identifiant de juré dans une requête | l'API ne lit que le jeton |

## Ce qu'il faut comprendre

- **Brouillon côté serveur** (REC-23) : chaque saisie est enregistrée ; une tablette redémarrée retrouve ses notes.
- **Code contre jeton** : le code de 8 caractères est facile à saisir mais court ; on limite donc les essais, puis on l'échange contre un jeton de 256 bits dont seule l'empreinte est stockée.
- **Une note validée change par une correction** : le juré demande (motif obligatoire), le responsable du client approuve ; l'ancienne et la nouvelle valeur, l'auteur, l'approbateur et la date sont conservés, et l'opération est journalisée (chapitre 20).

## Étape A — Les évaluations

Ajoutez les exceptions, les modèles `Evaluation`, `Note`, `CorrectionNote` (fichiers complets) puis le service :

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


class EvaluationInterditeError(Exception):
    """Ce juré ne peut pas noter cette prestation maintenant (affectation, état de la prestation, §10, RM-15)."""


class NoteInvalideError(Exception):
    """Une valeur de note est refusée (hors barème, non numérique, critère d'une autre épreuve)."""


class EvaluationIncompleteError(Exception):
    """L'évaluation ne peut pas être validée : il manque des notes (RM-16, REC-12). Jamais converties en zéro."""

    def __init__(self, manquants):
        self.manquants = list(manquants)
        super().__init__("Évaluation incomplète : il manque " + ", ".join(self.manquants) + ".")


class EvaluationValideeError(Exception):
    """Une évaluation validée ne se modifie que par une correction approuvée (§10.2, REC-17)."""


class CorrectionInvalideError(Exception):
    """Une demande ou un traitement de correction est refusé."""


class TropDEssaisError(Exception):
    """Trop de codes erronés depuis cette adresse : la connexion est bloquée un moment (D5, anti force brute)."""

    def __init__(self, attente_secondes):
        self.attente_secondes = attente_secondes
        super().__init__(f"Trop d'essais. Réessayez dans {attente_secondes} secondes.")


class JetonInvalideError(Exception):
    """Jeton de connexion d'un juré inconnu, expiré ou révoqué."""
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


class Evaluation(ModeleDuClient):
    """L'évaluation d'une prestation par UN juré : brouillon, puis validée (§10.2, RM-15 ; D43).

    Les notes sont enregistrées séparément par juré. Une évaluation validée ne change plus que par une
    correction approuvée (``CorrectionNote``).
    """

    PARENTS_CLIENT = ("jure", "prestation")

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        VALIDEE = "validee", "Validée"

    jure = models.ForeignKey(Jure, on_delete=models.PROTECT, related_name="evaluations")
    prestation = models.ForeignKey("prestations.Prestation", on_delete=models.PROTECT, related_name="evaluations")
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    observation = models.TextField(blank=True)
    validee_le = models.DateTimeField(null=True, blank=True)
    # D43 : libellés des séries évaluées, figés à la validation (REC-11 : « le bon tirage »).
    series_evaluees = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "évaluation"
        verbose_name_plural = "évaluations"
        ordering = ["prestation", "jure"]
        constraints = [
            models.UniqueConstraint(fields=["jure", "prestation"], name="evaluation_unique_par_jure_et_prestation"),
            models.CheckConstraint(
                condition=(Q(statut="brouillon", validee_le__isnull=True) | Q(statut="validee", validee_le__isnull=False)),
                name="evaluation_validee_a_une_date",
            ),
        ]

    def __str__(self):
        return f"Évaluation de {self.jure} ({self.get_statut_display()})"


class Note(ModeleDuClient):
    """La valeur d'un critère dans une évaluation.

    RM-16 : une note MANQUANTE n'a pas de ligne ; un ZÉRO est une ligne à 0. On ne confond jamais les deux.
    """

    PARENTS_CLIENT = ("evaluation", "critere")

    evaluation = models.ForeignKey(Evaluation, on_delete=models.PROTECT, related_name="notes")
    critere = models.ForeignKey("concours.CritereNotation", on_delete=models.PROTECT, related_name="notes")
    valeur = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        verbose_name = "note"
        verbose_name_plural = "notes"
        ordering = ["evaluation", "critere__ordre"]
        constraints = [
            models.UniqueConstraint(fields=["evaluation", "critere"], name="note_unique_par_critere"),
            models.CheckConstraint(condition=Q(valeur__gte=0), name="note_positive_ou_nulle"),
        ]

    def __str__(self):
        return f"{self.critere} : {self.valeur}"


class CorrectionNote(ModeleDuClient):
    """Demande motivée de correction d'une note validée, approuvée par le responsable client (§10.2, REC-17).

    Conserve l'ancienne valeur, la nouvelle, l'auteur (le juré), l'approbateur, les dates et le motif.
    """

    PARENTS_CLIENT = ("evaluation", "critere")

    class Statut(models.TextChoices):
        DEMANDEE = "demandee", "Demandée"
        APPROUVEE = "approuvee", "Approuvée"
        REFUSEE = "refusee", "Refusée"

    evaluation = models.ForeignKey(Evaluation, on_delete=models.PROTECT, related_name="corrections")
    critere = models.ForeignKey("concours.CritereNotation", on_delete=models.PROTECT, related_name="+")
    ancienne_valeur = models.DecimalField(max_digits=6, decimal_places=2)
    nouvelle_valeur = models.DecimalField(max_digits=6, decimal_places=2)
    motif = models.TextField()
    demandee_le = models.DateTimeField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.DEMANDEE)
    traitee_par = models.ForeignKey("utilisateurs.Utilisateur", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    traitee_le = models.DateTimeField(null=True, blank=True)
    commentaire_decision = models.TextField(blank=True)

    class Meta:
        verbose_name = "correction de note"
        verbose_name_plural = "corrections de notes"
        ordering = ["demandee_le"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(statut="demandee", traitee_par__isnull=True, traitee_le__isnull=True)
                    | (~Q(statut="demandee") & Q(traitee_par__isnull=False, traitee_le__isnull=False))
                ),
                name="correction_traitee_a_un_auteur_et_une_date",
            ),
            models.UniqueConstraint(
                fields=["evaluation", "critere"], condition=Q(statut="demandee"), name="correction_une_en_attente_par_note"
            ),
        ]

    def __str__(self):
        return f"Correction {self.critere} : {self.ancienne_valeur} → {self.nouvelle_valeur} ({self.get_statut_display()})"


class ConnexionJure(ModeleDuClient):
    """Une tablette de juré connectée : un jeton long (D46), échangé contre le code court, valable autant que lui.

    Seule l'empreinte du jeton est stockée. Le jeton sert à l'API de notation et au WebSocket du diaporama.
    """

    PARENTS_CLIENT = ("acces",)

    acces = models.ForeignKey(CodeAccesJure, on_delete=models.PROTECT, related_name="connexions")
    empreinte = models.CharField(max_length=64, unique=True)
    valide_jusqu_au = models.DateTimeField()
    revoque_le = models.DateTimeField(null=True, blank=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)
    adresse = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "connexion de juré"
        verbose_name_plural = "connexions de jurés"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Connexion de {self.acces.jure}"


class TentativeCode(ModeleDuClient):
    """Un essai de code (réussi ou non), pour limiter les essais d'une même adresse (D5)."""

    PARENTS_CLIENT = ("session",)

    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="+")
    adresse = models.CharField(max_length=64)
    reussie = models.BooleanField()

    class Meta:
        verbose_name = "tentative de code"
        verbose_name_plural = "tentatives de code"
        indexes = [models.Index(fields=["adresse", "cree_le"])]
```

```powershell
python manage.py makemigrations jury
python manage.py migrate
```

Les tests d'abord :

**Fichier `apps\jury\tests\test_evaluations.py`**

```python
"""Tests de l'évaluation par les jurés (§10 ; RM-15, RM-16 ; REC-11, REC-12, REC-17)."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_critere, creer_jure, creer_utilisateur
from apps.jury import evaluations
from apps.jury.exceptions import (
    CorrectionInvalideError,
    EvaluationIncompleteError,
    EvaluationInterditeError,
    EvaluationValideeError,
    NoteInvalideError,
)
from apps.jury.models import AffectationJury, CorrectionNote, Evaluation, Note
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage
from apps.utilisateurs.models import Utilisateur


def poste(etat=Prestation.Etat.EN_NOTATION, jures=1):
    """(prestation, [jurés affectés], [critères]) : 3 critères (maximums 10, 10, 5)."""
    epreuve = creer_epreuve_ouverte(series=2)
    criteres = [creer_critere(epreuve, maximum=m, coefficient=c) for m, c in ((10, 2), (10, 1), (5, 1))]
    liste = []
    for _ in range(jures):
        jure = creer_jure(epreuve.organisation)
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)
        liste.append(jure)
    prestation = creer_prestation(epreuve, etat=etat)
    creer_tirage(prestation, epreuve.lot.series.first())
    return prestation, liste, criteres


def notes_completes(criteres, valeurs=(9, 8, 4)):
    return {str(c.pk): v for c, v in zip(criteres, valeurs)}


def actions():
    return list(EntreeAudit.objects.values_list("action", flat=True))


# --- Brouillon -----------------------------------------------------------------------


@pytest.mark.django_db
def test_rec11_la_note_est_enregistree_pour_le_bon_jure_la_bonne_prestation():
    prestation, (jure1, jure2), criteres = poste(jures=2)

    evaluations.enregistrer_brouillon(jure1, prestation, notes_completes(criteres, (9, 8, 4)))
    evaluations.enregistrer_brouillon(jure2, prestation, notes_completes(criteres, (5, 6, 3)))

    e1, e2 = (Evaluation.objects.get(jure=j, prestation=prestation) for j in (jure1, jure2))
    assert [n.valeur for n in e1.notes.all()] == [Decimal("9"), Decimal("8"), Decimal("4")]
    assert [n.valeur for n in e2.notes.all()] == [Decimal("5"), Decimal("6"), Decimal("3")]
    assert e1.organisation_id == prestation.organisation_id


@pytest.mark.django_db
def test_rec12_une_note_omise_n_est_pas_un_zero():
    prestation, (jure,), criteres = poste()

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 0, str(criteres[1].pk): 7})
    etat = evaluations.etat_evaluation(prestation, evaluation)

    valeurs = {ligne["libelle"]: ligne["valeur"] for ligne in etat["criteres"]}
    assert valeurs[criteres[0].libelle] == Decimal("0")  # un zéro saisi : c'est une note
    assert valeurs[criteres[2].libelle] is None  # une note omise : manquante, pas zéro
    assert etat["manquants"] == [criteres[2].libelle] and etat["complete"] is False
    assert evaluation.notes.count() == 2  # pas de ligne pour la note manquante


@pytest.mark.django_db
def test_effacer_une_note_la_rend_manquante():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[1].pk): None})

    assert evaluation.notes.count() == 2
    assert evaluations.etat_evaluation(prestation, evaluation)["manquants"] == [criteres[1].libelle]


@pytest.mark.django_db
def test_les_criteres_non_cites_ne_changent_pas_et_l_observation_est_gardee():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres), observation="Très bien")

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 7})

    assert evaluation.notes.get(critere=criteres[0]).valeur == Decimal("7")
    assert evaluation.notes.get(critere=criteres[1]).valeur == Decimal("8")
    assert evaluation.observation == "Très bien"


@pytest.mark.django_db
@pytest.mark.parametrize("valeur", ["11", "-1", "abc", "NaN", "Infinity", "7.555", True, "10.01"])
def test_les_valeurs_hors_bareme_ou_invalides_sont_refusees(valeur):
    prestation, (jure,), criteres = poste()

    with pytest.raises(NoteInvalideError):
        evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): valeur})

    assert Note.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("saisie, attendu", [("7,5", "7.50"), ("7.5", "7.50"), (" 8 ", "8.00"), (0, "0.00"), ("10", "10.00")])
def test_les_formats_de_saisie_acceptes(saisie, attendu):
    prestation, (jure,), criteres = poste()

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): saisie})

    assert evaluation.notes.get().valeur == Decimal(attendu)


@pytest.mark.django_db
def test_un_critere_d_une_autre_epreuve_est_refuse():
    prestation, (jure,), _ = poste()
    _, _, autres_criteres = poste()

    with pytest.raises(NoteInvalideError, match="critère"):
        evaluations.enregistrer_brouillon(jure, prestation, {str(autres_criteres[0].pk): 5})


@pytest.mark.django_db
def test_rm15_un_jure_non_affecte_ne_note_pas():
    prestation, _, criteres = poste()
    intrus = creer_jure(prestation.organisation)

    with pytest.raises(EvaluationInterditeError, match="affecté"):
        evaluations.enregistrer_brouillon(intrus, prestation, notes_completes(criteres))


@pytest.mark.django_db
def test_rm20_un_jure_d_un_autre_client_ne_note_pas():
    prestation, _, criteres = poste()

    with pytest.raises(EvaluationInterditeError, match="clients"):
        evaluations.enregistrer_brouillon(creer_jure(), prestation, notes_completes(criteres))


@pytest.mark.django_db
def test_un_jure_inactif_ne_note_pas():
    prestation, (jure,), criteres = poste()
    jure.actif = False
    jure.save()

    with pytest.raises(EvaluationInterditeError, match="inactif"):
        evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))


@pytest.mark.django_db
@pytest.mark.parametrize("etat, permis", [
    (Prestation.Etat.EN_ATTENTE, False), (Prestation.Etat.TIRE, False), (Prestation.Etat.EN_AFFICHAGE, True),
    (Prestation.Etat.EN_PAUSE, True), (Prestation.Etat.EN_NOTATION, True), (Prestation.Etat.CLOTUREE, False),
    (Prestation.Etat.ANNULEE, False),
])
def test_la_saisie_est_possible_des_l_affichage_jusqu_a_la_cloture(etat, permis):
    prestation, (jure,), criteres = poste(etat=etat)

    if permis:
        evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    else:
        with pytest.raises(EvaluationInterditeError):
            evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))


# --- Validation ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_rec12_une_evaluation_incomplete_ne_se_valide_pas_et_signale_ce_qui_manque():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 9})

    with pytest.raises(EvaluationIncompleteError) as erreur:
        evaluations.valider_evaluation(jure, prestation)

    assert erreur.value.manquants == [criteres[1].libelle, criteres[2].libelle]
    assert Evaluation.objects.get().statut == Evaluation.Statut.BROUILLON


@pytest.mark.django_db
def test_valider_sans_rien_avoir_saisi_liste_tous_les_criteres():
    prestation, (jure,), criteres = poste()

    with pytest.raises(EvaluationIncompleteError) as erreur:
        evaluations.valider_evaluation(jure, prestation)

    assert len(erreur.value.manquants) == 3


@pytest.mark.django_db
def test_la_validation_fige_l_evaluation_et_les_series_evaluees_et_est_journalisee():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    evaluation = evaluations.valider_evaluation(jure, prestation)

    assert evaluation.statut == Evaluation.Statut.VALIDEE and evaluation.validee_le is not None
    assert evaluation.series_evaluees == ["Série 1"]  # D43 : REC-11, « le bon tirage »
    assert "evaluation.validee" in actions()


@pytest.mark.django_db
def test_la_validation_n_est_possible_qu_apres_terminer_la_prestation():
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    with pytest.raises(EvaluationInterditeError, match="Terminer"):
        evaluations.valider_evaluation(jure, prestation)


@pytest.mark.django_db
def test_une_evaluation_ne_se_valide_que_par_son_jure():
    prestation, (jure1, jure2), criteres = poste(jures=2)
    evaluations.enregistrer_brouillon(jure1, prestation, notes_completes(criteres))

    with pytest.raises(EvaluationIncompleteError):  # jure2 n'a rien saisi : il ne valide pas l'évaluation de jure1
        evaluations.valider_evaluation(jure2, prestation)

    assert Evaluation.objects.get(jure=jure1).statut == Evaluation.Statut.BROUILLON


@pytest.mark.django_db
def test_une_evaluation_validee_ne_se_modifie_plus_et_ne_se_valide_pas_deux_fois():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)

    with pytest.raises(EvaluationValideeError, match="correction"):
        evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 1})
    with pytest.raises(EvaluationValideeError, match="déjà validée"):
        evaluations.valider_evaluation(jure, prestation)
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("9")


@pytest.mark.django_db
def test_les_contraintes_de_base_une_evaluation_par_jure_et_prestation_note_positive():
    prestation, (jure,), criteres = poste()
    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 5})

    with pytest.raises(IntegrityError), transaction.atomic():
        Evaluation.objects.create(jure=jure, prestation=prestation)
    with pytest.raises(IntegrityError), transaction.atomic():
        Note.objects.filter(pk=evaluation.notes.get().pk).update(valeur=Decimal("-1"))


# --- Suivi et clôture -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_suivi_de_notation_par_jure():
    prestation, (jure1, jure2, jure3), criteres = poste(jures=3)
    evaluations.enregistrer_brouillon(jure1, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure1, prestation)
    evaluations.enregistrer_brouillon(jure2, prestation, {str(criteres[0].pk): 3})

    suivi = {jure.pk: statut for jure, statut in evaluations.statut_notation(prestation)}

    assert suivi == {jure1.pk: "validee", jure2.pk: "brouillon", jure3.pk: "non_commencee"}


@pytest.mark.django_db
def test_l_operateur_cloture_quand_toutes_les_evaluations_sont_validees():
    prestation, (jure1, jure2), criteres = poste(jures=2)
    operateur = creer_utilisateur()
    for jure in (jure1, jure2):
        evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure1, prestation)
    with pytest.raises(EvaluationInterditeError, match="non validées"):
        evaluations.cloturer_prestation(prestation, operateur)

    evaluations.valider_evaluation(jure2, prestation)
    evaluations.cloturer_prestation(prestation, operateur)

    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.CLOTUREE and "prestation.cloturee" in actions()


@pytest.mark.django_db
def test_seul_le_personnel_du_prestataire_cloture():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation)

    with pytest.raises(EvaluationInterditeError, match="prestataire"):
        evaluations.cloturer_prestation(prestation, responsable)


@pytest.mark.django_db
def test_on_ne_cloture_pas_sans_jure_affecte():
    epreuve = creer_epreuve_ouverte(series=1)
    prestation = creer_prestation(epreuve, etat=Prestation.Etat.EN_NOTATION)

    with pytest.raises(EvaluationInterditeError, match="Aucun juré"):
        evaluations.cloturer_prestation(prestation, creer_utilisateur())


# --- Corrections (REC-17) ------------------------------------------------------------------------------


def evaluation_validee():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation)
    return prestation, jure, criteres, responsable


@pytest.mark.django_db
def test_rec17_la_correction_suit_la_procedure_et_laisse_une_trace():
    prestation, jure, criteres, responsable = evaluation_validee()

    correction = evaluations.demander_correction(jure, prestation, criteres[0], "7,5", "Erreur de saisie : 7,5 et non 9.")
    assert correction.statut == CorrectionNote.Statut.DEMANDEE
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("9")  # rien ne change tant que ce n'est pas approuvé

    evaluations.traiter_correction(correction, responsable, True, "Vérifié avec la fiche papier")

    correction.refresh_from_db()
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("7.50")
    assert (correction.ancienne_valeur, correction.nouvelle_valeur) == (Decimal("9"), Decimal("7.50"))
    assert correction.traitee_par == responsable and correction.traitee_le and correction.motif.startswith("Erreur")
    assert "note.correction_demandee" in actions() and "note.corrigee" in actions()
    traitee = EntreeAudit.objects.get(action="note.corrigee")
    assert traitee.auteur == responsable and traitee.details["ancienne"] == "9.00"


@pytest.mark.django_db
def test_une_correction_refusee_ne_change_pas_la_note_mais_est_conservee():
    prestation, jure, criteres, responsable = evaluation_validee()
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 5, "Je me suis trompé")

    evaluations.traiter_correction(correction, responsable, False, "Non justifié")

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.REFUSEE
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("9")
    assert "note.correction_refusee" in actions()


@pytest.mark.django_db
def test_l_operateur_n_approuve_pas_une_correction():
    prestation, jure, criteres, _ = evaluation_validee()
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 5, "Motif")

    with pytest.raises(CorrectionInvalideError, match="responsable"):
        evaluations.traiter_correction(correction, creer_utilisateur(), True)
    with pytest.raises(CorrectionInvalideError):  # le responsable d'un AUTRE client non plus
        evaluations.traiter_correction(correction, creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT), True)

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.DEMANDEE


@pytest.mark.django_db
def test_une_correction_exige_un_motif_une_evaluation_validee_et_une_vraie_difference():
    prestation, jure, criteres, _ = evaluation_validee()

    with pytest.raises(CorrectionInvalideError, match="motif"):
        evaluations.demander_correction(jure, prestation, criteres[0], 5, "  ")
    with pytest.raises(CorrectionInvalideError, match="identique"):
        evaluations.demander_correction(jure, prestation, criteres[0], 9, "Motif")
    with pytest.raises(NoteInvalideError):
        evaluations.demander_correction(jure, prestation, criteres[0], 11, "Hors barème")
    autre_prestation, (autre_jure,), autres_criteres = poste()
    evaluations.enregistrer_brouillon(autre_jure, autre_prestation, notes_completes(autres_criteres))
    with pytest.raises(CorrectionInvalideError, match="validée"):
        evaluations.demander_correction(autre_jure, autre_prestation, autres_criteres[0], 5, "Motif")


@pytest.mark.django_db
def test_une_seule_correction_en_attente_par_note_et_pas_de_double_traitement():
    prestation, jure, criteres, responsable = evaluation_validee()
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 5, "Motif")

    with pytest.raises(CorrectionInvalideError, match="en attente"):
        evaluations.demander_correction(jure, prestation, criteres[0], 4, "Autre motif")
    evaluations.traiter_correction(correction, responsable, True)
    with pytest.raises(CorrectionInvalideError, match="déjà été traitée"):
        evaluations.traiter_correction(correction, responsable, True)
```

**Fichier `apps\jury\evaluations.py`**

```python
"""Évaluation d'une prestation par un juré : brouillon, validation, clôture, corrections (§10 ; RM-15, RM-16 ; REC-11, 12, 17).

Règles clés :
- chaque juré note SEPARÉMENT ; il ne note que les épreuves auxquelles il est affecté (RM-15, §6.3) ;
- la saisie est possible dès que l'affichage a commencé ; la VALIDATION n'est possible qu'après « Terminer la
  prestation » (§8.3) ;
- une note manquante n'est JAMAIS convertie en zéro : l'évaluation est « incomplète » et ne se valide pas (RM-16) ;
- une évaluation validée ne change que par une correction motivée, approuvée par le responsable client (REC-17).
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.jury.exceptions import (
    CorrectionInvalideError,
    EvaluationIncompleteError,
    EvaluationInterditeError,
    EvaluationValideeError,
    NoteInvalideError,
)
from apps.jury.models import AffectationJury, CorrectionNote, Evaluation, Note
from apps.prestations.models import Prestation, Tirage
from apps.utilisateurs.models import Utilisateur

ETATS_DE_SAISIE = (Prestation.Etat.EN_AFFICHAGE, Prestation.Etat.EN_PAUSE, Prestation.Etat.EN_NOTATION)
DEUX_DECIMALES = Decimal("0.01")


def _verifier_droit_de_noter(jure, prestation):
    if not jure.actif:
        raise EvaluationInterditeError("Ce juré est inactif.")
    if jure.organisation_id != prestation.organisation_id:
        raise EvaluationInterditeError("Ce juré et cette prestation appartiennent à deux clients différents (RM-20).")
    if not AffectationJury.objects.filter(jure=jure, epreuve_id=prestation.epreuve_id).exists():
        raise EvaluationInterditeError("Ce juré n'est pas affecté à l'épreuve de cette prestation.")


def _verifier_etat_de_saisie(prestation):
    if prestation.etat not in ETATS_DE_SAISIE:
        raise EvaluationInterditeError(
            "La notation n'est possible qu'à partir du début de l'affichage et jusqu'à la clôture de la prestation."
        )


def lire_valeur(brut, critere):
    """Convertit une saisie en ``Decimal`` dans le barème du critère ; refuse le reste (jamais d'arrondi caché)."""
    if isinstance(brut, bool):
        raise NoteInvalideError(f"« {critere.libelle} » : valeur invalide.")
    try:
        valeur = Decimal(str(brut).strip().replace(",", "."))
    except InvalidOperation:
        raise NoteInvalideError(f"« {critere.libelle} » : « {brut} » n'est pas un nombre.") from None
    if not valeur.is_finite():
        raise NoteInvalideError(f"« {critere.libelle} » : valeur invalide.")
    if valeur != valeur.quantize(DEUX_DECIMALES):
        raise NoteInvalideError(f"« {critere.libelle} » : au plus deux décimales.")
    if valeur < 0 or valeur > critere.maximum:
        raise NoteInvalideError(f"« {critere.libelle} » : la note doit être comprise entre 0 et {format(Decimal(critere.maximum).normalize(), 'f')}.")
    return valeur.quantize(DEUX_DECIMALES)


def _criteres_par_id(prestation):
    return {str(c.pk): c for c in prestation.epreuve.criteres.all()}


def enregistrer_brouillon(jure, prestation, notes=None, observation=None):
    """Enregistre (ou met à jour) le brouillon du juré, côté serveur. ``notes`` : {identifiant du critère : valeur}.

    Une valeur ``None`` ou vide EFFACE la note (elle redevient « manquante », pas zéro). Les critères non cités
    ne changent pas.
    """
    _verifier_droit_de_noter(jure, prestation)
    _verifier_etat_de_saisie(prestation)
    criteres = _criteres_par_id(prestation)
    notes = {str(k): v for k, v in (notes or {}).items()}
    for identifiant in notes:
        if identifiant not in criteres:
            raise NoteInvalideError("Ce critère n'appartient pas à l'épreuve de cette prestation.")
    valeurs = {i: (None if v is None or str(v).strip() == "" else lire_valeur(v, criteres[i])) for i, v in notes.items()}

    with transaction.atomic():
        evaluation, _ = Evaluation.objects.select_for_update().get_or_create(
            jure=jure, prestation=prestation, defaults={"organisation_id": prestation.organisation_id}
        )
        if evaluation.statut == Evaluation.Statut.VALIDEE:
            raise EvaluationValideeError(
                "Cette évaluation est validée : elle ne se modifie que par une demande de correction approuvée."
            )
        for identifiant, valeur in valeurs.items():
            if valeur is None:
                Note.objects.filter(evaluation=evaluation, critere_id=identifiant).delete()
            else:
                Note.objects.update_or_create(
                    evaluation=evaluation, critere=criteres[identifiant],
                    defaults={"valeur": valeur, "organisation_id": prestation.organisation_id},
                )
        if observation is not None:
            evaluation.observation = observation
            evaluation.save(update_fields=["observation", "modifie_le"])
    return evaluation


def etat_evaluation(prestation, evaluation=None):
    """L'état d'une évaluation pour l'écran du juré : une valeur par critère (``None`` = manquante), ce qui manque."""
    notes = {n.critere_id: n.valeur for n in evaluation.notes.all()} if evaluation is not None else {}
    criteres = list(prestation.epreuve.criteres.order_by("ordre"))
    lignes = [
        {"critere": str(c.pk), "libelle": c.libelle, "maximum": c.maximum, "coefficient": c.coefficient,
         "valeur": notes.get(c.pk)}
        for c in criteres
    ]
    manquants = [ligne["libelle"] for ligne in lignes if ligne["valeur"] is None]
    return {
        "statut": evaluation.statut if evaluation is not None else "non_commencee",
        "observation": evaluation.observation if evaluation is not None else "",
        "criteres": lignes,
        "manquants": manquants,
        "complete": not manquants,
    }


def valider_evaluation(jure, prestation):
    """Le juré valide SA propre évaluation (§14.2) : complète, et après « Terminer la prestation » (§8.3)."""
    _verifier_droit_de_noter(jure, prestation)
    with transaction.atomic():
        evaluation = (
            Evaluation.objects.select_for_update().filter(jure=jure, prestation=prestation).first()
        )
        if evaluation is None:
            raise EvaluationIncompleteError(c.libelle for c in prestation.epreuve.criteres.order_by("ordre"))
        if evaluation.statut == Evaluation.Statut.VALIDEE:
            raise EvaluationValideeError("Cette évaluation est déjà validée.")
        prestation = Prestation.objects.get(pk=prestation.pk)
        if prestation.etat != Prestation.Etat.EN_NOTATION:
            raise EvaluationInterditeError(
                "La validation n'est possible qu'après « Terminer la prestation » (la prestation n'est pas en notation)."
            )
        manquants = etat_evaluation(prestation, evaluation)["manquants"]
        if manquants:
            raise EvaluationIncompleteError(manquants)  # RM-16, REC-12 : jamais converties en zéro
        evaluation.statut = Evaluation.Statut.VALIDEE
        evaluation.validee_le = timezone.now()
        evaluation.series_evaluees = [
            t.serie.libelle
            for t in prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang")
        ]
        evaluation.save(update_fields=["statut", "validee_le", "series_evaluees", "modifie_le"])
        journaliser(
            "evaluation.validee", organisation=prestation.organisation, auteur_libelle=f"juré {jure.nom_complet}",
            objet=evaluation, details={"prestation": prestation.pk, "series": evaluation.series_evaluees},
        )
    return evaluation


def statut_notation(prestation):
    """Pour chaque juré affecté : « non_commencee », « brouillon » ou « validee » (suivi de l'opérateur)."""
    evaluations = {e.jure_id: e.statut for e in prestation.evaluations.all()}
    jures = [a.jure for a in AffectationJury.objects.filter(epreuve_id=prestation.epreuve_id, jure__actif=True)
             .select_related("jure").order_by("jure__nom", "jure__prenom")]
    return [(jure, evaluations.get(jure.pk, "non_commencee")) for jure in jures]


def cloturer_prestation(prestation, operateur):
    """L'opérateur clôture la prestation quand TOUTES les évaluations requises sont validées (§8.3 étape 6)."""
    if operateur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        raise EvaluationInterditeError("Seul le personnel du prestataire clôture une prestation.")
    with transaction.atomic():
        prestation = Prestation.objects.select_for_update().get(pk=prestation.pk)
        if prestation.etat != Prestation.Etat.EN_NOTATION:
            raise EvaluationInterditeError("Seule une prestation en notation peut être clôturée.")
        attendus = statut_notation(prestation)
        if not attendus:
            raise EvaluationInterditeError("Aucun juré n'est affecté à cette épreuve : rien ne peut être clôturé.")
        en_attente = [jure.nom_complet for jure, statut in attendus if statut != Evaluation.Statut.VALIDEE]
        if en_attente:
            raise EvaluationInterditeError("Évaluations non validées : " + ", ".join(en_attente) + ".")
        prestation.etat = Prestation.Etat.CLOTUREE
        prestation.save(update_fields=["etat", "modifie_le"])
        journaliser("prestation.cloturee", organisation=prestation.organisation, auteur=operateur, objet=prestation)
    return prestation


# --- Corrections d'une note validée (REC-17) ------------------------------------------------------


def demander_correction(jure, prestation, critere, nouvelle_valeur, motif):
    """Le juré demande, avec un motif, de corriger UNE note de son évaluation validée."""
    _verifier_droit_de_noter(jure, prestation)
    motif = (motif or "").strip()
    if not motif:
        raise CorrectionInvalideError("Un motif est obligatoire pour demander la correction d'une note validée.")
    with transaction.atomic():
        evaluation = Evaluation.objects.select_for_update().filter(jure=jure, prestation=prestation).first()
        if evaluation is None or evaluation.statut != Evaluation.Statut.VALIDEE:
            raise CorrectionInvalideError("Seule une évaluation validée se corrige : modifiez directement votre brouillon.")
        if str(critere.pk) not in _criteres_par_id(prestation):
            raise NoteInvalideError("Ce critère n'appartient pas à l'épreuve de cette prestation.")
        valeur = lire_valeur(nouvelle_valeur, critere)
        note = Note.objects.get(evaluation=evaluation, critere=critere)
        if valeur == note.valeur:
            raise CorrectionInvalideError("La nouvelle valeur est identique à la valeur actuelle.")
        if CorrectionNote.objects.filter(evaluation=evaluation, critere=critere, statut=CorrectionNote.Statut.DEMANDEE).exists():
            raise CorrectionInvalideError("Une correction est déjà en attente pour cette note.")
        correction = CorrectionNote.objects.create(
            evaluation=evaluation, critere=critere, ancienne_valeur=note.valeur, nouvelle_valeur=valeur,
            motif=motif, demandee_le=timezone.now(),
        )
        journaliser(
            "note.correction_demandee", organisation=prestation.organisation, auteur_libelle=f"juré {jure.nom_complet}",
            objet=correction, details={"critere": critere.libelle, "ancienne": note.valeur, "nouvelle": valeur, "motif": motif},
        )
    return correction


def traiter_correction(correction, utilisateur, approuver, commentaire=""):
    """Le responsable client du concerné approuve ou refuse (jamais l'opérateur, RM-18, §6.2)."""
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != correction.organisation_id
    ):
        raise CorrectionInvalideError("Seul le responsable du client concerné peut approuver ou refuser une correction.")
    with transaction.atomic():
        correction = CorrectionNote.objects.select_for_update().select_related("evaluation", "critere").get(pk=correction.pk)
        if correction.statut != CorrectionNote.Statut.DEMANDEE:
            raise CorrectionInvalideError("Cette correction a déjà été traitée.")
        correction.statut = CorrectionNote.Statut.APPROUVEE if approuver else CorrectionNote.Statut.REFUSEE
        correction.traitee_par, correction.traitee_le = utilisateur, timezone.now()
        correction.commentaire_decision = commentaire
        correction.save()
        if approuver:
            Note.objects.filter(evaluation=correction.evaluation, critere=correction.critere).update(
                valeur=correction.nouvelle_valeur
            )
        journaliser(
            "note.corrigee" if approuver else "note.correction_refusee", organisation=correction.organisation,
            auteur=utilisateur, objet=correction,
            details={"critere": correction.critere.libelle, "ancienne": correction.ancienne_valeur,
                     "nouvelle": correction.nouvelle_valeur, "motif": correction.motif, "commentaire": commentaire,
                     "evaluation": correction.evaluation_id},
        )
    return correction
```

```powershell
pytest apps\jury\tests\test_evaluations.py
```

Attendu : `44 passed`.

## Étape B — La connexion du juré

**Fichier `apps\jury\tests\test_connexion.py`**

```python
"""Tests de la connexion des jurés : code contre jeton, limitation des essais (D4, D5, D46)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_jure, creer_session
from apps.jury import connexion, services
from apps.jury.exceptions import CodeInvalideError, JetonInvalideError, TropDEssaisError
from apps.jury.models import ConnexionJure


@pytest.fixture
def poste(db):
    session = creer_session()
    jure = creer_jure(session.organisation)
    acces, code = services.generer_code(jure, session)
    return session, jure, acces, code


@pytest.mark.django_db
def test_un_code_valide_donne_un_jeton_long_non_stocke_en_clair(poste):
    session, jure, acces, code = poste

    conn, jeton = connexion.ouvrir_connexion(code, session, "10.0.0.5")

    assert len(jeton) >= 40 and conn.empreinte != jeton and len(conn.empreinte) == 64
    assert conn.acces == acces and conn.organisation_id == session.organisation_id
    assert conn.valide_jusqu_au == acces.valide_jusqu_au  # D46
    assert not ConnexionJure.objects.filter(empreinte=jeton).exists()


@pytest.mark.django_db
def test_le_jeton_identifie_le_jure_et_note_l_activite(poste):
    session, jure, _, code = poste
    conn, jeton = connexion.ouvrir_connexion(code, session)

    trouvee = connexion.authentifier_jeton(jeton, session)

    assert trouvee.acces.jure == jure
    conn.refresh_from_db()
    assert conn.derniere_activite is not None


@pytest.mark.django_db
@pytest.mark.parametrize("jeton", ["", None, "faux", "a" * 43])
def test_un_jeton_inconnu_est_refuse(poste, jeton):
    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, poste[0])


@pytest.mark.django_db
def test_d46_le_jeton_expire_avec_le_code(poste):
    session, _, acces, code = poste
    _, jeton = connexion.ouvrir_connexion(code, session)

    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, session, maintenant=acces.valide_jusqu_au + timedelta(seconds=1))


@pytest.mark.django_db
def test_un_code_revoque_ou_un_jure_desactive_invalide_le_jeton(poste):
    session, jure, acces, code = poste
    _, jeton = connexion.ouvrir_connexion(code, session)
    services.revoquer_code(acces)
    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, session)

    session2 = creer_session()
    jure2 = creer_jure(session2.organisation)
    _, code2 = services.generer_code(jure2, session2)
    _, jeton2 = connexion.ouvrir_connexion(code2, session2)
    jure2.actif = False
    jure2.save()
    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton2, session2)


@pytest.mark.django_db
def test_un_jeton_d_une_autre_session_est_refuse(poste):
    session, _, _, code = poste
    _, jeton = connexion.ouvrir_connexion(code, session)

    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, creer_session(session.concours))


@pytest.mark.django_db
def test_la_connexion_peut_etre_revoquee(poste):
    session, _, _, code = poste
    conn, jeton = connexion.ouvrir_connexion(code, session)

    connexion.revoquer_connexion(conn)

    with pytest.raises(JetonInvalideError):
        connexion.authentifier_jeton(jeton, session)


@pytest.mark.django_db
def test_d5_apres_cinq_codes_faux_l_adresse_est_bloquee_meme_avec_le_bon_code(poste):
    session, _, _, code = poste
    for _ in range(5):
        with pytest.raises(CodeInvalideError):
            connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")

    with pytest.raises(TropDEssaisError) as erreur:
        connexion.ouvrir_connexion(code, session, "10.0.0.9")

    assert 0 < erreur.value.attente_secondes <= 300


@pytest.mark.django_db
def test_le_blocage_ne_touche_pas_une_autre_adresse_et_se_leve_apres_la_fenetre(poste):
    session, _, _, code = poste
    for _ in range(5):
        with pytest.raises(CodeInvalideError):
            connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")

    connexion.ouvrir_connexion(code, session, "10.0.0.10")  # autre tablette : acceptée
    plus_tard = timezone.now() + timedelta(minutes=6)
    conn, _ = connexion.ouvrir_connexion(code, session, "10.0.0.9", maintenant=plus_tard)  # fenêtre écoulée

    assert conn.adresse == "10.0.0.9"


@pytest.mark.django_db
def test_quatre_codes_faux_ne_bloquent_pas(poste):
    session, _, _, code = poste
    for _ in range(4):
        with pytest.raises(CodeInvalideError):
            connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")

    connexion.ouvrir_connexion(code, session, "10.0.0.9")


@pytest.mark.django_db
def test_les_connexions_reussies_et_les_echecs_sont_journalises_sans_le_code(poste):
    session, jure, _, code = poste
    with pytest.raises(CodeInvalideError):
        connexion.ouvrir_connexion("ZZZZ-ZZZZ", session, "10.0.0.9")
    connexion.ouvrir_connexion(code, session, "10.0.0.9")

    echec = EntreeAudit.objects.get(action="jury.connexion_echouee")
    reussie = EntreeAudit.objects.get(action="jury.connexion")
    assert echec.details["raison"] == "inconnu" and echec.terminal == "10.0.0.9"
    assert reussie.auteur_libelle == f"juré {jure.nom_complet}"
    assert "ZZZZ" not in str(echec.details) and code.replace("-", "") not in str(reussie.details)
```

**Fichier `apps\jury\connexion.py`**

```python
"""Connexion d'un juré : code court contre jeton long, avec limitation des essais (D4, D5, D46, §15).

Le code (8 caractères) est facile à saisir mais court : on limite donc les essais par adresse. Une fois le code
accepté, la tablette reçoit un jeton de 256 bits (stocké sous forme d'empreinte HMAC) valable aussi longtemps
que le code ; c'est lui, et non le code, qui accompagne les requêtes suivantes.
"""
from datetime import timedelta

from django.utils import timezone

from apps.audit.services import journaliser
from apps.commun.jetons import empreinte_du_jeton, fabriquer_jeton
from apps.jury import services
from apps.jury.exceptions import CodeInvalideError, JetonInvalideError, TropDEssaisError
from apps.jury.models import ConnexionJure, TentativeCode

CONTEXTE_JETON = "jure"
ESSAIS_MAXIMUM = 5
FENETRE = timedelta(minutes=5)


def _verifier_limite(session, adresse, maintenant):
    echecs = list(
        TentativeCode.objects.filter(adresse=adresse, reussie=False, cree_le__gte=maintenant - FENETRE).order_by("cree_le")
    )
    if len(echecs) >= ESSAIS_MAXIMUM:
        reste = int((echecs[-ESSAIS_MAXIMUM].cree_le + FENETRE - maintenant).total_seconds()) + 1
        raise TropDEssaisError(max(reste, 1))


def ouvrir_connexion(saisie, session, adresse="", maintenant=None):
    """Échange un code contre un jeton. Renvoie ``(connexion, jeton)`` ; le jeton n'est montré qu'ici."""
    maintenant = maintenant or timezone.now()
    _verifier_limite(session, adresse, maintenant)
    try:
        acces = services.authentifier_par_code(saisie, session, maintenant=maintenant)
    except CodeInvalideError as erreur:
        TentativeCode.objects.create(session=session, adresse=adresse, reussie=False)
        journaliser(
            "jury.connexion_echouee", organisation=session.organisation, terminal=adresse,
            auteur_libelle="code de juré", details={"raison": erreur.raison, "session": session.pk},
        )
        raise
    jeton = fabriquer_jeton()
    connexion = ConnexionJure.objects.create(
        acces=acces, empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), valide_jusqu_au=acces.valide_jusqu_au,
        adresse=adresse, derniere_activite=maintenant,
    )
    TentativeCode.objects.create(session=session, adresse=adresse, reussie=True)
    journaliser(
        "jury.connexion", organisation=session.organisation, terminal=adresse,
        auteur_libelle=f"juré {acces.jure.nom_complet}", objet=connexion, details={"session": session.pk},
    )
    return connexion, jeton


def authentifier_jeton(jeton, session=None, maintenant=None):
    """La connexion correspondant au jeton, ou ``JetonInvalideError`` (message vague)."""
    maintenant = maintenant or timezone.now()
    if not jeton:
        raise JetonInvalideError("Connexion non reconnue.")
    connexion = (
        ConnexionJure.objects.select_related("acces__jure", "acces__session")
        .filter(empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), revoque_le__isnull=True,
                valide_jusqu_au__gt=maintenant)
        .first()
    )
    if (
        connexion is None
        or connexion.acces.revoque_le is not None
        or not connexion.acces.jure.actif
        or (session is not None and connexion.acces.session_id != session.pk)
    ):
        raise JetonInvalideError("Connexion non reconnue.")
    ConnexionJure.objects.filter(pk=connexion.pk).update(derniere_activite=maintenant)
    return connexion


def revoquer_connexion(connexion, maintenant=None):
    connexion.revoque_le = maintenant or timezone.now()
    connexion.save(update_fields=["revoque_le", "modifie_le"])
```

```powershell
pytest apps\jury\tests\test_connexion.py
```

## Étape C — L'API de la tablette

**Fichier `apps\jury\tests\test_api.py`**

```python
"""Tests de l'API du juré (§10.2 ; RM-15, REC-11, REC-12, REC-14, REC-25 ; D5)."""
import json
import uuid

import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_critere, creer_epreuve, creer_jure, creer_session
from apps.jury import connexion, services
from apps.jury.models import AffectationJury, Evaluation, Note
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage


@pytest.fixture
def poste(db):
    """(session, jure, en-têtes, prestation en notation, critères, épreuve)."""
    epreuve = creer_epreuve_ouverte(series=2)
    criteres = [creer_critere(epreuve, maximum=m) for m in (10, 10, 5)]
    session = creer_session(epreuve.categorie.concours)
    jure = creer_jure(epreuve.organisation)
    AffectationJury.objects.create(jure=jure, epreuve=epreuve)
    _, code = services.generer_code(jure, session)
    _, jeton = connexion.ouvrir_connexion(code, session)
    prestation = creer_prestation(epreuve, session=session, etat=Prestation.Etat.EN_NOTATION)
    creer_tirage(prestation, epreuve.lot.series.first())
    return session, jure, {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}, prestation, criteres, epreuve


def url(nom, session, prestation=None):
    args = [session.pk] + ([prestation.pk] if prestation else [])
    return reverse(f"jury:{nom}", args=args)


def put(client, session, prestation, en_tetes, corps):
    return client.put(url("api_evaluation", session, prestation), data=json.dumps(corps), content_type="application/json", **en_tetes)


def post(client, adresse, en_tetes, corps=None):
    return client.post(adresse, data=json.dumps(corps or {}), content_type="application/json", **en_tetes)


# --- Connexion ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_code_donne_un_jeton(client):
    session = creer_session()
    jure = creer_jure(session.organisation)
    _, code = services.generer_code(jure, session)

    reponse = post(client, url("api_connexion", session), {}, {"code": code.lower()})

    corps = reponse.json()
    assert reponse.status_code == 200 and len(corps["jeton"]) >= 40
    assert corps["jure"] == {"prenom": jure.prenom, "nom": jure.nom}


@pytest.mark.django_db
def test_un_code_faux_donne_401_avec_un_message_vague(client):
    session = creer_session()

    reponse = post(client, url("api_connexion", session), {}, {"code": "ZZZZ-ZZZZ"})

    assert reponse.status_code == 401 and reponse.json()["code"] == "code_invalide"
    assert "inconnu" not in reponse.json()["message"].lower()


@pytest.mark.django_db
def test_d5_apres_cinq_essais_faux_429_meme_avec_le_bon_code(client):
    session = creer_session()
    _, code = services.generer_code(creer_jure(session.organisation), session)
    for _ in range(5):
        post(client, url("api_connexion", session), {}, {"code": "ZZZZ-ZZZZ"})

    reponse = post(client, url("api_connexion", session), {}, {"code": code})

    assert reponse.status_code == 429 and reponse.json()["attente_secondes"] > 0


@pytest.mark.django_db
@pytest.mark.parametrize("corps", [{}, {"code": 12}, []])
def test_connexion_requete_invalide(client, corps):
    assert post(client, url("api_connexion", creer_session()), {}, corps).status_code == 400


# --- Authentification ------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("en_tete", [{}, {"HTTP_AUTHORIZATION": "Bearer faux"}, {"HTTP_AUTHORIZATION": "Basic x"}])
def test_sans_jeton_valide_toutes_les_routes_repondent_401(client, poste, en_tete):
    session, _, _, prestation, _, _ = poste

    assert client.get(url("api_prestations", session), **en_tete).status_code == 401
    assert client.get(url("api_evaluation", session, prestation), **en_tete).status_code == 401
    assert post(client, url("api_valider", session, prestation), en_tete).status_code == 401


@pytest.mark.django_db
def test_le_jeton_d_une_session_n_ouvre_pas_une_autre_session(client, poste):
    session, _, en_tetes, _, _, epreuve = poste
    autre = creer_session(session.concours)

    assert client.get(url("api_prestations", autre), **en_tetes).status_code == 401


# --- Prestations et évaluation -----------------------------------------------------------------


@pytest.mark.django_db
def test_la_liste_ne_contient_que_les_prestations_des_epreuves_du_jure(client, poste):
    session, jure, en_tetes, prestation, _, epreuve = poste
    autre_epreuve = creer_epreuve(epreuve.categorie)  # une autre épreuve du même concours, sans ce juré
    creer_prestation(autre_epreuve, session=session, etat=Prestation.Etat.EN_NOTATION)  # épreuve non affectée
    creer_prestation(epreuve, session=session, etat=Prestation.Etat.EN_ATTENTE)  # pas encore affichée

    liste = client.get(url("api_prestations", session), **en_tetes).json()["prestations"]

    assert [p["id"] for p in liste] == [str(prestation.pk)]
    assert liste[0]["evaluation"] == "non_commencee"
    assert "nom" not in liste[0] and liste[0]["prenom"] == prestation.participation.candidat.prenom


@pytest.mark.django_db
def test_rec25_une_prestation_non_affectee_ou_d_une_autre_session_donne_404(client, poste):
    session, _, en_tetes, _, _, _ = poste
    autre_epreuve = creer_epreuve_ouverte(series=1)
    non_affectee = creer_prestation(autre_epreuve, session=creer_session(autre_epreuve.categorie.concours), etat=Prestation.Etat.EN_NOTATION)
    inexistante = type("P", (), {"pk": uuid.uuid4()})()

    assert client.get(url("api_evaluation", session, non_affectee), **en_tetes).status_code == 404
    assert client.get(url("api_evaluation", session, inexistante), **en_tetes).status_code == 404


@pytest.mark.django_db
def test_rec11_rec12_brouillon_serveur_et_note_manquante_distincte_de_zero(client, poste):
    session, jure, en_tetes, prestation, criteres, _ = poste

    reponse = put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): "0", str(criteres[1].pk): "7,5"}, "observation": "RAS"})

    etat = reponse.json()
    valeurs = {c["critere"]: c["valeur"] for c in etat["criteres"]}
    assert reponse.status_code == 200
    assert valeurs[str(criteres[0].pk)] == "0.00"  # un zéro est une note
    assert valeurs[str(criteres[1].pk)] == "7.50"
    assert valeurs[str(criteres[2].pk)] is None  # manquante : null, pas zéro
    assert etat["complete"] is False and etat["manquants"] == [criteres[2].libelle]
    assert etat["observation"] == "RAS" and etat["peut_valider"] is False
    # Le brouillon est côté serveur : un autre appel (tablette redémarrée, REC-23) le retrouve.
    relu = client.get(url("api_evaluation", session, prestation), **en_tetes).json()
    assert relu["criteres"] == etat["criteres"]


@pytest.mark.django_db
def test_une_note_hors_bareme_donne_400(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste

    reponse = put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): "11"}})

    assert reponse.status_code == 400 and reponse.json()["code"] == "note_invalide"
    assert Note.objects.count() == 0


@pytest.mark.django_db
def test_l_api_ne_lit_jamais_d_identifiant_de_jure_dans_le_corps(client, poste):
    """REC-25 : même si le corps désigne un autre juré, seule l'évaluation du juré authentifié est écrite."""
    session, jure, en_tetes, prestation, criteres, epreuve = poste
    autre = creer_jure(epreuve.organisation)
    AffectationJury.objects.create(jure=autre, epreuve=epreuve)

    put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): 5}, "jure": str(autre.pk), "jure_id": autre.pk if False else str(autre.pk)})

    assert Evaluation.objects.get().jure == jure


@pytest.mark.django_db
def test_validation_incomplete_409_avec_la_liste_puis_complete_200(client, poste):
    session, jure, en_tetes, prestation, criteres, _ = poste
    put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): 9}})

    refus = post(client, url("api_valider", session, prestation), en_tetes)
    assert refus.status_code == 409 and refus.json()["code"] == "evaluation_incomplete"
    assert refus.json()["manquants"] == [criteres[1].libelle, criteres[2].libelle]

    complet = put(client, session, prestation, en_tetes, {"notes": {str(criteres[1].pk): 8, str(criteres[2].pk): 4}})
    assert complet.json()["peut_valider"] is True
    ok = post(client, url("api_valider", session, prestation), en_tetes)
    assert ok.status_code == 200 and ok.json()["statut"] == "validee" and ok.json()["peut_saisir"] is False


@pytest.mark.django_db
def test_apres_validation_la_modification_est_refusee_409(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste
    put(client, session, prestation, en_tetes, {"notes": {str(c.pk): 3 for c in criteres}})
    post(client, url("api_valider", session, prestation), en_tetes)

    reponse = put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): 1}})

    assert reponse.status_code == 409 and reponse.json()["code"] == "evaluation_validee"


@pytest.mark.django_db
def test_la_validation_avant_la_fin_de_la_prestation_est_refusee(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste
    Prestation.objects.filter(pk=prestation.pk).update(etat=Prestation.Etat.EN_AFFICHAGE)
    put(client, session, prestation, en_tetes, {"notes": {str(c.pk): 3 for c in criteres}})

    reponse = post(client, url("api_valider", session, prestation), en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "pas_encore"


@pytest.mark.django_db
def test_demande_de_correction_via_l_api(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste
    put(client, session, prestation, en_tetes, {"notes": {str(c.pk): 3 for c in criteres}})
    post(client, url("api_valider", session, prestation), en_tetes)

    reponse = post(client, url("api_correction", session, prestation), en_tetes,
                   {"critere": str(criteres[0].pk), "valeur": "5", "motif": "Erreur de saisie"})
    sans_motif = post(client, url("api_correction", session, prestation), en_tetes, {"critere": str(criteres[1].pk), "valeur": "5", "motif": ""})

    assert reponse.status_code == 201
    assert reponse.json()["corrections"][0]["statut"] == "demandee" and reponse.json()["corrections"][0]["ancienne"] == "3.00"
    assert sans_motif.status_code == 400


@pytest.mark.django_db
def test_les_methodes_non_prevues_sont_refusees(client, poste):
    session, _, en_tetes, prestation, _, _ = poste

    assert client.post(url("api_prestations", session), **en_tetes).status_code == 405
    assert client.get(url("api_valider", session, prestation), **en_tetes).status_code == 405


@pytest.mark.django_db
def test_la_page_du_jure_est_publique_et_vide(client, poste):
    session = poste[0]

    reponse = client.get(reverse("jury:ecran_jury", args=[session.pk]))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200 and 'id="app"' in contenu and "jury.js" in contenu
    assert client.get(reverse("jury:ecran_jury", args=[uuid.uuid4()])).status_code == 404
```

**Fichier `apps\jury\api.py`**

```python
"""API JSON de la tablette du juré (§10.2 ; RM-15, REC-14, REC-25).

Authentification : ``Authorization: Bearer <jeton>`` obtenu en échange du code de session. Aucun cookie, donc aucun
CSRF possible (vues exemptées pour cette raison précise). Le juré identifié par le jeton est le SEUL juré pour
lequel on lit ou on écrit : aucun identifiant de juré n'est jamais lu dans une requête (REC-25).
"""
import json
from decimal import Decimal
from functools import wraps

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.concours.models import CritereNotation, Session
from apps.jury import connexion, evaluations
from apps.jury.exceptions import (
    CodeInvalideError,
    CorrectionInvalideError,
    EvaluationIncompleteError,
    EvaluationInterditeError,
    EvaluationValideeError,
    JetonInvalideError,
    NoteInvalideError,
    TropDEssaisError,
)
from apps.jury.models import AffectationJury, CorrectionNote, Evaluation
from apps.prestations.models import Prestation
from apps.presentation.models import EtatPresentation

ETATS_VISIBLES = (
    Prestation.Etat.EN_AFFICHAGE, Prestation.Etat.EN_PAUSE, Prestation.Etat.EN_NOTATION, Prestation.Etat.CLOTUREE,
)


class _Json(JsonResponse):
    def __init__(self, donnees, statut=200):
        super().__init__(donnees, status=statut, json_dumps_params={"ensure_ascii": False}, encoder=_Encodeur)
        self["Cache-Control"] = "no-store"


class _Encodeur(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return format(o, "f")  # « 7.50 » : jamais de flottant binaire pour une note
        return super().default(o)


def _erreur(statut, code, message, **plus):
    return _Json({"code": code, "message": message, **plus}, statut)


def _corps(request):
    try:
        corps = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return corps if isinstance(corps, dict) else None


def avec_jure(vue):
    """Authentifie le juré par son jeton, pour la session de l'URL ; sinon 401."""

    @wraps(vue)
    def enveloppe(request, session_id, *args, **kwargs):
        session = get_object_or_404(Session.objects.select_related("concours"), pk=session_id)
        en_tete = request.headers.get("Authorization", "")
        jeton = en_tete[7:].strip() if en_tete.startswith("Bearer ") else ""
        try:
            conn = connexion.authentifier_jeton(jeton, session)
        except JetonInvalideError:
            return _erreur(401, "connexion_inconnue", "Connexion non reconnue.")
        return vue(request, session, conn.acces.jure, *args, **kwargs)

    return enveloppe


def _prestation_du_jure(session, jure, prestation_id):
    """La prestation, seulement si elle est de cette session ET d'une épreuve du juré : sinon 404 (REC-25)."""
    prestation = (
        Prestation.objects.select_related("epreuve", "participation__candidat")
        .filter(pk=prestation_id, session=session).first()
    )
    if prestation is None or not AffectationJury.objects.filter(jure=jure, epreuve_id=prestation.epreuve_id).exists():
        raise Http404
    return prestation


@csrf_exempt
@require_http_methods(["POST"])
def ouvrir(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours"), pk=session_id)
    corps = _corps(request)
    if corps is None or not isinstance(corps.get("code"), str):
        return _erreur(400, "requete_invalide", "Requête invalide : un code est attendu.")
    adresse = request.META.get("REMOTE_ADDR", "")
    try:
        conn, jeton = connexion.ouvrir_connexion(corps["code"], session, adresse)
    except TropDEssaisError as erreur:
        return _erreur(429, "trop_d_essais", str(erreur), attente_secondes=erreur.attente_secondes)
    except CodeInvalideError as erreur:
        return _erreur(401, "code_invalide", str(erreur))  # message vague : la raison reste dans le journal
    jure = conn.acces.jure
    return _Json({"jeton": jeton, "jure": {"prenom": jure.prenom, "nom": jure.nom}, "valide_jusqu_au": conn.valide_jusqu_au.isoformat()})


@csrf_exempt
@require_http_methods(["GET"])
@avec_jure
def prestations(request, session, jure):
    affectees = AffectationJury.objects.filter(jure=jure).values_list("epreuve_id", flat=True)
    actif = EtatPresentation.objects.filter(session=session, active=True).values_list("prestation_id", flat=True).first()
    liste = (
        Prestation.objects.filter(session=session, epreuve_id__in=affectees, etat__in=ETATS_VISIBLES)
        .select_related("participation__candidat", "epreuve").order_by("rang_passage")
    )
    statuts = {e.prestation_id: e.statut for e in Evaluation.objects.filter(jure=jure, prestation__in=liste)}
    return _Json({"prestations": [
        {"id": str(p.pk), "rang": p.rang_passage, "numero": p.participation.numero_candidat,
         "prenom": p.participation.candidat.prenom, "epreuve": p.epreuve.nom, "etat": p.etat,
         "evaluation": statuts.get(p.pk, "non_commencee"), "active": p.pk == actif}
        for p in liste
    ]})


def _etat_complet(prestation, jure):
    evaluation = Evaluation.objects.filter(jure=jure, prestation=prestation).first()
    etat = evaluations.etat_evaluation(prestation, evaluation)
    etat["peut_saisir"] = evaluation is None or evaluation.statut == Evaluation.Statut.BROUILLON
    etat["peut_valider"] = (
        etat["peut_saisir"] and etat["complete"] and prestation.etat == Prestation.Etat.EN_NOTATION
    )
    etat["prestation"] = {
        "id": str(prestation.pk), "numero": prestation.participation.numero_candidat,
        "prenom": prestation.participation.candidat.prenom, "epreuve": prestation.epreuve.nom, "etat": prestation.etat,
    }
    etat["corrections"] = [
        {"critere": str(c.critere_id), "ancienne": c.ancienne_valeur, "nouvelle": c.nouvelle_valeur,
         "statut": c.statut, "motif": c.motif}
        for c in (evaluation.corrections.all() if evaluation else [])
    ]
    return etat


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@avec_jure
def evaluation(request, session, jure, prestation_id):
    prestation = _prestation_du_jure(session, jure, prestation_id)
    if request.method == "PUT":
        corps = _corps(request)
        if corps is None or not isinstance(corps.get("notes", {}), dict):
            return _erreur(400, "requete_invalide", "Requête invalide.")
        try:
            evaluations.enregistrer_brouillon(jure, prestation, corps.get("notes"), corps.get("observation"))
        except NoteInvalideError as erreur:
            return _erreur(400, "note_invalide", str(erreur))
        except EvaluationValideeError as erreur:
            return _erreur(409, "evaluation_validee", str(erreur))
        except EvaluationInterditeError as erreur:
            return _erreur(403, "interdit", str(erreur))
    return _Json(_etat_complet(prestation, jure))


@csrf_exempt
@require_http_methods(["POST"])
@avec_jure
def valider(request, session, jure, prestation_id):
    prestation = _prestation_du_jure(session, jure, prestation_id)
    try:
        evaluations.valider_evaluation(jure, prestation)
    except EvaluationIncompleteError as erreur:
        return _erreur(409, "evaluation_incomplete", str(erreur), manquants=erreur.manquants)
    except EvaluationValideeError as erreur:
        return _erreur(409, "evaluation_validee", str(erreur))
    except EvaluationInterditeError as erreur:
        return _erreur(409, "pas_encore", str(erreur))
    return _Json(_etat_complet(prestation, jure))


@csrf_exempt
@require_http_methods(["POST"])
@avec_jure
def correction(request, session, jure, prestation_id):
    prestation = _prestation_du_jure(session, jure, prestation_id)
    corps = _corps(request)
    if corps is None or not isinstance(corps.get("critere"), str):
        return _erreur(400, "requete_invalide", "Requête invalide.")
    critere = CritereNotation.objects.filter(pk=corps["critere"], epreuve=prestation.epreuve).first() if _uuid(corps["critere"]) else None
    if critere is None:
        return _erreur(400, "note_invalide", "Critère inconnu pour cette épreuve.")
    try:
        evaluations.demander_correction(jure, prestation, critere, corps.get("valeur"), corps.get("motif"))
    except (NoteInvalideError, CorrectionInvalideError) as erreur:
        return _erreur(400, "correction_refusee", str(erreur))
    return _Json(_etat_complet(prestation, jure), 201)


def _uuid(texte):
    import uuid

    try:
        uuid.UUID(texte)
        return True
    except ValueError:
        return False
```

**Fichier `apps\jury\views.py`**

```python
"""Page de la tablette du juré : publique et vide ; les données passent par l'API, protégée par le jeton."""
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.concours.models import Session


@require_GET
def ecran_jury(request, session_id):
    get_object_or_404(Session, pk=session_id)
    return render(request, "jury.html", {"session_id": session_id})
```

**Fichier `apps\jury\urls.py`**

```python
from django.urls import path

from apps.jury import api, views

app_name = "jury"

urlpatterns = [
    path("jury/<uuid:session_id>/", views.ecran_jury, name="ecran_jury"),
    path("api/jury/<uuid:session_id>/connexion/", api.ouvrir, name="api_connexion"),
    path("api/jury/<uuid:session_id>/prestations/", api.prestations, name="api_prestations"),
    path("api/jury/<uuid:session_id>/prestations/<uuid:prestation_id>/evaluation/", api.evaluation, name="api_evaluation"),
    path("api/jury/<uuid:session_id>/prestations/<uuid:prestation_id>/evaluation/valider/", api.valider, name="api_valider"),
    path("api/jury/<uuid:session_id>/prestations/<uuid:prestation_id>/evaluation/correction/", api.correction, name="api_correction"),
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
    path("", include("apps.presentation.urls")),
    path("", include("apps.jury.urls")),
    path("", include("apps.resultats.urls")),
]
```

**Fichier `templates\jury.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>QURANOVA — Jury</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="{% static 'frontend/frontend.css' %}">
</head>
<body>
  <div id="app"></div>
  <noscript>Cet écran nécessite JavaScript.</noscript>
  <script type="module" src="{% static 'frontend/jury.js' %}"></script>
</body>
</html>
```

## Étape D — Le rôle « jury » sur le WebSocket

Le consumer accepte un premier message `{"type": "auth", "jeton_jure": "…"}` ; le juré reçoit le texte (D44). Fichiers complets :

**Fichier `apps\presentation\instantane.py`**

```python
"""Instantané de l'état de présentation envoyé aux écrans (protocole §3.1), projeté selon le rôle (RM-14).

La projection est faite ICI, côté serveur, avant tout envoi : un écran non autorisé ne reçoit jamais le texte.
"""
from apps.presentation import diapositives
from apps.presentation.services import etat_actif

OPERATEUR, SCENE, JURY = "operateur", "scene", "jury"


def texte_autorise(role, epreuve):
    """L'opérateur et les jurés voient toujours le texte (D44, §9.1) ; la scène seulement si l'épreuve l'a activé (D15)."""
    return role in (OPERATEUR, JURY) or (role == SCENE and epreuve.affichage_scene)


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

**Fichier `apps\presentation\consumers.py`**

```python
"""Consumer WebSocket de la présentation (§9.4, §13.5 ; protocole : docs/conception/protocole-temps-reel.md).

Un consumer par écran connecté. Il ne détient AUCUN état : l'état est en base, géré par les services. Le
canal ne sert qu'à diffuser vite ; un message perdu se rattrape par l'instantané (numéro de version).

Chaque message reçu est contrôlé (règle absolue n°4) : le rôle est fixé à la connexion et vérifié à chaque
commande, jamais déduit d'une valeur envoyée par le client.
"""
import asyncio
import uuid
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.concours.models import Session
from apps.jury import connexion as connexion_jure
from apps.jury.exceptions import JetonInvalideError as JetonJureInvalideError
from apps.jury.models import CodeAccesJure, ConnexionJure
from apps.prestations import terminaux
from apps.prestations.exceptions import TerminalInvalideError
from apps.prestations.models import Prestation, Terminal
from apps.presentation import instantane, services
from apps.presentation.instantane import JURY, OPERATEUR, SCENE

DELAI_AUTHENTIFICATION_S = 5
SEUIL_PRESENCE = timedelta(seconds=30)

CODE_NON_AUTHENTIFIE, CODE_INTERDIT, CODE_DELAI = 4401, 4403, 4408


def groupe(session_id, role):
    return f"presentation.{session_id}.{role}"


class PresentationConsumer(AsyncJsonWebsocketConsumer):
    role = None
    session = None
    terminal = None
    connexion = None  # connexion d'un juré

    # --- connexion ----------------------------------------------------------------

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session = await self._charger_session()
        await self.accept()
        if self.session is None:
            await self.close(code=CODE_INTERDIT)
            return
        utilisateur = self.scope.get("user")
        if utilisateur is not None and await database_sync_to_async(services.peut_commander)(utilisateur, self.session):
            await self._entrer(OPERATEUR)  # authentifié par son cookie de session Django
            return
        self._attente_auth = asyncio.create_task(self._delai_authentification())

    async def _delai_authentification(self):
        await asyncio.sleep(DELAI_AUTHENTIFICATION_S)
        if self.role is None:
            await self.close(code=CODE_DELAI)

    async def disconnect(self, code):
        tache = getattr(self, "_attente_auth", None)
        if tache is not None:
            tache.cancel()
        if self.role is not None:
            await self.channel_layer.group_discard(groupe(self.session_id, self.role), self.channel_name)

    async def _entrer(self, role):
        self.role = role
        await self.channel_layer.group_add(groupe(self.session_id, role), self.channel_name)
        await self._envoyer_instantane()

    # --- réception ----------------------------------------------------------------

    async def receive_json(self, contenu, **kwargs):
        if not isinstance(contenu, dict) or not isinstance(contenu.get("type"), str):
            await self.send_json({"type": "erreur", "code": "requete_invalide"})
            return
        type_message = contenu["type"]
        if self.role is None:
            if type_message == "auth" and contenu.get("jeton_jure") is not None:
                await self._authentifier_jure(contenu.get("jeton_jure"))
            elif type_message == "auth":
                await self._authentifier(contenu.get("jeton"))
            else:
                await self.close(code=CODE_NON_AUTHENTIFIE)  # rien d'autre avant l'authentification
            return
        if type_message == "ping":
            await self._ping()
        elif type_message == "snapshot":
            await self._envoyer_instantane()
        elif type_message == "commande":
            await self._commande(contenu)
        elif type_message == "auth":
            pass  # déjà authentifié
        else:
            await self.send_json({"type": "erreur", "code": "message_inconnu"})

    async def _authentifier(self, jeton):
        try:
            terminal = await database_sync_to_async(terminaux.authentifier_terminal)(jeton, Terminal.Type.SCENE)
        except TerminalInvalideError:
            await self.close(code=CODE_NON_AUTHENTIFIE)
            return
        if terminal.session_id != self.session.pk:
            await self.close(code=CODE_INTERDIT)  # le jeton d'une autre session ne donne rien ici
            return
        self.terminal = terminal
        tache = getattr(self, "_attente_auth", None)
        if tache is not None:
            tache.cancel()
        await self._entrer(SCENE)

    async def _authentifier_jure(self, jeton):
        """Un juré s'authentifie avec le jeton obtenu en échange de son code (D44, D46) : il reçoit le texte."""
        try:
            conn = await database_sync_to_async(connexion_jure.authentifier_jeton)(jeton, self.session)
        except JetonJureInvalideError:
            await self.close(code=CODE_NON_AUTHENTIFIE)
            return
        self.connexion = conn
        tache = getattr(self, "_attente_auth", None)
        if tache is not None:
            tache.cancel()
        await self._entrer(JURY)

    async def _ping(self):
        if self.terminal is not None or self.connexion is not None:
            await database_sync_to_async(self._noter_activite)()
        await self.send_json({"type": "pong"})
        if self.role == OPERATEUR:
            await self.send_json(await database_sync_to_async(self._ecrans)())

    async def _commande(self, contenu):
        identifiant = contenu.get("id")
        try:
            id_commande = uuid.UUID(str(identifiant))
            action = contenu["action"]
            version = contenu.get("version_attendue")
            if not isinstance(action, str) or not (version is None or (isinstance(version, int) and not isinstance(version, bool))):
                raise ValueError
            prestation_id = uuid.UUID(str(contenu["prestation"])) if contenu.get("prestation") else None
        except (ValueError, KeyError, TypeError):
            await self.send_json({"type": "erreur", "code": "requete_invalide"})
            return
        if self.role != OPERATEUR:
            # REC-14 : un écran de scène ne commande jamais, quoi qu'il envoie.
            await self.send_json({"type": "ack", "id": str(id_commande), "statut": "rejetee",
                                  "raison": "non_autorise", "version": await database_sync_to_async(self._version)()})
            return
        resultat = await database_sync_to_async(self._executer)(id_commande, action, version, prestation_id)
        ack = {"type": "ack", "id": str(id_commande), "statut": resultat.statut, "version": resultat.version}
        if resultat.raison:
            ack["raison"] = resultat.raison
        await self.send_json(ack)
        if resultat.statut == "appliquee":
            await self._diffuser()

    # --- accès à la base (synchrone, dans un thread) --------------------------------

    @database_sync_to_async
    def _charger_session(self):
        return Session.objects.select_related("concours").filter(pk=self.session_id).first()

    def _executer(self, id_commande, action, version, prestation_id):
        prestation = Prestation.objects.filter(pk=prestation_id).first() if prestation_id else None
        return services.appliquer_commande(
            self.session, id_commande, action, version, auteur=self.scope["user"], prestation=prestation
        )

    def _version(self):
        return services._version_courante(self.session)

    def _noter_activite(self):
        if self.terminal is not None:
            Terminal.objects.filter(pk=self.terminal.pk).update(derniere_activite=timezone.now())
        if self.connexion is not None:
            ConnexionJure.objects.filter(pk=self.connexion.pk).update(derniere_activite=timezone.now())

    def _ecrans(self):
        limite = timezone.now() - SEUIL_PRESENCE
        ecrans = [
            {"nom": t.nom, "type": t.type, "connecte": t.derniere_activite is not None and t.derniere_activite >= limite}
            for t in Terminal.objects.filter(session=self.session, type=Terminal.Type.SCENE, revoque_le__isnull=True)
        ]
        jures = {}
        for acces in CodeAccesJure.objects.filter(session=self.session, revoque_le__isnull=True).select_related("jure"):
            actif = acces.connexions.filter(
                revoque_le__isnull=True, derniere_activite__gte=limite
            ).exists()
            jures[acces.jure_id] = {"nom": acces.jure.nom_complet, "connecte": actif}
        return {"type": "ecrans", "ecrans": ecrans, "jures": list(jures.values())}

    def _instantane(self, role, instantane_complet):
        return instantane.construire_instantane(self.session, role, instantane=instantane_complet)

    # --- envois ---------------------------------------------------------------------

    async def _envoyer_instantane(self):
        await self.send_json(await database_sync_to_async(self._instantane)(self.role, True))

    async def _diffuser(self):
        """Après une commande appliquée : chaque rôle reçoit SA projection de l'état (RM-14)."""
        for role in (OPERATEUR, SCENE, JURY):
            message = await database_sync_to_async(self._instantane)(role, False)
            await self.channel_layer.group_send(
                groupe(self.session_id, role), {"type": "diffuser.etat", "message": message}
            )

    async def diffuser_etat(self, evenement):
        await self.send_json(evenement["message"])
```

```powershell
pytest apps\jury apps\presentation
```

## Questions de compréhension

1. Pourquoi une note manquante n'a-t-elle **pas de ligne** plutôt qu'une ligne à `NULL` ?
2. Pourquoi l'API de notation ne lit-elle jamais d'identifiant de juré dans la requête ?
3. Après 5 codes faux, même le **bon** code est refusé pendant un moment. Pourquoi ?

<details>
<summary>Réponses</summary>

1. Pour que « zéro » et « manquante » ne puissent jamais être confondus, même par une somme SQL ou une moyenne qui ignorerait `NULL` : une moyenne sur les lignes existantes ne compte jamais une note qui n'existe pas.
2. Sinon un juré pourrait écrire dans l'évaluation d'un autre (REC-25). Le juré est celui du jeton, point.
3. Parce que sinon un attaquant pourrait tester des codes en boucle : le blocage s'applique à l'adresse, quelle que soit la valeur essayée.
</details>

## Journal d'apprentissage

Décrivez ce qui se passe, du clic de l'opérateur sur « Terminer » jusqu'à la validation de la dernière évaluation et la clôture.

## Commit proposé

```text
Itération 4b-4c : évaluations des jurés, connexion par code, API de notation
```
