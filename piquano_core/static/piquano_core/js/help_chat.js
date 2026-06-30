/* Help-Chat Widget + Bug-Report JS */
(function() {
    'use strict';

    var btn = document.getElementById('pq-help-btn');
    var panel = document.getElementById('pq-help-panel');
    var closeBtn = document.getElementById('pq-help-close');
    var input = document.getElementById('pq-help-input');
    var sendBtn = document.getElementById('pq-help-send');
    var body = document.getElementById('pq-help-body');

    if (!btn || !panel) return;

    // ─── Chat-Tab ────────────────────────────────────────────────

    btn.addEventListener('click', function() {
        var hidden = panel.classList.toggle('pq-help-hidden');
        if (!hidden) {
            if (activeTab === 'chat') input.focus();
            else document.getElementById('pq-bug-title').focus();
        }
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

        var qDiv = document.createElement('div');
        qDiv.className = 'pq-help-q';
        qDiv.textContent = question;
        body.appendChild(qDiv);

        var loadDiv = document.createElement('div');
        loadDiv.className = 'pq-help-loading';
        loadDiv.innerHTML = '<span class="pq-dot"></span><span class="pq-dot"></span><span class="pq-dot"></span>';
        body.appendChild(loadDiv);
        body.scrollTop = body.scrollHeight;

        var intro = body.querySelector('.pq-help-intro');
        if (intro) intro.remove();

        var csrfToken = getCSRF();

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
        .catch(function() {
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
            .replace(/```[\s\S]*?```/g, function(m) {
                var code = m.slice(3, -3).replace(/^\w*\n/, '');
                return '<pre><code>' + escapeHtml(code) + '</code></pre>';
            })
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');

        html = html.replace(/((?:^|\n)[-•] .+(?:\n[-•] .+)*)/g, function(m) {
            var items = m.trim().split(/\n/).map(function(li) {
                return '<li>' + li.replace(/^[-•] /, '') + '</li>';
            }).join('');
            return '<ul>' + items + '</ul>';
        });

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

    // ─── Tab-Switching ───────────────────────────────────────────

    var activeTab = 'chat';
    var tabs = panel.querySelectorAll('.pq-help-tab');
    var inputRow = document.getElementById('pq-help-input-row');
    var bugBody = document.getElementById('pq-bug-body');
    var bugFooter = document.getElementById('pq-bug-footer');
    var urlPrefilled = false;

    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            var target = this.getAttribute('data-tab');
            if (target === activeTab) return;
            activeTab = target;

            tabs.forEach(function(t) { t.classList.remove('pq-tab-active'); });
            this.classList.add('pq-tab-active');

            if (target === 'chat') {
                body.style.display = '';
                inputRow.style.display = '';
                bugBody.style.display = 'none';
                bugFooter.style.display = 'none';
                input.focus();
            } else {
                body.style.display = 'none';
                inputRow.style.display = 'none';
                bugBody.style.display = '';
                bugFooter.style.display = '';
                if (!urlPrefilled) {
                    document.getElementById('pq-bug-url').value = window.location.href;
                    urlPrefilled = true;
                }
                document.getElementById('pq-bug-title').focus();
            }
        });
    });

    // ─── Bug-Report: File-Upload ─────────────────────────────────

    var MAX_FILES = 3;
    var MAX_SIZE = 5 * 1024 * 1024;
    var selectedFiles = [];
    var dropzone = document.getElementById('pq-bug-dropzone');
    var fileInput = document.getElementById('pq-bug-fileinput');
    var pillsContainer = document.getElementById('pq-bug-pills');
    var fileErr = document.getElementById('pq-bug-file-err');

    if (dropzone && fileInput) {
        dropzone.addEventListener('click', function() { fileInput.click(); });
        dropzone.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
        });

        fileInput.addEventListener('change', function() {
            var newFiles = Array.from(this.files);
            this.value = '';
            hideError(fileErr);

            for (var i = 0; i < newFiles.length; i++) {
                if (selectedFiles.length >= MAX_FILES) {
                    showFieldError(fileErr, 'Maximal ' + MAX_FILES + ' Dateien.');
                    break;
                }
                if (newFiles[i].size > MAX_SIZE) {
                    showFieldError(fileErr, '"' + newFiles[i].name + '" ist größer als 5 MB.');
                    continue;
                }
                selectedFiles.push(newFiles[i]);
            }
            renderPills();
        });
    }

    function renderPills() {
        pillsContainer.innerHTML = '';
        selectedFiles.forEach(function(f, idx) {
            var pill = document.createElement('span');
            pill.className = 'pq-bug-pill';
            pill.innerHTML = escapeHtml(f.name) +
                '<button class="pq-bug-pill-remove" type="button" data-idx="' + idx +
                '" aria-label="Entfernen">&times;</button>';
            pillsContainer.appendChild(pill);
        });
        pillsContainer.querySelectorAll('.pq-bug-pill-remove').forEach(function(btn) {
            btn.addEventListener('click', function() {
                selectedFiles.splice(parseInt(this.getAttribute('data-idx')), 1);
                renderPills();
                hideError(fileErr);
            });
        });
    }

    // ─── Bug-Report: Validierung ─────────────────────────────────

    var bugFields = [
        { id: 'pq-bug-title', errId: 'pq-bug-title-err', msg: 'Bitte gib eine kurze Beschreibung an.' },
        { id: 'pq-bug-url', errId: 'pq-bug-url-err', msg: 'Die URL fehlt noch.' },
        { id: 'pq-bug-expected', errId: 'pq-bug-expected-err', msg: 'Bitte beschreib kurz, was du erwartet hast.' },
        { id: 'pq-bug-actual', errId: 'pq-bug-actual-err', msg: 'Sag uns, was wirklich passiert ist.' }
    ];

    bugFields.forEach(function(field) {
        var el = document.getElementById(field.id);
        var errEl = document.getElementById(field.errId);
        if (el) {
            el.addEventListener('blur', function() {
                if (!this.value.trim()) {
                    showFieldError(errEl, field.msg);
                    this.classList.add('pq-field-error');
                } else {
                    hideError(errEl);
                    this.classList.remove('pq-field-error');
                }
            });
        }
    });

    function showFieldError(errEl, msg) {
        errEl.textContent = msg;
        errEl.classList.add('pq-visible');
    }

    function hideError(errEl) {
        errEl.textContent = '';
        errEl.classList.remove('pq-visible');
    }

    function validateAll() {
        var valid = true;
        var firstInvalid = null;
        bugFields.forEach(function(field) {
            var el = document.getElementById(field.id);
            var errEl = document.getElementById(field.errId);
            if (!el.value.trim()) {
                showFieldError(errEl, field.msg);
                el.classList.add('pq-field-error');
                valid = false;
                if (!firstInvalid) firstInvalid = el;
            } else {
                hideError(errEl);
                el.classList.remove('pq-field-error');
            }
        });
        if (firstInvalid) firstInvalid.focus();
        return valid;
    }

    // ─── Bug-Report: Submit ──────────────────────────────────────

    var submitBtn = document.getElementById('pq-bug-submit');
    if (submitBtn) {
        submitBtn.addEventListener('click', function() {
            if (!validateAll()) return;

            submitBtn.disabled = true;
            submitBtn.textContent = 'Wird gesendet...';

            var formData = new FormData();
            formData.append('title', document.getElementById('pq-bug-title').value.trim());
            formData.append('url', document.getElementById('pq-bug-url').value.trim());
            formData.append('expected', document.getElementById('pq-bug-expected').value.trim());
            formData.append('actual', document.getElementById('pq-bug-actual').value.trim());

            selectedFiles.forEach(function(f) {
                formData.append('files', f);
            });

            formData.append('meta', JSON.stringify({
                user_agent: navigator.userAgent,
                screen: screen.width + 'x' + screen.height,
                viewport: window.innerWidth + 'x' + window.innerHeight,
                timestamp: new Date().toISOString()
            }));

            var csrfToken = getCSRF();

            fetch('/help-chat/bug/', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData
            })
            .then(function(resp) { return resp.json(); })
            .then(function(data) {
                if (data.ok) {
                    showBugSuccess(data.ticket_nr);
                } else if (data.errors) {
                    // Server-seitige Validierungsfehler
                    Object.keys(data.errors).forEach(function(key) {
                        var errEl = document.getElementById('pq-bug-' + key + '-err');
                        if (errEl) showFieldError(errEl, data.errors[key]);
                    });
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Bug melden';
                } else {
                    showFieldError(document.getElementById('pq-bug-file-err'),
                        data.error || 'Ein Fehler ist aufgetreten.');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Bug melden';
                }
            })
            .catch(function() {
                showFieldError(document.getElementById('pq-bug-file-err'),
                    'Verbindungsfehler. Bitte versuch es nochmal.');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Bug melden';
            });
        });
    }

    function showBugSuccess(ticketNr) {
        bugBody.innerHTML =
            '<div class="pq-bug-success">' +
            '<div class="pq-bug-success-icon">&#10003;</div>' +
            '<div class="pq-bug-success-ticket">Danke, dein Bericht ist angekommen.</div>' +
            '<div class="pq-bug-success-sub">Ticket-Nr.: ' + escapeHtml(ticketNr) +
            '<br>Du bekommst eine Bestätigung per E-Mail.</div>' +
            '<button class="pq-bug-reset-link" id="pq-bug-reset" type="button">Weiteres Problem melden</button>' +
            '</div>';
        bugFooter.style.display = 'none';

        document.getElementById('pq-bug-reset').addEventListener('click', resetBugForm);
    }

    function resetBugForm() {
        selectedFiles = [];
        urlPrefilled = false;

        bugBody.innerHTML =
            '<form id="pq-bug-form" novalidate>' +
            '<div class="pq-bug-field">' +
            '<label class="pq-bug-label" for="pq-bug-title">Titel <span class="pq-bug-required">*</span></label>' +
            '<input class="pq-bug-input" id="pq-bug-title" type="text" placeholder="z.B. Speichern klappt nicht im Kontakt-Edit" maxlength="120" autocomplete="off" aria-required="true">' +
            '<div class="pq-bug-error-msg" id="pq-bug-title-err"></div></div>' +
            '<div class="pq-bug-field">' +
            '<label class="pq-bug-label" for="pq-bug-url">Seite <span class="pq-bug-required">*</span></label>' +
            '<input class="pq-bug-input" id="pq-bug-url" type="url" aria-required="true">' +
            '<div class="pq-bug-hint">Automatisch aus deiner aktuellen Seite übernommen.</div>' +
            '<div class="pq-bug-error-msg" id="pq-bug-url-err"></div></div>' +
            '<div class="pq-bug-field">' +
            '<label class="pq-bug-label" for="pq-bug-expected">Was sollte passieren? <span class="pq-bug-required">*</span></label>' +
            '<textarea class="pq-bug-textarea" id="pq-bug-expected" rows="3" placeholder="Ich wollte den Kontakt speichern und danach zur Detailansicht zurückkehren." aria-required="true"></textarea>' +
            '<div class="pq-bug-error-msg" id="pq-bug-expected-err"></div></div>' +
            '<div class="pq-bug-field">' +
            '<label class="pq-bug-label" for="pq-bug-actual">Was passiert stattdessen? <span class="pq-bug-required">*</span></label>' +
            '<textarea class="pq-bug-textarea" id="pq-bug-actual" rows="3" placeholder="Nach dem Klick auf Speichern kam eine rote Fehlermeldung, die Seite hat sich nicht aktualisiert." aria-required="true"></textarea>' +
            '<div class="pq-bug-error-msg" id="pq-bug-actual-err"></div></div>' +
            '<div class="pq-bug-field">' +
            '<label class="pq-bug-label">Dateien <span class="pq-bug-optional">(optional)</span></label>' +
            '<div class="pq-bug-dropzone" id="pq-bug-dropzone" role="button" tabindex="0" aria-label="Datei hinzufügen">+ Screenshot oder Datei hinzufügen</div>' +
            '<input type="file" id="pq-bug-fileinput" multiple accept="image/*,.pdf" style="display:none">' +
            '<div class="pq-bug-hint">Bilder oder PDF, max. 5 MB pro Datei, bis zu 3 Dateien</div>' +
            '<div class="pq-bug-file-pills" id="pq-bug-pills"></div>' +
            '<div class="pq-bug-error-msg" id="pq-bug-file-err"></div></div>' +
            '</form>';

        // Footer wieder einblenden, Submit-Button zurücksetzen
        bugFooter.style.display = '';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Bug melden';

        // Event-Listener neu binden
        rebindBugEvents();

        // URL vorbelegen
        document.getElementById('pq-bug-url').value = window.location.href;
        urlPrefilled = true;
        document.getElementById('pq-bug-title').focus();
    }

    function rebindBugEvents() {
        // Dropzone + FileInput
        dropzone = document.getElementById('pq-bug-dropzone');
        fileInput = document.getElementById('pq-bug-fileinput');
        pillsContainer = document.getElementById('pq-bug-pills');
        fileErr = document.getElementById('pq-bug-file-err');

        dropzone.addEventListener('click', function() { fileInput.click(); });
        dropzone.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
        });
        fileInput.addEventListener('change', function() {
            var newFiles = Array.from(this.files);
            this.value = '';
            hideError(fileErr);
            for (var i = 0; i < newFiles.length; i++) {
                if (selectedFiles.length >= MAX_FILES) {
                    showFieldError(fileErr, 'Maximal ' + MAX_FILES + ' Dateien.');
                    break;
                }
                if (newFiles[i].size > MAX_SIZE) {
                    showFieldError(fileErr, '"' + newFiles[i].name + '" ist größer als 5 MB.');
                    continue;
                }
                selectedFiles.push(newFiles[i]);
            }
            renderPills();
        });

        // Blur-Validierung
        bugFields.forEach(function(field) {
            var el = document.getElementById(field.id);
            var errEl = document.getElementById(field.errId);
            if (el) {
                el.addEventListener('blur', function() {
                    if (!this.value.trim()) {
                        showFieldError(errEl, field.msg);
                        this.classList.add('pq-field-error');
                    } else {
                        hideError(errEl);
                        this.classList.remove('pq-field-error');
                    }
                });
            }
        });
    }

    // ─── Helpers ─────────────────────────────────────────────────

    function getCSRF() {
        var csrfToken = '';
        var csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfEl) csrfToken = csrfEl.value;
        if (!csrfToken) {
            var match = document.cookie.match(/csrftoken=([^;]+)/);
            if (match) csrfToken = match[1];
        }
        return csrfToken;
    }
})();
