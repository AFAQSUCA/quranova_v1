# Image du serveur de salle QURANOVA (phase 3). Trois étapes :
#   front  : compile le front Vue (Node n'existe PAS dans l'image finale) ;
#   base   : Python + code + front compilé ; lance Daphne (cible « web », par défaut) ;
#   test   : la même chose + pytest (cible « test », pour lancer les tests dans Docker).

FROM node:22-alpine AS front
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts écrit dans ../static/frontend
RUN mkdir -p /app/static && npm run build

FROM python:3.12-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# postgresql-client : pg_dump / pg_restore pour « manage.py sauvegarder / restaurer » (client 17, serveur 16 : accepté).
# libpango*, libharfbuzz-subset0, fonts-dejavu-core : WeasyPrint (procès-verbal et classements en PDF).
RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt
COPY . .
COPY --from=front /app/static/frontend static/frontend
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh && useradd --system --uid 1000 quranova \
    && mkdir -p /data/media /data/sauvegardes /app/staticfiles && chown -R quranova /data /app/staticfiles
USER quranova
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

FROM base AS test
USER root
RUN pip install --no-cache-dir -r requirements/dev.txt
USER quranova
ENV DJANGO_SETTINGS_MODULE=config.settings.dev
ENTRYPOINT []
CMD ["pytest", "-q"]

# La cible finale par défaut doit être « web » : on la place en dernier.
FROM base AS web
