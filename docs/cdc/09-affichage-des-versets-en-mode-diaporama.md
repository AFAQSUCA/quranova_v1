# 9. Affichage des versets en mode diaporama

## 9.1. Principe visuel

Après validation du tirage, les versets devront être présentés un par un, comme dans un diaporama de présentation, sur les écrans de l'opérateur, des jurés et, si l'épreuve le prévoit, de la scène. Un verset trop long pour rester lisible à la taille de texte configurée est découpé en plusieurs diapositives.

L'affichage des versets sur l'écran scène est un paramètre de l'épreuve (activé ou désactivé). Pour les épreuves de mémorisation, l'opérateur veille à ce que l'écran scène ne soit pas visible du candidat ; à défaut, il désactive ce paramètre.

## 9.2. Règles d'animation

L'animation devra respecter les règles suivantes :

- afficher une seule diapositive à la fois, c'est-à-dire un verset entier ou un segment de verset ;
- découper un verset long uniquement entre deux mots, sans jamais altérer, réordonner ni dupliquer le texte ; la concaténation des segments d'un verset doit être strictement identique au texte du corpus ; chaque segment porte la référence du verset et son rang (ex. « 2:282 — 1/3 ») ;
- présenter le texte arabe avec une police adaptée au texte Uthmani et une direction de lecture de droite à gauche ;
- effectuer la transition entre deux diapositives par un balayage de droite vers la gauche ;
- afficher les références de la sourate et du verset ;
- conserver la même diapositive tant que l'opérateur ne demande pas de passer à la suivante ;
- empêcher le déclenchement involontaire de plusieurs transitions simultanées ;
- assurer une présentation lisible sur un vidéoprojecteur, un grand écran et un ordinateur ;
- proposer un mode plein écran ;
- permettre de configurer la taille du texte, les marges et les éléments visuels.

> **Distinction technique importante :** le sens de l'animation de la diapositive ne doit pas modifier l'ordre du texte arabe ni sa direction typographique. Le balayage est un effet visuel de transition ; la lecture du verset reste de droite à gauche.

## 9.3. Commandes de l'opérateur

L'interface de commande comportera les boutons suivants :

| Bouton | Fonction |
|---|---|
| Préparer l'affichage | Charger la série tirée et initialiser le diaporama. |
| Démarrer la prestation | Autoriser le début de la présentation. |
| Diapositive suivante | Passer à la diapositive suivante avec l'animation. |
| Diapositive précédente | Revenir à la diapositive précédente, si autorisé ; action journalisée. |
| Mettre en pause | Bloquer temporairement l'avancement. |
| Reprendre | Réactiver les commandes. |
| Réafficher la diapositive | Rejouer l'affichage de la diapositive courante. |
| Terminer la prestation | Clôturer le défilement et ouvrir la validation des notes. |

L'avancement à la diapositive suivante doit être une action explicite de l'opérateur. Aucun changement automatique ne doit se produire.

Une action de retour à la diapositive précédente devra être journalisée. Le système devra également empêcher qu'un double-clic ou une latence réseau fasse sauter accidentellement plusieurs diapositives : chaque commande porte un identifiant unique et la version d'état attendue, et le serveur rejette toute commande dont la version ne correspond pas à l'état courant (RM-30, cf. §13.5).

## 9.4. Synchronisation des écrans

Les écrans de l'opérateur, des jurés et de la scène doivent recevoir le même état de présentation :

- numéro ou nom du candidat ;
- numéro de la sourate et du verset courant, et rang du segment le cas échéant ;
- rang de la question dans la série ;
- état de la prestation ;
- état de pause ;
- libellé de la série tirée ;
- numéro de version de l'état (compteur croissant).

Les changements d'état sont transmis en temps réel par WebSocket, avec des mécanismes de repli et de reprise d'état décrits en §13.5. Un écran qui se reconnecte retrouve la diapositive courante sans redémarrer le tirage.
