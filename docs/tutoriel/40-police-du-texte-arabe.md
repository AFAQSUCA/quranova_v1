# Chapitre 40 — Police du texte arabe réglable par concours

## Objectif
Permettre à l'administration de choisir, **concours par concours**, la police et la taille du texte arabe affiché sur la scène, chez le juré et sur la commande — sans jamais toucher au texte du verset (règle absolue n° 1 : c'est un réglage d'affichage).

## Décisions
- **Par concours** (champs sur `Concours`) : chaque édition peut avoir sa police ; la duplication d'un concours reprend les réglages.
- **Liste fixe + fichier téléversé** : la liste (Amiri Quran par défaut, Scheherazade New, Noto Naskh Arabic, Traditional Arabic, KFGQPC Uthmanic Script HAFS) dépend de ce qui est installé sur chaque appareil ; un **fichier téléversé** est servi par le serveur de salle et marche hors ligne sur tous les appareils.
- **Taille de base en %** (50 à 200), appliquée au verset de la scène. Le réglage au clavier (+ / −) de l'écran de scène reste possible par-dessus.
- Le tirage n'est pas concerné : l'écran candidat ne montre jamais de verset (RM-14).

## Fichiers
| Fichier | Rôle |
|---|---|
| `apps/concours/models.py` | Champs `police_arabe`, `police_arabe_fichier`, `taille_texte_arabe` ; `clean()` exige le fichier si « Fichier de police téléversé ». Migration `0003_police_texte_arabe`. |
| `apps/concours/polices.py` | Liste des polices (constantes), validation du fichier, production du CSS. |
| `apps/concours/admin.py` | Section « Affichage du texte arabe » avec **aperçu** : le premier verset **du corpus du concours** (jamais un texte saisi). |
| `apps/presentation/views.py`, `apps/jury/views.py` | Passent le CSS aux pages de scène, de commande et de jury. |
| `templates/_police_arabe.html` | Insère `<style>` après la feuille de style des écrans. |
| `frontend/src/scene/style.css` | `font-size: calc(6vw × --taille × --echelle-coran)`. Les polices passent par `--police-coran` (déjà utilisée). |
| `apps/concours/tests/test_police_arabe.py` | 22 tests. |

## Sécurité : ce que contient le CSS inséré
Le CSS est inséré **tel quel** dans la page : il ne doit donc pouvoir contenir que du sûr.
1. le **nom de police** vient d'une table de constantes, jamais d'une saisie ;
2. l'**échelle** est un nombre borné entre 0,50 et 2,00 ;
3. l'**adresse du fichier** n'est acceptée que si elle ne contient que `A-Z a-z 0-9 . _ / -` (sinon repli sur la police par défaut : test `test_une_adresse_suspecte_n_entre_jamais_dans_le_css`) ;
4. le **fichier** est contrôlé par sa signature (`wOF2`, `wOFF`, `OTTO`, `0x00010000`) **et** son extension, et limité à 3 Mo : un fichier HTML renommé en `.woff2` est refusé.

## Commandes (PowerShell)
```powershell
python manage.py migrate        # applique 0003_police_texte_arabe
pytest apps\concours\tests\test_police_arabe.py
cd frontend; npm run build      # l'échelle du verset est dans le CSS compilé
```
Puis *Concours → fiche → « Affichage du texte arabe »*.

## Résultat attendu
La scène (et le jury, la commande) utilisent la police choisie ; l'aperçu de l'admin montre le premier verset du corpus avec la police et la taille enregistrées.

**Question :** pourquoi accepte-t-on une police à téléverser alors qu'on refuse qu'un administrateur saisisse librement un nom de police CSS ? (Pense à ce que devient la valeur saisie dans la page.)
