/* static/js/app.js — progressive enhancements shared by every page. No framework.
   Everything here degrades gracefully: without JS, forms post normally. */
(function () {
  'use strict';

  var NS = (window.NS = window.NS || {});

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : null;
  }
  NS.csrfToken = function () {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return getCookie('csrftoken') || (input ? input.value : '');
  };

  /* ── Toasts ─────────────────────────────────────── */
  function dismissLater(toast) {
    if (toast.classList.contains('error')) return; // errors stay until dismissed
    setTimeout(function () {
      toast.style.transition = 'opacity .3s';
      toast.style.opacity = '0';
      setTimeout(function () { toast.remove(); }, 320);
    }, 6000);
  }
  function wireToast(toast) {
    var close = toast.querySelector('.toast-close');
    if (close) close.addEventListener('click', function () { toast.remove(); });
    dismissLater(toast);
  }
  document.querySelectorAll('[data-toast]').forEach(wireToast);

  NS.toast = function (message, kind) {
    var stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    var toast = document.createElement('div');
    toast.className = 'toast ' + (kind || 'info');
    toast.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    var text = document.createElement('span');
    text.textContent = message;
    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.textContent = '×';
    toast.appendChild(text);
    toast.appendChild(close);
    stack.appendChild(toast);
    wireToast(toast);
  };

  /* ── Mobile navigation ──────────────────────────── */
  var toggle = document.querySelector('[data-nav-toggle]');
  var links = document.querySelector('[data-nav-links]');
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && links.classList.contains('open')) {
        links.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.focus();
      }
    });
  }

  /* ── Lightbox ───────────────────────────────────── */
  var lightbox = document.querySelector('[data-lightbox]');
  if (lightbox) {
    var lbImg = lightbox.querySelector('img');
    var lbClose = lightbox.querySelector('.lightbox-close');
    var opener = null;
    var closeLightbox = function () {
      lightbox.classList.remove('open');
      if (opener) opener.focus();
    };
    document.querySelectorAll('.zoomable').forEach(function (el) {
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      var open = function () {
        opener = el;
        lbImg.src = el.dataset.full || el.src;
        lbImg.alt = el.alt;
        lightbox.classList.add('open');
        lbClose.focus();
      };
      el.addEventListener('click', open);
      el.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    });
    lightbox.addEventListener('click', closeLightbox);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && lightbox.classList.contains('open')) closeLightbox(); });
  }

  /* ── Confirm dialog for destructive forms ───────── */
  var dialog = document.querySelector('[data-confirm-dialog]');
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.confirmed === 'yes' || !dialog || typeof dialog.showModal !== 'function') {
        if (!dialog || typeof dialog.showModal !== 'function') {
          if (!window.confirm(form.dataset.confirm)) e.preventDefault();
        }
        return;
      }
      e.preventDefault();
      dialog.querySelector('[data-confirm-title]').textContent = form.dataset.confirm;
      dialog.querySelector('[data-confirm-text]').textContent = form.dataset.confirmText || '';
      dialog.querySelector('[data-confirm-ok]').textContent = form.dataset.confirmLabel || 'Confirm';
      dialog.returnValue = '';
      dialog.showModal();
      dialog.addEventListener('close', function onClose() {
        dialog.removeEventListener('close', onClose);
        if (dialog.returnValue === 'confirm') {
          form.dataset.confirmed = 'yes';
          form.requestSubmit ? form.requestSubmit() : form.submit();
        }
      });
    });
  });

  /* ── Busy state on submit (prevents double posts) ─ */
  document.querySelectorAll('form[data-busy-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (e.defaultPrevented) return;
      var button = e.submitter || form.querySelector('[type="submit"]');
      if (!button) return;
      // Defer so the button's own name/value is still submitted.
      setTimeout(function () {
        button.classList.add('is-loading');
        button.disabled = true;
      }, 0);
    });
  });
  // Restore buttons when the page is shown again from the back/forward cache.
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    document.querySelectorAll('.btn.is-loading').forEach(function (b) {
      b.classList.remove('is-loading');
      b.disabled = false;
    });
  });

  /* ── Upvote (AJAX, degrades to a normal form post) ─ */
  document.querySelectorAll('form[data-upvote]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var button = form.querySelector('button');
      button.disabled = true;

      fetch(form.action, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': NS.csrfToken(), 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
      })
        .then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (body) { return { ok: r.ok, status: r.status, body: body }; });
        })
        .then(function (res) {
          if (!res.ok) {
            NS.toast(res.body.detail || (res.status === 404 ? 'That complaint is no longer available.' : 'Could not record your vote. Please try again.'), 'error');
            return;
          }
          button.classList.toggle('is-on', res.body.upvoted);
          button.setAttribute('aria-pressed', String(res.body.upvoted));
          var count = button.querySelector('[data-upvote-count]');
          if (count) count.textContent = res.body.count;
        })
        .catch(function () { NS.toast('You appear to be offline. Your vote was not recorded.', 'error'); })
        .finally(function () { button.disabled = false; });
    });
  });

  /* ── Filter bars: selects apply immediately ─────── */
  document.querySelectorAll('[data-autofilter] select').forEach(function (select) {
    select.addEventListener('change', function () {
      var page = select.form.querySelector('input[name="page"]');
      if (page) page.remove();
      select.form.submit();
    });
  });

  /* ── Bar charts (width set via CSSOM, CSP-safe) ─── */
  document.querySelectorAll('.bar-fill[data-width]').forEach(function (bar) {
    bar.style.width = Math.max(0, Math.min(100, Number(bar.dataset.width) || 0)) + '%';
  });

  /* ── Shared status colours for Leaflet maps ─────── */
  NS.STATUS_COLORS = {
    submitted: '#c77d0a', seen: '#2563a8', in_progress: '#6d4fc4', resolved: '#238250', rejected: '#b83434'
  };
})();
