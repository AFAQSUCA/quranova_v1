# 12. Corpus coranique de référence

La fiabilité du texte coranique est une exigence fondamentale du projet. La présente section fixe la source unique, les procédures de vérification et de versionnement ainsi que les règles de numérotation.

## 12.1. Source officielle unique

| Élément | Décision |
|---|---|
| Source | Projet Tanzil (tanzil.net) — « Tanzil Quran Text », dernière version publiée à la date d'intégration. |
| Type de texte | Uthmani (graphie du Mushaf de Médine). |
| Riwāya | Hafs ʿan ʿĀṣim. |
| Format importé | Fichier XML ou texte avec numéros de sourate et de verset, téléchargé exclusivement depuis le site officiel du projet. |
| Métadonnées | Fichier de métadonnées Tanzil (noms des sourates, nombre de versets, ordre, sajdas). |
| Traduction française | Traduction distribuée par Tanzil, choisie et validée par le référent coranique, sous réserve de vérification de sa licence. |
| Licence | Le texte est utilisé verbatim, sans aucune modification ; la source (Projet Tanzil) est citée et un lien vers tanzil.net est affiché dans l'application, conformément aux conditions d'utilisation du projet. |

Le fichier `quranova.xlsx` mentionné dans la version 1.0 comme source alternative est **supprimé** : aucune autre source de texte coranique n'est admise. Aucun compte d'organisation ne peut importer ni modifier de texte coranique.

## 12.2. Procédure de vérification avant intégration

1. téléchargement du fichier depuis le site officiel Tanzil et consignation de son empreinte SHA-256, de la version source et de la date ;
2. import sans aucune transformation : aucune normalisation Unicode, suppression de diacritiques ou correction automatique n'est appliquée ; le texte est stocké tel quel en UTF-8 ;
3. contrôles automatiques : 114 sourates, 6 236 versets, nombre de versets de chaque sourate conforme aux métadonnées, absence de verset vide, continuité de la numérotation ;
4. contrôle d'aller-retour : l'export du corpus depuis la base est comparé octet par octet au fichier source ;
5. relecture par le référent coranique d'un échantillon défini (sourate 1, verset 2:255, verset 2:282, sourates 36 et 112 à 114, ainsi qu'au moins 1 % de versets tirés au hasard), comparé au Mushaf de Médine ;
6. validation du rendu typographique (police, ligatures, signes de récitation) sur l'écran scène et sur l'écran jury ;
7. signature d'un procès-verbal de validation du corpus par le référent coranique, préalable à l'activation de la version.

## 12.3. Versionnement et mise à jour

- chaque import crée une **version du corpus** identifiée (identifiant, source, version source, riwāya, date, empreinte, statut : importée, validée, active, retirée) ;
- une version validée est immuable ; toute correction donne lieu à une nouvelle version ;
- chaque concours est rattaché à une version du corpus, figée à son ouverture ; chaque passage coranique enregistre l'identifiant de cette version ;
- mise à jour : veille sur les publications du projet Tanzil, import de la nouvelle version, production d'un rapport de différences verset par verset, validation du référent coranique, puis activation pour les nouveaux concours uniquement ; les concours existants conservent leur version ;
- si une anomalie est découverte dans une version active, l'administrateur QURANOVA informe les clients dont des passages coraniques sont concernés ;
- toutes les opérations sur le corpus sont réservées à l'administrateur QURANOVA et journalisées.

## 12.4. Règles de numérotation des versets

- la numérotation suit le comptage koufi associé à la riwāya Hafs (6 236 versets) ;
- une référence s'écrit « sourate:verset » (ex. 2:255) ; un passage coranique s'écrit « 2:142–2:150 » ;
- la basmala est comptée comme verset uniquement dans la sourate 1 (Al-Fātiḥa, 1:1) ;
- pour les autres sourates, à l'exception de la sourate 9 (At-Tawba) qui n'en comporte pas, la basmala n'est pas numérotée ; lorsqu'un passage coranique commence au verset 1, elle peut être affichée sous forme de diapositive intercalaire non numérotée (paramètre de l'épreuve) ;
- les noms des sourates sont affichés en arabe et dans leur translittération française usuelle.

## 12.5. Options de riwāya

Le périmètre initial est limité à la riwāya Hafs ʿan ʿĀṣim. Le modèle de données comporte toutefois un attribut « riwāya » sur chaque version du corpus afin de permettre l'ajout ultérieur d'une autre riwāya (par exemple Warsh ʿan Nāfiʿ) sans restructuration. Une telle évolution nécessiterait une source distincte validée selon §12.2 et une table de correspondance de numérotation, le comptage des versets différant selon les riwāyāt.
