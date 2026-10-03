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
| quran-uthmani.xml | | | |
| quran-data.xml | | | |

## Licence

Le texte Tanzil peut être utilisé verbatim, sans modification, à condition de citer la source (Projet Tanzil)
et de faire un lien vers tanzil.net. Ces mentions devront figurer dans l'application (page « À propos » et pied de l'écran scène).
