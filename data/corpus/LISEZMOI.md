# Corpus coranique (cf. §12 du cahier des charges)

Ce dossier contient le texte coranique de référence. **Il est téléchargé à la main depuis le site officiel du projet Tanzil,
jamais généré, recopié ou corrigé (ni par vous, ni par Claude).**

## Téléchargement

1. Aller sur https://tanzil.net/download
2. Choisir : type de texte **Uthmani**, format **XML** (laisser les options par défaut).
3. Enregistrer le fichier ici sous le nom `quran-uthmani.xml`.
4. Télécharger aussi le fichier de métadonnées `quran-data.xml` (noms des sourates, nombre de versets), disponible sur le site Tanzil, et l'enregistrer ici.
5. Noter dans le tableau ci-dessous la version indiquée dans l'en-tête du fichier et son empreinte :
   `Get-FileHash .\quran-uthmani.xml -Algorithm SHA256` (dans PowerShell)

| Fichier | Version Tanzil | Date de téléchargement | SHA-256 |
|---|---|---|---|
| quran-uthmani.xml | 1.1 (Uthmani, Tanzil Quran Text) | À compléter par vous | `af9311c521b5dadab01ea1ef259c281ffa83cf224bad24ee89469ce1c3c72916` |
| quran-data.xml | 1.0 (métadonnées) | À compléter par vous | `8867c1d88191472adec9db694b3cd9f135b1a2ef580574d32cf888dcb22c5c7a` |

## Licence

Le texte Tanzil peut être utilisé verbatim, sans modification, à condition de citer la source (Projet Tanzil)
et de faire un lien vers tanzil.net. Ces mentions devront figurer dans l'application (page « À propos » et pied de l'écran scène).

## Contrôles déjà réalisés par le projet

- `python manage.py import_corpus --dry-run` : lit les deux fichiers, lance les contrôles du §12.2 et annule sans rien enregistrer.
- `data/corpus/*` est déclaré `-text` dans `.gitattributes` : Git ne convertit jamais les fins de ligne de ces fichiers (l'empreinte reste valable après un clone sous Windows).
- Les empreintes ci-dessus ont été recalculées sur les fichiers du dépôt. **Recalculez-les sur votre poste** avec `Get-FileHash` : elles doivent être identiques.

## Reste à faire avant le jalon J0 (« corpus validé »)

- Désigner le référent coranique et lui faire valider l'échantillon du §12.2, point 5.
- Faire signer le procès-verbal de validation (§12.2, point 7), puis passer la version à « validée » (garde d'immuabilité à écrire).
