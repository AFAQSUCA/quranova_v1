# 26. Décisions techniques structurantes

| Sujet | Décision | Référence |
|---|---|---|
| Modèle d'exploitation | Outil interne du prestataire ; vente de missions et non de licences. | §3.2 |
| Déploiement | Local d'abord : serveur de salle sur réseau Wi-Fi dédié ; instance centrale en V2. | §13.1 |
| Interfaces | Gabarits Django et HTMX pour la gestion ; Vue.js 3 pour les quatre écrans temps réel. | §13.3 |
| Séparation des clients | `organization_id` et filtrage applicatif ; RLS PostgreSQL en prérequis de la V3. | §13.4 |
| Temps réel | WebSocket, état versionné détenu par le serveur, commandes idempotentes ; repli SSE et long-polling en V2. | §13.5 |
| Continuité | Onduleur, routeur et ordinateur de secours, sauvegardes toutes les 15 minutes. | §13.6, §15.5 |
| Corpus coranique | Source unique Tanzil, Uthmani, Hafs, versionnée et validée. | §12 |
| Tirage | Déclenché par le candidat, exécuté par le serveur, règles de réutilisation configurables. | §8 |
| Validation des résultats | Par le responsable client, jamais par l'opérateur seul. | §6.2, RM-18 |
