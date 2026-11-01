/* Pages d'authentification : œil sur les mots de passe, indicateur de robustesse, bouton en attente. */
(function () {
  'use strict';
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

  // Afficher / masquer un mot de passe
  $$('.au-input input[type="password"]').forEach(function (champ) {
    var bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'au-eye';
    bouton.setAttribute('aria-label', 'Afficher ou masquer le mot de passe');
    bouton.innerHTML = '<i class="fas fa-eye"></i>';
    champ.parentNode.appendChild(bouton);
    bouton.addEventListener('click', function () {
      var visible = champ.type === 'text';
      champ.type = visible ? 'password' : 'text';
      bouton.firstChild.className = visible ? 'fas fa-eye' : 'fas fa-eye-slash';
    });
  });

  // Indicateur de robustesse (indicatif : les règles de validation sont appliquées par le serveur)
  $$('[data-strength]').forEach(function (champ) {
    var barre = document.createElement('div');
    barre.className = 'au-strength';
    barre.innerHTML = '<i></i>';
    champ.closest('.au-field').appendChild(barre);
    champ.addEventListener('input', function () {
      var v = champ.value, points = 0;
      if (v.length >= 8) points++;
      if (v.length >= 12) points++;
      if (/[a-z]/.test(v) && /[A-Z]/.test(v)) points++;
      if (/\d/.test(v)) points++;
      if (/[^A-Za-z0-9]/.test(v)) points++;
      var barreI = barre.firstChild;
      barreI.style.width = (v ? Math.max(points, 1) * 20 : 0) + '%';
      barreI.style.background = points <= 2 ? 'var(--red)' : points <= 3 ? 'var(--yellow)' : 'var(--green)';
    });
  });

  // Empêche le double envoi et indique que la demande est en cours
  $$('form[data-attente]').forEach(function (f) {
    f.addEventListener('submit', function () {
      var b = f.querySelector('button[type="submit"]');
      if (b && !b.disabled) {
        setTimeout(function () { b.disabled = true; b.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + (f.getAttribute('data-attente') || 'Patientez…'); }, 0);
      }
    });
  });
})();
