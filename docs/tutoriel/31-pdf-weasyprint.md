# Chapitre 31 — Procès-verbal et classements en PDF (WeasyPrint)

## Objectif
Remettre au client, comme le demande §11 et §17.1, le **procès-verbal** et les **classements par catégorie** en PDF (le tableur CSV existait déjà).

## Principe : une seule source de vérité
Le PDF est fabriqué à partir du **même HTML** que la version imprimable du navigateur (`templates/documents/pv.html`). Conséquence : tout ce qui est vrai de
l'HTML l'est du PDF (REC-16 : seuls les classements validés par le responsable du client figurent ; mineurs en initiales sans consentement de publication).
Les classements par catégorie ont leur propre gabarit court (`classements.html`).

## Fichiers
- `apps/resultats/pdf.py` : `html_vers_pdf(html)` et le **chercheur de ressources** : WeasyPrint ne peut lire que `/static/` et `/media/` de ce serveur
  (logos) ; jamais le réseau, jamais `file:///etc/passwd`, jamais `../`. Si WeasyPrint ou Pango manque : `PdfIndisponibleError` avec un message clair.
- `apps/resultats/documents.py` : `proces_verbal_pdf`, `classements_pdf` (journalisés : `document.pv_pdf_genere`, `document.classements_pdf_genere`).
- `apps/resultats/views.py`, `urls.py` : `documents/pv/<id>/pdf/` et `documents/classements/<id>/pdf/` — mêmes contrôles d'accès que l'HTML (RM-20, REC-29) ;
  si le PDF est impossible, la page répond 503 avec un lien vers la version imprimable.
- `apps/concours/admin.py` : liens « Procès-verbal (PDF) » et « Classements par catégorie (PDF) » dans la fiche du concours.
- `Dockerfile` : paquets Pango et polices ; `DEMARRAGE.md` : installation sous Windows (MSYS2) ; `requirements/base.txt` : `weasyprint>=68,<71` (dépendance validée).
- `apps/resultats/tests/test_pdf.py` : 19 tests (sécurité du chercheur, contenu via `pdftotext`, REC-16, REC-29, REC-42 en PDF, vue 503).

## Commandes (PowerShell)
```powershell
pip install -r requirements\dev.txt
pytest apps\resultats\tests\test_pdf.py
# puis dans /admin/ : Concours → fiche d'un concours → « Procès-verbal (PDF) »
```

## Résultat attendu
Les tests passent (ou sont « skipped » si Pango n'est pas installé sur votre PC). Le PDF affiche l'en-tête (logo du client et QURANOVA), les classements,
l'historique des tirages, les incidents, le journal d'audit et la pagination « Page 1 / 2 ».

## Ce qui n'a pas pu être vérifié ici
Les paquets système du `Dockerfile` (le dépôt Debian est bloqué dans l'environnement de développement) et l'installation sous Windows (MSYS2) : à contrôler chez vous
avec `.\scripts\demarrer.ps1` puis le lien PDF de la fiche d'un concours.

**Question :** pourquoi interdit-on à WeasyPrint d'aller chercher des images sur Internet, alors que le HTML est généré par notre propre code ?
