# 6. Acteurs et gestion des rôles

L'application applique un système de permissions fondé sur le rôle de l'utilisateur, l'organisation cliente concernée et le concours auquel il est affecté.

## 6.1. Rôles

| Acteur | Côté | Responsabilités principales |
|---|---|---|
| Administrateur QURANOVA | Prestataire | Gérer l'application, les clients, les opérateurs, les serveurs de salle et les paramètres généraux ; importer le corpus coranique validé. |
| Opérateur | Prestataire | Paramétrer le concours du client (catégories, épreuves, candidats, jurés, lots), conduire les sessions, commander le diaporama, produire les documents de résultats. |
| Responsable client | Client | Valider la configuration du concours (barème, séries, règles), consulter le déroulement, valider le classement définitif, recevoir les résultats. |
| Superviseur du concours (V2) | Client ou tiers désigné | Observer le déroulement, contrôler la régularité des opérations, contre-valider les résultats lorsque la double validation est activée. |
| Juré | Client | Suivre l'affichage des versets de la prestation et noter les prestations qui lui sont attribuées. |
| Candidat | Client | Déclencher son tirage au sort lorsqu'il y est autorisé. |
| Public | — | Consulter les informations et classements rendus publics (V2). |

## 6.2. Séparation entre exécution et validation

Le prestataire **exécute** le concours ; le client le **valide**. Cette séparation est la garantie de transparence offerte au client : l'opérateur ne peut pas valider seul les résultats d'un concours qu'il a conduit.

| Action | Opérateur | Responsable client | Superviseur (V2) |
|---|---|---|---|
| Paramétrer le concours, les épreuves et les lots | Oui | Validation de la configuration | Lecture |
| Importer et modifier les candidats | Oui | Lecture | Lecture |
| Commander le diaporama | Oui | Non | Non |
| Annuler un tirage | Oui, avec motif | Alerté | Alerté |
| Consulter le journal d'audit | Oui | Oui | Oui |
| Ouvrir un incident | Oui | Oui | Oui |
| Valider le classement définitif | Non | Oui | Contre-validation si activée |
| Générer et remettre les documents de résultats | Oui, après validation | Reçoit | Reçoit |

**Limites du superviseur (V2) :**

- il ne peut ni créer, ni modifier, ni supprimer un candidat, une catégorie, une épreuve, une série ou un juré ;
- il ne peut pas déclencher un tirage ni commander le diaporama ;
- il ne peut ni saisir, ni modifier, ni supprimer une note ;
- il n'a accès qu'aux concours pour lesquels il a été désigné.

## 6.3. Règles d'accès

- un opérateur n'accède qu'aux concours des missions qui lui sont affectées ; l'administrateur QURANOVA accède à tous les concours, chaque accès étant journalisé ;
- un responsable client n'accède qu'aux concours de son organisation ;
- un candidat ne peut pas accéder aux interfaces de notation ou de commande de l'affichage ;
- un juré ne peut noter que les prestations des épreuves qui lui sont attribuées ;
- le public n'a accès qu'aux données explicitement publiées ;
- les classements provisoires et définitifs sont distingués ;
- les changements de rôle et les opérations sensibles sont journalisés (cf. §15.2).

> **Exigence importante :** masquer un bouton ne suffit pas à sécuriser une fonction. Les droits doivent être vérifiés côté serveur pour chaque opération protégée, y compris pour les messages reçus par le canal temps réel.
