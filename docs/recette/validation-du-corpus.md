# Validation du corpus par le référent coranique (jalon J0, livrable L-07)

Aucun concours réel ne peut être ouvert tant qu'une version du corpus n'est pas **validée** (RM-09, RM-27). Cette procédure suit §12.2 et §12.3 du cahier des charges.

## Qui fait quoi
| Rôle | Action |
|---|---|
| Administrateur QURANOVA | importe, imprime le procès-verbal, enregistre la validation, active la version |
| **Référent coranique** (à désigner) | relit l'échantillon au Mushaf de Médine, valide le rendu typographique, **signe** le procès-verbal |

## Étapes
1. **Télécharger** les fichiers depuis tanzil.net (texte Uthmani et métadonnées) dans `data\corpus\` ; **ne pas les ouvrir ni les enregistrer depuis un éditeur**.
2. **Importer** (sans aucune transformation) :
   ```powershell
   python manage.py import_corpus --dry-run     # contrôle sans rien écrire
   python manage.py import_corpus
   ```
3. **Imprimer le procès-verbal** : `/admin/` → *Versions du corpus* → la version « Importée » → **Procès-verbal à signer (imprimable)** ou **(PDF)**. Il contient :
   les 5 contrôles automatiques (114 sourates, 6 236 versets, métadonnées, numérotation, **aller-retour octet par octet avec le fichier source**),
   l'**échantillon de relecture** (sourate 1, 2:255, 2:282, sourates 36 et 112 à 114, plus au moins 1 % de versets tirés — reproductible : même échantillon à chaque impression),
   la liste de vérification du **rendu typographique** et le bloc de signatures.
   Si un contrôle échoue, le procès-verbal le dit et la version **ne peut pas** être validée : importez une nouvelle version.
4. **Relecture par le référent** : comparer chaque verset au Mushaf de Médine (case « Conforme »). Vérifier le **rendu** sur l'écran de scène et l'écran du jury, avec les tablettes et le projecteur de salle
   (police, ligatures, signes de récitation, verset 2:282 découpé).
5. **Signature** du procès-verbal par le référent, puis par l'administrateur. Archiver l'original (et un scan) : c'est le livrable **L-07**.
6. **Enregistrer la validation** : liste des versions → cocher la version → action **« Enregistrer la validation du référent coranique »** → nom, qualité, date de signature, attestation d'avoir le procès-verbal signé.
   Les contrôles sont **rejoués** à l'enregistrement ; la version devient « Validée » et **définitivement figée** (RM-27). Une correction ultérieure = une nouvelle version.
7. **Activer** : action **« Activer pour les nouveaux concours »** (une seule version active à la fois). Les concours existants gardent leur version.

## Ce que le logiciel garantit
- Seul l'administrateur valide ou active (testé, y compris en forçant la requête) ; l'opérateur et le client n'ont même pas accès au procès-verbal (404).
- La validation est tracée : qui, quand, quel référent, résultat de chaque contrôle, empreinte de l'échantillon signé ; opérations journalisées (`corpus.valide`, `corpus.active`, `document.pv_corpus_genere`).
- Le texte coranique n'est jamais modifié : le procès-verbal **affiche** le texte de la base (`lang="ar" dir="rtl"`), il ne le retape pas.

## Ce que le logiciel ne fait pas (à ta charge)
La comparaison au Mushaf de Médine, le jugement sur le rendu typographique et la signature : ce sont des actes humains du référent. Le rapport de différences verset par verset pour une **mise à jour** de Tanzil (§12.3)
n'est pas encore codé : à faire avant la première mise à jour du corpus.
