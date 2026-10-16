"""Sauvegarde et restauration PostgreSQL du serveur de salle (§15.5, REC-18).

Une sauvegarde est un fichier ``pg_dump`` au format « custom » (compressé, restaurable table par table) accompagné de
son empreinte SHA-256 : avant toute restauration, on vérifie que le fichier n'a pas été altéré ni tronqué (disque
externe débranché en cours d'écriture, par exemple). Les anciennes sauvegardes sont supprimées au-delà d'un nombre
conservé (rotation).
"""
import hashlib
import os
import re
import shutil
# seuls pg_dump, pg_restore et manage.py sont lancés, jamais via un shell
import subprocess  # nosec B404
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql
from django.conf import settings
from django.db import connection
from django.utils import timezone

PREFIXE = "quranova-"
SUFFIXE = ".dump"


class SauvegardeError(Exception):
    pass


NOM_DE_BASE_VALIDE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")  # un identifiant PostgreSQL simple : jamais de guillemet ni d'espace


def _outil(nom):
    chemin = shutil.which(nom) or (shutil.which(str(Path(os.environ["PG_BIN"]) / nom)) if os.environ.get("PG_BIN") else None)
    if chemin is None:
        raise SauvegardeError(
            f"« {nom} » est introuvable. Ajoutez le dossier « bin » de PostgreSQL au PATH (Windows : "
            f"C:\\Program Files\\PostgreSQL\\<version>\\bin) ou définissez la variable PG_BIN."
        )
    return chemin


def _parametres(base=None):
    reglages = connection.settings_dict
    return {
        "dbname": base or reglages["NAME"], "host": reglages.get("HOST") or "localhost",
        "port": str(reglages.get("PORT") or "5432"), "user": reglages["USER"], "password": reglages.get("PASSWORD") or "",
    }


def _environnement(parametres):
    return {**os.environ, "PGPASSWORD": parametres["password"]}


def empreinte_fichier(chemin):
    sha = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
            sha.update(bloc)
    return sha.hexdigest()


def sauvegarder(dossier, conserver=96, maintenant=None):
    """Écrit une sauvegarde horodatée dans ``dossier`` ; renvoie son chemin. Lève ``SauvegardeError`` en cas d'échec."""
    dossier = Path(dossier)
    try:
        dossier.mkdir(parents=True, exist_ok=True)
    except OSError as erreur:
        raise SauvegardeError(f"Dossier de sauvegarde inutilisable ({dossier}) : {erreur}") from None
    maintenant = maintenant or timezone.now()
    cible = dossier / f"{PREFIXE}{maintenant.strftime('%Y%m%d-%H%M%S')}{SUFFIXE}"
    p = _parametres()
    temporaire = cible.with_suffix(".en-cours")
    commande = [_outil("pg_dump"), "--format=custom", "--no-owner", f"--file={temporaire}", "--host", p["host"],
                "--port", p["port"], "--username", p["user"], p["dbname"]]
    # liste d'arguments, outil résolu par _outil, pas de shell
    resultat = subprocess.run(commande, env=_environnement(p), capture_output=True, text=True)  # nosec B603
    if resultat.returncode != 0 or not temporaire.exists() or temporaire.stat().st_size == 0:
        temporaire.unlink(missing_ok=True)
        raise SauvegardeError(f"pg_dump a échoué : {resultat.stderr.strip() or 'fichier vide'}")
    # idem
    verification = subprocess.run([_outil("pg_restore"), "--list", str(temporaire)], capture_output=True, text=True)  # nosec B603
    if verification.returncode != 0:
        temporaire.unlink(missing_ok=True)
        raise SauvegardeError(f"La sauvegarde produite est illisible : {verification.stderr.strip()}")
    temporaire.replace(cible)  # le fichier n'apparaît sous son vrai nom qu'une fois complet et vérifié
    Path(f"{cible}.sha256").write_text(f"{empreinte_fichier(cible)}  {cible.name}\n", encoding="utf-8")
    _faire_tourner(dossier, conserver)
    return cible


def _faire_tourner(dossier, conserver):
    anciennes = sorted(dossier.glob(f"{PREFIXE}*{SUFFIXE}"))
    for ancienne in anciennes[: max(0, len(anciennes) - conserver)]:
        ancienne.unlink(missing_ok=True)
        Path(f"{ancienne}.sha256").unlink(missing_ok=True)


def verifier_sauvegarde(fichier):
    """Vérifie l'empreinte enregistrée à côté du fichier ; refuse un fichier altéré ou sans empreinte."""
    fichier = Path(fichier)
    if not fichier.is_file():
        raise SauvegardeError(f"Fichier introuvable : {fichier}")
    empreinte_attendue = Path(f"{fichier}.sha256")
    if not empreinte_attendue.is_file():
        raise SauvegardeError("Aucune empreinte (.sha256) à côté de la sauvegarde : intégrité invérifiable.")
    if empreinte_attendue.read_text(encoding="utf-8").split()[0] != empreinte_fichier(fichier):
        raise SauvegardeError("La sauvegarde est altérée ou incomplète : son empreinte ne correspond pas.")


def restaurer(fichier, vers_base, ecraser=False, verifier=True):
    """Restaure ``fichier`` dans la base ``vers_base`` (créée) ; ne touche JAMAIS à la base en service sans l'écraser exprès."""
    if not NOM_DE_BASE_VALIDE.fullmatch(vers_base):  # avant tout : le nom finit dans des commandes SQL et dans pg_restore
        raise SauvegardeError(
            f"Nom de base refusé : « {vers_base} ». Utilisez des lettres, chiffres et « _ » (63 caractères au plus, sans commencer par un chiffre)."
        )
    verifier_sauvegarde(fichier)
    if vers_base == connection.settings_dict["NAME"]:
        raise SauvegardeError("Refus : la restauration vers la base en service écraserait les données courantes. Choisissez une autre base.")
    p = _parametres("postgres")
    try:
        with psycopg.connect(**p, autocommit=True) as maintenance:
            existe = maintenance.execute("SELECT 1 FROM pg_database WHERE datname = %s", [vers_base]).fetchone()
            if existe and not ecraser:
                raise SauvegardeError(f"La base « {vers_base} » existe déjà : utilisez --ecraser pour la remplacer.")
            if existe:
                maintenance.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(vers_base)))
            maintenance.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(vers_base)))
    except psycopg.Error as erreur:
        raise SauvegardeError(f"Impossible de préparer la base « {vers_base} » : {erreur}") from None
    cible = _parametres(vers_base)
    # liste d'arguments ; le nom de base est validé (NOM_DE_BASE_VALIDE)
    resultat = subprocess.run(  # nosec B603
        [_outil("pg_restore"), "--no-owner", "--exit-on-error", "--host", cible["host"], "--port", cible["port"],
         "--username", cible["user"], "--dbname", vers_base, str(fichier)],
        env=_environnement(cible), capture_output=True, text=True,
    )
    if resultat.returncode != 0:
        raise SauvegardeError(f"pg_restore a échoué : {resultat.stderr.strip()}")
    if verifier:
        controle = verifier_integrite(vers_base)
        if controle.returncode != 0:
            raise SauvegardeError("La base restaurée est incohérente :\n" + (controle.stdout + controle.stderr).strip())


def verifier_integrite(base):
    """Lance ``verifier_audit`` SUR la base restaurée (processus à part, pointé vers cette base)."""
    # interpréteur courant et manage.py, nom de base validé
    return subprocess.run(  # nosec B603
        [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "verifier_audit"],
        env={**os.environ, "DB_NAME": base, "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.dev")},
        capture_output=True, text=True, cwd=str(settings.BASE_DIR),
    )
