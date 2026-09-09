/* Site-wide behaviour: theme toggle, scroll progress, copy buttons. */
(function () {
  'use strict';

  var root = document.documentElement;

  /* ------------------------------------------------------------ theme */
  document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      var nowDark = root.classList.toggle('dark');
      try {
        localStorage.setItem('spongebob:theme', nowDark ? 'dark' : 'light');
      } catch (e) {}
    });
  });

  /* --------------------------------------------------- scroll progress */
  var bar = document.querySelector('[data-scroll-progress]');
  if (bar) {
    var update = function () {
      var max = document.documentElement.scrollHeight - window.innerHeight;
      var pct = max > 0 ? (window.scrollY / max) * 100 : 0;
      bar.style.width = Math.min(100, Math.max(0, pct)).toFixed(2) + '%';
    };
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();
  }

  /* ------------------------------------------------------ copy buttons */
  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var card = button.closest('.sb-card') || button.parentElement;
      var pre = card ? card.querySelector('pre') : null;
      if (!pre || !navigator.clipboard) return;
      navigator.clipboard.writeText(pre.innerText.replace(/\n$/, '')).then(function () {
        var original = button.textContent;
        button.textContent = 'Copied';
        setTimeout(function () { button.textContent = original; }, 1400);
      });
    });
  });
})();
