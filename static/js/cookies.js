/*
 * Consentement aux cookies de StockMaster.
 * Le choix est mémorisé dans le cookie « sm_consent » (180 jours). Seuls les cookies strictement nécessaires
 * (session, protection CSRF, ce cookie de choix) sont déposés sans consentement ; la catégorie « mesure » est
 * réservée à d'éventuels outils de mesure d'audience ou de supervision : tout futur traceur de ce type doit
 * tester window.StockMasterConsent.has('mesure') avant de s'exécuter.
 */
(function () {
  'use strict';
  var NOM = 'sm_consent';
  var DUREE = 180 * 24 * 3600;
  var VERSION = 1;

  function lire() {
    var m = document.cookie.match(new RegExp('(?:^|; )' + NOM + '=([^;]*)'));
    if (!m) return null;
    try {
      var c = JSON.parse(decodeURIComponent(m[1]));
      return c && c.v === VERSION ? c : null;
    } catch (e) { return null; }
  }

  function ecrire(mesure) {
    var c = { v: VERSION, mesure: !!mesure, t: Math.floor(Date.now() / 1000) };
    var attrs = '; path=/; max-age=' + DUREE + '; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
    document.cookie = NOM + '=' + encodeURIComponent(JSON.stringify(c)) + attrs;
    document.dispatchEvent(new CustomEvent('sm:consent', { detail: c }));
    return c;
  }

  function $(id) { return document.getElementById(id); }

  function afficher(banniere, modale) {
    banniere.hidden = false;
    requestAnimationFrame(function () { banniere.classList.add('ck-visible'); });
  }
  function masquer(el) {
    el.classList.remove('ck-visible');
    setTimeout(function () { el.hidden = true; }, 250);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var banniere = $('ck-banner'), modale = $('ck-modal');
    if (!banniere || !modale) return;
    var interrupteur = $('ck-mesure');

    function valider(mesure) {
      ecrire(mesure);
      masquer(banniere);
      modale.hidden = true;
      document.body.classList.remove('ck-open');
    }
    function ouvrirModale() {
      var c = lire();
      interrupteur.checked = !!(c && c.mesure);
      modale.hidden = false;
      document.body.classList.add('ck-open');
      $('ck-save').focus();
    }

    $('ck-accept').addEventListener('click', function () { valider(true); });
    $('ck-refuse').addEventListener('click', function () { valider(false); });
    $('ck-custom').addEventListener('click', ouvrirModale);
    $('ck-save').addEventListener('click', function () { valider(interrupteur.checked); });
    $('ck-close').addEventListener('click', function () { modale.hidden = true; document.body.classList.remove('ck-open'); });
    modale.addEventListener('click', function (e) { if (e.target === modale) $('ck-close').click(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !modale.hidden) $('ck-close').click(); });

    window.StockMasterConsent = {
      /** Choix enregistré ({mesure: bool, ...}) ou null tant que le visiteur n'a pas choisi. */
      get: lire,
      /** true si la catégorie ('mesure') a été acceptée. Les cookies nécessaires sont toujours actifs. */
      has: function (categorie) { var c = lire(); return categorie === 'necessaires' || !!(c && c[categorie]); },
      /** Rouvre la fenêtre de choix (lien « Gérer mes cookies »). */
      open: ouvrirModale,
    };
    document.querySelectorAll('[data-cookies-open]').forEach(function (a) {
      a.addEventListener('click', function (e) { e.preventDefault(); ouvrirModale(); });
    });

    if (!lire()) afficher(banniere);
  });
})();
