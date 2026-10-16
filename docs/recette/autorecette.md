# Autorecette — état des critères REC (§21)

Légende : **A** = couvert par un test automatisé (`pytest` / `npm test`) · **M** = procédure manuelle à jouer
(avec qui, sur quel matériel) · **P3** = livré par la phase 3 (voir plus bas) · **⚠** = fonctionnalité absente.

| REC | Sujet | État | Où / comment |
|---|---|---|---|
| 01 | Deux clients indépendants | A | `apps/clients/tests/`, `apps/commun/tests/test_modele_du_client.py` |
| 02 | Créer un concours, puis le dupliquer | A | saisie : `apps/concours/tests/` ; duplication : `test_duplication.py` (action « Dupliquer vers une nouvelle édition ») |
| 03 | Paramètres et Q = T × P | A | `apps/concours/tests/test_configuration.py::test_rm03_q_est_calcule_t_fois_p` |
| 04 | Passage 2:142 à 2:150 | A | `apps/coran/tests/test_passages.py`, `test_regles_passage.py` |
| 05 | Référence invalide | A | `apps/questions/tests/test_services.py` |
| 06 | Un tirage valide | A | `apps/prestations/tests/test_tirage.py`, `test_api_tirage.py` |
| 07 | Double clic | A | `test_concurrence.py` (vrai parallélisme PostgreSQL) |
| 08 | Diapositive suivante, balayage D→G | A (état) · M (animation) | Test de l'état : `apps/presentation/tests/`; l'animation se regarde sur écran scène |
| 09 | Pas de clic = pas de changement | A | `apps/presentation/tests/test_commandes.py` |
| 10 | Écrans synchronisés | A | `test_consumer.py::test_rec10_…` ; M sur le matériel réel |
| 11 | Note enregistrée pour le bon juré | A | `apps/jury/tests/test_evaluations.py` |
| 12 | Note omise ≠ zéro | A | idem |
| 13 | Classement = calcul manuel | A | `apps/resultats/tests/test_services.py::test_rec13_…` (TODO(human) `calcul.py`) |
| 14 | Accès non autorisé | A | consumers, commandes, API jury/tirage |
| 15 | Reconnexion | A | `test_consumer.py::test_rec15_rec23_…` + `frontend/src/commun/client.test.ts` |
| 16 | PV : résultats validés seulement | A | `apps/resultats/tests/test_documents.py` (HTML) et `test_pdf.py` (PDF) |
| 17 | Correction d'une note validée | A | `apps/jury/tests/test_evaluations.py`, `apps/resultats/tests/test_validation.py` |
| 18 | Restauration | A | `apps/commun/tests/test_sauvegarde.py` |
| 19 | Charge : 500 candidats, 30 terminaux | outil prêt · objectifs à mesurer sur le matériel cible | `simuler_charge` ; résultats et goulots : `docs/recette/charge.md` |
| 20 | Propagation < 300 ms (95 %) | outil prêt · à mesurer sur le matériel cible | idem (p95 mesuré : 306–612 ms dans le bac à sable) |
| 21 | Coupure Wi-Fi 30 s | A (logique client) · M (matériel) | Backoff testé dans `client.test.ts` ; coupure réelle à jouer en répétition |
| 23 | Redémarrage scène + juré | A | `test_rec15_rec23_…`, brouillon serveur du juré |
| 24 | Deux « suivante » simultanées | A | `test_commandes.py`, `test_consumer.py` |
| 25 | IDOR | A | `test_rec25_…` dans admin, jury, présentation, tirage |
| 26 | XSS | A | PV échappé, tableur neutralisé, **import** (`apps/commun/tests/test_securite.py`) |
| 27 | CSRF | A | `test_securite.py::test_rec27_…` |
| 28 | Injection SQL | A | tests d'injection (`test_securite.py`, `test_sauvegarde.py`) + analyse automatisée : `scripts/audit-securite.ps1` (bandit, pip-audit, npm audit : aucune alerte) — voir `docs/recette/securite.md` |
| 29 | Opérateur A ne voit pas le client B | A | `apps/utilisateurs/tests/test_acces_missions.py` |
| 30 | Intégrité du corpus | A | `apps/coran/tests/test_controles_corpus.py`, `test_import.py` |
| 31 | Références invalides | A | `apps/coran/tests/test_passages.py` |
| 32 | Traversée de sourates | A | idem |
| 33 | Verset 2:282 segmenté | A | `apps/presentation/tests/test_segmentation.py` |
| 34 | Accessibilité | A (audit navigateur) + M | `scripts/audit-accessibilite.mjs` : 0 violation axe ; `test_accessibilite.py` ; vérifications manuelles : `docs/recette/accessibilite.md` |
| 35 | Réutilisation des séries, lot épuisé | A | `test_rm21_selection.py`, `test_tirage.py::test_lot_epuise_…` |
| 36 | Panne du serveur de salle < 15 min | M + P3 | procédure §5 de `docs/recette/installation-serveur-de-salle.md` ; à chronométrer sur le matériel |
| 37 | Import avec erreurs | A | `apps/candidats/tests/test_import_csv.py` |
| 38 | Mineur sans consentement | A | `test_rm28_…` (service et API) |
| 39 | Opérateur ne valide pas | A | `test_validation.py::test_rec39_…` |
| 40 | Répétition générale, installation < 45 min | M | `docs/recette/repetition-generale.md` (checklist chronométrée) |
| 41 | Coupure secteur (onduleur) | M | §4 de `docs/recette/repetition-generale.md` |
| 42 | PV de 500 candidats < 30 s | A | `test_documents.py::test_rec42_…` (HTML) et `test_pdf.py::test_rec42_…` (PDF) |

## Lacunes à décider

1. **REC-08 / REC-10 / REC-21 / REC-41** : une part reste physique (animation, matériel, Wi-Fi, onduleur) : à jouer à
   la répétition générale (REC-40).
