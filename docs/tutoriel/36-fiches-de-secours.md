# Chapitre 36 — Fiches de notation de secours (phase 4, C2 ; §13.6)

## Objectif
Prévoir le pire cas du §13.6 : **panne simultanée des deux ordinateurs**. Les fiches sont imprimées la veille ; en cas de panne les jurés notent sur papier ; l'opérateur les saisit ensuite
**avec un motif**. Rien ne s'invente : les règles de notation (barème, RM-16) s'appliquent toujours.

## Fichiers
- `apps/jury/fiches.py` : `fiches_html` / `fiches_pdf` (impression), `saisir_fiche` (saisie différée), `references`.
- `templates/documents/fiches_secours.html` : une fiche A4 par prestation et par juré affecté (barème, coefficient, case de note, observation, signature, référence unique `FS-<passage>-<juré>`, consigne).
  Le candidat y figure par **numéro, prénom et initiale** (une fiche circule en salle). La **série tirée** n'est pas connue à l'impression : le juré l'écrit à la main.
- `apps/jury/models.py` + migration : `Evaluation.saisie_differee`, `motif_saisie_differee`, `saisie_par`, `reference_fiche` ; contrainte en base : pas de saisie différée sans motif ni auteur.
- `apps/jury/views.py`, `urls.py` : `documents/fiches/<session>/` (+ `/pdf/`) pour le personnel affecté (404 sinon, RM-20) ; lien dans la fiche d'une **session**.
- `apps/prestations/admin.py` : action **« Saisir une fiche de secours (papier) d'un juré »** (formulaire adapté au barème de l'épreuve) ; `templates/admin/prestations/saisir_fiche.html`.
- `templates/documents/pv.html` : tableau « Évaluations saisies depuis une fiche de secours » (juré, fiche, motif, saisi par).

## Règles de la saisie différée
- **Motif obligatoire** ; qui, quand, quelle fiche : tracés (audit `evaluation.saisie_differee`, procès-verbal).
- **Tous les critères renseignés** : une case vide est refusée (**jamais** convertie en zéro, RM-16) ; un « 0 » écrit est une vraie note. Tout ou rien.
- Seuls le personnel affecté et l'administrateur saisissent ; le juré doit être affecté à l'épreuve ; la prestation doit avoir un tirage valable (pas en attente, pas annulée).
- Pas de remplacement d'une évaluation existante : pour la corriger, on passe par la **correction approuvée** par le responsable client (REC-17).
- Quand **tous** les jurés affectés ont leur évaluation validée, la prestation est **clôturée** (journalisée), comme après une notation normale.

## Commandes (PowerShell)
```powershell
python manage.py migrate
pytest apps\jury\tests\test_fiches_secours.py
# /admin/ -> Sessions -> une session -> « Fiches de notation de secours » (la veille)
# /admin/ -> Prestations -> cocher UNE prestation -> « Saisir une fiche de secours (papier) d'un juré »
```

## Résultat attendu
23 tests passent ; l'impression donne une fiche par prestation et par juré ; la saisie crée une évaluation validée et tracée.

## Limite assumée
Ce flux suppose que le tirage de la prestation existe dans l'application (restaurée depuis la dernière sauvegarde). Un tirage fait **pendant** la panne n'est pas saisissable ici : à enregistrer d'abord
(procédure d'incident du guide de l'opérateur, étape D).

**Question :** pourquoi refuse-t-on une fiche dont une case est vide, au lieu de la saisir quand même en laissant ce critère « manquant » ?
