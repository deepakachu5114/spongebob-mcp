/* Quiz runner. Questions come from a server-rendered JSON blob; best score per
   quiz is remembered in localStorage. */
(function () {
  'use strict';

  var blob = document.querySelector('script[data-quiz-data]');
  if (!blob) return;

  var site = document.body.dataset.site || 'site';
  var quizzes = JSON.parse(blob.textContent || '[]');

  function bestKey(quizId) { return 'spongebob:' + site + ':quiz:' + quizId; }

  function readBest(quizId) {
    try { return JSON.parse(localStorage.getItem(bestKey(quizId))); } catch (e) { return null; }
  }

  function writeBest(quizId, score) {
    var current = readBest(quizId);
    if (current && current.score >= score) return;
    try {
      localStorage.setItem(bestKey(quizId), JSON.stringify({ score: score, at: Date.now() }));
    } catch (e) {}
  }

  function normalise(text) {
    return String(text || '').trim().toLowerCase().replace(/\s+/g, ' ').replace(/[.,!?;:]+$/, '');
  }

  quizzes.forEach(function (quiz) {
    var root = document.querySelector('[data-quiz="' + quiz.id + '"]');
    if (!root) return;

    var body = root.querySelector('[data-quiz-body]');
    var submit = root.querySelector('[data-quiz-submit]');
    var retry = root.querySelector('[data-quiz-retry]');
    var result = root.querySelector('[data-quiz-result]');
    var bestEl = root.querySelector('[data-quiz-best]');

    var best = readBest(quiz.id);
    bestEl.textContent = best ? 'best ' + best.score + '%' : 'not attempted';

    function build() {
      body.innerHTML = '';
      quiz.questions.forEach(function (question, index) {
        var wrap = document.createElement('div');
        wrap.className = 'sb-q';
        wrap.dataset.question = question.id;

        var prompt = document.createElement('div');
        prompt.className = 'sb-q-prompt';
        prompt.innerHTML = '<span class="sb-q-num">' + (index + 1) + '</span>' + question.prompt;
        wrap.appendChild(prompt);

        if (question.kind === 'short') {
          var input = document.createElement('input');
          input.type = 'text';
          input.className = 'sb-text-input';
          input.style.marginTop = '0.75rem';
          input.placeholder = 'Type your answer';
          input.dataset.answerInput = '1';
          wrap.appendChild(input);
        } else {
          var list = document.createElement('div');
          list.style.display = 'grid';
          list.style.gap = '0.5rem';
          list.style.marginTop = '0.75rem';
          var multi = question.kind === 'multi';
          question.choices.forEach(function (choice, choiceIndex) {
            var label = document.createElement('label');
            label.className = 'sb-choice';
            label.dataset.choice = String(choiceIndex);
            var input = document.createElement('input');
            input.type = multi ? 'checkbox' : 'radio';
            input.name = question.id;
            input.value = String(choiceIndex);
            var span = document.createElement('span');
            span.innerHTML = choice;
            label.appendChild(input);
            label.appendChild(span);
            list.appendChild(label);
          });
          wrap.appendChild(list);
        }

        if (question.explanation) {
          var explain = document.createElement('div');
          explain.className = 'sb-explain';
          explain.hidden = true;
          explain.dataset.explain = '1';
          explain.innerHTML = question.explanation;
          wrap.appendChild(explain);
        }

        body.appendChild(wrap);
      });

      result.textContent = '';
      submit.hidden = false;
      submit.disabled = false;
      retry.hidden = true;
    }

    function check() {
      var correctCount = 0;

      quiz.questions.forEach(function (question) {
        var wrap = body.querySelector('[data-question="' + question.id + '"]');
        var isCorrect;

        if (question.kind === 'short') {
          var input = wrap.querySelector('[data-answer-input]');
          isCorrect = normalise(input.value) === normalise(question.answerText);
          input.style.borderColor = isCorrect ? '#10b981' : '#ef4444';
          input.disabled = true;
        } else {
          var expected = question.answerIndices.slice().sort().join(',');
          var chosen = Array.prototype.slice
            .call(wrap.querySelectorAll('input:checked'))
            .map(function (input) { return Number(input.value); })
            .sort()
            .join(',');
          isCorrect = expected === chosen;

          wrap.querySelectorAll('[data-choice]').forEach(function (label) {
            var index = Number(label.dataset.choice);
            var input = label.querySelector('input');
            var picked = input.checked;
            var shouldBe = question.answerIndices.indexOf(index) !== -1;
            input.disabled = true;
            if (picked && shouldBe) label.classList.add('sb-choice--correct');
            else if (picked && !shouldBe) label.classList.add('sb-choice--wrong');
            else if (!picked && shouldBe) label.classList.add('sb-choice--missed');
          });
        }

        var explain = wrap.querySelector('[data-explain]');
        if (explain) explain.hidden = false;
        if (isCorrect) correctCount += 1;
      });

      var total = quiz.questions.length || 1;
      var score = Math.round((correctCount / total) * 100);
      writeBest(quiz.id, score);

      var passed = quiz.passScore ? score >= quiz.passScore : score === 100;
      result.textContent = correctCount + ' / ' + total + ' correct · ' + score + '%' +
        (quiz.passScore ? (passed ? ' · passed' : ' · below ' + quiz.passScore + '%') : '');
      result.style.color = passed ? '#10b981' : '#f59e0b';

      var stored = readBest(quiz.id);
      bestEl.textContent = stored ? 'best ' + stored.score + '%' : '';

      submit.hidden = true;
      retry.hidden = false;
    }

    submit.addEventListener('click', check);
    retry.addEventListener('click', build);
    build();
  });
})();
