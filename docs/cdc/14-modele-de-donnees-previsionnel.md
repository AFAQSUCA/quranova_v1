# 14. Modèle de données prévisionnel

## 14.1. Principales entités

| Entité | Informations principales |
|---|---|
| Organisation (client) | Nom, logo, couleurs, coordonnées, responsable client, statut. |
| Mission | Organisation, concours, dates, lieu, opérateurs affectés, formule commerciale, statut. |
| Utilisateur | Identifiants, rôle, état du compte, authentification à deux facteurs. |
| Code d'accès de juré | Juré, session, code, période de validité. |
| Concours | Organisation, nom, édition, dates, format, version du corpus, double validation, état. |
| Catégorie | Concours, discipline, conditions d'admission, règles de classement. |
| Épreuve | Catégorie, règles, T, P, règles de réutilisation (RM-21), mode d'affichage, barème. |
| Candidat | Identité et coordonnées minimales, date de naissance si nécessaire. |
| Consentement | Candidat, représentant légal, version du formulaire, date, consentements accordés, document, statut. |
| Participation | Candidat, concours, catégorie, numéro de candidat, statut. |
| Session | Concours, date, lieu, ordre de passage, serveur de salle utilisé. |
| Prestation | Participation, épreuve, session, rang dans l'ordre de passage, état. |
| Version du corpus, Sourate, Verset, Traduction | Cf. §12. |
| Passage coranique | Référence de début, référence de fin, version du corpus. |
| Question | Type (passage coranique ou énoncé), contenu, organisation. |
| Série | Lot, libellé, questions ordonnées (exactement P), statut de disponibilité. |
| Lot | Épreuve, séries. |
| Tirage | Prestation, série, rang (1 à T), horodatage, terminal déclencheur, identifiant de demande, statut, motif d'annulation. |
| Affectation de jury | Juré, épreuve. |
| Critère de notation | Épreuve, libellé, maximum, coefficient. |
| Évaluation | Juré, prestation, notes par critère, observation, statut de validation. |
| Événement de présentation | Prestation, version d'état, commande, auteur, horodatage. |
| Incident | Concours, auteur, description, statut. |
| Historique d'audit | Auteur, action, date, objet, terminal, empreinte chaînée. |

## 14.2. Règles d'intégrité

- un tirage ne peut pas être enregistré pour une participation non admise ;
- une série doit appartenir au lot de l'épreuve concernée et contenir exactement P questions ;
- un tirage validé ne peut pas être remplacé silencieusement ;
- une évaluation ne peut être validée que par le juré concerné ;
- un classement définitif ne peut être remis ou publié avant validation par le responsable client ;
- les données d'un client ne sont jamais visibles dans le concours d'un autre client ;
- les données du corpus coranique ne peuvent pas être modifiées depuis l'application.
