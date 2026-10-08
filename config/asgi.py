"""Point d'entrée ASGI : HTTP classique et WebSocket (Django Channels, §13.5).

Le WebSocket passe par deux protections : le contrôle d'origine (``AllowedHostsOriginValidator``, qui refuse
une page d'un autre site, contre le détournement de WebSocket) et l'authentification par cookie de session.
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Django doit être initialisé AVANT d'importer le routage (qui importe des modèles).
application_http = get_asgi_application()

from apps.presentation.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": application_http,
        "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
    }
)
