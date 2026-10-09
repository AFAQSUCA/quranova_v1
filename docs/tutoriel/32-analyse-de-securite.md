# Chapitre 32 — Analyse de sécurité automatisée (REC-28)

## Objectif
Mettre en place trois analyses automatiques et corriger ce qu'elles trouvent : **bandit** (code Python), **pip-audit** (dépendances Python), **npm audit** (dépendances du front).

## Ce qui a été fait
- `requirements/dev.txt` : `bandit` et `pip-audit` (dépendances de développement validées), `pytest>=9.0.3` (correctif de sécurité).
- `bandit.yaml` et `scripts/audit-securite.ps1` ; garde-fou pytest dans `apps/commun/tests/test_securite.py`.
- Durcissements : XML refusé s'il porte `DOCTYPE`/`ENTITY` (`apps/coran/importation.py`) ; nom de base de restauration validé et identifiants SQL quotés
  (`apps/commun/sauvegarde.py`) ; SHA-1 marqué non-sécuritaire (`apps/commun/charge/client_ws.py`).
- Détails et traitement de chaque alerte : `docs/recette/securite.md`.

## Commandes (PowerShell)
```powershell
pip install -r requirements\dev.txt
.\scripts\audit-securite.ps1
pytest apps\commun\tests\test_securite.py apps\commun\tests\test_sauvegarde.py apps\coran\tests\test_import.py
```

## Résultat attendu
« Aucune alerte : audit de sécurité réussi. » ; les tests passent.

## À retenir
- Une alerte se traite de trois façons : corriger le code, justifier (`# nosec Bxxx` + explication sur la ligne au-dessus), ou accepter un risque documenté. Jamais ignorer sans trace.
- Le meilleur résultat de l'étape n'est pas venu de bandit mais de sa lecture : le `DROP DATABASE` construit à la main n'était signalé par aucun outil.

**Question :** pourquoi bandit et pip-audit sont-ils dans `requirements/dev.txt` et pas dans `requirements/base.txt` ?
