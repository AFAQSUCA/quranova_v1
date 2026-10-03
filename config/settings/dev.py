"""Réglages de développement : Windows local, sans Docker ni Redis."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Couche de canaux en mémoire : valable avec UN seul processus (cf. phase 3 : Redis).
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}
