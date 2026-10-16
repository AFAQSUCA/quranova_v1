/* QURANOVA — comportements de l'interface d'administration.
   Aucune dépendance. Chaque bloc est indépendant et tolère l'absence de localStorage
   (navigation privée, stockage bloqué) : l'interface reste utilisable, sans mémoire. */
'use strict';
(function () {
  var racine = document.documentElement;

  function lire(cle) { try { return localStorage.getItem(cle); } catch (e) { return null; } }
  function ecrire(cle, valeur) { try { localStorage.setItem(cle, valeur); } catch (e) { /* ignoré */ } }

  /* ── Thème clair / sombre (même clé « theme » que le script de Django) ── */
  function themeEffectif() {
    var t = racine.dataset.theme;
    if (t === 'light' || t === 'dark') return t;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function basculerTheme() {
    var suivant = themeEffectif() === 'dark' ? 'light' : 'dark';
    racine.dataset.theme = suivant;
    ecrire('theme', suivant);
  }
  document.querySelectorAll('#q-theme').forEach(function (b) { b.addEventListener('click', basculerTheme); });

  /* ── Rail replié (bureau) et tiroir (mobile) ── */
  var rail = document.getElementById('q-rail-toggle');
  function majRail() {
    var replie = racine.classList.contains('q-rail');
    if (rail) {
      rail.setAttribute('aria-pressed', replie ? 'true' : 'false');
      var texte = replie ? 'Déplier le menu' : 'Replier le menu';
      rail.setAttribute('aria-label', texte);
      rail.setAttribute('data-tip', texte);
      var lib = rail.querySelector('.q-label');
      if (lib) lib.textContent = 'Replier le menu';
    }
  }
  if (rail) {
    rail.addEventListener('click', function () {
      racine.classList.toggle('q-rail');
      ecrire('q-rail', racine.classList.contains('q-rail') ? '1' : '0');
      majRail();
    });
    majRail();
  }

  var burger = document.getElementById('q-burger');
  var scrim = document.querySelector('.q-scrim');
  function ouvrirTiroir(ouvert) {
    racine.classList.toggle('q-nav-open', ouvert);
    if (scrim) scrim.hidden = !ouvert;
    if (burger) burger.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  }
  if (burger) burger.addEventListener('click', function () { ouvrirTiroir(!racine.classList.contains('q-nav-open')); });
  if (scrim) scrim.addEventListener('click', function () { ouvrirTiroir(false); });

  /* ── Groupes repliables (état mémorisé) ── */
  var etatGroupes = {};
  try { etatGroupes = JSON.parse(lire('q-groupes') || '{}') || {}; } catch (e) { etatGroupes = {}; }
  document.querySelectorAll('.q-group').forEach(function (groupe) {
    var cle = groupe.dataset.group;
    var bouton = groupe.querySelector('.q-group-title');
    function appliquer(replie) {
      groupe.classList.toggle('is-collapsed', replie);
      bouton.setAttribute('aria-expanded', replie ? 'false' : 'true');
    }
    /* Un groupe qui contient la page courante reste déplié, quoi qu'on ait mémorisé. */
    appliquer(!!etatGroupes[cle] && !groupe.classList.contains('has-active'));
    bouton.addEventListener('click', function () {
      var replie = !groupe.classList.contains('is-collapsed');
      appliquer(replie);
      etatGroupes[cle] = replie;
      ecrire('q-groupes', JSON.stringify(etatGroupes));
    });
  });

  /* ── Menu utilisateur : se ferme au clic extérieur et sur Échap ── */
  var menu = document.getElementById('q-user');
  document.addEventListener('click', function (e) { if (menu && menu.open && !menu.contains(e.target)) menu.open = false; });

  /* ── Recherche globale : pages de l'administration + repli sur la liste des candidats ── */
  var champ = document.getElementById('q-search-input');
  var liste = document.getElementById('q-search-results');
  if (champ && liste) {
    var pages = [];
    document.querySelectorAll('.q-nav a.q-item').forEach(function (a) {
      var libelle = a.querySelector('.q-label');
      var groupe = a.closest('.q-group');
      var use = a.querySelector('use');
      pages.push({
        libelle: libelle ? libelle.textContent.trim() : '',
        url: a.getAttribute('href'),
        groupe: groupe ? groupe.querySelector('.q-group-title span').textContent.trim() : '',
        icone: use ? use.getAttribute('href') : '#i-search'
      });
    });
    var formulaire = champ.form;
    var selection = -1;
    var normaliser = function (t) { return t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); };
    var lignes = function () { return Array.prototype.slice.call(liste.querySelectorAll('li[data-url]')); };
    var marquer = function (i) {
      lignes().forEach(function (li, k) {
        li.classList.toggle('is-selected', k === i);
        li.setAttribute('aria-selected', k === i ? 'true' : 'false');
      });
      selection = i;
    };
    var fermer = function () { liste.hidden = true; champ.setAttribute('aria-expanded', 'false'); selection = -1; };
    var ajouter = function (url, icone, texte, groupe) {
      var li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.dataset.url = url;
      li.innerHTML = '<a><svg class="q-i" aria-hidden="true"><use href=""></use></svg><span></span><small></small></a>';
      li.querySelector('a').setAttribute('href', url);
      li.querySelector('use').setAttribute('href', icone);
      li.querySelector('span').textContent = texte;
      li.querySelector('small').textContent = groupe;
      liste.appendChild(li);
    };
    var rendre = function () {
      var saisie = champ.value.trim();
      var q = normaliser(saisie);
      if (!q) { fermer(); return; }
      liste.innerHTML = '';
      pages.filter(function (p) { return normaliser(p.libelle).indexOf(q) !== -1; }).slice(0, 6)
        .forEach(function (p) { ajouter(p.url, p.icone, p.libelle, p.groupe); });
      var action = formulaire.getAttribute('action');
      if (action && action !== '#') {
        ajouter(action + '?q=' + encodeURIComponent(saisie), '#i-users', 'Chercher « ' + saisie + ' » parmi les candidats', 'Candidats');
      }
      if (!liste.children.length) {
        liste.innerHTML = '<li class="q-results-empty">Aucun résultat.</li>';
      }
      liste.hidden = false;
      champ.setAttribute('aria-expanded', 'true');
      marquer(lignes().length ? 0 : -1);
    };
    champ.addEventListener('input', rendre);
    champ.addEventListener('keydown', function (e) {
      var l = lignes();
      if (e.key === 'ArrowDown' && l.length) { e.preventDefault(); marquer((selection + 1) % l.length); }
      else if (e.key === 'ArrowUp' && l.length) { e.preventDefault(); marquer((selection - 1 + l.length) % l.length); }
      else if (e.key === 'Enter' && selection >= 0 && l[selection]) { e.preventDefault(); window.location.href = l[selection].dataset.url; }
      else if (e.key === 'Escape') { fermer(); champ.blur(); }
    });
    document.addEventListener('click', function (e) { if (!document.getElementById('q-search').contains(e.target)) fermer(); });
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); champ.focus(); champ.select(); }
      else if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) { e.preventDefault(); champ.focus(); }
    });
  }

  /* ── Échap : ferme tiroir et menu utilisateur ── */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    ouvrirTiroir(false);
    if (menu) menu.open = false;
  });

  /* ── Messages Django → toasts ── */
  var conteneur = document.getElementById('q-toasts');
  var messages = document.getElementById('q-messages');
  var icones = { success: 'check-circle', error: 'alert-circle', warning: 'alert', info: 'info', debug: 'info' };
  function toast(texte, type) {
    type = icones[type] ? type : 'info';
    var el = document.createElement('div');
    el.className = 'q-toast ' + type;
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');
    el.innerHTML = '<svg class="q-i" aria-hidden="true"><use href="#i-' + icones[type] + '"></use></svg><span></span>' +
      '<button type="button" aria-label="Fermer"><svg class="q-i" aria-hidden="true"><use href="#i-x"></use></svg></button>';
    el.querySelector('span').textContent = texte;
    function retirer() { el.classList.add('is-leaving'); setTimeout(function () { el.remove(); }, 200); }
    el.querySelector('button').addEventListener('click', retirer);
    conteneur.appendChild(el);
    /* Les erreurs restent jusqu'à fermeture : on ne doit jamais en rater une. */
    if (type !== 'error') setTimeout(retirer, type === 'success' ? 5000 : 8000);
  }
  window.qToast = toast;
  if (conteneur && messages) {
    messages.querySelectorAll('li').forEach(function (li) {
      var type = (li.className || '').split(/\s+/).filter(function (c) { return icones[c]; })[0] || 'info';
      toast(li.textContent.trim(), type);
    });
    racine.classList.add('has-toasts');
  }

  /* ── Listes : filtres en pastilles, icônes d'action par ligne ── */
  document.querySelectorAll('#changelist-filter details').forEach(function (d) { d.removeAttribute('open'); });
  document.addEventListener('click', function (e) {
    document.querySelectorAll('#changelist-filter details[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('#changelist-filter details[open]').forEach(function (d) { d.removeAttribute('open'); });
  });

  var carte = document.querySelector('.q-table-card');
  var table = document.getElementById('result_list');
  if (carte && table) {
    var peutModifier = carte.dataset.canChange === '1';
    var peutSupprimer = carte.dataset.canDelete === '1';
    var enTete = table.querySelector('thead tr');
    if (enTete) {
      var th = document.createElement('th');
      th.className = 'q-actions-col';
      th.scope = 'col';
      th.innerHTML = '<span class="visually-hidden">Actions</span>';
      enTete.appendChild(th);
    }
    var icone = function (nom) { return '<svg class="q-i" aria-hidden="true"><use href="#i-' + nom + '"></use></svg>'; };
    table.querySelectorAll('tbody tr').forEach(function (tr) {
      var lien = tr.querySelector('th a, td a');
      var td = document.createElement('td');
      td.className = 'q-actions-col';
      if (lien) {
        var href = lien.getAttribute('href');
        var libelle = peutModifier ? 'Modifier' : 'Consulter';
        var html = '<span class="q-actions"><a href="' + href + '" data-tip="' + libelle + '" aria-label="' + libelle + '">' +
          icone(peutModifier ? 'edit' : 'eye') + '</a>';
        if (peutSupprimer) {
          var suppr = href.replace(/change\/(\?|$)/, 'delete/$1');
          if (suppr !== href) {
            html += '<a class="q-danger" href="' + suppr + '" data-tip="Supprimer" aria-label="Supprimer">' + icone('trash') + '</a>';
          }
        }
        td.innerHTML = html + '</span>';
      }
      tr.appendChild(td);
    });
  }
})();
