# Protocole temps réel de la présentation (étape 1.3 — §9, §13.5, RM-30)

Ce document fixe **le format des messages** échangés par WebSocket entre le serveur et les écrans de
**commande** (opérateur) et de **scène**. Il est écrit AVANT le code (consumer, store Vue) : les deux côtés
le suivent à la lettre. Le jury s'y raccordera à l'itération 4 (D40).

## 1. Principes

1. **Le serveur détient l'état** (base de données). Les écrans n'en sont que des reflets : ils ne calculent
   jamais une diapositive eux-mêmes (§13.5).
2. **Le bus WebSocket n'est jamais une garantie.** Un message diffusé peut se perdre (couche en mémoire en
   développement, coupure Wi-Fi). Chaque état porte donc une **version** strictement croissante ; un écran qui
   constate un trou redemande un **instantané** complet.
3. **Une commande est idempotente** : elle porte un `id` unique et la `version_attendue` (RM-30). Rejouée,
   elle n'est jamais appliquée deux fois.
4. **Le texte des versets n'est envoyé qu'aux écrans autorisés** (RM-14) : opérateur ; scène seulement si
   l'épreuve a `affichage_scene` (D15). Le terminal de tirage et l'écran candidat n'ouvrent jamais ce canal.
   La projection est faite **côté serveur** avant l'envoi.
5. **Une seule présentation active par session** (D41) : la connexion se fait sur la **session** ; l'état
   suivi est celui de `session.prestation_active`. Changer de prestation active = nouvel état, version
   repartant de 1.

## 2. Connexion et authentification

URL : `ws://<serveur>/ws/presentation/<uuid de la session>/`.

| Écran | Authentification | Rôle |
|---|---|---|
| Commande (opérateur) | cookie de session Django, **contrôle d'origine**, accès à la mission (RM-20) | `operateur` |
| Scène | **premier message** `{"type":"auth","jeton":"…"}` dans les 5 s (D38) ; jamais dans l'URL | `scene` |

Codes de fermeture : `4401` non authentifié ou jeton invalide · `4403` interdit (autre session, autre client) ·
`4408` délai d'authentification dépassé.

Dès l'authentification réussie, le serveur envoie l'**instantané** (§3).

## 3. Messages du serveur vers l'écran

### 3.1. `etat` — l'instantané versionné

```json
{
  "type": "etat",
  "instantane": true,
  "session": "7c9b…",
  "prestation": {
    "id": "bd6b…",
    "candidat": {"numero": 12, "prenom": "Awa"},
    "epreuve": "Mémorisation",
    "serie": "Série 4"
  },
  "version": 17,
  "phase": "affichage",
  "rejeu": 0,
  "diapositive": {
    "index": 5,
    "total": 23,
    "type": "verset",
    "question": {"rang": 2, "total": 3, "libelle": "Sourate 2, versets 142 à 150"},
    "reference": "2:144",
    "segment": {"rang": 1, "total": 2},
    "texte": "…"
  }
}
```

- `prestation` vaut `null` quand aucune présentation n'est active (l'écran affiche « en attente »).
- `phase` : `preparee` (série chargée, rien d'affiché) · `affichage` · `pause` · `terminee`.
- `diapositive` vaut `null` en phase `preparee`.
- `diapositive.type` : `intercalaire_question` (« Question 1/3 — Sourate 2, versets 142 à 150 ») · `verset` ·
  `fin_question` · `fin_serie`.
- `reference` et `segment` n'existent que pour un `verset` (« 2:282 — 1/3 »). La concaténation des
  `texte` des segments d'un verset est **identique** au texte du corpus (REC-33).
- `texte` est **absent** pour un écran non autorisé (scène avec `affichage_scene` faux). Les intercalaires
  n'ont jamais de texte coranique : ils ne contiennent que le libellé de la question.
- `rejeu` est un compteur : quand il augmente alors que `index` ne change pas, l'écran rejoue l'animation
  (« Réafficher la diapositive »).
- `instantane` est vrai pour une réponse à la connexion ou à une demande de `snapshot` : l'écran se
  **reconstruit sans animation**. Il est faux (ou absent) pour une diffusion après commande : l'écran anime
  la transition (balayage de droite à gauche).

### 3.2. `ack` — réponse à une commande (envoyée à l'émetteur seulement)

```json
{"type": "ack", "id": "5f1c…", "statut": "appliquee", "version": 18}
{"type": "ack", "id": "5f1c…", "statut": "deja_traitee", "version": 18}
{"type": "ack", "id": "9a2e…", "statut": "rejetee", "raison": "version_obsolete", "version": 18}
```

`raison` : `version_obsolete` · `transition_interdite` · `non_autorise` · `commande_inconnue`.
Un refus renvoie toujours la `version` courante : l'écran sait de quoi il est en retard.

### 3.3. `ecrans` — présence (envoyé à l'opérateur)

```json
{"type": "ecrans", "ecrans": [{"nom": "Scène 1", "type": "scene", "connecte": true}]}
```

Calculé depuis la dernière activité enregistrée en base (30 s) : correct même avec plusieurs processus.

### 3.4. `pong`

```json
{"type": "pong"}
```

## 4. Messages de l'écran vers le serveur

### 4.1. `commande`

```json
{"type": "commande", "id": "5f1c…", "version_attendue": 17, "action": "suivante"}
```

Actions : `preparer` · `demarrer` · `suivante` · `precedente` · `pause` · `reprendre` · `reafficher` · `terminer`.

- `preparer` ajoute `"prestation": "<uuid>"` (elle devient la prestation active de la session) et n'exige pas
  de `version_attendue`. Refusée tant qu'une présentation est en `affichage` ou `pause`.
- `precedente` est **journalisée** (§9.3).
- Seul l'opérateur envoie des commandes (REC-14) : le serveur refuse (`non_autorise`) toute commande d'un
  écran de scène, **message par message** (règle absolue n°4).

### 4.2. `auth`, `snapshot`, `ping`

```json
{"type": "auth", "jeton": "…"}
{"type": "snapshot"}
{"type": "ping"}
```

`ping` toutes les **15 s** ; sans `pong` pendant **30 s**, l'écran considère la connexion perdue.

## 5. Règles côté écran

| Message reçu | Action |
|---|---|
| `etat`, même prestation, `version` = locale + 1 | appliquer, avec animation si `instantane` est faux |
| `etat`, même prestation, `version` ≤ locale | ignorer (message en retard ou doublon) |
| `etat`, même prestation, `version` > locale + 1 | **trou** : envoyer `snapshot`, ne rien appliquer |
| `etat`, autre prestation ou `instantane` vrai | remplacer l'état, **sans animation** |
| `ack` `rejetee` + `version_obsolete` | afficher la version courante, ne pas renvoyer automatiquement |

## 6. Trois exemples

**a) L'opérateur passe à la diapositive suivante.**

```text
opérateur → {"type":"commande","id":"5f1c…","version_attendue":17,"action":"suivante"}
serveur   → opérateur : {"type":"ack","id":"5f1c…","statut":"appliquee","version":18}
serveur   → opérateur, scène : {"type":"etat","version":18,"phase":"affichage","diapositive":{"index":6,…}}
```

**b) Double clic (REC-24) : deux « suivante » avec la même version.**

```text
opérateur → {…"id":"A","version_attendue":17,"action":"suivante"}
opérateur → {…"id":"B","version_attendue":17,"action":"suivante"}
serveur   → ack A : appliquee (version 18)
serveur   → ack B : rejetee, version_obsolete (version 18)       ← une seule diapositive franchie
```

**c) Message perdu, puis trou de version.**

```text
scène a la version 18. Elle reçoit la version 20 (la 19 s'est perdue).
scène → {"type":"snapshot"}
serveur → {"type":"etat","instantane":true,"version":20,…}      ← sans animation
```

## 7. Scénario de reconnexion (REC-15, REC-21, REC-23)

1. Le Wi-Fi coupe 30 s en pleine présentation, à la diapositive 5 de la scène.
2. L'écran de scène n'a plus de `pong` depuis 30 s : il affiche un bandeau « connexion perdue » mais
   **conserve** la diapositive 5 (mieux vaut une diapositive figée qu'un écran vide).
3. Il retente la connexion avec les délais 0,5 s → 1 s → 2 s → 5 s (puis toutes les 5 s).
4. Wi-Fi rétabli : connexion, message `auth`, puis l'instantané `etat` (version courante, `instantane: true`).
5. L'écran **remplace** son état sans rejouer les diapositives manquées : il affiche directement la
   diapositive courante (objectif : moins de 2 s).
6. Côté opérateur, une commande envoyée pendant la coupure est **renvoyée avec le même `id`** : si le serveur
   l'avait déjà appliquée, il répond `deja_traitee` ; sinon il la traite (ou la rejette si la version a changé).
   Aucune commande n'est perdue ni dupliquée.

## 8. Décisions

| N° | Décision |
|---|---|
| D36 | `pytest-asyncio` (dev) pour tester le consumer. |
| D37 | `TerminalTirage` devient `Terminal` avec un type `tirage` ou `scene`. |
| D38 | Le jeton de la scène passe par le premier message, jamais par l'URL. |
| D39 | Le plan des diapositives est calculé à « Préparer l'affichage » puis figé ; il ne contient que des références. |
| D40 | Le jury se raccorde à l'itération 4. |
| D41 | Une seule présentation active par session ; la connexion se fait sur la session. |
