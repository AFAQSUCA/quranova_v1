"""Réglages de production (phase 3) : démarrage refusé si un réglage dangereux est oublié ; Redis partagé entre processus.

Chaque contrôle est lancé dans un sous-processus : les réglages sont lus une seule fois à l'import.
"""
import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
CLE_VALIDE = "k3Zr9Wq1xV7mTn2LpB8sD4fG6hJ0aC5eY9uI3oQ7wE1rTbN8mK2"


def lancer(**env):
    """Importe config.settings.prod avec UNIQUEMENT ces variables ; renvoie (code, sortie)."""
    environnement = {"PATH": os.environ["PATH"], "DJANGO_SETTINGS_MODULE": "config.settings.prod", "DB_PASSWORD": "x"}
    environnement.update(env)
    code = "import django; from django.conf import settings; settings.ALLOWED_HOSTS; print('OK', settings.ALLOWED_HOSTS)"
    r = subprocess.run([sys.executable, "-c", code], cwd=RACINE, env=environnement, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_la_production_demarre_avec_des_reglages_complets():
    code, sortie = lancer(DJANGO_SECRET_KEY=CLE_VALIDE, DJANGO_ALLOWED_HOSTS="192.168.50.10,quranova.local")
    assert code == 0 and "192.168.50.10" in sortie, sortie


@pytest.mark.parametrize("cle", ["remplacer-par-une-cle-aleatoire", "courte", "django-insecure-" + "a" * 60])
def test_la_production_refuse_une_cle_secrete_faible_ou_du_modele(cle):
    code, sortie = lancer(DJANGO_SECRET_KEY=cle, DJANGO_ALLOWED_HOSTS="192.168.50.10")
    assert code != 0 and "DJANGO_SECRET_KEY" in sortie


@pytest.mark.parametrize("hotes", ["", "*", "192.168.50.10,*"])
def test_la_production_refuse_des_hotes_absents_ou_ouverts_a_tous(hotes):
    code, sortie = lancer(DJANGO_SECRET_KEY=CLE_VALIDE, DJANGO_ALLOWED_HOSTS=hotes)
    assert code != 0 and "DJANGO_ALLOWED_HOSTS" in sortie


def test_la_production_utilise_redis_et_des_cookies_surs():
    code = (
        "from django.conf import settings as s; print(s.CHANNEL_LAYERS['default']['BACKEND'], s.DEBUG, "
        "s.SESSION_COOKIE_HTTPONLY, s.CSRF_TRUSTED_ORIGINS)"
    )
    env = {"PATH": os.environ["PATH"], "DJANGO_SETTINGS_MODULE": "config.settings.prod", "DB_PASSWORD": "x",
           "DJANGO_SECRET_KEY": CLE_VALIDE, "DJANGO_ALLOWED_HOSTS": "10.0.0.5"}
    r = subprocess.run([sys.executable, "-c", code], cwd=RACINE, env=env, capture_output=True, text=True)
    assert "RedisChannelLayer False True ['http://10.0.0.5']" in r.stdout, r.stdout + r.stderr


def _redis_disponible():
    try:
        socket.create_connection(("localhost", 6379), timeout=0.3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _redis_disponible(), reason="Redis absent sur localhost:6379")
def test_un_message_de_groupe_traverse_deux_processus_via_redis():
    """C'est la raison d'être de Redis : deux couches distinctes (= deux processus Daphne) partagent leurs groupes."""
    from channels_redis.core import RedisChannelLayer

    async def scenario():
        a = RedisChannelLayer(hosts=["redis://localhost:6379/9"], prefix="test-quranova")
        b = RedisChannelLayer(hosts=["redis://localhost:6379/9"], prefix="test-quranova")
        canal = await a.new_channel()
        await a.group_add("scene-1", canal)
        await b.group_send("scene-1", {"type": "etat.diffuse", "version": 7})
        message = await asyncio.wait_for(a.receive(canal), timeout=3)
        await a.flush()
        await a.close_pools()
        await b.close_pools()
        return message

    message = asyncio.run(scenario())
    assert message["version"] == 7
