/* Aperçu instantané de la police du texte arabe (fiche d'un concours, administration).
   Dès qu'on change la police, la taille ou le fichier, le verset d'aperçu se met à jour, sans enregistrer.
   Les piles de polices viennent du serveur (data-familles) : on ne construit jamais un nom de police à partir d'une saisie. */
'use strict';
function demarrer() {
  var conteneur = document.getElementById('q-apercu-police');
  var texte = document.getElementById('q-apercu-texte');
  var police = document.getElementById('id_police_arabe');
  var taille = document.getElementById('id_taille_texte_arabe');
  var fichier = document.getElementById('id_police_arabe_fichier');
  if (!conteneur || !texte || !police || !taille) return;

  var familles = {};
  try { familles = JSON.parse(conteneur.dataset.familles || '{}'); } catch (e) { familles = {}; }
  var secours = familles.defaut || 'serif';
  var familleTeleversee = null; // « "QuranovaApercu", … » une fois un fichier choisi sur ce poste

  function actualiser() {
    var echelle = Math.min(200, Math.max(50, parseInt(taille.value, 10) || 100)) / 100;
    var pile = familles[police.value] || secours;
    if (police.value === 'personnalisee' && familleTeleversee) pile = familleTeleversee;
    texte.style.fontFamily = pile;
    texte.style.fontSize = Math.round(32 * echelle) + 'px';
  }

  if (fichier) {
    fichier.addEventListener('change', function () {
      var f = fichier.files && fichier.files[0];
      if (!f || !window.FontFace) { familleTeleversee = null; actualiser(); return; }
      f.arrayBuffer().then(function (octets) {
        var face = new FontFace('QuranovaApercu', octets);
        return face.load().then(function () {
          document.fonts.add(face);
          familleTeleversee = '"QuranovaApercu", ' + secours;
          actualiser();
        });
      }).catch(function () {
        familleTeleversee = null; // fichier illisible : le serveur le refusera aussi à l'enregistrement
        actualiser();
      });
    });
  }

  police.addEventListener('change', actualiser);
  taille.addEventListener('input', actualiser);
  taille.addEventListener('change', actualiser);
  actualiser();
}
// L'administration charge ce script dans l'en-tête : on attend que la page soit construite.
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer);
else demarrer();
