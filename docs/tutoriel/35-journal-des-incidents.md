# Chapitre 35 — Journal des incidents en salle (phase 4, C1 ; §13.6)

## Objectif
Consigner pendant le concours ce qui s'est mal passé (coupure, panne de routeur, Wi-Fi coupé, tablette HS, contestation…) et ce qui a été fait. Le journal alimente la section
« Incidents » du procès-verbal, l'export de données et le bilan du pilote (livrable L-09). Jusqu'ici, seuls les tirages annulés figuraient au procès-verbal.

## Fichiers
- `apps/incidents/` : nouvelle application (`models.py`, `services.py`, `admin.py`, `exceptions.py`, migration, tests).
- `Incident` : type (liste du §13.6 + « autre »), gravité (mineure / bloquante), heure réelle, description, session et prestation facultatives, déclarant, résolution et son heure.
  Contraintes en base : la résolution ne précède pas l'incident ; pas de date de résolution sans texte.
- `services.py` : `declarer`, `resoudre`, `bilan` ; droits (personnel affecté à la mission seulement, RM-20), cohérence session/prestation avec le concours, journalisation `incident.declare` / `incident.resolu`.
- `admin.py` : l'opérateur déclare puis résout depuis l'administration ; **la déclaration d'origine n'est jamais réécrite** (champs en lecture seule), un incident résolu ne bouge plus, **personne ne supprime** ; le responsable client consulte.
- `apps/resultats/documents.py` et `templates/documents/pv.html` : section 3 du procès-verbal (bilan « 3 incidents déclarés, dont 1 bloquant », tableau, tirages annulés à part) et `incidents.csv` dans l'export.

## Points à comprendre
- **Traçabilité** : on peut compléter une déclaration en la résolvant, pas la corriger après coup. Un incident est un témoignage daté.
- **Heure réelle** : l'opérateur peut déclarer après coup (il était occupé à réparer) en indiquant l'heure de l'incident ; le futur est refusé (tolérance de 2 minutes pour l'horloge d'une tablette).
- **Échappement** : le texte saisi est échappé dans le procès-verbal et neutralisé dans le tableur (REC-26), testé.

## Commandes (PowerShell)
```powershell
python manage.py migrate
pytest apps\incidents
# /admin/ -> Incidents -> Ajouter
```

## Résultat attendu
26 tests passent ; le procès-verbal d'un concours avec incident affiche le type, la description, la résolution et la durée.

**Question :** pourquoi l'administration interdit-elle de modifier la description d'un incident déjà déclaré, alors qu'elle permet d'en saisir la résolution ?
