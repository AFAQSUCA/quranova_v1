# 13. Architecture technique

## 13.1. Principe « local d'abord »

QURANOVA est une application web unique, déployable selon deux modes à partir du même code et de la même image Docker :

| Mode | Version | Rôle |
|---|---|---|
| Serveur de salle | V1 | Mode de fonctionnement par défaut le jour J. Un ordinateur portable du prestataire exécute l'application ; tous les écrans de la salle s'y connectent par un réseau Wi-Fi dédié. Aucune connexion Internet n'est nécessaire. |
| Instance centrale | V2 | Installation en ligne servant à la préparation à distance avec le client, à l'archivage des concours, à la sauvegarde et à la publication des résultats. |

**Configuration de la salle (V1) :**

- tous les terminaux appartiennent au prestataire : ordinateur serveur et de commande, tablette de tirage, tablettes des jurés, mini-ordinateur ou sortie HDMI pour l'écran scène ;
- routeur Wi-Fi dédié, réseau protégé (WPA2 ou WPA3) dont le mot de passe est changé à chaque mission ; aucun appareil extérieur n'y est admis ;
- adresse fixe du serveur sur le réseau local et accès HTTPS au moyen d'une autorité de certification locale installée sur les terminaux du prestataire ;
- tablettes en mode kiosque, écran maintenu allumé pendant la session (API de verrouillage d'éveil) ;
- onduleur assurant au moins une heure d'autonomie au serveur et au routeur.

## 13.2. Technologies retenues

| Couche | Technologie retenue | Rôle |
|---|---|---|
| Logique métier | Python 3.12 ou supérieur, Django 5.2 LTS | Gestion des clients, concours, candidats, tirages, notes. |
| Interfaces de gestion | Gabarits Django, HTMX, Tailwind CSS | Écrans de paramétrage, d'import, de suivi et de résultats. |
| Écrans temps réel | Vue.js 3, TypeScript, Pinia, construits avec Vite | Écrans de tirage, de commande, de jury et de scène (cf. §13.3). |
| Temps réel | Django Channels (WebSocket) | Synchronisation des diapositives et des écrans (cf. §13.5). |
| Couche de messages | Redis | Couche de canaux Channels et cache de l'état de présentation. |
| Base de données | PostgreSQL 16 ou supérieur | Stockage des données ; colonne `organization_id` sur les tables propres à un client (cf. §13.4). |
| Documents | WeasyPrint | Génération des procès-verbaux, classements et certificats en PDF. |
| Source coranique | Corpus Tanzil Uthmani, Hafs, versionné | Références et textes exacts des versets (cf. §12). |
| Serveur web | Nginx et serveur ASGI (Daphne ou Uvicorn) | TLS, fichiers statiques, mandataire inverse. |
| Conteneurisation | Docker et Docker Compose | Déploiement identique sur le serveur de salle et sur l'instance centrale. |
| Sauvegardes | Sauvegardes PostgreSQL automatiques sur disque externe ; copie chiffrée en ligne (V2) | Protection contre les pertes de données (cf. §15.5). |
| Tâches asynchrones (V2) | Celery | Exports volumineux, synchronisation, purges planifiées. |
| Supervision (V2) | Collecte d'erreurs (type Sentry) | Détection des incidents sur l'instance centrale. |

## 13.3. Choix des technologies d'interface

**Décision : architecture d'interface hybride.** Les écrans de gestion sont rendus côté serveur (gabarits Django et HTMX) ; seuls les quatre écrans temps réel sont développés en Vue.js 3.

**Justification :**

- **productivité d'un développeur seul** : les écrans de gestion (formulaires, listes, imports) représentent la majorité du volume ; les gabarits Django avec HTMX permettent de les produire rapidement sans dupliquer la logique entre une API et une application cliente ;
- **exigences temps réel concentrées** : les écrans de tirage, de commande, de jury et de scène partagent un état de présentation versionné ; un magasin d'état réactif (Pinia) et le composant de transition de Vue gèrent proprement la reconstruction de l'écran à partir d'un instantané, le balayage de droite à gauche et la neutralisation des transitions concurrentes ;
- **coût d'apprentissage limité** : Vue.js est le framework le plus accessible des trois envisagés (React, Vue, Svelte) et son usage reste circonscrit à quatre écrans ;
- **évolutivité** : si QURANOVA est ouvert en libre-service (V3), les écrans de gestion pourront être migrés progressivement vers Vue.js sans modifier les écrans temps réel.

## 13.4. Séparation des données des clients

**Décision : base de données unique, colonne `organization_id` sur toutes les tables propres à un client, filtrage applicatif systématique.** La Row-Level Security PostgreSQL est reportée à la V3.

- chaque table propre à un client comporte une colonne `organization_id` non nulle, indexée ;
- toutes les requêtes passent par des gestionnaires de modèles et des contrôles de permission qui imposent le filtre par client ; un test automatisé vérifie qu'aucune vue ne renvoie de données d'un autre client ;
- les identifiants exposés dans les URL sont des UUID ;
- les tables du corpus coranique sont globales et en lecture seule.

**Justification du report de la RLS :** en V1 et V2, seuls le prestataire et ses opérateurs administrent les données, sur un réseau fermé ou une instance à accès restreint ; le risque d'accès croisé par un utilisateur malveillant d'un autre client est faible. La colonne `organization_id` étant présente dès l'origine, l'activation de la RLS en V3 ne nécessitera aucune migration de données. Cette activation est un **prérequis** à toute ouverture en libre-service.

## 13.5. Communication temps réel et reprise d'état

L'état de présentation de chaque prestation est **détenu par le serveur** (base de données, avec copie en cache Redis). Les écrans n'en sont que des reflets ; ils ne calculent jamais l'état localement.

**Transport :**

- sur le serveur de salle (V1) : WebSocket uniquement, le réseau local étant maîtrisé ;
- sur l'instance centrale (V2), exposée à Internet : repli automatique sur Server-Sent Events puis sur long-polling lorsque WebSocket est bloqué par un réseau ou un mandataire.

**Reconnexion et reprise d'état :**

- battement de présence toutes les 15 secondes ; une connexion sans réponse pendant 30 secondes est considérée comme perdue ;
- reconnexion automatique avec délais croissants (0,5 s, 1 s, 2 s, puis 5 s au maximum) ;
- chaque état diffusé porte un numéro de version strictement croissant ; à la reconnexion, le serveur renvoie un **instantané complet** de l'état courant et l'écran se reconstruit sans rejouer les animations intermédiaires ;
- un indicateur signale à l'opérateur tout écran déconnecté ;
- objectif : retour à l'état courant en moins de 2 secondes après rétablissement du réseau.

**Commandes idempotentes (RM-30) :**

- chaque commande porte un identifiant unique et la version d'état sur laquelle elle s'appuie ;
- le serveur applique la commande uniquement si la version correspond à l'état courant ; une commande déjà traitée n'est jamais appliquée deux fois ;
- les commandes d'une même prestation sont sérialisées.

## 13.6. Continuité en salle et synchronisation

**Incidents en salle (V1) :**

| Incident | Réponse prévue | Délai cible |
|---|---|---|
| Coupure d'électricité | Onduleur sur le serveur et le routeur ; tablettes sur batterie. | Aucune interruption |
| Panne du routeur Wi-Fi | Routeur de rechange préconfiguré (même nom de réseau et même mot de passe). | Moins de 5 minutes |
| Panne d'une tablette de juré | Tablette de rechange ; le brouillon de notes est conservé côté serveur. | Moins de 2 minutes |
| Panne du serveur de salle | Restauration de la dernière sauvegarde (au plus 15 minutes) sur l'ordinateur de secours, puis reprise à la dernière prestation clôturée. | Moins de 15 minutes |
| Panne simultanée des deux ordinateurs | Mesure de dernier recours : fiches de notation imprimées depuis l'application la veille, saisies ultérieurement avec motif. | — |

**Synchronisation avec l'instance centrale (V2) :**

- la préparation peut se faire sur l'instance centrale, avec le responsable client ; la veille de l'événement, l'opérateur télécharge un **paquet de concours** chiffré et signé, importé sur le serveur de salle ;
- pendant le concours, l'instance centrale est verrouillée en écriture pour ce concours (RM-29) : une seule source de vérité existe à tout instant ;
- après le concours, le journal des opérations du serveur de salle est téléversé et importé de manière idempotente ; un rapport de cohérence est produit avant déverrouillage et publication.

## 13.7. Architecture logique

```text
  SALLE (réseau Wi-Fi dédié, sans Internet)                         V1
  ┌───────────────────────────────────────────────────────────────┐
  │ Tablette tirage │ Tablettes jurés │ Écran scène │ Commande     │
  │        └──────────── WSS / HTTPS (réseau local) ─────┘         │
  │                              ▼                                 │
  │ SERVEUR DE SALLE (ordinateur du prestataire, Docker Compose)   │
  │   Nginx → Django ASGI (gestion + Channels) ⇄ Redis             │
  │                  ▼                                             │
  │             PostgreSQL ──► sauvegarde toutes les 15 min        │
  │                            sur disque externe                  │
  └───────────────────────────────────────────────────────────────┘
                 │  paquet de concours / journal d'opérations     V2
                 ▼  (hors session, lorsqu'Internet est disponible)
  ┌───────────────────────────────────────────────────────────────┐
  │ INSTANCE CENTRALE : même image Docker + Celery + stockage     │
  │ objet chiffré ; préparation, archivage, publication           │
  └───────────────────────────────────────────────────────────────┘
```

## 13.8. Architecture fonctionnelle en modules

- `clients` : organisations clientes, missions, séparation des données ;
- `utilisateurs` : comptes, codes d'accès des jurés, permissions ;
- `concours` : concours, éditions, catégories, épreuves, sessions et paramètres ;
- `candidats` : candidats, import, participations, consentements ;
- `questions` : questions, passages coraniques, séries, lots et règles de tirage ;
- `coran` : versions du corpus, sourates, versets, traductions ;
- `prestations` : déroulement, tirages et état des prestations ;
- `presentation` : diapositives, animation et synchronisation ;
- `jury` : affectations, critères et notes ;
- `resultats` : calculs, classements, procès-verbaux et documents PDF ;
- `audit` : historique des actions sensibles ;
- `synchro` (V2) : paquets de concours et resynchronisation.
