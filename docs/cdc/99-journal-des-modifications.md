# Journal des modifications

Le tableau ci-dessous recense les modifications apportées à la version 1.1 pour produire la présente version 2.0. Le journal détaillé du passage de la version 1.0 à la version 1.1 figure dans le document de la version 1.1.

| N° | Section | Type | Description | Justification |
|---|---|---|---|---|
| 1 | Page de garde | Modification | Version 2.0 ; nature « référentiel interne » ; maîtrise d'ouvrage et réalisation assurées par le prestataire. | Le porteur du projet développe et exploite lui-même l'outil. |
| 2 | §1 | Modification | Résumé exécutif réécrit : QURANOVA devient l'outil interne d'un prestataire qui vend des missions ; fonctionnement local d'abord. | Nouveau modèle d'exploitation. |
| 3 | §2 | Ajout | Termes ajoutés : prestataire, mission, opérateur, responsable client, serveur de salle, instance centrale. « Organisation » rendu équivalent à « client ». | Éviter la confusion entre la mission commerciale et la prestation du candidat. |
| 4 | §3 | Modification | Section étendue : contexte, modèle d'exploitation (§3.2) et justification économique (§3.3). | Expliciter le modèle « vente de missions ». |
| 5 | §4 | Modification | Objectifs adaptés : import des candidats, fonctionnement sans Internet, documents remis au client. | Besoins propres à l'exploitation en mission. |
| 6 | §5 | Modification | Périmètre découpé en V1 (pilote), V2 (industrialisation), V3 (évolutions) et exclusions. | Développement par un développeur seul, priorisé. |
| 7 | §6 | Modification | Rôles revus : administrateur QURANOVA, opérateur, responsable client, superviseur (V2). Séparation entre exécution (prestataire) et validation (client). | Garantie de transparence pour le client. |
| 8 | §7.1 | Modification | « Gestion multi-organisations » remplacé par « gestion des clients » (missions, personnalisation visuelle, historique). | Les clients n'administrent pas eux-mêmes leur espace. |
| 9 | §7.2 | Clarification | Validation de la configuration par le responsable client ; duplication d'un concours d'une édition précédente. | Gain de temps sur les missions récurrentes. |
| 10 | §7.3 | Ajout | Import des candidats depuis un fichier CSV ou Excel avec rapport d'erreurs ; génération de l'ordre de passage. | Les données proviennent du client. |
| 11 | §7.4 | Clarification | Accès des jurés par code personnel limité à la session, sur tablette du prestataire. | Simplicité en salle, sans adresse électronique. |
| 12 | §8 à §10 | Clarification | « Organisateur de concours » remplacé par « opérateur » ; mode « concours en ligne » reporté en V2. | Cohérence avec les nouveaux rôles. |
| 13 | §10.4, §11 | Modification | Validation du classement définitif par le responsable client ; liste des documents remis au client en fin de mission. | L'opérateur ne valide pas seul les résultats. |
| 14 | §12 | Clarification | Rôles du superadministrateur attribués à l'administrateur QURANOVA. | Cohérence terminologique. |
| 15 | §13.1 | Modification | Principe « local d'abord » : serveur de salle sur réseau Wi-Fi dédié en V1, instance centrale en V2 ; configuration de la salle. | Fiabilité sans Internet ; coût d'hébergement quasi nul en V1. |
| 16 | §13.2 | Modification | Pile simplifiée : WeasyPrint pour les PDF ; Celery et supervision reportés en V2. | Réduction de la charge de développement. |
| 17 | §13.3 | Modification | Interfaces hybrides : gabarits Django et HTMX pour la gestion, Vue.js 3 limité aux quatre écrans temps réel. | Productivité d'un développeur seul. |
| 18 | §13.4 | Modification | Séparation des clients par `organization_id` et filtrage applicatif ; RLS reportée et rendue obligatoire avant la V3. | Risque d'accès croisé faible tant que seul le prestataire administre. |
| 19 | §13.5 | Modification | WebSocket seul sur le réseau local ; repli SSE et long-polling limité à l'instance centrale (V2). | Réseau de salle maîtrisé. |
| 20 | §13.6 | Ajout | Procédures d'incident en salle (électricité, routeur, tablette, serveur) et synchronisation avec l'instance centrale. | Remplace la stratégie de serveur local de secours de la v1.1, devenue le mode normal. |
| 21 | §13.7, §13.8 | Modification | Schéma d'architecture et modules mis à jour (clients, missions, synchronisation). | Nouveau mode de déploiement. |
| 22 | §14 | Modification | Entités « Mission » et « Code d'accès de juré » ajoutées ; entités liées aux demandes de données simplifiées. | Nouveau modèle d'exploitation. |
| 23 | §15 | Modification | Référentiel OWASP ASVS niveau 1 pour V1 et V2 (niveau 2 avant V3) ; sécurité du réseau de salle ; autoévaluation avant la première mission ; test d'intrusion exigé avant la V2 en ligne ; sauvegardes toutes les 15 minutes sur disque externe. | Exigences proportionnées au risque. |
| 24 | §16 | Modification | Le client devient responsable de traitement, le prestataire sous-traitant ; clause contractuelle dans le contrat de mission ; durées de conservation raccourcies ; formalités ARTCI du prestataire. | Répartition des rôles propre au modèle de prestation. |
| 25 | §17 | Modification | « Export et portabilité » remplacé par « Restitution et portabilité » : remise des documents et des exports à la fin de chaque mission. | Le client ne dispose pas d'un accès en libre-service. |
| 26 | §18.1 | Modification | Objectifs chiffrés recalibrés sur un serveur de salle (500 candidats, 30 terminaux) ; ajout de l'installation en salle, de la préparation et de la continuité. | Objectifs de 100 concours simultanés sans objet. |
| 27 | §19 | Modification | RM-02 à RM-05, RM-11, RM-18 et RM-26 adaptées ; RM-31 ajoutée (validation de la configuration par le client). | Nouveaux rôles. |
| 28 | §20 | Modification | Scénarios adaptés ; scénario E remplacé par la panne du serveur de salle. | Nouveau mode de déploiement. |
| 29 | §21 | Modification | Recette transformée en autorecette, répétition générale et concours pilote ; tests de charge recalibrés ; REC-22 reporté en V2 ; REC-36 à REC-42 adaptés ou ajoutés. | Le réalisateur est aussi l'utilisateur. |
| 30 | §22 | Ajout | Exploitation des missions : déroulé type, kit matériel chiffré, équipe d'opérateurs. | Industrialiser les missions. |
| 31 | §23 | Modification | Livrables internes (code, guide de l'opérateur, fiches mémo, modèles destinés aux clients, supports commerciaux). | Plus de prestataire de développement externe. |
| 32 | §24 | Modification | Planning d'un développeur seul (15 à 20 h par semaine) en 18 semaines jusqu'au lancement commercial, avec un concours pilote avant le Ramadan 2027 ; V2 après la saison. | Ressources réelles du projet. |
| 33 | §25 | Modification | Budget de développement externe remplacé par un modèle économique : offre, investissement, coûts récurrents, seuil de rentabilité, scénarios. | Rentabilité fondée sur les missions. |
| 34 | §26, §27 | Modification | Décisions structurantes et conclusion mises à jour. | Cohérence d'ensemble. |
| 35 | Ensemble | Correction | Titres marqués d'un astérisque en v1.1 et non modifiés en v2.0 : marque retirée (convention désormais relative à la v1.1). | Lisibilité du suivi des versions. |
