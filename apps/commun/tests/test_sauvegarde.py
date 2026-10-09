"""Sauvegarde et restauration (§15.5, REC-18). Vraies transactions : pg_dump lit la base depuis un autre processus."""
import uuid
from io import StringIO
from pathlib import Path

import psycopg
import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.audit.models import EntreeAudit
from apps.commun import sauvegarde
from apps.commun.tests.outils import creer_organisation, creer_utilisateur
from apps.prestations import services
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.audit.services import journaliser, verifier_chaine

pytestmark = pytest.mark.skipif(
    __import__("shutil").which("pg_dump") is None, reason="pg_dump n'est pas installé (PostgreSQL client)"
)


@pytest.fixture
def base_restauree():
    """Un nom de base de restauration unique ; supprimée à la fin du test."""
    nom = f"test_restauration_{uuid.uuid4().hex[:8]}"
    yield nom
    p = sauvegarde._parametres("postgres")
    with psycopg.connect(**p, autocommit=True) as maintenance:
        maintenance.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')


def compter(base, requete):
    with psycopg.connect(**sauvegarde._parametres(base)) as c:
        return c.execute(requete).fetchone()[0]


@pytest.mark.django_db(transaction=True)
def test_rec18_restaurer_une_sauvegarde_donne_des_donnees_coherentes_et_exploitables(tmp_path, base_restauree):
    epreuve = creer_epreuve_ouverte(series=3)
    for _ in range(2):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4(), terminal="Tablette 1")
    fichier = sauvegarde.sauvegarder(tmp_path)

    sauvegarde.restaurer(fichier, base_restauree)  # inclut verifier_audit sur la base restaurée

    for requete in ("select count(*) from prestations_tirage", "select count(*) from audit_entreeaudit",
                    "select count(*) from questions_serie", "select count(*) from candidats_participation"):
        assert compter(base_restauree, requete) == compter(connection.settings_dict["NAME"], requete) > 0
    assert compter(base_restauree, "select count(*) from audit_entreeaudit where action = 'tirage.effectue'") == 2


@pytest.mark.django_db(transaction=True)
def test_la_restauration_detecte_un_journal_d_audit_altere_dans_la_sauvegarde(tmp_path, base_restauree):
    organisation = creer_organisation()
    journaliser("a", organisation=organisation)
    journaliser("b", organisation=organisation)
    with connection.cursor() as curseur:  # on falsifie le journal AVANT la sauvegarde
        curseur.execute("ALTER TABLE audit_entreeaudit DISABLE TRIGGER USER")
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee' WHERE numero = 1")
        curseur.execute("ALTER TABLE audit_entreeaudit ENABLE TRIGGER USER")
    fichier = sauvegarde.sauvegarder(tmp_path)

    with pytest.raises(sauvegarde.SauvegardeError, match="incohérente"):
        sauvegarde.restaurer(fichier, base_restauree)


@pytest.mark.django_db(transaction=True)
def test_une_sauvegarde_alteree_est_refusee_avant_toute_restauration(tmp_path, base_restauree):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)
    contenu = bytearray(fichier.read_bytes())
    contenu[len(contenu) // 2] ^= 0xFF
    fichier.write_bytes(bytes(contenu))

    with pytest.raises(sauvegarde.SauvegardeError, match="altérée"):
        sauvegarde.restaurer(fichier, base_restauree)
    with psycopg.connect(**sauvegarde._parametres("postgres")) as c:
        assert c.execute("select 1 from pg_database where datname = %s", [base_restauree]).fetchone() is None


@pytest.mark.django_db(transaction=True)
def test_une_sauvegarde_sans_empreinte_est_refusee(tmp_path, base_restauree):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)
    Path(f"{fichier}.sha256").unlink()

    with pytest.raises(sauvegarde.SauvegardeError, match="empreinte"):
        sauvegarde.restaurer(fichier, base_restauree)


@pytest.mark.django_db(transaction=True)
def test_on_ne_restaure_jamais_sur_la_base_en_service(tmp_path):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)

    with pytest.raises(sauvegarde.SauvegardeError, match="base en service"):
        sauvegarde.restaurer(fichier, connection.settings_dict["NAME"], ecraser=True)


@pytest.mark.django_db(transaction=True)
def test_on_n_ecrase_une_base_existante_qu_a_la_demande(tmp_path, base_restauree):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)
    sauvegarde.restaurer(fichier, base_restauree)

    with pytest.raises(sauvegarde.SauvegardeError, match="existe déjà"):
        sauvegarde.restaurer(fichier, base_restauree)
    sauvegarde.restaurer(fichier, base_restauree, ecraser=True)


@pytest.mark.django_db(transaction=True)
def test_la_rotation_garde_les_plus_recentes_et_supprime_aussi_les_empreintes(tmp_path):
    creer_organisation()
    from datetime import datetime, timedelta, timezone

    depart = datetime(2027, 1, 20, 9, 0, tzinfo=timezone.utc)
    for i in range(4):
        sauvegarde.sauvegarder(tmp_path, conserver=2, maintenant=depart + timedelta(minutes=15 * i))

    dumps = sorted(p.name for p in tmp_path.glob("*.dump"))
    assert dumps == ["quranova-20270120-093000.dump", "quranova-20270120-094500.dump"]
    assert len(list(tmp_path.glob("*.sha256"))) == 2


@pytest.mark.django_db(transaction=True)
def test_aucun_fichier_partiel_ne_reste_apres_un_echec(tmp_path, monkeypatch):
    """Une base inexistante fait échouer pg_dump : ni sauvegarde ni fichier temporaire ne doivent subsister."""
    monkeypatch.setattr(
        sauvegarde, "_parametres",
        lambda base=None: {"dbname": "base_inexistante_xyz", "host": "localhost", "port": "5432", "user": "quranova", "password": "mauvais"},
    )

    with pytest.raises(sauvegarde.SauvegardeError, match="pg_dump a échoué"):
        sauvegarde.sauvegarder(tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.django_db(transaction=True)
def test_un_dossier_inutilisable_est_signale(tmp_path):
    fichier = tmp_path / "pas-un-dossier"
    fichier.write_text("x")

    with pytest.raises(sauvegarde.SauvegardeError, match="Dossier de sauvegarde inutilisable"):
        sauvegarde.sauvegarder(fichier / "sous-dossier")


@pytest.mark.django_db(transaction=True)
def test_l_outil_pg_dump_absent_donne_une_explication_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nulle-part")
    monkeypatch.delenv("PG_BIN", raising=False)

    with pytest.raises(sauvegarde.SauvegardeError, match="PATH"):
        sauvegarde.sauvegarder(tmp_path)


@pytest.mark.django_db(transaction=True)
def test_les_commandes_sauvegarder_et_restaurer(tmp_path, base_restauree):
    creer_organisation()
    sortie = StringIO()

    call_command("sauvegarder", "--dossier", str(tmp_path), "--conserver", "5", stdout=sortie)
    (fichier,) = tmp_path.glob("*.dump")
    call_command("restaurer", str(fichier), "--vers-base", base_restauree, stdout=sortie)

    assert "Sauvegarde écrite" in sortie.getvalue() and "restaurée et vérifiée" in sortie.getvalue()
    entree = EntreeAudit.objects.get(action="sauvegarde.effectuee")
    assert entree.organisation is None and entree.details["fichier"] == fichier.name  # chaîne « système »
    with pytest.raises(CommandError, match="altérée|empreinte|introuvable"):
        call_command("restaurer", str(tmp_path / "absent.dump"), "--vers-base", base_restauree + "x")


@pytest.mark.parametrize("nom", [
    'x"; DROP DATABASE quranova_dev; --', "a b", "1abc", "", "a" * 64, "-oops", "base;drop", 'guillemet"',
])
def test_rec28_un_nom_de_base_dangereux_est_refuse_avant_toute_commande_sql(tmp_path, nom):
    """Le nom de la base cible finit dans DROP/CREATE DATABASE et dans pg_restore : seuls les identifiants simples passent."""
    with pytest.raises(sauvegarde.SauvegardeError, match="Nom de base refusé"):
        sauvegarde.restaurer(tmp_path / "inexistant.dump", nom, ecraser=True)
