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
