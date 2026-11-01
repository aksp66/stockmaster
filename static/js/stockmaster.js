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
