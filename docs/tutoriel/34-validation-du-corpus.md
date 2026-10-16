# Chapitre 34 — Validation du corpus et procès-verbal du référent (phase 4, B ; jalon J0)

## Objectif
Donner un vrai chemin à la validation du corpus : l'administrateur imprime un procès-verbal, le référent coranique relit un échantillon et signe, puis l'administrateur enregistre la validation.
Jusqu'ici, seule une validation « d'essai » (`creer_demo`) existait.

## Fichiers
- `apps/coran/validation.py` : `controles_automatiques` (5 contrôles dont l'**aller-retour** avec le fichier source retrouvé **par son empreinte**), `echantillon_de_relecture`,
  `valider_version`, `activer_version`.
- `apps/coran/models.py` : `ValidationCorpus` (qui, quand, quel référent, résultats des contrôles ; jamais modifiée ni supprimée) + migration.
- `apps/coran/documents.py`, `templates/documents/pv_corpus.html` : le procès-verbal (HTML imprimable et PDF).
- `apps/coran/views.py`, `urls.py` : pages du procès-verbal, **administrateur seulement** (404 pour les autres).
- `apps/coran/admin.py`, `templates/admin/coran/valider_corpus.html` : actions « Enregistrer la validation » et « Activer ».
- Tests : `test_validation_corpus.py` (18), `test_pv_corpus.py` (12), sur les **vrais fichiers Tanzil**.
- Procédure humaine : `docs/recette/validation-du-corpus.md`.

## Points à comprendre
- **Aller-retour indépendant du parseur** : on relit les textes bruts du fichier par expression régulière et on les compare, dans l'ordre canonique, à la base. Un verset altéré en base
  (même par du SQL direct) fait échouer le contrôle ; testé.
- **Échantillon reproductible** : les versets « tirés » (≥ 1 %) sont classés par `SHA-256(empreinte | référence)`, sans générateur aléatoire : le procès-verbal réimprimé demain porte le même échantillon
  que celui signé aujourd'hui, et son empreinte est enregistrée avec la validation.
- **Rien ne se valide si un contrôle échoue**, y compris si le fichier source est introuvable.
- **Une version validée est figée** : on ne la valide pas deux fois, on ne la modifie plus (RM-27). Activer exige « validée » et une seule version active par riwāya.

## Commandes (PowerShell)
```powershell
pytest apps\coran\tests\test_validation_corpus.py apps\coran\tests\test_pv_corpus.py
python manage.py runserver     # /admin/ -> Versions du corpus -> Procès-verbal à signer
```

## Résultat attendu
Les tests passent ; le procès-verbal fait une quinzaine de pages (≈ 170 versets) avec le texte arabe correctement affiché.

**Question :** pourquoi retrouve-t-on le fichier source par son empreinte plutôt que par son nom de fichier ?
