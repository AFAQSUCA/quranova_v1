# Chapitre 28 — Simulation de charge (phase 3, étape 6.2)

## Objectif
Mesurer, avec des chiffres, si le serveur tient 500 candidats et 30 terminaux (REC-19) et si une commande de diaporama arrive à tous
les écrans en moins de 300 ms (REC-20).

## Fichiers
- `apps/commun/charge/mesures.py` : percentile « rang le plus proche », objectifs, rapport Markdown.
- `apps/commun/charge/client_ws.py` : client WebSocket (RFC 6455) en bibliothèque standard : poignée de main avec `Origin` et `Cookie`,
  trames masquées, heure d'arrivée relevée dès la lecture.
- `apps/commun/charge/preparation.py` : le jeu de données de charge (concours, 500 candidats, 500 séries, terminaux, présentation longue).
- `apps/commun/charge/execution.py` : les terminaux de tirage (HTTP) et l'opérateur + écrans (WebSocket), exécutés en même temps.
- `apps/commun/management/commands/simuler_charge.py` : la commande (`--confirmer-base-jetable` obligatoire).
- `apps/commun/tests/test_charge.py`, `docs/recette/charge.md` (procédure et résultats).

## Pourquoi un client WebSocket maison ?
Aucune bibliothèque cliente n'était installée, et ajouter une dépendance pour un outil de mesure n'était pas justifié : le protocole tient en
une centaine de lignes. Il est testé contre un faux serveur.

## Pourquoi un percentile « rang le plus proche » ?
« 95 % des requêtes en moins de 300 ms » se lit : au moins 95 % des mesures sont sous 300 ms. On trie et on prend la valeur au rang
⌈0,95 × n⌉, sans moyenne ni interpolation qui cacheraient la queue.

## Commandes (PowerShell)
```powershell
pytest apps\commun\tests\test_charge.py
docker compose up -d
docker compose exec web python manage.py simuler_charge --confirmer-base-jetable --url http://nginx
```

## Ce qu'on a appris
Voir `docs/recette/charge.md` : cohérence parfaite, mais latences au-dessus des objectifs **dans le bac à sable** ; le goulot principal est
la connexion PostgreSQL ouverte à chaque requête (un pool de connexions, activé par défaut en production, l'atténue) ; le tirage est sérialisé par conception.

**Question :** pourquoi une simulation où toutes les tablettes tirent à la même seconde est-elle plus sévère que la réalité, et pourquoi
faut-il pourtant la lancer ?
