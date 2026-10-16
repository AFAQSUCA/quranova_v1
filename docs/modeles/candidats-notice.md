# Notice du modèle d'import des candidats (livrable L-05)

Fichier à remplir : **`candidats-modele.csv`** (ouvrable dans Excel ou LibreOffice ; **« Enregistrer sous » → CSV UTF-8** avec séparateur point-virgule).

| Colonne | Obligatoire | Contenu |
|---|---|---|
| `nom` | oui | Nom de famille |
| `prenom` | oui | Prénom(s) |
| `categorie` | oui | **Nom exact** d'une catégorie du concours (l'opérateur vous donne la liste) |
| `date_naissance` | non (mais **très recommandée**) | `JJ/MM/AAAA` ou `AAAA-MM-JJ`. **Sans date, le candidat est traité comme mineur** par prudence |
| `sexe` | non | `M` ou `F` |
| `ville` | non | |
| `structure` | non | École, mosquée, association |

**Avant de nous envoyer le fichier**
1. **Supprimez les deux lignes d'exemple** (elles commencent par `EXEMPLE-`).
2. Une ligne par candidat ; pas de ligne de titre supplémentaire ; pas de cellule fusionnée.
3. Ne mettez **aucune** pièce d'identité, photographie ni donnée de santé (collecte interdite par minimisation, §16.1).

**Ce que fait l'import** : un candidat déjà inscrit dans la catégorie est signalé comme doublon ; toutes les erreurs sont listées ligne par ligne ; **rien n'est enregistré** tant que le fichier contient une erreur.
Pour un candidat **mineur** (moins de 18 ans à la date du concours), le **formulaire de consentement parental signé** doit nous parvenir : sans lui, le candidat ne peut pas tirer.
