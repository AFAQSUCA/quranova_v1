# 19. Règles métier détaillées

Cette section formalise les règles qui devront être respectées par le logiciel. La règle RM-31 est ajoutée par la présente version ; les règles RM-02 à RM-05, RM-11, RM-18 et RM-26 sont adaptées au modèle d'exploitation.

| Référence | Règle métier |
|---|---|
| RM-01 | Chaque concours est rattaché à une organisation cliente. |
| RM-02 | L'opérateur enregistre le nombre de candidats attendu ou autorisé, selon les indications du client. |
| RM-03 | L'opérateur définit, pour chaque épreuve, le nombre de tirages par candidat (T) et le nombre de questions par série (P) ; le nombre de questions par candidat est calculé (Q = T × P). |
| RM-04 | L'opérateur enregistre les jurés désignés par le client et leurs affectations. |
| RM-05 | Les candidats sont inscrits par un opérateur à partir des informations transmises par le client. |
| RM-06 | Le candidat déclenche son tirage au sort par une action explicite sur l'écran de tirage. |
| RM-07 | Le tirage est effectué côté serveur et enregistré avant sa confirmation. |
| RM-08 | Le passage coranique est défini par une référence de début et une référence de fin. |
| RM-09 | Le texte affiché provient du corpus coranique validé. |
| RM-10 | Les versets sont présentés une diapositive à la fois. |
| RM-11 | L'avancement à la diapositive suivante est commandé manuellement par l'opérateur. |
| RM-12 | L'animation de transition s'effectue de droite vers la gauche. |
| RM-13 | Les écrans autorisés sont synchronisés sur la même diapositive courante. |
| RM-14 | Le candidat ne dispose ni des commandes de présentation, ni des fonctions de notation, ni du texte des versets. |
| RM-15 | Chaque juré saisit et valide ses propres notes. |
| RM-16 | Les notes manquantes sont distinguées des notes égales à zéro. |
| RM-17 | Le calcul des résultats applique uniquement le barème et les règles validés. |
| RM-18 | Le classement définitif est validé par le responsable client avant toute remise ou publication ; l'opérateur ne peut pas le valider. |
| RM-19 | Toute correction sensible est conservée dans l'historique. |
| RM-20 | Les données de deux clients restent isolées. |
| RM-21 | Réutilisation des séries tirées : réattribution à un autre candidat (défaut : non), au même candidat dans une autre épreuve (défaut : non), exclusion définitive déduite (défaut : oui) ; jamais deux fois la même série pour un candidat dans une épreuve (cf. §8.5). |
| RM-22 | Toutes les séries d'un lot contiennent exactement P questions. |
| RM-23 | Une série est composée de questions rattachées à la version du corpus du concours. |
| RM-24 | L'ouverture d'une épreuve est bloquée si le lot est insuffisant au regard de N, T et RM-21 (cf. §8.2). |
| RM-25 | Un tirage annulé conserve sa trace ; sa série n'est réintégrée au lot que si aucune de ses diapositives n'a été affichée. |
| RM-26 | Lorsque la double validation est activée (V2), le classement définitif requiert la validation du responsable client et la contre-validation du superviseur. |
| RM-27 | Chaque concours est rattaché à une version unique et immuable du corpus, figée à son ouverture. |
| RM-28 | Aucun tirage ne peut être déclenché pour un candidat mineur sans consentement parental enregistré. |
| RM-29 | Pendant qu'un concours est conduit sur un serveur de salle, il est verrouillé en écriture sur l'instance centrale (V2). |
| RM-30 | Toute commande d'affichage porte un identifiant unique et la version d'état attendue ; une commande obsolète ou déjà traitée est rejetée. |
| RM-31 | Un concours ne peut être ouvert qu'après validation de sa configuration (catégories, épreuves, barèmes, lots, règles de réutilisation) par le responsable client. |
