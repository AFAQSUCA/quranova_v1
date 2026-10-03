# 20. Scénarios d'utilisation à couvrir

## Scénario A — Préparer une mission

1. L'administrateur QURANOVA crée le client (ou le sélectionne) et la mission, et y affecte un opérateur.
2. L'opérateur crée le concours, éventuellement par duplication de l'édition précédente.
3. Il importe la liste des candidats transmise par le client et corrige les erreurs signalées.
4. Il enregistre les consentements parentaux des mineurs.
5. Il enregistre les jurés et leurs affectations.
6. Il configure T et P, définit les passages coraniques et compose les séries des lots ; le système contrôle la suffisance des lots.
7. Le responsable client valide la configuration.
8. L'opérateur prépare le serveur de salle, imprime les fiches de secours et ouvre le concours le jour J.

## Scénario B — Conduire une prestation

1. L'opérateur appelle le candidat attendu selon l'ordre de passage.
2. Le candidat se présente devant la tablette de tirage.
3. Il clique sur le bouton de tirage.
4. Le serveur sélectionne et enregistre la série.
5. Les écrans autorisés reçoivent le résultat du tirage.
6. L'opérateur démarre la prestation.
7. Les diapositives défilent une à une, au rythme des clics de l'opérateur.
8. Les jurés saisissent leurs notes sur leur tablette.
9. L'opérateur termine la prestation.
10. Les notes sont validées et la prestation est clôturée.

## Scénario C — Valider et remettre les résultats

1. Le système vérifie que les évaluations requises sont présentes.
2. Il calcule les résultats selon le barème applicable.
3. L'opérateur présente les classements provisoires au responsable client.
4. Les éventuelles anomalies sont résolues.
5. Le responsable client valide les résultats ; le superviseur les contre-valide si la double validation est activée.
6. Le classement définitif est affiché sur l'écran scène ; le procès-verbal est généré, signé et remis au client.

## Scénario D — Plusieurs clients

1. Le prestataire réalise des missions pour deux clients différents.
2. Chaque concours possède ses propres candidats, jurés, séries, sessions et résultats.
3. Un opérateur affecté à la mission du client A ne voit pas les données du client B.
4. L'administrateur QURANOVA conserve une vue générale de toutes les missions.

## Scénario E — Panne du serveur de salle

1. Le serveur de salle tombe en panne pendant une session.
2. L'opérateur démarre l'ordinateur de secours et y restaure la dernière sauvegarde du disque externe.
3. Les écrans se reconnectent à l'ordinateur de secours, qui reprend la même adresse sur le réseau local.
4. La session reprend à la dernière prestation clôturée ; une prestation interrompue est reprise à partir de son tirage enregistré, ou rejouée avec motif si le tirage est postérieur à la sauvegarde.
5. L'incident est consigné dans le procès-verbal.
