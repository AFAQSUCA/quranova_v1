# Chapitre 38 — Interface d'administration : sidebar, barre supérieure, charte vert et or

## Objectif
Donner à l'administration (qui sert de console de gestion) l'allure d'un tableau de bord professionnel — sobre, institutionnelle — **sans nouvelle dépendance** et **sans toucher à une seule règle métier** :
toutes les actions (tirage, import, validation du corpus…) restent celles de Django, simplement habillées.

## Choix et alternatives écartées
- **Habiller l'administration Django** (gabarits + un CSS + un JS maison) plutôt qu'ajouter `django-unfold` : pas de dépendance à valider, palette entièrement sous notre contrôle, et nos pages d'action intermédiaires continuent de fonctionner.
- **Le menu est décrit à la main** (`apps/commun/navigation.py`) plutôt que déduit de `admin.site.get_app_list` : on choisit les groupes, l'ordre, les libellés et les icônes.
- **Les compteurs du menu passent par `get_queryset(request)`** de chaque administration : ils appliquent donc le cloisonnement par client (RM-20, règle absolue n° 3). Un opérateur ne voit jamais le nombre de candidats d'un autre client. Le menu est de l'affichage, pas de la sécurité : chaque vue revérifie la permission (règle n° 4).

## Fichiers
| Fichier | Rôle |
|---|---|
| `apps/commun/navigation.py` | Processeur de contexte : groupes du menu, entrées visibles selon les droits, compteurs, profil. Ne s'exécute que sous `/admin/` pour un membre du personnel connecté. |
| `config/settings/base.py` | Déclare ce processeur de contexte. |
| `templates/admin/base.html` | La coque : sidebar (260 px, rail de 72 px, tiroir sur mobile), barre supérieure (fil d'Ariane, recherche globale, thème, menu utilisateur), zone de contenu, toasts. Garde **tous** les blocs de Django (`breadcrumbs`, `content`, `extrastyle`…) pour que les gabarits existants fonctionnent. |
| `templates/admin/_icones.html` | Palette d'icônes (traits SVG), appelées par `<use href="#i-nom">`. |
| `templates/admin/login.html` | Page de connexion centrée (logo, champs élevés, bouton plein). |
| `templates/admin/index.html` | Tableau de bord : une carte par groupe, avec compteurs. |
| `templates/admin/change_list.html` | Étend la liste standard : en-tête (titre, nombre d'éléments, **+ Ajouter**), état vide avec appel à l'action, conteneur du tableau. |
| `apps/commun/templatetags/q_admin.py` | `peut_supprimer` : n'affiche l'icône « supprimer » que si l'utilisateur en a le droit (la vue de suppression revérifie). |
| `static/css/admin-quranova.css` | Jetons de couleur (clair/sombre), composants, adaptation mobile. Chargé **en dernier** pour l'emporter sur les feuilles de Django. |
| `static/js/admin-quranova.js` | Rail replié, groupes repliables, tiroir mobile, recherche globale (Ctrl + K), thème, toasts, icônes d'action des lignes. |
| `apps/commun/tests/test_navigation_admin.py` | Menu, compteurs cloisonnés, entrée active, état vide, lecture seule, messages. |

## Palette et accessibilité
Vert profond `#0a4c30` (marque), or doux `#d6b03a` réservé aux **actions principales**, à l'état actif et aux liserés, neutres ardoise. Le texte sur l'or est vert très foncé (`#0b2a1c`, 7,4 : 1) — jamais du blanc.
Toutes les paires texte/fond utilisées ont été calculées : **minimum 5,4 : 1** (seuil AA : 4,5 : 1), y compris l'or sur le vert sombre de la sidebar (7,8 : 1) et le thème sombre. Aucun texte gris clair sur fond blanc.

## Pièges rencontrés (à retenir)
1. **Le cache de gabarits de Django** (actif même en développement) ne recharge pas les `.html` quand on lance `runserver --noreload` : après une modification de gabarit, relancer le serveur.
2. **Spécificité CSS** : Django style `a:link` et certains champs par identifiant (`#toolbar #searchbar`). Nos classes seules perdent ; on écrit `a.q-item`, `#toolbar #searchbar`… et on charge notre feuille en dernier.
3. **Un enfant de conteneur flex ne rétrécit pas sous son contenu** (`min-width: auto`) : sans `min-width: 0`, un tableau large étirait toute la page sur mobile.
4. **Les éléments `position: absolute`** (les libellés « visually-hidden ») échappent à `overflow: hidden` si aucun ancêtre n'est positionné : le conteneur du tableau est `position: relative`.
5. Les icônes d'action des lignes sont **ajoutées en JavaScript** à partir du lien de la première colonne : rien à modifier dans chaque administration. Sans JavaScript, le lien du nom reste utilisable.

## Commandes (PowerShell)
```powershell
pytest apps\commun\tests\test_navigation_admin.py
python manage.py runserver     # puis http://127.0.0.1:8000/admin/ ; Ctrl + K pour la recherche globale
```

## Résultat attendu
Page de connexion épurée ; sidebar verte avec trois groupes demandés (Candidats, Clients, Concours) puis Salle, Résultats, Corpus coranique, Suivi, Comptes ; rail de 72 px au clic sur « Replier le menu » ; thème clair/sombre mémorisé ; sur téléphone, la sidebar devient un tiroir.

**Question :** les compteurs du menu s'appuient sur `get_queryset(request)` et non sur `Modele.objects.count()`. Quelle règle absolue du projet cela protège-t-il, et que verrait un opérateur avec la seconde écriture ?
