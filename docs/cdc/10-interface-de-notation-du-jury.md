# 10. Interface de notation du jury

## 10.1. Principe

Chaque juré disposera d'un écran de notation indépendant de l'écran de projection. Il pourra consulter les références coraniques et suivre le défilement des diapositives tout en saisissant ses notes.

## 10.2. Fonctionnalités de notation

Chaque juré pourra :

- voir la série tirée et les références des passages coraniques ;
- suivre le verset courant en temps réel ;
- remplir les critères de notation ;
- saisir une observation, si cette fonction est activée ;
- enregistrer un brouillon ;
- valider sa note ;
- consulter l'état de sa propre évaluation.

Les notes devront être enregistrées séparément par juré. Une note validée ne pourra être modifiée que sur demande motivée du juré, approuvée par le responsable client, avec conservation de l'ancienne valeur, de la nouvelle valeur, de l'auteur, de l'approbateur, de la date et du motif.

## 10.3. Calcul des résultats

Le système devra prendre en charge :

- le total par juré ;
- la moyenne des notes valides ;
- les coefficients éventuels ;
- les pénalités et bonus si le règlement les prévoit ;
- les notes manquantes ;
- le classement provisoire ;
- le classement définitif après validation.

La formule dépendra du barème configuré.

Les notes ne devront pas être considérées comme nulles lorsqu'un juré n'a pas encore évalué un candidat. L'interface devra distinguer une note manquante d'une note égale à zéro.

## 10.4. Gestion des égalités et des désaccords

L'application devra permettre de définir une règle de départage, par exemple :

- moyenne générale ;
- priorité à un critère défini par le règlement ;
- épreuve supplémentaire ;
- décision documentée du comité de concours (instance désignée par le règlement du concours).

Le système ne devra pas inventer automatiquement une règle en cas d'égalité. Il appliquera uniquement la règle prévue par le règlement du client et validée par le responsable client.
