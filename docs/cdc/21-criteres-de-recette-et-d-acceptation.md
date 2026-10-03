# 21. Critères de recette et d'acceptation

Le prestataire étant à la fois réalisateur et utilisateur, la recette est une **autorecette** formalisée, complétée par une répétition générale et un concours pilote. Elle est conduite sur le matériel réel du kit de salle. La V1 est déclarée apte à la première mission payante lorsque tous les tests ci-dessous sont conformes, qu'aucune anomalie bloquante ne subsiste et que le concours pilote s'est déroulé sans incident bloquant.

| ID | Test | Résultat attendu |
|---|---|---|
| REC-01 | Créer deux clients | Les deux clients sont enregistrés indépendamment. |
| REC-02 | Créer un concours, par saisie puis par duplication | Les paramètres obligatoires sont enregistrés et contrôlés ; la duplication reprend catégories, épreuves, barèmes et séries. |
| REC-03 | Définir le nombre de candidats, de tirages par candidat, de questions par série et de jurés | Les paramètres sont appliqués ; Q = T × P est calculé. |
| REC-04 | Définir un passage coranique 2:142 à 2:150 | Le système reconnaît les 9 versets dans le bon ordre. |
| REC-05 | Saisir une référence invalide | Le système refuse la référence et explique l'erreur. |
| REC-06 | Déclencher un tirage | Un seul tirage valide est enregistré. |
| REC-07 | Cliquer deux fois rapidement sur le bouton de tirage | Aucun double tirage n'est créé. |
| REC-08 | Passer à la diapositive suivante | La diapositive suivante apparaît avec le balayage de droite vers la gauche. |
| REC-09 | Ne pas cliquer sur « Diapositive suivante » | La diapositive courante reste affichée. |
| REC-10 | Connecter tous les écrans du kit | Les écrans restent synchronisés. |
| REC-11 | Saisir une note de juré | La note est enregistrée pour le bon juré, la bonne prestation et le bon tirage. |
| REC-12 | Omettre une note | Le système signale une évaluation incomplète sans la convertir en zéro. |
| REC-13 | Calculer un classement | Les résultats correspondent au barème, vérifiés par un calcul manuel indépendant. |
| REC-14 | Tenter un accès non autorisé (juré vers commande, tirage vers notation) | L'accès est refusé côté serveur. |
| REC-15 | Déconnecter puis reconnecter un écran | L'écran retrouve l'état de présentation courant. |
| REC-16 | Générer les documents de résultats | Seuls les résultats validés par le responsable client figurent dans le procès-verbal définitif. |
| REC-17 | Corriger une note validée | La correction suit la procédure et laisse une trace. |
| REC-18 | Restaurer une sauvegarde | Les données récupérées sont cohérentes et exploitables. |
| REC-19 | Simulation de charge en salle : 500 candidats, 30 terminaux, une journée de concours accélérée | Objectifs de §18.1 atteints ; aucune erreur serveur. |
| REC-20 | Mesurer la propagation des commandes | 95 % des commandes affichées sur tous les écrans en moins de 300 ms. |
| REC-21 | Couper le Wi-Fi 30 secondes pendant une prestation | Tous les écrans retrouvent l'état courant en moins de 2 s après rétablissement ; aucune commande perdue ni dupliquée. |
| REC-23 | Redémarrer l'écran scène et une tablette de juré à la 5e diapositive | Les écrans affichent la 5e diapositive en moins de 2 s, sans relance du tirage ni perte du brouillon de notes. |
| REC-24 | Envoyer deux commandes « Diapositive suivante » simultanées | Une seule commande est appliquée. |
| REC-25 | IDOR : modifier les identifiants dans les URL et les messages WebSocket | Refus systématique ; aucune donnée divulguée. |
| REC-26 | XSS : saisir des charges de script dans les noms et observations, y compris par import | Contenu échappé ; aucune exécution. |
| REC-27 | CSRF : soumettre une requête forgée | Requête rejetée. |
| REC-28 | Injection SQL sur les champs, filtres et fichiers importés | Aucun effet ; aucune vulnérabilité critique ou élevée à l'analyse automatisée. |
| REC-29 | Un opérateur affecté au client A tente d'accéder aux données du client B | Accès refusé. |
| REC-30 | Contrôler l'intégrité du corpus | 114 sourates, 6 236 versets, empreinte conforme, export identique octet par octet. |
| REC-31 | Saisir des versets invalides : 2:287, 115:1, 0:1, 1:0, fin antérieure au début | Chaque référence est refusée avec un message explicite. |
| REC-32 | Traversée de sourates : 1:6 à 2:5 et 113:5 à 114:6 | Respectivement 7 versets et 7 versets, dans l'ordre canonique, basmala de la sourate 2 non numérotée. |
| REC-33 | Afficher le verset 2:282 avec une grande taille de texte | Le verset est segmenté entre deux mots ; la concaténation des segments est identique au corpus. |
| REC-34 | Accessibilité des parcours clés | Critères de §18.2 respectés. |
| REC-35 | Réutilisation des séries en configuration par défaut | Une série tirée n'est plus proposée ; lot épuisé : tirage bloqué avec message. |
| REC-36 | Simuler la panne du serveur de salle en cours de session | Reprise sur l'ordinateur de secours en moins de 15 minutes, conformément au scénario E. |
| REC-37 | Importer un fichier de candidats comportant des doublons, des champs manquants et des dates invalides | Rapport d'erreurs ligne par ligne ; aucune donnée invalide enregistrée. |
| REC-38 | Tirage pour un candidat mineur sans consentement enregistré | Tirage refusé avec message explicite. |
| REC-39 | Tentative de validation du classement par un opérateur | Validation refusée ; seul le responsable client peut valider. |
| REC-40 | Répétition générale : concours fictif de 20 candidats avec de vrais jurés, installation complète du kit | Déroulement complet sans anomalie bloquante ; installation en moins de 45 minutes. |
| REC-41 | Débrancher l'alimentation secteur pendant une prestation | Aucune interruption grâce à l'onduleur et aux batteries. |
| REC-42 | Générer le procès-verbal d'un concours de 500 candidats | Document conforme généré en moins de 30 secondes. |

Le test REC-22 (repli SSE et long-polling) est reporté à la recette de la V2, ce mécanisme ne concernant que l'instance centrale.

Les anomalies sont classées en trois niveaux : **bloquante** (fonction essentielle indisponible, atteinte à l'intégrité du texte, des tirages ou des notes, faille de sécurité critique ou élevée, fuite entre clients), **majeure** (fonction dégradée sans contournement raisonnable) et **mineure**. Le résultat de l'autorecette est consigné dans un procès-verbal daté, conservé avec le code source.
