from django.urls import path

from apps.presentation.consumers import PresentationConsumer

websocket_urlpatterns = [
    path("ws/presentation/<uuid:session_id>/", PresentationConsumer.as_asgi()),
]
