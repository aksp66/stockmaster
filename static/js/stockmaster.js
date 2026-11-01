/*
 * Comportements communs à tous les espaces de StockMaster.
 *
 * Confirmation d'une action : ajouter data-confirm="Question ?" sur un <form> (confirmation à l'envoi) ou sur un
 * bouton / lien (confirmation au clic). Attributs facultatifs :
 *   data-confirm-title="Titre"      data-confirm-label="Texte du bouton"      data-confirm-tone="danger|warning|info"
 */
(function () {
  'use strict';
  var TONS = {
    danger: { icone: 'fa-triangle-exclamation', cls: 'cf-danger' },
    warning: { icone: 'fa-circle-exclamation', cls: 'cf-warning' },
    info: { icone: 'fa-circle-question', cls: 'cf-info' },
  };
  var modale = null, suite = null, precedent = null;

  function creer() {
    modale = document.createElement('div');
    modale.className = 'cf-overlay';
    modale.hidden = true;
    modale.innerHTML =
      '<div class="cf-box" role="alertdialog" aria-modal="true" aria-labelledby="cf-titre" aria-describedby="cf-texte">' +
      '<div class="cf-icon"><i class="fas"></i></div>' +
      '<h3 id="cf-titre" class="cf-title"></h3>' +
      '<p id="cf-texte" class="cf-text"></p>' +
      '<div class="cf-actions"><button type="button" class="btn b-gh cf-cancel">Annuler</button>' +
      '<button type="button" class="btn cf-ok"></button></div></div>';
    document.body.appendChild(modale);
    modale.addEventListener('click', function (e) { if (e.target === modale) fermer(); });
    modale.querySelector('.cf-cancel').addEventListener('click', fermer);
    modale.querySelector('.cf-ok').addEventListener('click', function () {
      var f = suite; fermer(); if (f) f();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !modale.hidden) fermer(); });
  }

  function fermer() {
    if (!modale) return;
    modale.hidden = true;
    suite = null;
    document.body.classList.remove('cf-open');
    if (precedent && precedent.focus) precedent.focus();
  }

  function demander(el, executer) {
    if (!modale) creer();
    var ton = TONS[el.getAttribute('data-confirm-tone')] || TONS.danger;
    var titre = el.getAttribute('data-confirm-title') || 'Confirmer cette action';
    var label = el.getAttribute('data-confirm-label') || 'Confirmer';
    var box = modale.querySelector('.cf-box');
    box.className = 'cf-box ' + ton.cls;
    modale.querySelector('.cf-icon i').className = 'fas ' + ton.icone;
    modale.querySelector('.cf-title').textContent = titre;
    modale.querySelector('.cf-text').textContent = el.getAttribute('data-confirm');
    var ok = modale.querySelector('.cf-ok');
    ok.textContent = label;
    ok.className = 'btn cf-ok ' + (ton === TONS.danger ? 'b-re cf-ok-danger' : 'b-or');
    suite = executer;
    precedent = document.activeElement;
    modale.hidden = false;
    document.body.classList.add('cf-open');
    modale.querySelector('.cf-cancel').focus();
  }

  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f.matches || !f.matches('form[data-confirm]') || f.dataset.confirmed === '1') return;
    e.preventDefault();
    demander(f, function () {
      f.dataset.confirmed = '1';
      if (f.requestSubmit) f.requestSubmit(e.submitter || undefined); else f.submit();
    });
  }, true);

  document.addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('a[data-confirm], button[data-confirm]') : null;
    if (!el || el.closest('form[data-confirm]') === el.form && el.form) return;
    e.preventDefault();
    demander(el, function () {
      if (el.tagName === 'A') { window.location.href = el.href; }
      else if (el.form) { el.form.requestSubmit ? el.form.requestSubmit(el) : el.form.submit(); }
    });
  }, true);
})();

/*
 * Animations communes aux espaces des rôles : apparition des cartes au défilement, compteurs, lignes de tableau
 * en cascade, ondulation des boutons, barre de progression lors d'un changement de page.
 * Désactivées pour les visiteurs qui demandent moins de mouvement.
 */
(function () {
  'use strict';
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function demarrer() {
    var racine = document.querySelector('#main, #content, main');
    if (!racine) return;

    // Cartes et tuiles sous la ligne de flottaison : elles apparaissent en entrant dans l'écran
    if ('IntersectionObserver' in window) {
      var obs = new IntersectionObserver(function (entrees) {
        entrees.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add('sm-in'); obs.unobserve(e.target); }
        });
      }, { threshold: 0.08 });
      $$('.card, .stat, .stat-card', racine).forEach(function (el) {
        if (el.parentElement && el.parentElement.closest('.card, .stat, .stat-card')) return;  // pas les cartes imbriquées
        if (el.getBoundingClientRect().top > window.innerHeight - 60) { el.classList.add('sm-pre'); obs.observe(el); }
      });

      // Compteurs : un entier simple se compte de 0 à sa valeur la première fois qu'il est visible
      var compte = new IntersectionObserver(function (entrees) {
        entrees.forEach(function (e) {
          if (!e.isIntersecting) return;
          compte.unobserve(e.target);
          var cible = parseInt(e.target.getAttribute('data-sm-cible'), 10), debut = null;
          (function pas(t) {
            if (debut === null) debut = t;
            var p = Math.min((t - debut) / 900, 1);
            e.target.textContent = Math.round(cible * (1 - Math.pow(1 - p, 3)));
            if (p < 1) requestAnimationFrame(pas);
          })(performance.now());
        });
      }, { threshold: 0.6 });
      $$('.sv, .stat-value', racine).forEach(function (el) {
        var texte = el.textContent.trim();
        if (/^\d{1,7}$/.test(texte) && parseInt(texte, 10) > 0) { el.setAttribute('data-sm-cible', texte); el.textContent = '0'; compte.observe(el); }
      });
    }

    // Lignes de tableau : apparition en cascade (les 14 premières)
    $$('.tbl tbody tr, .data-table tbody tr', racine).slice(0, 14).forEach(function (tr, i) {
      tr.classList.add('sm-row');
      tr.style.animationDelay = (i * 0.035) + 's';
    });
  }

  // Ondulation au clic sur un bouton
  document.addEventListener('click', function (e) {
    var bouton = e.target.closest ? e.target.closest('.btn') : null;
    if (!bouton || bouton.disabled) return;
    var r = bouton.getBoundingClientRect(), taille = Math.max(r.width, r.height) * 1.6;
    var onde = document.createElement('span');
    onde.className = 'sm-onde';
    onde.style.cssText = 'width:' + taille + 'px;height:' + taille + 'px;left:' + (e.clientX - r.left - taille / 2) + 'px;top:' + (e.clientY - r.top - taille / 2) + 'px;';
    bouton.appendChild(onde);
    setTimeout(function () { if (onde.parentNode) onde.parentNode.removeChild(onde); }, 600);
  });

  // Barre de progression en haut de page pendant un changement de page ou un envoi de formulaire
  function progression() {
    if (document.getElementById('sm-progress')) return;
    var barre = document.createElement('div');
    barre.id = 'sm-progress';
    document.body.appendChild(barre);
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || e.defaultPrevented || a.target === '_blank' || a.hasAttribute('data-confirm') || a.hasAttribute('download')) return;
    var href = a.getAttribute('href') || '';
    if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0 || a.origin !== window.location.origin) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey) return;
    progression();
  });
  document.addEventListener('submit', function (e) { if (!e.defaultPrevented) progression(); });
  window.addEventListener('pageshow', function () { var b = document.getElementById('sm-progress'); if (b) b.remove(); });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', demarrer); else demarrer();
})();
