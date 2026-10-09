# Accessibilité des parcours clés (REC-34, §18.2 : WCAG 2.1 AA)

## Audit automatisé

`scripts/audit-accessibilite.mjs` pilote un vrai navigateur (Chromium) sur les parcours clés : accueil, administration (connexion, accueil,
prestations), tirage, commande (diaporama en cours), scène (verset affiché), jury (connexion, liste, évaluation). Pour chaque écran :

- **axe-core** (règles WCAG 2 A/AA, WCAG 2.1 A/AA et bonnes pratiques) : zéro violation exigée (le CdC tolère 0 « critique/sérieuse » ; on vise 0 tout court) ;
- **cibles tactiles** ≥ 44 × 44 px (tirage, commande, jury) ;
- **focus visible** sur chaque élément atteint au clavier (25 Tab) ;
- **pas de défilement horizontal** à 320 px de large et à 200 % d'agrandissement ;
- **langue du texte coranique** : `lang="ar" dir="rtl"` sur le verset de la scène.

Aucune dépendance n'est ajoutée au projet : les outils vont dans un dossier temporaire.

```powershell
# 1. Outils (une fois, dossier hors du projet)
mkdir $env:TEMP\outils-a11y ; cd $env:TEMP\outils-a11y
npm init -y ; npm install axe-core playwright-core
# 2. Données : creer_demo, puis jeton de scène, code de juré, prestation appelée (voir chapitre 29)
# 3. Fichier de paramètres C:\Temp\a11y.json  (modèle dans l'en-tête du script), puis, depuis la racine du projet :
node scripts\audit-accessibilite.mjs C:\Temp\a11y.json
```
Windows : mettre `"chromium": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"` dans le fichier de paramètres.

### Résultat du dernier audit (bac à sable, Chromium, données de démonstration)
Zéro violation sur tous les écrans listés ci-dessus. Trois défauts réels avaient été trouvés puis corrigés :

| Défaut trouvé | Écran | Correction |
|---|---|---|
| pas de `<title>` (grave) | toute l'administration (mon gabarit d'en-tête avait écrasé le bloc) | bloc `title` rétabli dans `templates/admin/base_site.html` |
| pas de titre de niveau 1 | accueil | le logo est dans un `<h1>` |
| zoom interdit (`user-scalable=no`) | tirage | retiré (WCAG 1.4.4) |
| contenu hors repère | sceau QURANOVA | regroupé dans un `<aside aria-label>` |

Deux écarts au CdC ont aussi été corrigés sans passer par axe : la **zone live de la commande** (phase et rang de diapositive annoncés, le texte coranique
volontairement exclu) et le **balayage de la scène** qui était coupé par « réduire les animations » alors que §18.2 le conserve sur cet écran collectif.

## Garde-fous automatisés (pytest, vitest)
`apps/commun/tests/test_accessibilite.py` : langue et titre de chaque page, zoom autorisé, balayage conservé sur la scène, animation du tirage coupée en
mode « réduire les animations », aucune animation en boucle plus rapide que 3 Hz. `EcranCommande.test.ts` : zone live.

## À vérifier à la main (non automatisable)

À faire sur **les tablettes réellement utilisées en salle**, une fois :

- [ ] Texte lisible à 1 m sur l'écran de scène avec la taille de verset choisie ; contraste sur le projecteur réel (les projecteurs lavent les couleurs).
- [ ] Bouton de tirage atteint au pouce, tablette tenue d'une main, sans appuyer à côté (REC-07).
- [ ] Parcours complet de tirage au clavier seul (Tab, Entrée, Échap pour annuler la confirmation).
- [ ] Lecteur d'écran (NVDA, gratuit) sur la commande : la phase et la diapositive sont annoncées sans relire le verset.
- [ ] Agrandissement 200 % du navigateur sur la commande et sur le jury, sans contenu masqué.
- [ ] Aucun clignotement perceptible lors d'un enchaînement rapide de diapositives.
