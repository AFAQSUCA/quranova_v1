# 7. Description détaillée des fonctionnalités

## 7.1. Module de gestion des clients

L'application gère les organisations clientes du prestataire. Chaque client dispose d'un espace dont les données sont séparées de celles des autres clients (cf. §13.4).

Fonctionnalités attendues :

- création et modification d'une organisation cliente ;
- enregistrement du nom, du logo, des coordonnées et du responsable client ;
- rattachement des missions et des concours au client ;
- archivage des concours terminés ;
- consultation de l'historique des concours réalisés pour le client ;
- personnalisation visuelle des écrans (logo, couleurs) pour chaque client ;
- restitution des données du client (cf. §17).

## 7.2. Module de création et de paramétrage des concours

L'opérateur doit pouvoir créer un concours en définissant les paramètres suivants. La configuration est soumise à la validation du responsable client avant l'ouverture du concours.

| Paramètre | Niveau | Description |
|---|---|---|
| Nom du concours | Concours | Intitulé officiel de l'événement. |
| Organisation | Concours | Client pour lequel le concours est réalisé. |
| Édition | Concours | Millésime ou numéro d'édition. |
| Format | Concours | Présentiel (V1) ; en ligne ou hybride (V2). |
| Dates | Concours | Dates de début et de fin. |
| Version du corpus | Concours | Version du corpus coranique utilisée, figée à l'ouverture du concours (cf. §12.3). |
| Catégories | Concours | Mémorisation, tajwid, tilawa, questions ou catégories personnalisées. |
| Nombre de candidats | Catégorie | Effectif prévu ou limite d'inscription. |
| Tirages par candidat (T) | Épreuve | Nombre de tirages effectués par chaque candidat pour l'épreuve. |
| Questions par série (P) | Épreuve | Nombre de questions contenues dans chaque série du lot. |
| Questions par candidat (Q) | Épreuve | Valeur calculée : Q = T × P (non saisissable, cf. §8.2). |
| Réutilisation des séries | Épreuve | Règles de réattribution des séries tirées (cf. RM-21). |
| Mode d'affichage | Épreuve | Arabe seul, ou arabe avec traduction française. |
| Affichage sur l'écran scène | Épreuve | Activé ou désactivé (cf. §9.1). |
| Nombre de jurés | Concours, catégorie ou épreuve | Nombre de jurés affectés. |
| Barème | Épreuve | Critères, notes maximales et pondérations. |
| Règles de classement | Catégorie | Moyenne, total, élimination ou départage. |
| Double validation | Concours | Contre-validation du classement par un superviseur (V2). |
| État | Concours | Brouillon, ouvert, en cours, suspendu, terminé ou archivé. |

Les paramètres structurants (T, P, barème, règles de réutilisation, version du corpus) sont verrouillés lorsque le concours est en cours, sauf modification exceptionnelle motivée, approuvée par le responsable client et enregistrée dans l'historique.

L'application permet de **dupliquer** un concours d'une édition précédente (catégories, épreuves, barèmes, séries) afin d'accélérer la préparation des missions récurrentes.

## 7.3. Module de gestion des candidats

Les candidats sont inscrits par l'opérateur à partir des informations transmises par le client ; ils ne s'inscrivent pas eux-mêmes.

L'opérateur pourra :

- importer la liste des candidats depuis un fichier CSV ou Excel selon un modèle fourni au client, avec contrôle des doublons et rapport d'erreurs ;
- ajouter, modifier ou retirer un candidat ;
- créer sa participation dans une catégorie et vérifier les conditions de participation ;
- lui attribuer un numéro unique ;
- enregistrer le consentement parental lorsque le candidat est mineur (cf. §16.2) ;
- générer l'ordre de passage (tirage au sort de l'ordre ou ordre fourni par le client) ;
- corriger une erreur avant le démarrage de sa prestation.

Les champs collectés respectent le principe de minimisation (cf. §16) : nom, prénom, date de naissance si la catégorie dépend de l'âge, sexe si pertinent, ville, structure représentée et catégorie.

## 7.4. Module de gestion des jurys

L'opérateur pourra :

- ajouter les jurés ;
- définir leur rôle et leurs catégories de compétence ;
- attribuer des épreuves ou des prestations à chaque juré ;
- définir le barème applicable ;
- suivre la saisie des notes ;
- détecter les évaluations manquantes ;
- clôturer la notation lorsque les conditions sont satisfaites.

Chaque juré dispose d'un accès personnel. En salle, il se connecte sur la tablette qui lui est attribuée au moyen d'un code personnel à usage limité à la session, généré par l'opérateur ; aucune adresse électronique n'est exigée. Il ne peut pas modifier les notes des autres jurés.

Le nombre de jurés pourra être défini globalement pour le concours ou séparément pour chaque catégorie ou épreuve. Cette distinction devra être prise en charge dans la conception.
