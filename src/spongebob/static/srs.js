/* SM-2 spaced repetition.
 *
 * An independent implementation of the SM-2 algorithm, the same family of
 * scheduler Anki uses and that StudyCraft's review mode is built on. No
 * StudyCraft code is used here.
 *
 * Progress is stored per site and per deck in localStorage under
 * `spongebob:<site>:srs:<deck>`. It is therefore per-browser: clearing site
 * data, or serving the site from a different port, starts the schedule over.
 */
window.SpongebobSRS = (function () {
  'use strict';

  var DAY = 86400000;

  /* Multipliers applied to the interval, indexed by grade. */
  var GRADES = {
    again: { quality: 0, easeDelta: -0.20 },
    hard:  { quality: 3, easeDelta: -0.15 },
    good:  { quality: 4, easeDelta: 0.00 },
    easy:  { quality: 5, easeDelta: +0.15 }
  };

  var MIN_EASE = 1.3;
  var DEFAULT_EASE = 2.5;
  /* Graduating steps in days for a card's first two successful reviews. */
  var LEARNING_STEPS = [1, 6];

  function freshCard() {
    return { reps: 0, lapses: 0, ease: DEFAULT_EASE, interval: 0, due: 0, last: null };
  }

  function storageKey(site, deckId) {
    return 'spongebob:' + site + ':srs:' + deckId;
  }

  function load(site, deckId) {
    try {
      return JSON.parse(localStorage.getItem(storageKey(site, deckId))) || {};
    } catch (e) {
      return {};
    }
  }

  function save(site, deckId, state) {
    try {
      localStorage.setItem(storageKey(site, deckId), JSON.stringify(state));
    } catch (e) {
      /* Private browsing or a full quota — reviewing still works, it just
         won't be remembered. */
    }
  }

  function reset(site, deckId) {
    try {
      localStorage.removeItem(storageKey(site, deckId));
    } catch (e) {}
  }

  /* Apply one grade to one card's schedule. Returns the updated record. */
  function grade(card, gradeName, now) {
    var g = GRADES[gradeName] || GRADES.good;
    var record = card || freshCard();
    now = now || Date.now();

    record.ease = Math.max(MIN_EASE, (record.ease || DEFAULT_EASE) + g.easeDelta);

    if (g.quality < 3) {
      /* Lapse: back to the start of the learning steps, due in 10 minutes. */
      record.lapses = (record.lapses || 0) + 1;
      record.reps = 0;
      record.interval = 0;
      record.due = now + 10 * 60 * 1000;
    } else if (record.reps === 0) {
      record.reps = 1;
      record.interval = LEARNING_STEPS[0];
      record.due = now + record.interval * DAY;
    } else if (record.reps === 1) {
      record.reps = 2;
      record.interval = LEARNING_STEPS[1];
      record.due = now + record.interval * DAY;
    } else {
      record.reps += 1;
      var multiplier = record.ease * (gradeName === 'hard' ? 0.8 : 1);
      if (gradeName === 'easy') multiplier *= 1.3;
      record.interval = Math.max(1, Math.round(record.interval * multiplier));
      record.due = now + record.interval * DAY;
    }

    record.last = now;
    return record;
  }

  function isDue(record, now) {
    if (!record || !record.last) return true;   // never seen
    return (record.due || 0) <= (now || Date.now());
  }

  /* Cards never seen come first, then the most overdue. */
  function queue(cards, state, now) {
    now = now || Date.now();
    return cards
      .filter(function (card) { return isDue(state[card.id], now); })
      .sort(function (a, b) {
        var ra = state[a.id], rb = state[b.id];
        var na = !ra || !ra.last, nb = !rb || !rb.last;
        if (na !== nb) return na ? -1 : 1;
        return ((ra && ra.due) || 0) - ((rb && rb.due) || 0);
      });
  }

  /* Share of the deck that has graduated past the learning steps. */
  function progress(cards, state) {
    if (!cards.length) return 0;
    var known = cards.filter(function (card) {
      var record = state[card.id];
      return record && record.reps >= 2;
    }).length;
    return Math.round((known / cards.length) * 100);
  }

  function formatInterval(days) {
    if (!days) return 'today';
    if (days < 1) return 'in minutes';
    if (days === 1) return 'tomorrow';
    if (days < 30) return 'in ' + days + ' days';
    if (days < 365) return 'in ' + Math.round(days / 30) + ' months';
    return 'in ' + (days / 365).toFixed(1) + ' years';
  }

  return {
    freshCard: freshCard,
    load: load,
    save: save,
    reset: reset,
    grade: grade,
    isDue: isDue,
    queue: queue,
    progress: progress,
    formatInterval: formatInterval
  };
})();
