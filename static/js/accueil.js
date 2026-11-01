/* Animations de la page d'accueil (JavaScript natif, aucune dépendance). */
(function () {
  'use strict';
  var calme = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ── Apparition en cascade des enfants d'un conteneur [data-stagger] ───────
  $$('[data-stagger]').forEach(function (conteneur) {
    Array.prototype.slice.call(conteneur.children).forEach(function (enfant, i) {
      enfant.classList.add('ac-reveal');
      enfant.style.setProperty('--d', Math.min(i, 10) * 0.05 + 's');
    });
  });

  // ── Apparition au défilement ──────────────────────────────────────────────
  var revele = function (el) { el.classList.add('ac-in'); };
  if (calme || !('IntersectionObserver' in window)) {
    $$('.ac-reveal, .ac-steps').forEach(revele);
  } else {
    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) { if (e.isIntersecting) { revele(e.target); obs.unobserve(e.target); } });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    $$('.ac-reveal, .ac-steps').forEach(function (el) { obs.observe(el); });
  }

  // ── Compteurs animés (chiffres réels et aperçu illustratif) ───────────────
  function compter(el) {
    var cible = parseFloat(el.getAttribute('data-count')), dec = parseInt(el.getAttribute('data-dec') || '0', 10);
    var suffixe = el.getAttribute('data-suffixe') || '';
    if (calme || isNaN(cible)) { el.textContent = cible.toFixed(dec).replace('.', ',') + suffixe; return; }
    var debut = null, duree = 1600;
    (function pas(t) {
      if (debut === null) debut = t;
      var p = Math.min((t - debut) / duree, 1), v = cible * (1 - Math.pow(1 - p, 3));
      el.textContent = v.toFixed(dec).replace('.', ',') + suffixe;
      if (p < 1) requestAnimationFrame(pas);
    })(performance.now());
  }
  if ('IntersectionObserver' in window) {
    var oc = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) { if (e.isIntersecting) { compter(e.target); oc.unobserve(e.target); } });
    }, { threshold: 0.5 });
    $$('[data-count]').forEach(function (el) { oc.observe(el); });
  } else { $$('[data-count]').forEach(compter); }

  // ── Mot qui change dans le titre ──────────────────────────────────────────
  var rot = document.querySelector('.ac-rotator');
  if (rot && !calme) {
    var mots = JSON.parse(rot.getAttribute('data-mots') || '[]'), i = 0;
    if (mots.length > 1) {
      setInterval(function () {
        rot.classList.add('ac-out');
        setTimeout(function () { i = (i + 1) % mots.length; rot.textContent = mots[i]; rot.classList.remove('ac-out'); }, 360);
      }, 2800);
    }
  }

  // ── Inclinaison 3D de la maquette ─────────────────────────────────────────
  var scene = document.querySelector('.ac-stage'), mock = document.querySelector('.ac-mock');
  if (scene && mock && !calme && window.matchMedia('(hover: hover)').matches) {
    scene.addEventListener('mousemove', function (e) {
      var r = scene.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      mock.classList.add('ac-tilting');
      mock.style.transform = 'rotateY(' + (x * 12) + 'deg) rotateX(' + (-y * 10) + 'deg)';
    });
    scene.addEventListener('mouseleave', function () { mock.style.transform = ''; mock.classList.remove('ac-tilting'); });
  }

  // ── Lueur qui suit le curseur sur les cartes ──────────────────────────────
  $$('.ac-card').forEach(function (c) {
    c.addEventListener('mousemove', function (e) {
      var r = c.getBoundingClientRect();
      c.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      c.style.setProperty('--my', (e.clientY - r.top) + 'px');
    });
  });

  // ── Bandeau défilant : contenu dupliqué pour une boucle continue ──────────
  var piste = document.querySelector('.ac-track');
  if (piste) piste.innerHTML += piste.innerHTML;

  // ── Onglets par rôle (clavier compris) ────────────────────────────────────
  var onglets = $$('.ac-tab'), panneaux = $$('.ac-panel');
  function choisir(n, focus) {
    onglets.forEach(function (o, k) { o.setAttribute('aria-selected', k === n ? 'true' : 'false'); o.tabIndex = k === n ? 0 : -1; });
    panneaux.forEach(function (p, k) { p.hidden = k !== n; p.classList.toggle('ac-show', k === n); });
    if (focus) onglets[n].focus();
  }
  onglets.forEach(function (o, k) {
    o.addEventListener('click', function () { choisir(k); });
    o.addEventListener('keydown', function (e) {
      var d = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
      if (d) { e.preventDefault(); choisir((k + d + onglets.length) % onglets.length, true); }
    });
  });
  if (onglets.length) choisir(0);
})();
