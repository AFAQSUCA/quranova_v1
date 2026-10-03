# 18. Exigences non fonctionnelles

## 18.1. Objectifs chiffrés

| Domaine | Exigence cible | Méthode de mesure |
|---|---|---|
| Capacité d'un serveur de salle | Un concours de 500 candidats, 30 terminaux connectés simultanément | REC-19 |
| Temps de réponse (réseau local) | 95 % des requêtes inférieures à 300 ms ; tirage confirmé en moins de 1 s | REC-19 |
| Temps réel | Propagation d'une commande à tous les écrans en moins de 300 ms pour 95 % des commandes | REC-20 |
| Reconnexion d'un écran | Retour à l'état courant en moins de 2 s après rétablissement du réseau | REC-21, REC-23 |
| Continuité en salle | Aucune interruption de plus de 5 minutes imputable au dispositif ; autonomie électrique d'au moins 1 heure | REC-36, REC-41 |
| Restauration | Perte maximale de 15 minutes ; reprise sur l'ordinateur de secours en moins de 15 minutes | REC-36 |
| Installation en salle | Dispositif opérationnel en moins de 45 minutes à l'arrivée sur site | Répétition générale (REC-40) |
| Préparation d'un concours | Import et paramétrage d'un concours type en moins de 2 heures | Mesure lors du concours pilote |
| Documents | Procès-verbal généré en moins de 30 secondes | REC-42 |
| Missions simultanées (V2) | Au moins 3 missions le même jour, avec 3 serveurs de salle | Recette V2 |
| Disponibilité de l'instance centrale (V2) | 99 % par mois hors maintenance ; aucune maintenance un jour de mission | Sonde externe |
| Fiabilité | Aucun saut involontaire de diapositive | REC-07, REC-24 |
| Intégrité coranique | Texte identique octet par octet au corpus validé | REC-30 |
| Maintenabilité | Couverture des tests automatisés d'au moins 70 % sur les modules métier et 100 % des règles RM | Rapport de couverture |
| Compatibilité | Tablettes Android 10 ou supérieur (Chrome) ; Chrome, Edge et Firefox récents ; écran scène 1920 × 1080 | Recette sur le matériel du kit |

## 18.2. Accessibilité

Le référentiel d'accessibilité retenu est **WCAG 2.1, niveau AA**, pour toutes les interfaces à l'exception du contenu coranique lui-même, dont la présentation obéit aux règles de §9. Critères mesurables exigés :

- contraste d'au moins 4,5:1 pour le texte courant, 3:1 pour le texte de grande taille et les composants d'interface ;
- totalité des fonctions utilisables au clavier, focus toujours visible, absence de piège au clavier ;
- agrandissement à 200 % sans perte de contenu, et affichage sur 320 pixels CSS de large sans défilement horizontal ;
- étiquette associée à chaque champ de formulaire ; messages d'erreur identifiant le champ et la correction attendue ;
- attributs de langue (`lang="fr"` pour l'interface, `lang="ar" dir="rtl"` pour le texte coranique) ;
- annonce des changements d'état importants (tirage enregistré, verset courant) aux technologies d'assistance sur les écrans jury et commande ;
- respect de la préférence « réduction des animations » sur les écrans individuels (fondu à la place du balayage), l'écran scène conservant le balayage de RM-12 ;
- absence de contenu clignotant plus de trois fois par seconde ;
- exigence propre au projet : cibles tactiles d'au moins 44 × 44 pixels pour le bouton de tirage et les commandes du diaporama ;
- mesure : zéro violation « critique » ou « sérieuse » à l'audit automatisé (axe-core) sur les parcours clés, et vérification manuelle des écrans temps réel sur les tablettes utilisées en salle.
