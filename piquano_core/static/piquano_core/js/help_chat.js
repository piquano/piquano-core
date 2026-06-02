/* Help-Chat Widget JS */
(function() {
    'use strict';

    var btn = document.getElementById('pq-help-btn');
    var panel = document.getElementById('pq-help-panel');
    var closeBtn = document.getElementById('pq-help-close');
    var input = document.getElementById('pq-help-input');
    var sendBtn = document.getElementById('pq-help-send');
    var body = document.getElementById('pq-help-body');

    if (!btn || !panel) return;

    btn.addEventListener('click', function() {
        var hidden = panel.classList.toggle('pq-help-hidden');
        if (!hidden) input.focus();
    });

    closeBtn.addEventListener('click', function() {
        panel.classList.add('pq-help-hidden');
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitQuestion();
        }
    });

    sendBtn.addEventListener('click', submitQuestion);

    function submitQuestion() {
        var question = input.value.trim();
        if (!question) return;

        input.value = '';
        sendBtn.disabled = true;

        // Frage anzeigen
        var qDiv = document.createElement('div');
        qDiv.className = 'pq-help-q';
        qDiv.textContent = question;
        body.appendChild(qDiv);

        // Loading
        var loadDiv = document.createElement('div');
        loadDiv.className = 'pq-help-loading';
        loadDiv.innerHTML = '<span class="pq-dot"></span><span class="pq-dot"></span><span class="pq-dot"></span>';
        body.appendChild(loadDiv);
        body.scrollTop = body.scrollHeight;

        // Intro-Text entfernen
        var intro = body.querySelector('.pq-help-intro');
        if (intro) intro.remove();

        var csrfToken = '';
        var csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfEl) csrfToken = csrfEl.value;
        if (!csrfToken) {
            var match = document.cookie.match(/csrftoken=([^;]+)/);
            if (match) csrfToken = match[1];
        }

        fetch('/help-chat/ask/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                url: window.location.pathname,
                title: document.title,
                question: question
            })
        })
        .then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.json();
        })
        .then(function(data) {
            loadDiv.remove();
            if (data.error) {
                showError(data.error);
            } else {
                showAnswer(data.answer);
            }
        })
        .catch(function(err) {
            loadDiv.remove();
            showError('Verbindungsfehler. Bitte versuch es nochmal.');
        })
        .finally(function() {
            sendBtn.disabled = false;
            input.focus();
        });
    }

    function showAnswer(md) {
        var aDiv = document.createElement('div');
        aDiv.className = 'pq-help-a';
        aDiv.innerHTML = renderMarkdown(md);
        body.appendChild(aDiv);
        body.scrollTop = body.scrollHeight;
    }

    function showError(msg) {
        var eDiv = document.createElement('div');
        eDiv.className = 'pq-help-error';
        eDiv.textContent = msg;
        body.appendChild(eDiv);
        body.scrollTop = body.scrollHeight;
    }

    /** Minimaler Markdown-Renderer (kein externer Lib nötig). */
    function renderMarkdown(text) {
        var html = text
            // Code-Blöcke
            .replace(/```[\s\S]*?```/g, function(m) {
                var code = m.slice(3, -3).replace(/^\w*\n/, '');
                return '<pre><code>' + escapeHtml(code) + '</code></pre>';
            })
            // Inline-Code
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Bold
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Absätze
            .replace(/\n\n/g, '</p><p>')
            // Zeilenumbrüche
            .replace(/\n/g, '<br>');

        // Listen (einfach)
        html = html.replace(/((?:^|\n)[-•] .+(?:\n[-•] .+)*)/g, function(m) {
            var items = m.trim().split(/\n/).map(function(li) {
                return '<li>' + li.replace(/^[-•] /, '') + '</li>';
            }).join('');
            return '<ul>' + items + '</ul>';
        });

        // Nummerierte Listen
        html = html.replace(/((?:^|\n)\d+\. .+(?:\n\d+\. .+)*)/g, function(m) {
            var items = m.trim().split(/\n/).map(function(li) {
                return '<li>' + li.replace(/^\d+\. /, '') + '</li>';
            }).join('');
            return '<ol>' + items + '</ol>';
        });

        return '<p>' + html + '</p>';
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }
})();
