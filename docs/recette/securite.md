# Analyse de sécurité automatisée (REC-28 et REC-25 à REC-29)

REC-28 exige « aucune vulnérabilité critique ou élevée à l'analyse automatisée ». Trois outils, un seul script :

```powershell
.\scripts\audit-securite.ps1
```

| Outil | Ce qu'il examine | Où |
|---|---|---|
| **bandit** | le code Python de `apps/` et `config/` (shell, SQL construit à la main, XML non protégé, aléa pour la sécurité…) | `bandit.yaml` ; garde-fou pytest : `test_rec28_l_analyse_statique_bandit_ne_signale_aucune_alerte` |
| **pip-audit** | les dépendances Python (`requirements\dev.txt`, donc aussi la production) face aux vulnérabilités connues | nécessite Internet |
| **npm audit** | les dépendances du front (niveau élevé et critique) | nécessite Internet |

Ces outils ne sont que des **outils de développement** : ils ne sont pas installés dans l'image du serveur de salle (`requirements/base.txt`).

## Premier passage (bac à sable)

**bandit** : 1 alerte élevée, 1 moyenne, 7 faibles. Aucune n'était exploitable, mais quatre ont mené à de vrais durcissements :

| Alerte | Traitement |
|---|---|
| B324 SHA-1 (poignée de main WebSocket du simulateur de charge) | `usedforsecurity=False` : la RFC 6455 l'impose, ce n'est pas un usage de sécurité |
| B314/B405 analyse XML (import du corpus) | **durcissement** : un XML contenant `DOCTYPE` ou `ENTITY` est refusé avant l'analyse (attaques par entités). Aucune dépendance `defusedxml` ajoutée. Les vrais fichiers Tanzil n'en ont pas (testé) |
| B404/B603 sous-processus (`pg_dump`, `pg_restore`, `verifier_audit`) | arguments en liste, jamais de shell ; marqués `# nosec` avec l'explication ; **durcissement** associé ci-dessous |
| B311 aléa du simulateur de charge | marqué `# nosec` : simple désynchronisation, rien de secret |

**Trouvaille hors bandit, corrigée** : `restaurer` construisait `DROP DATABASE "<nom>"` en collant le nom saisi en ligne de commande. Un nom contenant un guillemet sortait de
l'identifiant. Maintenant : nom validé (`[A-Za-z_][A-Za-z0-9_]{0,62}`) **avant tout**, et identifiants SQL quotés par `psycopg.sql.Identifier`
(8 tests de noms hostiles).

**pip-audit** : `pytest 8.4.2` (dépendance de développement) portait la vulnérabilité PYSEC-2026-1845 ; mise à jour vers `pytest>=9.0.3,<10`, toute la suite repasse. Plus aucune alerte.

**npm audit** : 0 vulnérabilité.

## Ce que l'analyse automatisée ne remplace pas
Un scanner ne trouve ni une règle métier oubliée, ni un contrôle d'accès manquant : REC-25 (IDOR), REC-26 (XSS), REC-27 (CSRF), REC-29 (cloisonnement) restent couverts par
leurs **tests** (`apps/commun/tests/test_securite.py` et les tests de chaque application). Avant le concours pilote, relancer le script et relire toute nouvelle alerte.
Un scan dynamique (par exemple OWASP ZAP contre la pile Docker) pourra compléter la recette si le client l'exige : à décider.
