/* static/js/detail-map.js — small location map on the complaint detail page. */
(function () {
  'use strict';

  var el = document.querySelector('[data-detail-map]');
  if (!el) return;
  if (!window.L) { el.hidden = true; return; }

  var lat = Number(el.dataset.lat), lng = Number(el.dataset.lng);
  if (!isFinite(lat) || !isFinite(lng)) { el.hidden = true; return; }

  var colors = (window.NS && NS.STATUS_COLORS) || {};
  var map = L.map(el, { scrollWheelZoom: false, dragging: !L.Browser.mobile }).setView([lat, lng], 16);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);
  L.circleMarker([lat, lng], {
    radius: 10, color: '#fff', weight: 3, fillColor: colors[el.dataset.status] || '#2563a8', fillOpacity: 1
  }).addTo(map);
})();
