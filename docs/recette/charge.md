# Simulation de charge (REC-19, REC-20 ; objectifs §18.1)

## Ce que fait la simulation

`python manage.py simuler_charge` crée un concours de charge (500 candidats, 500 séries d'un verset, 20 tablettes de tirage,
10 écrans de scène = 30 terminaux, plus l'opérateur) puis, **en même temps** :

- chaque tablette appelle un candidat, lit son état et déclenche son tirage par HTTP (avec rejeu d'une demande sur dix : même série attendue) ;
- l'opérateur envoie 200 commandes de diaporama (`suivante` / `precedente`) par WebSocket sur une présentation longue, et chaque
  écran mesure le délai entre l'envoi et la réception de l'état (REC-20).

À la fin, elle vérifie la cohérence : un seul tirage valide par candidat, aucune série tirée deux fois (RM-21), toutes les
prestations « tirées », chaîne du journal d'audit intacte (« aucune erreur » de REC-19).

Aucune dépendance : un client HTTP basé sur la bibliothèque standard et un petit client WebSocket maison (`apps/commun/charge/`).

## Lancer

**À faire sur une base jetable** (les données de charge ne se suppriment pas : le journal d'audit est en ajout seul).

```powershell
# Pile Docker de test, base vide ; il faut un corpus importé et validé (jalon J0, ou validation d'essai) :
docker compose up -d
docker compose exec web python manage.py import_corpus
# valider la version importée pour l'essai (base jetable seulement) : docker compose exec web python manage.py shell
docker compose exec web python manage.py simuler_charge --confirmer-base-jetable --url http://nginx --rapport /data/sauvegardes/rapport-charge.md
```
Dans le conteneur, l'adresse `nginx` doit figurer dans `DJANGO_ALLOWED_HOSTS` (ajoutez `nginx` à la liste, pour l'essai seulement).
Options : `--candidats`, `--terminaux-tirage`, `--ecrans-scene`, `--commandes`, `--pause-terminal` (3 s par défaut ≈ journée
accélérée ×20 ; **0 = rafale**, où toutes les tablettes tirent sans pause), `--intervalle-commandes`.
Pour repartir de zéro : `docker compose down -v`.

## Objectifs vérifiés

| Objectif | Seuil |
|---|---|
| 95 % des requêtes HTTP | < 300 ms |
| Tirage (99 %) | < 1 s |
| Propagation d'une commande à tous les écrans (95 %) | < 300 ms |
| Erreurs serveur, doubles tirages, séries réutilisées, audit | aucun |

## Résultats mesurés (bac à sable de développement)

**Attention** : ces mesures ont été prises dans un conteneur de développement à **4 cœurs partagés** où tournent aussi, en même temps,
le générateur de charge, Daphne, PostgreSQL, Redis et Nginx. Elles montrent les ordres de grandeur et les goulots, pas la performance
du portable de salle : **REC-19 et REC-20 restent à mesurer sur le matériel cible**.

| Essai | HTTP p95 | Tirage p99 | Propagation p95 | Cohérence |
|---|---|---|---|---|
| Rafale (pause 0,2 s), sans pool de connexions | 2 701 ms | 2 842 ms | 612 ms | OK |
| Charge nominale (pause 3 s), sans pool | 680 ms | 1 401 ms | 537 ms | OK |
| Charge nominale, avec pool de connexions | 401 ms | 1 439 ms | 306 ms | OK |
| Charge nominale + désynchronisation, avec pool | 591 ms | 1 357 ms | 333 ms | OK |

Ce que ces essais apprennent :

1. **Aucune anomalie de cohérence** dans aucun essai : 500 tirages uniques, aucune série réutilisée, audit intact, aucune commande perdue.
2. **Goulot n° 1 : une connexion PostgreSQL par requête.** Django ouvre et ferme une connexion pour chaque requête HTTP et chaque commande
   WebSocket (observé au profilage : Daphne à ~120 % de CPU, PostgreSQL à ~60 %). Un **pool de connexions** (`psycopg_pool`) a nettement
   amélioré les latences (p95 HTTP 680 → 401 ms, propagation 537 → 306 ms). Il est **actif par défaut** en production
   (`config/settings/prod.py`, paquet `psycopg_pool` ajouté avec ton accord ; `DB_POOL=0` pour le couper).
3. **Goulot n° 2 : le tirage est sérialisé par conception** (verrou sur le lot, règle absolue n° 2) : environ 50 ms par tirage ici. Vingt
   tablettes qui appuient dans la même seconde se mettent en file ; le dernier attend ~1 s. C'est le prix de « jamais deux fois la même série ».
4. Sur le portable cible (SSD, cœurs non partagés avec le générateur), les temps devraient être nettement meilleurs ; seule la mesure le dira.

## À faire pour clore REC-19 / REC-20

1. Lancer la simulation **sur le portable de salle**, depuis un autre ordinateur du Wi-Fi dédié pour que le générateur ne vole pas de CPU
   (ou au moins avec le même Docker Compose), et joindre le rapport au dossier de recette.
2. Si le tirage dépasse 1 s en rafale sur le matériel cible : réduire le travail fait sous le verrou (journal d'audit, requêtes de
   `series_admissibles`) plutôt que d'assouplir la règle.
