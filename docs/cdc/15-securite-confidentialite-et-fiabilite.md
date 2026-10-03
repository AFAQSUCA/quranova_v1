# 15. Sécurité, confidentialité et fiabilité

Le référentiel de vérification retenu est l'**OWASP ASVS niveau 1** pour la V1 et la V2, et le **niveau 2** comme prérequis à toute ouverture en libre-service (V3).

## 15.1. Authentification et autorisations

- comptes nominatifs pour l'administrateur QURANOVA, les opérateurs et les responsables clients ; authentification à deux facteurs obligatoire pour l'administrateur et les opérateurs ;
- mots de passe d'au moins 12 caractères, hachage Argon2 ou PBKDF2 ;
- jurés : code personnel valable pour une session uniquement, désactivé à la clôture de la session ;
- tablette de tirage : ouverte en mode kiosque par l'opérateur ; le candidat appelé est fixé par l'opérateur ;
- contrôle des permissions côté serveur, y compris sur les messages WebSocket ;
- limitation des tentatives de connexion ; désactivation immédiate d'un compte ;
- les écrans de jury et de commande ne sont pas déconnectés pendant une prestation en cours.

## 15.2. Sécurité applicative

| Menace | Mesures exigées |
|---|---|
| XSS | • échappement automatique des gabarits Django et de Vue.js ; interdiction de `v-html` sur des données saisies<br>• politique CSP sans script en ligne |
| CSRF | • jetons CSRF Django, y compris pour les requêtes HTMX<br>• cookies `Secure`, `HttpOnly`, `SameSite=Lax`<br>• contrôle de l'origine à l'ouverture des connexions WebSocket |
| Injection SQL | Usage exclusif de l'ORM Django ou de requêtes paramétrées. |
| IDOR | • contrôle d'autorisation au niveau de chaque objet et de chaque canal temps réel<br>• filtre systématique par client (cf. §13.4)<br>• identifiants UUID |
| Import de fichiers | Contrôle du type et de la taille des fichiers CSV/Excel importés ; aucune formule exécutée ; neutralisation des cellules commençant par =, +, - ou @ lors des exports tableur. |
| Réseau de salle | Réseau dédié chiffré, mot de passe changé à chaque mission, aucun appareil extérieur, interfaces de gestion accessibles depuis les seuls terminaux de l'opérateur. |

**Validation côté serveur :**

Toute donnée reçue (formulaires, fichiers importés, messages WebSocket, paquets de concours) est validée côté serveur. La validation côté navigateur n'a qu'une fonction ergonomique.

**Journalisation des opérations sensibles :**

- connexions, tirages et annulations, retours à la diapositive précédente, saisie et correction de notes, validation des résultats, import de candidats, consultation des données de mineurs, export ;
- journal en ajout seul, chaque entrée comportant l'empreinte de la précédente ; extrait joint au procès-verbal remis au client ;
- aucun mot de passe ni code d'accès en clair dans les journaux.

**Gestion des secrets :**

- aucun secret dans le dépôt Git (fichier d'environnement exclu, analyse automatique des secrets avant chaque envoi) ;
- rotation annuelle des secrets, et immédiate lors du départ d'un opérateur ou en cas de suspicion de compromission ;
- chiffrement du disque des serveurs de salle et des disques de sauvegarde.

**Vérification avant la première mission :**

- autoévaluation selon la liste de contrôle OWASP ASVS niveau 1 ;
- analyses automatiques : Bandit, pip-audit, npm audit, et analyse OWASP ZAP sur l'application en fonctionnement ;
- aucune vulnérabilité critique ou élevée ouverte ;
- un test d'intrusion réalisé par un tiers indépendant est obligatoire avant toute mise en ligne de l'instance centrale accessible aux clients (V2) et avant toute ouverture en libre-service (V3).

## 15.3. Protection des résultats

Les notes sont enregistrées avec l'identité du juré et l'heure de validation. Les corrections laissent une trace. Les notes ne sont pas visibles du candidat pendant l'évaluation, sauf si le règlement du client prévoit explicitement une communication particulière.

## 15.4. Protection du tirage au sort

Le tirage est effectué par le serveur selon la procédure de §8.5, avec un générateur aléatoire cryptographiquement sûr (module `secrets` de Python). Il est résistant aux doubles clics, aux requêtes répétées et aux actualisations de page.

Le système enregistre : le candidat et la participation ; l'épreuve et la prestation ; la série attribuée ; la date et l'heure ; le terminal ayant déclenché le tirage ; le statut ; toute annulation, avec motif et auteur. L'historique des tirages figure dans le procès-verbal remis au client.

## 15.5. Sauvegardes et continuité

- sauvegarde automatique de la base toutes les 15 minutes pendant une session, sur un disque externe chiffré relié au serveur de salle (perte de données maximale : 15 minutes) ;
- sauvegarde complète à la fin de chaque journée de concours, conservée sur un second support ; copie chiffrée en ligne dès qu'Internet est disponible (V2) ;
- conservation des sauvegardes : 30 jours après la clôture de la mission, puis suppression (les données archivées suivent les durées de §16.3) ;
- test de restauration sur l'ordinateur de secours avant chaque saison de concours et au moins une fois par trimestre ;
- procédures d'incident en salle décrites en §13.6.
