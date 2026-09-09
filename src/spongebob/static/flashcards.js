/* Flashcard review UI. Card HTML is rendered server-side from markdown, so this
   file only ever inserts markup our own pipeline produced. */
(function () {
  'use strict';

  var blob = document.querySelector('script[data-decks]');
  if (!blob) return;

  var SRS = window.SpongebobSRS;
  var site = document.body.dataset.site || 'site';
  var decks = JSON.parse(blob.textContent || '[]');
  var byId = {};
  decks.forEach(function (deck) { byId[deck.id] = deck; });

  var overlay = document.querySelector('[data-review-overlay]');
  var flip = overlay.querySelector('[data-flip]');
  var frontEl = overlay.querySelector('[data-card-front]');
  var backEl = overlay.querySelector('[data-card-back]');
  var hintEl = overlay.querySelector('[data-card-hint]');
  var codeEl = overlay.querySelector('[data-card-code]');
  var titleEl = overlay.querySelector('[data-review-title]');
  var counterEl = overlay.querySelector('[data-review-counter]');
  var flipBtn = overlay.querySelector('[data-flip-btn]');
  var grades = overlay.querySelector('[data-grades]');
  var doneEl = overlay.querySelector('[data-review-done]');
  var summaryEl = overlay.querySelector('[data-review-summary]');
  var footEl = overlay.querySelector('.sb-review-foot');

  var session = null;

  /* ------------------------------------------------------------ deck cards */

  function refreshDeckCard(deck) {
    var card = document.querySelector('[data-deck-card="' + deck.id + '"]');
    if (!card) return;
    var state = SRS.load(site, deck.id);
    var due = SRS.queue(deck.cards, state).length;
    var pct = SRS.progress(deck.cards, state);

    var dueEl = card.querySelector('[data-deck-due]');
    if (dueEl) dueEl.textContent = String(due);

    var ring = card.querySelector('[data-deck-ring]');
    if (ring) {
      ring.style.setProperty('--sb-ring-pct', String(pct));
      var pctEl = ring.querySelector('[data-deck-pct]');
      if (pctEl) pctEl.textContent = pct + '%';
    }

    var dueBtn = card.querySelector('[data-review][data-mode="due"]');
    if (dueBtn) {
      dueBtn.disabled = due === 0;
      dueBtn.textContent = due === 0 ? 'Nothing due' : 'Review due (' + due + ')';
    }
  }

  function refreshAll() { decks.forEach(refreshDeckCard); }

  /* -------------------------------------------------------------- session */

  function start(deckId, mode) {
    var deck = byId[deckId];
    if (!deck) return;
    var state = SRS.load(site, deckId);
    var queue = mode === 'all' ? deck.cards.slice() : SRS.queue(deck.cards, state);
    if (!queue.length) return;

    session = {
      deck: deck,
      state: state,
      queue: queue,
      index: 0,
      graded: { again: 0, hard: 0, good: 0, easy: 0 }
    };

    overlay.hidden = false;
    doneEl.hidden = true;
    footEl.hidden = false;
    flip.hidden = false;
    document.body.style.overflow = 'hidden';
    titleEl.textContent = deck.name;
    show();
  }

  function show() {
    var card = session.queue[session.index];
    if (!card) return finish();

    flip.classList.remove('is-flipped');
    grades.hidden = true;
    flipBtn.hidden = false;

    frontEl.innerHTML = card.front;
    backEl.innerHTML = card.back;

    if (card.hint) { hintEl.innerHTML = card.hint; hintEl.hidden = false; }
    else { hintEl.hidden = true; }

    if (card.code) { codeEl.innerHTML = card.code; codeEl.hidden = false; }
    else { codeEl.hidden = true; }

    counterEl.textContent = (session.index + 1) + ' / ' + session.queue.length;
  }

  function reveal() {
    flip.classList.add('is-flipped');
    flipBtn.hidden = true;
    grades.hidden = false;
  }

  function applyGrade(name) {
    if (!session || grades.hidden) return;
    var card = session.queue[session.index];
    session.state[card.id] = SRS.grade(session.state[card.id], name);
    session.graded[name] = (session.graded[name] || 0) + 1;
    SRS.save(site, session.deck.id, session.state);

    if (name === 'again') session.queue.push(card);   // see it again this session

    session.index += 1;
    if (session.index >= session.queue.length) finish();
    else show();
  }

  function finish() {
    var reviewed = Object.keys(session.graded).reduce(function (total, key) {
      return total + session.graded[key];
    }, 0);
    var pct = SRS.progress(session.deck.cards, session.state);
    summaryEl.textContent =
      reviewed + ' reviews · ' + session.graded.again + ' again, ' + session.graded.hard + ' hard, ' +
      session.graded.good + ' good, ' + session.graded.easy + ' easy · deck ' + pct + '% learned';
    flip.hidden = true;
    footEl.hidden = true;
    doneEl.hidden = false;
    refreshDeckCard(session.deck);
  }

  function close() {
    overlay.hidden = true;
    document.body.style.overflow = '';
    if (session) refreshDeckCard(session.deck);
    session = null;
  }

  /* --------------------------------------------------------------- events */

  document.querySelectorAll('[data-review]').forEach(function (button) {
    button.addEventListener('click', function () {
      start(button.dataset.review, button.dataset.mode);
    });
  });

  document.querySelectorAll('[data-reset-deck]').forEach(function (button) {
    button.addEventListener('click', function () {
      var deck = byId[button.dataset.resetDeck];
      if (!deck) return;
      if (!window.confirm('Reset review history for "' + deck.name + '"?')) return;
      SRS.reset(site, deck.id);
      refreshDeckCard(deck);
    });
  });

  overlay.querySelectorAll('[data-review-close]').forEach(function (button) {
    button.addEventListener('click', close);
  });
  overlay.addEventListener('click', function (event) {
    if (event.target === overlay) close();
  });

  flipBtn.addEventListener('click', reveal);
  flip.addEventListener('click', function () { if (grades.hidden) reveal(); });
  grades.querySelectorAll('[data-grade]').forEach(function (button) {
    button.addEventListener('click', function () { applyGrade(button.dataset.grade); });
  });

  document.addEventListener('keydown', function (event) {
    if (overlay.hidden) return;
    if (event.key === 'Escape') return close();
    if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault();
      if (grades.hidden && !flip.hidden) reveal();
      return;
    }
    var map = { '1': 'again', '2': 'hard', '3': 'good', '4': 'easy' };
    if (map[event.key]) {
      event.preventDefault();
      applyGrade(map[event.key]);
    }
  });

  refreshAll();
})();
