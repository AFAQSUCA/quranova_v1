# 24. Planning et phasage

Le planning repose sur un développeur unique disposant d'environ **15 à 20 heures par semaine**, en parallèle de ses autres activités. Il vise une première mission payante **avant le Ramadan 2027** (début attendu vers le 8 février 2027, date à confirmer), période de forte demande. Le démarrage est fixé à la semaine du 5 octobre 2026.

| Phase | Semaines | Période indicative | Contenu | Jalon |
|---|---|---|---|---|
| 0. Cadrage et corpus | S1 – S2 | 5 – 16 oct. 2026 | Environnement de développement, import et contrôles du corpus, désignation du référent coranique. | J0 : corpus validé |
| 1. Conception | S3 – S4 | 19 – 30 oct. 2026 | Modèle de données, maquettes des quatre écrans temps réel, protocole des messages. | J1 : conception figée |
| 2. Développement V1 — itération 1 | S5 – S6 | 2 – 13 nov. 2026 | Clients, concours, catégories, épreuves, import des candidats, jurés. | — |
| 2. Développement V1 — itération 2 | S7 – S8 | 16 – 27 nov. 2026 | Passages coraniques, séries, lots, tirage et écran de tirage. | — |
| 2. Développement V1 — itération 3 | S9 – S10 | 30 nov. – 11 déc. 2026 | Diaporama synchronisé, commande, écran scène, reprise d'état. | J2 : parcours d'une prestation démontré |
| 2. Développement V1 — itération 4 | S11 – S12 | 14 – 25 déc. 2026 | Notation, calculs, classements, procès-verbal PDF, sauvegardes, journal d'audit. | J3 : V1 complète |
| 3. Autorecette et kit | S13 – S14 | 28 déc. 2026 – 8 janv. 2027 | Tests REC, acquisition et configuration du kit, formation d'un premier opérateur, répétition générale. | J4 : V1 apte au pilote |
| 4. Concours pilote | S15 – S16 | 11 – 22 janv. 2027 | Concours réel, gratuit ou à tarif réduit, avec un client partenaire ; mesures et retours. | J5 : pilote réussi |
| 5. Corrections et lancement | S17 – S18 | 25 janv. – 5 févr. 2027 | Corrections issues du pilote, supports commerciaux, démarchage. | J6 : offre commerciale lancée |
| 6. V2 | Après la saison | Mars – juin 2027 (8 à 10 semaines) | Instance centrale, synchronisation, certificats, exports JSON, concours en ligne, missions simultanées, test d'intrusion. | J7 : V2 en service |

**Gestion du risque de délai :**

- le chemin critique est le diaporama synchronisé (itération 3) : il est développé avant les fonctions de confort ;
- en cas de retard, les fonctions suivantes sont reportées à la V2 sans compromettre le pilote : duplication de concours, personnalisation visuelle, journal d'audit chaîné (remplacé par un journal simple) ;
- le calendrier universitaire (examens, soutenance) est intégré dès la phase 0 et peut décaler le pilote après le Ramadan si nécessaire ;
- les fonctions déjà maîtrisées dans d'autres projets (Django, génération de PDF avec WeasyPrint) sont réutilisées.

**Ressources :**

- le prestataire : développement, conception, autorecette, conduite du pilote ;
- un référent coranique : environ 5 jours (validation du corpus, des traductions et du rendu) ;
- un à deux opérateurs à former avant le pilote ;
- un client pilote et trois jurés volontaires pour la répétition générale ;
- un conseil juridique ponctuel (contrat de mission, formalités ARTCI).
