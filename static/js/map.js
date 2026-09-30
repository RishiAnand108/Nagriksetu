/* static/js/map.js — the complaint map page. */
(function () {
  'use strict';

  var el = document.querySelector('[data-map]');
  if (!el) return;

  var overlays = {};
  document.querySelectorAll('[data-map-state]').forEach(function (node) { overlays[node.dataset.mapState] = node; });
  var counter = document.querySelector('[data-map-count]');

  var show = function (state) {
    Object.keys(overlays).forEach(function (key) { overlays[key].hidden = key !== state; });
  };
  var fail = function (heading, detail) {
    document.querySelector('[data-map-error-title]').textContent = heading;
    document.querySelector('[data-map-error-text]').textContent = detail;
    if (counter) counter.textContent = '';
    show('error');
  };

  if (!window.L) {
    fail('Map library did not load', 'Check your connection (or any content blocker) and reload the page.');
    return;
  }

  var COLORS = (window.NS && NS.STATUS_COLORS) || {};
  var map = L.map(el, { scrollWheelZoom: true }).setView([18.5204, 73.8567], 12); // Pune until data arrives
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  var layer = L.featureGroup().addTo(map);

  var escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  };
  // URLs come from our own server, but only same-origin paths or http(s) are ever rendered.
  var safeUrl = function (u) { return /^(\/|https?:\/\/)/.test(u || '') ? u : ''; };
  var validCoord = function (c) {
    return typeof c.lat === 'number' && typeof c.lng === 'number' && isFinite(c.lat) && isFinite(c.lng) &&
      Math.abs(c.lat) <= 90 && Math.abs(c.lng) <= 180 && !(c.lat === 0 && c.lng === 0);
  };

  var popup = function (c) {
    var thumb = safeUrl(c.thumb);
    return '<div class="popup-title">' + escapeHtml(c.title) + '</div>' +
      '<div class="popup-row"><span class="badge plain">' + escapeHtml(c.issue) + '</span>' +
      '<span class="badge plain">' + escapeHtml(c.status_label) + '</span>' +
      (c.high_priority ? '<span class="badge danger">' + escapeHtml(c.priority) + ' priority</span>' : '') + '</div>' +
      (thumb ? '<img class="popup-thumb" src="' + escapeHtml(thumb) + '" alt="">' : '') +
      '<div class="popup-meta">#' + escapeHtml(c.id) + ' · ' + escapeHtml(c.created) +
      (c.ward ? ' · ' + escapeHtml(c.ward) : '') +
      (c.address ? '<br>' + escapeHtml(c.address) : '') +
      (c.upvotes ? '<br>' + escapeHtml(c.upvotes) + ' resident' + (c.upvotes === 1 ? '' : 's') + ' affected' : '') + '</div>' +
      '<a class="popup-link" href="' + escapeHtml(safeUrl(c.url)) + '">Open complaint &rarr;</a>';
  };

  var load = function () {
    show('loading');
    var params = new URLSearchParams(window.location.search);
    params.delete('page');

    fetch(el.dataset.feed + '?' + params.toString(), {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (response) {
        if (response.status === 401 || response.status === 403) {
          throw { heading: 'Your session has ended', detail: 'Please sign in again to see the map.' };
        }
        if (!response.ok) {
          throw { heading: 'The server could not load the map data', detail: 'This is a problem on our side (error ' + response.status + '). Please try again shortly.' };
        }
        return response.json().catch(function () {
          throw { heading: 'Unexpected response', detail: 'The map data could not be read. Please reload the page.' };
        });
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.complaints)) {
          throw { heading: 'Unexpected response', detail: 'The map data could not be read. Please reload the page.' };
        }
        layer.clearLayers();
        var plotted = 0;
        data.complaints.forEach(function (c) {
          if (!validCoord(c)) return;
          L.circleMarker([c.lat, c.lng], {
            radius: c.high_priority ? 11 : 8,
            color: '#ffffff',
            weight: c.high_priority ? 3 : 2,
            fillColor: COLORS[c.status] || '#5f6e7e',
            fillOpacity: 0.92
          }).bindPopup(popup(c), { maxWidth: 260 }).bindTooltip(c.status_label + ': ' + c.title).addTo(layer);
          plotted += 1;
        });

        if (counter) counter.textContent = plotted + ' complaint' + (plotted === 1 ? '' : 's') + ' plotted' + (data.count >= 500 ? ' (first 500)' : '');
        if (!plotted) { show('empty'); return; }
        show(null);
        map.fitBounds(layer.getBounds(), { padding: [40, 40], maxZoom: 16 });
      })
      .catch(function (err) {
        if (err && err.heading) fail(err.heading, err.detail);
        else fail('You appear to be offline', 'We could not reach the server. Check your connection and try again.');
      });
  };

  var retry = document.querySelector('[data-map-retry]');
  if (retry) retry.addEventListener('click', load);
  load();
})();
