# Chapitre 30 — Dupliquer un concours (REC-02)

## Objectif
Préparer une nouvelle édition en un geste : « Dupliquer vers une nouvelle édition » reprend **catégories, épreuves, barèmes et séries** d'une édition précédente (§7).

## Règles retenues (décision D54)
| Reprise | Pas reprise |
|---|---|
| Catégories (discipline, âges, effectif prévu, règles de classement et de départage) | Candidats, participations, prestations, tirages |
| Épreuves (P, T, réglages RM-21, mode d'affichage, affichage scène) — remises « en préparation » | Sessions, terminaux, jurés et leurs codes |
| Barème : critères (libellé, maximum, coefficient) ; le **critère prioritaire** désigne le critère *de la copie* | Notes, évaluations, classements, validation de la configuration (RM-31) |
| Séries : questions **recréées** (jamais partagées avec l'original), même ordre | |

- La copie est en **brouillon** : le responsable du client doit **valider de nouveau** la configuration (RM-31).
- **Corpus (RM-23, RM-27)** : si la version du corpus d'origine est encore validée ou active, la copie la reprend et les passages sont **revérifiés** dans cette version.
  Sinon la copie n'a pas de version, les séries à passages coraniques ne sont pas copiées, et un avertissement l'explique.
- **Clé du client (RM-20)** : la copie reste dans le même client ; la mission cible est une mission de ce client à laquelle l'auteur a accès.
- **Qui** : l'administrateur, ou un opérateur affecté à la mission ; pas le responsable client (le prestataire exécute).
- Tout ou rien (une transaction) ; l'opération est **journalisée** (`concours.duplique`).

## Fichiers
- `apps/concours/services.py` : `dupliquer_concours` et `ResultatDuplication`.
- `apps/concours/admin.py` : l'action et son formulaire (`DuplicationForm`) ; `templates/admin/concours/dupliquer.html`.
- `apps/concours/tests/test_duplication.py` : 18 tests nommés d'après REC-02 / RM-20.

## Commandes (PowerShell)
```powershell
pytest apps\concours\tests\test_duplication.py
python manage.py runserver   # puis /admin/ → Concours → cocher un concours → « Dupliquer vers une nouvelle édition »
```

## Résultat attendu
La copie apparaît en brouillon avec les mêmes catégories, épreuves, critères et séries ; un message récapitule les nombres copiés.

**Question :** pourquoi recrée-t-on les questions au lieu de réutiliser celles de l'édition précédente dans les nouvelles séries ?
