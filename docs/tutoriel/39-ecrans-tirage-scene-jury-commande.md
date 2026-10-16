# Chapitre 39 — Design des écrans temps réel : tirage, scène, jury, commande

## Objectif
Donner aux quatre écrans Vue la même identité que l'administration (vert profond, or réservé à l'action principale), **en adaptant le design à l'appareil et à la distance de lecture** — sans toucher à la logique, aux protocoles ni aux règles (RM-12, RM-14, RM-30).

| Écran | Appareil | Principe de design |
|---|---|---|
| **Tirage** (`/tirage/`) | tablette du candidat, à bout de bras | fond vert, **une seule fiche papier** (numéro, prénom, épreuve) et **un seul gros bouton or** de 5 rem de haut ; l'attente est un anneau qui respire ; les erreurs sont une carte rouge, jamais un texte perdu |
| **Scène** (`/scene/<session>/`) | projecteur, lu de loin | tailles en `vw` (réglables avec + / −), verset dans un **cadre à double filet doré**, référence en pastille, emblème en veille ; le **balayage de droite à gauche (RM-12) est inchangé** |
| **Jury** (`/jury/<session>/`) | tablette du juré, en main | fiche claire : voyant « en direct », puces de prestations avec l'état de **ma** notation (liseré gris / or / vert), champs de note de 3,6 rem de haut, bouton **Valider** collé en bas de l'écran |
| **Commande** (`/commande/<session>/`) | ordinateur de l'opérateur | deux zones : à gauche **ce qui est affiché** (miniature de la scène), à droite le **pupitre** — « Diapositive suivante » en grand, « Terminer » à part en rouge |

## Ce qui a changé dans le code
| Fichier | Rôle |
|---|---|
| `frontend/src/commun/charte.css` | Jetons communs (couleurs, polices du système, ombres) importés par les quatre écrans. |
| `frontend/src/*/style.css` | Un style par écran. **Toutes les règles sont préfixées** (`.tirage`, `.scene`, `.jury`, `.commande`) : le build regroupe les styles dans un seul `frontend.css`, une règle non préfixée toucherait les quatre écrans (c'était déjà le cas de `h1` et `button` dans l'ancien style du tirage). |
| `EcranTirage.vue` | Classe racine `tirage`, classes `fiche` et `attente`. |
| `EcranScene.vue`, `EcranJury.vue` | Emblème décoratif (`aria-hidden`) ; l'adresse de l'image est une **constante** : Vite essaierait sinon de résoudre `/static/img/…` au build. |
| `EcranCommande.vue` | Classes `demarrer` et `danger` sur deux boutons. |

Aucun texte, aucun `role`, aucun `data-testid` n'a changé : les 95 tests du front passent tels quels.

## Choix de conception
- **Polices du système** (pas d'Inter) : le serveur de salle n'a pas Internet ; on ne charge aucune police distante.
- **Couleur jamais seule** : un voyant « en direct » a une pastille *et* un texte ; une prestation validée a un liseré vert *et* le mot « Validée ».
- **Or = action principale** (tirer, valider, suivante). Texte sur or : vert très foncé (7,4 : 1).
- **Cibles tactiles ≥ 3,4 rem** sur les tablettes ; `prefers-reduced-motion` coupe les animations des écrans individuels (tirage, jury) mais **pas** le balayage de la scène (§18.2 : écran collectif).
- **L'écran candidat ne reçoit jamais le texte d'un verset (RM-14)** : le design du tirage ne contient aucun verset, seulement « Série 4 ».

## Commandes (PowerShell)
```powershell
cd frontend
npm test            # 95 tests
npm run build       # recompile vers static\frontend\ (ignoré par Git : à refaire après chaque git pull)
cd ..
python manage.py runserver
```
Après un `git pull` qui modifie `frontend\`, relancer `npm run build` : sinon les écrans gardent l'ancien aspect.

## Résultat attendu
Quatre écrans cohérents avec l'administration ; les captures ont été vérifiées sur Chromium (tablette 1180×820, jury 820×1100, scène 1600×900, commande 1360×860).

**Question :** pourquoi l'animation de la scène ignore-t-elle `prefers-reduced-motion` alors que celle des cartes du tirage la respecte ?
