# 5. Périmètre fonctionnel et versions

Le développement est découpé en trois versions. Seule la V1 conditionne la première mission payante.

## 5.1. V1 — Version minimale opérationnelle (concours pilote)

- gestion des clients, des concours, des catégories, des épreuves et des sessions ;
- import des candidats depuis un fichier CSV ou Excel fourni par le client, et saisie manuelle ;
- gestion du consentement parental pour les mineurs (enregistrement du formulaire signé) ;
- gestion des jurés et de leurs affectations ;
- définition des passages coraniques par références et constitution des séries et des lots ;
- tirage au sort déclenché par le candidat et exécuté par le serveur ;
- diaporama synchronisé avec commande manuelle par l'opérateur ;
- écrans de notation des jurés sur tablette ;
- calcul des résultats et classements provisoire et définitif ;
- génération du procès-verbal de résultats et du classement en PDF ;
- fonctionnement complet sur le serveur de salle, sans Internet ;
- journal d'audit des opérations sensibles ;
- sauvegarde du serveur de salle sur support externe.

## 5.2. V2 — Industrialisation des missions

- instance centrale en ligne et synchronisation avec les serveurs de salle (cf. §13.6) ;
- publication en ligne des résultats et page publique du concours ;
- certificats personnalisés en PDF ;
- export complet des données d'un client (CSV, JSON) ;
- mode « concours en ligne » pour les candidats à distance ;
- gestion de plusieurs opérateurs et de plusieurs missions simultanées ;
- superviseur et double validation des résultats.

## 5.3. V3 — Évolutions possibles

- ouverture en libre-service à des organisations extérieures (nécessitant alors la Row-Level Security, un audit de sécurité externe et des tests de charge, cf. §13.4) ;
- notifications SMS ou WhatsApp ;
- diffusion vidéo en direct intégrée ;
- suivi pédagogique des candidats tout au long de l'année ;
- riwāya autres que Hafs ʿan ʿĀṣim.

## 5.4. Exclus du périmètre

- commercialisation de licences ou d'abonnements ;
- paiement en ligne des frais d'inscription ;
- application mobile native ;
- inscription des candidats en libre-service.
