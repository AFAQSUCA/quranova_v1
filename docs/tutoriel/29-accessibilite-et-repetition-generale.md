# Chapitre 29 — Accessibilité et répétition générale (phase 3, étape 6.3)

## Objectif
Prouver que les écrans respectent WCAG 2.1 AA (§18.2, REC-34) et préparer la répétition générale chronométrée (REC-40) avec les pannes provoquées
(REC-21, 23, 36, 41).

## Pool de connexions (rappel de l'étape 6.2)
`psycopg[binary,pool]` (nouvelle dépendance acceptée) : en production, Django réutilise des connexions PostgreSQL déjà ouvertes au lieu d'en ouvrir une
par requête. `DB_POOL=0` le coupe pour un diagnostic ; `DB_POOL_MAX` règle la taille (20 par défaut). Test : `test_reglages_production.py`.

## Ce qui a été fait
1. **Audit réel dans Chromium** avec axe-core sur chaque écran (script `scripts/audit-accessibilite.mjs`, sans dépendance ajoutée au projet).
   Quatre défauts trouvés et corrigés : titre absent de l'administration (mon gabarit d'en-tête avait écrasé le bloc `title`), pas de `<h1>` à l'accueil,
   zoom interdit sur le tirage, sceau QURANOVA hors repère.
2. **Deux écarts au cahier des charges** corrigés : zone `aria-live` sur la commande (phase et rang annoncés, sans relire le verset) ;
   le balayage de la scène n'est plus coupé par « réduire les animations » (§18.2 : écran collectif).
3. **Garde-fous automatisés** : `apps/commun/tests/test_accessibilite.py` (langue, titre, zoom, animations) et un test vitest de la zone live.
4. **Documents de recette** : `docs/recette/accessibilite.md` (audit + vérifications manuelles) et `docs/recette/repetition-generale.md`
   (installation chronométrée en 7 étapes, déroulement fictif, pannes provoquées, bilan à signer).

## Commandes (PowerShell)
```powershell
pip install -r requirements\dev.txt
pytest apps\commun\tests\test_accessibilite.py
cd frontend; npm test; cd ..
# audit navigateur : voir docs\recette\accessibilite.md
node scripts\audit-accessibilite.mjs C:\Temp\a11y.json
```

## Résultat attendu
Tests verts ; l'audit affiche « Aucune violation : audit réussi. ».

## Limites
Un audit automatique ne trouve qu'une partie des problèmes d'accessibilité (environ un tiers) : la liste « à vérifier à la main » sur les tablettes et le projecteur
réels reste obligatoire.

**Question :** pourquoi garde-t-on le balayage sur l'écran scène alors que l'utilisateur a demandé « réduire les animations » sur son système ?
