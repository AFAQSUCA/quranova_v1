# Chapitre 20 — Le journal d'audit chaîné (itération 4, étape 4a)

> **Commit de référence :** `2d20bb9` · **Durée :** 4 à 5 heures · **Résultat :** un journal **en ajout seul**, à empreintes chaînées, protégé par un déclencheur PostgreSQL, branché sur les opérations sensibles. **33 tests**.

## Objectif

Pouvoir **prouver** ce qui s'est passé pendant un concours (§15.2) : qui a tiré, annulé, importé, validé, et quand. Toutes les étapes suivantes de l'itération 4 (notes, validation du classement, exports) y écriront.

| Règle | Où elle est appliquée |
|---|---|
| **§15.2** : journal en ajout seul, chaque entrée contient l'empreinte de la précédente | `journaliser`, `EntreeAudit` |
| **Détecter une falsification** | `verifier_chaine`, commande `verifier_audit` |
| **D45** : même un accès direct à la base ne peut pas réécrire l'histoire | déclencheur PostgreSQL (migration 0002) |
| **RM-20** : l'extrait d'un client ne contient rien d'un autre | une chaîne **par client** + une chaîne « système » |
| **Pas de tirage sans trace, pas de trace sans tirage** | `journaliser` est appelé **dans la transaction** de l'opération |

## Comment fonctionne une chaîne d'empreintes

Chaque entrée contient l'empreinte SHA-256 de **son propre contenu** et celle de l'**entrée précédente** :

```text
#1  contenu1 + ""        → empreinte1
#2  contenu2 + empreinte1 → empreinte2
#3  contenu3 + empreinte2 → empreinte3
```

Si quelqu'un modifie le contenu de #2, son empreinte recalculée ne correspond plus ; s'il la recalcule aussi, l'entrée #3 (qui contient l'ancienne empreinte2) ne « colle » plus ; s'il supprime une entrée, la numérotation et le chaînage sont rompus ; s'il supprime la **dernière**, la tête de chaîne (numéro et empreinte du registre `ChaineAudit`) ne correspond plus.

Le **verrou** sur la tête de chaîne sérialise les ajouts : deux entrées simultanées ne peuvent pas partir de la même entrée précédente (pas de « fourche »).

## Décisions

| N° | Décision |
|---|---|
| D43 à D46 | Voir `docs\conception\modele-de-donnees.md` : D45 (déclencheur PostgreSQL, une chaîne par client) concerne ce chapitre. |

## Étape A — L'application

```powershell
New-Item -ItemType Directory "apps\audit\tests", "apps\audit\management\commands" -Force | Out-Null
New-Item -ItemType File "apps\audit\__init__.py", "apps\audit\tests\__init__.py", "apps\audit\management\__init__.py", "apps\audit\management\commands\__init__.py" -Force | Out-Null
```

Dans `config\settings\base.py`, ajoutez `"apps.audit",` à `INSTALLED_APPS` (après `apps.presentation`).

## Étape B — Les tests d'abord

**Fichier `apps\audit\tests\test_journal.py`**

```python
"""Tests du journal d'audit : chaînage, ajout seul, détection d'altération (§15.2 ; D45)."""
import threading
from datetime import datetime, timezone

import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit import services
from apps.audit.exceptions import AuditImmuableError
from apps.audit.models import ChaineAudit, EntreeAudit
from apps.commun.tests.outils import creer_organisation, creer_utilisateur

HORLOGE = datetime(2027, 1, 20, 9, 30, tzinfo=timezone.utc)


def ecrire(action="test.action", organisation=None, **champs):
    return services.journaliser(action, organisation=organisation, maintenant=HORLOGE, **champs)


@pytest.fixture
def organisation(db):
    return creer_organisation()


# --- Chaînage ----------------------------------------------------------------------


@pytest.mark.django_db
def test_la_premiere_entree_ouvre_la_chaine(organisation):
    entree = ecrire(organisation=organisation)

    assert entree.numero == 1 and entree.empreinte_precedente == ""
    assert len(entree.empreinte) == 64 and entree.organisation == organisation


@pytest.mark.django_db
def test_chaque_entree_porte_l_empreinte_de_la_precedente(organisation):
    premiere, seconde, troisieme = (ecrire(f"a{i}", organisation=organisation) for i in range(3))

    assert seconde.empreinte_precedente == premiere.empreinte
    assert troisieme.empreinte_precedente == seconde.empreinte
    assert [e.numero for e in (premiere, seconde, troisieme)] == [1, 2, 3]


@pytest.mark.django_db
def test_chaque_client_a_sa_propre_chaine_et_il_y_a_une_chaine_systeme(organisation):
    autre = creer_organisation()
    a1 = ecrire(organisation=organisation)
    b1 = ecrire(organisation=autre)
    systeme = ecrire()

    assert (a1.numero, b1.numero, systeme.numero) == (1, 1, 1)
    assert len({a1.chaine_id, b1.chaine_id, systeme.chaine_id}) == 3
    assert systeme.organisation is None
    assert a1.empreinte != b1.empreinte  # l'organisation entre dans l'empreinte


@pytest.mark.django_db
def test_l_empreinte_est_deterministe(organisation):
    entree = ecrire(organisation=organisation, details={"serie": "Série 4"}, terminal="Tablette 1")

    recalculee = services.calculer_empreinte(
        numero=entree.numero, horodatage=entree.horodatage, auteur_id=None, auteur_libelle="", action=entree.action,
        objet_type="", objet_id="", terminal="Tablette 1", details={"serie": "Série 4"},
        empreinte_precedente="", organisation_id=organisation.pk,
    )
    assert recalculee == entree.empreinte


@pytest.mark.django_db
def test_les_details_sont_normalises_en_json(organisation):
    import uuid

    identifiant = uuid.uuid4()

    entree = ecrire(organisation=organisation, details={"id": identifiant, "n": 3})
    entree.refresh_from_db()

    assert entree.details == {"id": str(identifiant), "n": 3}
    assert services.verifier_chaine(organisation) == []


@pytest.mark.django_db
def test_l_auteur_l_objet_et_le_terminal_sont_enregistres(organisation):
    operateur = creer_utilisateur()

    entree = ecrire("tirage.annule", organisation=organisation, auteur=operateur, objet=organisation, terminal="Tablette 1")

    assert entree.auteur == operateur
    assert (entree.objet_type, entree.objet_id) == ("Organisation", str(organisation.pk))
    assert entree.terminal == "Tablette 1"


@pytest.mark.django_db
def test_un_utilisateur_anonyme_n_est_pas_un_auteur(organisation):
    from django.contrib.auth.models import AnonymousUser

    assert ecrire(organisation=organisation, auteur=AnonymousUser()).auteur is None


@pytest.mark.django_db
def test_une_operation_annulee_n_laisse_pas_d_entree(organisation):
    with pytest.raises(RuntimeError), transaction.atomic():
        ecrire("operation.annulee", organisation=organisation)
        raise RuntimeError("l'opération échoue")

    assert EntreeAudit.objects.count() == 0
    assert ecrire(organisation=organisation).numero == 1  # et la chaîne n'a pas avancé


# --- Ajout seul ----------------------------------------------------------------------


@pytest.mark.django_db
def test_une_entree_ne_se_modifie_pas_par_l_orm(organisation):
    entree = ecrire(organisation=organisation)
    entree.action = "autre"

    with pytest.raises(AuditImmuableError):
        entree.save()


@pytest.mark.django_db
def test_une_entree_ne_se_supprime_pas_par_l_orm(organisation):
    entree = ecrire(organisation=organisation)

    with pytest.raises(AuditImmuableError):
        entree.delete()
    with pytest.raises(AuditImmuableError):
        EntreeAudit.objects.all().delete()
    with pytest.raises(AuditImmuableError):
        EntreeAudit.objects.all().update(action="x")
    assert EntreeAudit.objects.count() == 1


@pytest.mark.django_db
def test_d45_le_declencheur_refuse_un_update_meme_en_sql_direct(organisation):
    ecrire(organisation=organisation)

    with pytest.raises(DatabaseError, match="ajout seul"), transaction.atomic():
        with connection.cursor() as curseur:
            curseur.execute("UPDATE audit_entreeaudit SET action = 'pirate'")


@pytest.mark.django_db
def test_d45_le_declencheur_refuse_un_delete_meme_en_sql_direct(organisation):
    ecrire(organisation=organisation)

    with pytest.raises(DatabaseError, match="ajout seul"), transaction.atomic():
        with connection.cursor() as curseur:
            curseur.execute("DELETE FROM audit_entreeaudit")
    assert EntreeAudit.objects.count() == 1


# --- Vérification de la chaîne ----------------------------------------------------------


def sans_declencheur(curseur):
    """Pour SIMULER une attaque : on désactive le déclencheur (le temps de la transaction du test)."""
    curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # sinon PostgreSQL refuse l'ALTER (contraintes différées en attente)
    curseur.execute("ALTER TABLE audit_entreeaudit DISABLE TRIGGER USER")


@pytest.mark.django_db
def test_une_chaine_intacte_ou_vide_est_valide(organisation):
    assert services.verifier_chaine(organisation) == []
    for i in range(4):
        ecrire(f"a{i}", organisation=organisation)

    assert services.verifier_chaine(organisation) == []


@pytest.mark.django_db
def test_une_entree_modifiee_est_detectee(organisation):
    for i in range(3):
        ecrire(f"a{i}", organisation=organisation)
    with connection.cursor() as curseur:
        sans_declencheur(curseur)
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee' WHERE numero = 2")

    problemes = services.verifier_chaine(organisation)

    assert any("n° 2" in p and "modifié" in p for p in problemes)


@pytest.mark.django_db
def test_une_entree_supprimee_au_milieu_est_detectee(organisation):
    for i in range(4):
        ecrire(f"a{i}", organisation=organisation)
    with connection.cursor() as curseur:
        sans_declencheur(curseur)
        curseur.execute("DELETE FROM audit_entreeaudit WHERE numero = 2")

    problemes = services.verifier_chaine(organisation)

    assert any("manquante" in p for p in problemes)
    assert any("chaînage" in p for p in problemes)


@pytest.mark.django_db
def test_une_suppression_en_fin_de_chaine_est_detectee(organisation):
    for i in range(3):
        ecrire(f"a{i}", organisation=organisation)
    with connection.cursor() as curseur:
        sans_declencheur(curseur)
        curseur.execute("DELETE FROM audit_entreeaudit WHERE numero = 3")

    assert any("disparu" in p for p in services.verifier_chaine(organisation))


@pytest.mark.django_db
def test_une_entree_reecrite_avec_sa_propre_empreinte_est_detectee_par_la_suivante(organisation):
    """Un attaquant malin recalcule l'empreinte de l'entrée qu'il falsifie : la suivante ne colle plus."""
    for i in range(3):
        ecrire(f"a{i}", organisation=organisation)
    falsifiee = EntreeAudit.objects.get(numero=2)
    nouvelle = services.calculer_empreinte(
        numero=2, horodatage=falsifiee.horodatage, auteur_id=None, auteur_libelle="", action="falsifiee",
        objet_type="", objet_id="", terminal="", details={}, empreinte_precedente=falsifiee.empreinte_precedente,
        organisation_id=organisation.pk,
    )
    with connection.cursor() as curseur:
        sans_declencheur(curseur)
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee', empreinte = %s WHERE numero = 2", [nouvelle])

    problemes = services.verifier_chaine(organisation)

    assert any("n° 3" in p and "chaînage" in p for p in problemes)


@pytest.mark.django_db
def test_la_verification_d_un_client_ignore_les_autres(organisation):
    autre = creer_organisation()
    ecrire(organisation=organisation)
    ecrire(organisation=autre)
    with connection.cursor() as curseur:
        sans_declencheur(curseur)
        curseur.execute("UPDATE audit_entreeaudit SET action = 'x' WHERE organisation_id = %s", [autre.pk])

    assert services.verifier_chaine(organisation) == []
    assert services.verifier_chaine(autre) != []


# --- Concurrence --------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_des_ajouts_simultanes_gardent_une_chaine_continue_et_valide():
    organisation = creer_organisation()
    barriere = threading.Barrier(6)

    def ajouter(i):
        try:
            barriere.wait()
            services.journaliser(f"concurrent.{i}", organisation=organisation)
        finally:
            connection.close()

    fils = [threading.Thread(target=ajouter, args=(i,)) for i in range(6)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert sorted(EntreeAudit.objects.values_list("numero", flat=True)) == [1, 2, 3, 4, 5, 6]
    assert services.verifier_chaine(organisation) == []
    assert ChaineAudit.objects.get(organisation=organisation).dernier_numero == 6
```

**Fichier `apps\audit\tests\test_branchements.py`**

```python
"""Les opérations sensibles laissent une trace dans le journal d'audit (§15.2 ; REC-07)."""
import uuid

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import reverse

from apps.audit import services
from apps.audit.models import EntreeAudit
from apps.candidats.importation import importer_candidats
from apps.commun.tests.outils import creer_categorie, creer_concours, creer_utilisateur, configuration_complete, creer_version_validee
from apps.concours import services as services_concours
from apps.presentation.tests.outils import commande, creer_prestation_tiree, operateur_de, presentation_demarree
from apps.prestations import services as services_prestations
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import Utilisateur


def entrees(action):
    return list(EntreeAudit.objects.filter(action=action))


# --- Tirage et annulation ------------------------------------------------------------


@pytest.mark.django_db
def test_un_tirage_est_journalise_avec_la_serie_le_terminal_et_le_candidat():
    epreuve = creer_epreuve_ouverte(series=3)
    prestation = creer_prestation(epreuve)

    tirage = services_prestations.effectuer_tirage(prestation, uuid.uuid4(), terminal="Tablette 1")

    (entree,) = entrees("tirage.effectue")
    assert entree.organisation == epreuve.organisation and entree.terminal == "Tablette 1"
    assert entree.objet_type == "Tirage" and entree.objet_id == str(tirage.pk)
    assert entree.details["serie"] == tirage.serie.libelle and entree.details["rang"] == 1
    assert entree.details["candidat"] == prestation.participation.numero_candidat
    assert services.verifier_chaine(epreuve.organisation) == []


@pytest.mark.django_db
def test_rec07_une_demande_rejouee_ne_journalise_qu_une_fois():
    prestation = creer_prestation(creer_epreuve_ouverte(series=3))
    demande = uuid.uuid4()

    services_prestations.effectuer_tirage(prestation, demande)
    services_prestations.effectuer_tirage(prestation, demande)

    assert len(entrees("tirage.effectue")) == 1


@pytest.mark.django_db
def test_un_tirage_refuse_ne_laisse_aucune_trace():
    epreuve = creer_epreuve_ouverte(series=0)  # lot vide : tirage bloqué

    with pytest.raises(Exception):
        services_prestations.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())

    assert EntreeAudit.objects.count() == 0


@pytest.mark.django_db
def test_l_annulation_est_journalisee_avec_son_auteur_et_son_motif():
    epreuve = creer_epreuve_ouverte(series=2)
    tirage = services_prestations.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())
    operateur = creer_utilisateur()

    services_prestations.annuler_tirage(tirage, operateur, "Erreur d'appel du candidat")

    (entree,) = entrees("tirage.annule")
    assert entree.auteur == operateur and entree.details["motif"] == "Erreur d'appel du candidat"
    assert entree.details["diapositive_affichee"] is False


# --- Diaporama ------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_retour_a_la_diapositive_precedente_est_journalise_mais_pas_suivante():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)
    assert entrees("diaporama.precedente") == []

    commande(session, "precedente", 3, auteur=operateur)

    (entree,) = entrees("diaporama.precedente")
    assert entree.auteur == operateur and entree.objet_id == str(prestation.pk)
    assert entree.details == {"version": 4, "diapositive": 0}


@pytest.mark.django_db
def test_une_commande_rejetee_n_est_pas_journalisee_comme_un_retour_en_arriere():
    prestation, session, operateur, _ = presentation_demarree()

    commande(session, "precedente", 2, auteur=operateur)  # première diapositive : interdit

    assert entrees("diaporama.precedente") == []


# --- Import, configuration -----------------------------------------------------------------


def csv(chemin, lignes):
    chemin.write_text("nom;prenom;categorie\n" + "".join(f"{n};{p};Juniors\n" for n, p in lignes), encoding="utf-8")
    return chemin


@pytest.mark.django_db
def test_un_import_reel_est_journalise_une_simulation_non(tmp_path):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    fichier = csv(tmp_path / "candidats.csv", [("Diallo", "Awa"), ("Koné", "Ali")])

    importer_candidats(concours, fichier, simuler=True)
    assert entrees("candidats.importes") == []
    importer_candidats(concours, fichier, auteur=creer_utilisateur())

    (entree,) = entrees("candidats.importes")
    assert entree.details == {"fichier": "candidats.csv", "lignes": 2, "inscrits": 2}
    assert entree.objet_id == str(concours.pk)


@pytest.mark.django_db
def test_un_import_refuse_ne_laisse_aucune_trace(tmp_path):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")

    importer_candidats(concours, csv(tmp_path / "x.csv", [("", "Awa")]))

    assert entrees("candidats.importes") == []


@pytest.mark.django_db
def test_la_validation_de_la_configuration_et_l_ouverture_sont_journalisees():
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)
    from apps.commun.tests.outils import creer_mission

    concours = configuration_complete(creer_concours(creer_mission(responsable.organisation), version_corpus=creer_version_validee()))

    services_concours.valider_configuration(concours, responsable)
    services_concours.ouvrir_concours(concours)

    (validation,) = entrees("concours.configuration_validee")
    assert validation.auteur == responsable and validation.details["empreinte"] == concours.configuration_empreinte
    assert len(entrees("concours.ouvert")) == 1


# --- Connexions ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_connexion_est_journalisee(client):
    operateur = creer_utilisateur(is_staff=True)
    operateur.set_password("mot-de-passe-solide-42")
    operateur.save()

    client.login(username=operateur.username, password="mot-de-passe-solide-42")

    (entree,) = entrees("connexion")
    assert entree.auteur == operateur and entree.details == {"role": "operateur"}
    assert entree.organisation is None  # le personnel du prestataire n'appartient à aucun client


@pytest.mark.django_db
def test_la_connexion_d_un_responsable_client_va_dans_la_chaine_de_son_client(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    responsable.set_password("mot-de-passe-solide-42")
    responsable.save()

    client.login(username=responsable.username, password="mot-de-passe-solide-42")

    assert entrees("connexion")[0].organisation == responsable.organisation


# --- Commande de vérification et administration -----------------------------------------------------


@pytest.mark.django_db
def test_la_commande_verifier_audit_signale_une_chaine_intacte():
    from io import StringIO

    services.journaliser("a")
    sortie = StringIO()

    call_command("verifier_audit", stdout=sortie)

    assert "aucune anomalie" in sortie.getvalue()


@pytest.mark.django_db
def test_la_commande_verifier_audit_echoue_si_le_journal_est_altere():
    services.journaliser("a")
    services.journaliser("b")
    with connection.cursor() as curseur:
        curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        curseur.execute("ALTER TABLE audit_entreeaudit DISABLE TRIGGER USER")
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee' WHERE numero = 1")

    with pytest.raises(CommandError, match="ALTÉRÉ"):
        call_command("verifier_audit")


@pytest.mark.django_db
def test_l_administration_consulte_le_journal_sans_pouvoir_l_ecrire(client):
    services.journaliser("a")
    client.force_login(Utilisateur.objects.create_superuser("admin-audit", password="x"))
    entree = EntreeAudit.objects.get(action="a")

    assert client.get(reverse("admin:audit_entreeaudit_changelist")).status_code == 200
    assert client.get(reverse("admin:audit_entreeaudit_change", args=[entree.pk])).status_code == 200
    assert client.get(reverse("admin:audit_entreeaudit_add")).status_code == 403
    assert client.post(reverse("admin:audit_entreeaudit_delete", args=[entree.pk]), {"post": "yes"}).status_code == 403
```

## Étape C — Le code

**Fichier `apps\audit\apps.py`**

```python
from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Journal d'audit"

    def ready(self):
        from apps.audit import signaux  # noqa: F401  (branche l'enregistrement des connexions)
```

**Fichier `apps\audit\exceptions.py`**

```python
"""Erreurs de l'application audit."""


class AuditImmuableError(Exception):
    """Une entrée du journal d'audit ne se modifie ni ne se supprime jamais (§15.2)."""
```

**Fichier `apps\audit\models.py`**

```python
"""Journal d'audit en ajout seul, à empreinte chaînée (§15.2, §14.1).

Chaque entrée porte l'empreinte SHA-256 de la précédente de sa chaîne : modifier ou supprimer une entrée
passée casse toute la suite, et ``verifier_chaine`` le détecte. Il y a une chaîne PAR CLIENT (RM-20 : l'extrait
remis à un client ne contient rien d'un autre) et une chaîne « système » pour ce qui ne dépend d'aucun client.
Un déclencheur PostgreSQL (migration 0002) refuse en plus tout UPDATE ou DELETE, même hors de Django (D45).
"""
import uuid

from django.db import models
from django.db.models import Q

from apps.audit.exceptions import AuditImmuableError


class QuerySetAjoutSeul(models.QuerySet):
    """Refuse aussi les modifications en masse, qui contourneraient ``save`` et ``delete``."""

    def update(self, **kwargs):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : aucune modification.")

    def delete(self):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : aucune suppression.")

    def bulk_update(self, *args, **kwargs):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : aucune modification.")


class ChaineAudit(models.Model):
    """La tête d'une chaîne : numéro et empreinte de sa dernière entrée. Verrouillée à chaque ajout."""

    organisation = models.ForeignKey(
        "clients.Organisation", null=True, on_delete=models.PROTECT, related_name="+",
        help_text="Vide pour la chaîne « système ».",
    )
    dernier_numero = models.PositiveIntegerField(default=0)
    derniere_empreinte = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "chaîne d'audit"
        verbose_name_plural = "chaînes d'audit"
        constraints = [
            models.UniqueConstraint(fields=["organisation"], condition=Q(organisation__isnull=False), name="chaine_une_par_organisation"),
            models.UniqueConstraint(fields=["organisation"], condition=Q(organisation__isnull=True), name="chaine_systeme_unique"),
        ]

    def __str__(self):
        return f"Chaîne {self.organisation or 'système'} (n° {self.dernier_numero})"


class EntreeAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chaine = models.ForeignKey(ChaineAudit, on_delete=models.PROTECT, related_name="entrees")
    organisation = models.ForeignKey(
        "clients.Organisation", null=True, on_delete=models.PROTECT, related_name="entrees_audit", db_index=True
    )
    numero = models.PositiveIntegerField()
    horodatage = models.DateTimeField()
    auteur = models.ForeignKey("utilisateurs.Utilisateur", null=True, on_delete=models.PROTECT, related_name="+")
    # Pour ce qui n'a pas de compte : « juré Awa Diallo », « terminal Tablette 1 », « commande importer_candidats »…
    auteur_libelle = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=60)
    objet_type = models.CharField(max_length=60, blank=True)
    objet_id = models.CharField(max_length=64, blank=True)
    terminal = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict)
    empreinte_precedente = models.CharField(max_length=64, blank=True)
    empreinte = models.CharField(max_length=64)

    objects = QuerySetAjoutSeul.as_manager()

    class Meta:
        verbose_name = "entrée d'audit"
        verbose_name_plural = "entrées d'audit"
        ordering = ["chaine", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["chaine", "numero"], name="audit_numero_unique_par_chaine"),
            models.UniqueConstraint(fields=["empreinte"], name="audit_empreinte_unique"),
        ]
        indexes = [models.Index(fields=["organisation", "action"]), models.Index(fields=["objet_type", "objet_id"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditImmuableError("Le journal d'audit est en ajout seul : une entrée ne se modifie pas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : une entrée ne se supprime pas.")

    def __str__(self):
        return f"#{self.numero} {self.action}"
```

**Fichier `apps\audit\services.py`**

```python
"""Écriture et vérification du journal d'audit (§15.2).

``journaliser`` doit être appelé DANS la transaction de l'opération qu'il trace : si l'opération est annulée,
son entrée l'est aussi ; si elle réussit, l'entrée existe. Le verrou sur la tête de chaîne sérialise les ajouts :
la chaîne n'a jamais de fourche.
"""
import hashlib
import json
from datetime import timezone as fuseau_utc

from django.db import transaction
from django.utils import timezone

from apps.audit.models import ChaineAudit, EntreeAudit


def _normaliser(details):
    """Ce qui sera stocké ET haché : uniquement des types JSON (un UUID devient une chaîne)."""
    return json.loads(json.dumps(details or {}, default=str, ensure_ascii=False))


def calculer_empreinte(*, numero, horodatage, auteur_id, auteur_libelle, action, objet_type, objet_id,
                       terminal, details, empreinte_precedente, organisation_id):
    contenu = {
        "numero": numero,
        "horodatage": horodatage.astimezone(fuseau_utc.utc).isoformat(),
        "organisation": str(organisation_id) if organisation_id else "",
        "auteur": str(auteur_id) if auteur_id else "",
        "auteur_libelle": auteur_libelle,
        "action": action,
        "objet_type": objet_type,
        "objet_id": objet_id,
        "terminal": terminal,
        "details": details,
        "precedente": empreinte_precedente,
    }
    texte = json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _chaine_verrouillee(organisation):
    """La tête de chaîne, créée au premier ajout, puis verrouillée jusqu'à la fin de la transaction."""
    organisation_id = organisation.pk if organisation is not None else None
    ChaineAudit.objects.get_or_create(organisation_id=organisation_id)
    return ChaineAudit.objects.select_for_update().get(organisation_id=organisation_id)


def journaliser(action, *, organisation=None, auteur=None, auteur_libelle="", objet=None, terminal="",
                details=None, maintenant=None):
    """Ajoute une entrée à la chaîne du client (ou à la chaîne « système » sans organisation)."""
    if auteur is not None and not getattr(auteur, "is_authenticated", False):
        auteur = None  # un utilisateur anonyme n'est pas un auteur
    details = _normaliser(details)
    objet_type = type(objet).__name__ if objet is not None else ""
    objet_id = str(objet.pk) if objet is not None else ""
    with transaction.atomic():
        chaine = _chaine_verrouillee(organisation)
        numero = chaine.dernier_numero + 1
        horodatage = maintenant or timezone.now()
        champs = dict(
            numero=numero, horodatage=horodatage, auteur_id=auteur.pk if auteur else None,
            auteur_libelle=auteur_libelle, action=action, objet_type=objet_type, objet_id=objet_id,
            terminal=terminal, details=details, empreinte_precedente=chaine.derniere_empreinte,
            organisation_id=organisation.pk if organisation is not None else None,
        )
        empreinte = calculer_empreinte(**champs)
        entree = EntreeAudit.objects.create(chaine=chaine, empreinte=empreinte, **champs)
        chaine.dernier_numero, chaine.derniere_empreinte = numero, empreinte
        chaine.save(update_fields=["dernier_numero", "derniere_empreinte"])
    return entree


def verifier_chaine(organisation=None):
    """Contrôle toute une chaîne ; renvoie la liste des problèmes (vide si elle est intacte).

    Détecte une entrée modifiée (empreinte recalculée différente), une entrée supprimée (trou dans les numéros
    ou dans le chaînage), un chaînage altéré, et une suppression en fin de chaîne (la tête ne correspond plus).
    """
    organisation_id = organisation.pk if organisation is not None else None
    chaine = ChaineAudit.objects.filter(organisation_id=organisation_id).first()
    if chaine is None:
        return []
    problemes = []
    attendu_numero, attendue_precedente = 1, ""
    derniere = None
    for entree in EntreeAudit.objects.filter(chaine=chaine).order_by("numero"):
        if entree.numero != attendu_numero:
            problemes.append(f"Entrée manquante avant le n° {entree.numero} (attendu : {attendu_numero}).")
            attendu_numero = entree.numero
        if entree.empreinte_precedente != attendue_precedente:
            problemes.append(f"Entrée n° {entree.numero} : le chaînage ne correspond pas à l'entrée précédente.")
        recalculee = calculer_empreinte(
            numero=entree.numero, horodatage=entree.horodatage, auteur_id=entree.auteur_id,
            auteur_libelle=entree.auteur_libelle, action=entree.action, objet_type=entree.objet_type,
            objet_id=entree.objet_id, terminal=entree.terminal, details=entree.details,
            empreinte_precedente=entree.empreinte_precedente, organisation_id=entree.organisation_id,
        )
        if recalculee != entree.empreinte:
            problemes.append(f"Entrée n° {entree.numero} : son contenu a été modifié.")
        attendu_numero += 1
        attendue_precedente = entree.empreinte
        derniere = entree
    dernier_numero = derniere.numero if derniere else 0
    dernier_empreinte = derniere.empreinte if derniere else ""
    if (chaine.dernier_numero, chaine.derniere_empreinte) != (dernier_numero, dernier_empreinte):
        problemes.append("La fin de la chaîne ne correspond pas à son registre : des entrées ont disparu.")
    return problemes
```

**Fichier `apps\audit\signaux.py`**

```python
"""Enregistre les connexions des utilisateurs dans le journal d'audit (§15.2)."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.audit.services import journaliser


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    adresse = request.META.get("REMOTE_ADDR", "") if request is not None else ""
    journaliser(
        "connexion", organisation=getattr(user, "organisation", None), auteur=user,
        objet=user, terminal=adresse, details={"role": user.role},
    )
```

**Fichier `apps\audit\admin.py`**

```python
"""Le journal d'audit se consulte ; il ne s'écrit que par ``journaliser`` (§15.2)."""
from django.contrib import admin

from apps.audit.models import EntreeAudit
from apps.commun.admin import ConsultationSeule


@admin.register(EntreeAudit)
class EntreeAuditAdmin(ConsultationSeule):
    list_display = ("numero", "horodatage", "action", "auteur", "auteur_libelle", "objet_type", "terminal")
    list_filter = ("action", "organisation")
    search_fields = ("action", "objet_id", "auteur_libelle")
    date_hierarchy = "horodatage"
```

**Fichier `apps\audit\management\commands\verifier_audit.py`**

```python
"""Commande : vérifie l'intégrité des chaînes du journal d'audit (§15.2)."""
from django.core.management.base import BaseCommand, CommandError

from apps.audit.models import ChaineAudit
from apps.audit.services import verifier_chaine


class Command(BaseCommand):
    help = "Vérifie les empreintes chaînées du journal d'audit, chaîne par chaîne."

    def handle(self, *args, **options):
        total, anomalies = 0, []
        for chaine in ChaineAudit.objects.select_related("organisation").order_by("organisation__nom"):
            problemes = verifier_chaine(chaine.organisation)
            total += 1
            self.stdout.write(f"{chaine.organisation or 'Système'} : {chaine.dernier_numero} entrée(s), "
                              f"{'intacte' if not problemes else str(len(problemes)) + ' problème(s)'}")
            anomalies += [f"{chaine.organisation or 'Système'} : {p}" for p in problemes]
        if anomalies:
            raise CommandError("Journal d'audit ALTÉRÉ :\n" + "\n".join(anomalies))
        self.stdout.write(self.style.SUCCESS(f"{total} chaîne(s) vérifiée(s) : aucune anomalie."))
```

```powershell
python manage.py makemigrations audit
```

Puis créez à la main la migration du déclencheur, `apps\audit\migrations\0002_ajout_seul.py` :

**Fichier `apps\audit\migrations\0002_ajout_seul.py`**

```python
"""D45 : un déclencheur PostgreSQL interdit tout UPDATE et tout DELETE sur le journal d'audit.

Même un accès direct à la base (psql, un script, une erreur de développeur) ne peut pas réécrire l'histoire.
Pas de déclencheur TRUNCATE : Django vide les tables entre deux tests avec TRUNCATE ; la disparition d'entrées
est de toute façon détectée par ``verifier_chaine`` (la tête de chaîne ne correspond plus).
"""
from django.db import migrations

CREER = """
CREATE FUNCTION audit_interdire_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Le journal d''audit est en ajout seul : % interdit.', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_entreeaudit_ajout_seul
    BEFORE UPDATE OR DELETE ON audit_entreeaudit
    FOR EACH ROW EXECUTE FUNCTION audit_interdire_modification();
"""

SUPPRIMER = """
DROP TRIGGER IF EXISTS audit_entreeaudit_ajout_seul ON audit_entreeaudit;
DROP FUNCTION IF EXISTS audit_interdire_modification();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(CREER, reverse_sql=SUPPRIMER)]
```

```powershell
python manage.py migrate
```

> **Pourquoi pas de déclencheur TRUNCATE ?** Entre deux tests, Django vide les tables avec `TRUNCATE` : un déclencheur le bloquerait. La disparition d'entrées est de toute façon détectée par la tête de chaîne.

## Étape D — Brancher les opérations sensibles

Les appels à `journaliser` sont ajoutés **dans** les services existants, à l'intérieur de leur transaction. Fichiers complets à ce stade :

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

from apps.audit.services import journaliser
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
        # Dans la même transaction : pas de tirage sans trace, pas de trace sans tirage (§15.2).
        journaliser(
            "tirage.effectue", organisation=prestation.organisation, objet=tirage,
            auteur_libelle=f"terminal {terminal}" if terminal else "", terminal=terminal,
            details={"prestation": prestation.pk, "candidat": prestation.participation.numero_candidat,
                     "serie": serie.libelle, "rang": tirage.rang},
        )
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
        journaliser(
            "tirage.annule", organisation=tirage.organisation, auteur=auteur, objet=tirage,
            details={"prestation": prestation.pk, "serie": tirage.serie.libelle, "motif": motif,
                     "diapositive_affichee": tirage.diapositive_affichee},
        )
        # Il manque désormais un tirage valide : la prestation attend de nouveau son tirage.
        prestation.etat = Prestation.Etat.EN_ATTENTE
        prestation.save(update_fields=["etat", "modifie_le"])
    return tirage
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

from apps.audit.services import journaliser
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
        if action == "precedente":  # §15.2 : un retour en arrière est une opération sensible
            journaliser(
                "diaporama.precedente", organisation=session.organisation, auteur=auteur, objet=etat.prestation,
                details={"version": etat.version, "diapositive": etat.index},
            )
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

from apps.audit.services import journaliser
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


def importer_candidats(concours, chemin, *, simuler=False, auteur=None):
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
        else:
            journaliser(
                "candidats.importes", organisation=concours.organisation, auteur=auteur, objet=concours,
                auteur_libelle="" if auteur else "commande importer_candidats",
                details={"fichier": str(chemin).replace("\\", "/").rsplit("/", 1)[-1],
                         "lignes": rapport.lignes_lues, "inscrits": len(rapport.inscriptions)},
            )
    return rapport
```

**Fichier `apps\concours\services.py`**

```python
"""Règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31)."""
import hashlib
import json

from django.utils import timezone

from apps.audit.services import journaliser
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
    journaliser(
        "concours.configuration_validee", organisation=concours.organisation, auteur=utilisateur, objet=concours,
        details={"empreinte": concours.configuration_empreinte},
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
    journaliser("concours.ouvert", organisation=concours.organisation, objet=concours)


def demarrer_concours(concours):
    """Passe un concours « ouvert » à « en cours » : les tirages deviennent possibles (D25)."""
    if concours.etat != Concours.Etat.OUVERT:
        raise ConfigurationInvalideError(
            f"Seul un concours ouvert peut démarrer (état actuel : {concours.get_etat_display()})."
        )
    concours.etat = Concours.Etat.EN_COURS
    concours.save(update_fields=["etat", "modifie_le"])
```

```powershell
pytest apps\audit
python manage.py verifier_audit
```

Attendu : `33 passed` (avec vos règles du tirage écrites : les tests de tirage en dépendent), puis « aucune anomalie ».

## Essayer de tricher

Dans `psql`, essayez de modifier une entrée :

```sql
UPDATE audit_entreeaudit SET action = 'x';
```

PostgreSQL répond : `Le journal d'audit est en ajout seul : UPDATE interdit.`

## Questions de compréhension

1. Un administrateur de base de données désactive le déclencheur, modifie une entrée et recalcule **son** empreinte. Comment `verifier_chaine` le détecte-t-il ?
2. Pourquoi `journaliser` doit-il être appelé *dans* la transaction de l'opération qu'il trace ?
3. Pourquoi une chaîne par client plutôt qu'une chaîne unique ?

<details>
<summary>Réponses</summary>

1. L'entrée suivante contient l'**ancienne** empreinte de l'entrée falsifiée : son chaînage ne correspond plus. Pour passer inaperçu, il faudrait réécrire **toutes** les entrées suivantes *et* le registre de tête ; la sauvegarde et l'extrait remis au client (qui contient des empreintes) permettent de le contredire.
2. Pour qu'il n'y ait jamais de tirage sans trace (la transaction échoue : rien n'est enregistré) ni de trace d'une opération annulée.
3. Pour que l'extrait remis à un client (procès-verbal) soit vérifiable seul et ne révèle rien d'un autre client (RM-20).
</details>

## Journal d'apprentissage

Expliquez avec vos mots pourquoi un journal « en ajout seul » ne suffit pas sans empreintes chaînées.

## Commit proposé

```text
Itération 4a : journal d'audit à empreinte chaînée
```
