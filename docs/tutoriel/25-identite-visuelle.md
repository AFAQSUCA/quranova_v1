# Chapitre 25 — Identité visuelle (logo et charte)

## Objectif
Faire porter le logo QURANOVA et sa palette (vert profond `#0a4c30`, or `#c9a227`) par l'interface, tout en
laissant la **marque du client** au premier plan sur les écrans vus du public (décision D49).

## Fichiers créés ou modifiés
- `static/img/quranova-logo.png` : logo détouré du fichier `logoquranova.jpg` (fond remplacé par du blanc, avec ImageMagick).
- `static/img/quranova-embleme.png` : l'étoile seule, pour l'en-tête de l'administration ; `favicon.png`.
- `static/css/charte.css` : variables de couleur, cartouche du client (`.marque-client`), sceau QURANOVA (`.marque-quranova`).
- `apps/clients/marque.py` : `marque_du_client(organisation)` → logo, nom et couleurs (re-validées, car elles finissent dans un attribut `style`).
- `templates/_marque.html` inclus par `scene.html`, `commande.html`, `jury.html`, `tirage.html` ; `templates/admin/base_site.html`
  (en-tête vert/or) ; `templates/accueil.html` ; `templates/documents/pv.html` (en-tête avec les deux logos).
- `config/urls.py` : titres de l'administration, et service des logos téléversés **en développement seulement**.
- `apps/clients/tests/test_marque.py`.

## Commandes (PowerShell)
```powershell
pytest apps\clients\tests\test_marque.py
cd frontend; npm run build
python manage.py runserver   # puis http://127.0.0.1:8000/ et /admin/
```

## Résultat attendu
Page d'accueil avec le logo, administration verte et or, écran scène avec le logo du client en haut à gauche
(ou son nom s'il n'en a pas) et un petit sceau QURANOVA en bas à gauche.

## À savoir
- Le logo fourni est un JPG de maquette : une version vectorielle (SVG) donnerait un rendu net sur grand écran.
- Écran du tirage : pas de marque du client (le terminal n'est lié à aucune session avant l'authentification).
- En production (phase 3), Nginx servira `/media/` (logos) ; `urls.py` ne le fait qu'en `DEBUG`.

**Question :** pourquoi re-valide-t-on la couleur dans `marque_du_client` alors que la base la contrôle déjà ?
