/* static/js/complaint-form.js — photo picker and GPS capture for the complaint form. */
(function () {
  'use strict';

  var form = document.querySelector('[data-complaint-form]');
  if (!form) return;

  var mode = form.dataset.mode || 'create';
  var MAX_BYTES = (Number(form.dataset.maxMb) || 8) * 1024 * 1024;
  var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];

  /* ── Photo picker ───────────────────────────────── */
  var uploader = form.querySelector('[data-uploader]');
  var input = uploader && uploader.querySelector('input[type="file"]');
  if (input) {
    var dropzone = uploader.querySelector('[data-dropzone]');
    var preview = uploader.querySelector('[data-preview]');
    var previewImg = uploader.querySelector('[data-preview-img]');
    var previewName = uploader.querySelector('[data-preview-name]');
    var previewSize = uploader.querySelector('[data-preview-size]');
    var removeBtn = uploader.querySelector('[data-preview-remove]');
    var errorBox = uploader.querySelector('[data-upload-error]');
    var objectUrl = null;

    var showError = function (message) {
      errorBox.querySelector('span').textContent = message;
      errorBox.hidden = !message;
    };
    var formatSize = function (bytes) {
      return bytes >= 1024 * 1024 ? (bytes / 1024 / 1024).toFixed(1) + ' MB' : Math.max(1, Math.round(bytes / 1024)) + ' KB';
    };
    var reset = function () {
      input.value = '';
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null;
      preview.hidden = true;
      dropzone.hidden = false;
    };

    var accept = function (file) {
      if (!file) return;
      if (ALLOWED.indexOf(file.type) === -1) {
        reset();
        showError('"' + file.name + '" is not a supported photo. Please choose a JPEG, PNG or WebP image' +
                  (/hei[cf]/i.test(file.name) ? ' (iPhone HEIC photos can be exported as JPEG).' : '.'));
        return;
      }
      if (file.size > MAX_BYTES) {
        reset();
        showError('That photo is ' + formatSize(file.size) + '. Please choose one under ' + form.dataset.maxMb + ' MB.');
        return;
      }
      showError('');
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = URL.createObjectURL(file);
      previewImg.src = objectUrl;
      previewName.textContent = file.name;
      previewSize.textContent = formatSize(file.size) + (mode === 'edit' ? ' · replaces the current photo' : '');
      preview.hidden = false;
      dropzone.hidden = true;
      if (removeBtn) removeBtn.hidden = false;
    };

    input.addEventListener('change', function () { accept(input.files && input.files[0]); });
    if (removeBtn) removeBtn.addEventListener('click', function () { reset(); showError(''); });

    ['dragenter', 'dragover'].forEach(function (type) {
      dropzone.addEventListener(type, function (e) { e.preventDefault(); dropzone.classList.add('is-dragover'); });
    });
    ['dragleave', 'drop'].forEach(function (type) {
      dropzone.addEventListener(type, function () { dropzone.classList.remove('is-dragover'); });
    });
    dropzone.addEventListener('drop', function (e) {
      e.preventDefault();
      var file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      try {
        var transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
      } catch (err) { /* very old browsers: fall back to the picker */ }
      accept(file);
    });
  }

  /* ── GPS capture ────────────────────────────────── */
  var gps = form.querySelector('[data-gps]');
  var latField = document.getElementById('latitude');
  var lngField = document.getElementById('longitude');
  var title = gps.querySelector('[data-gps-title]');
  var text = gps.querySelector('[data-gps-text]');
  var retry = gps.querySelector('[data-gps-retry]');
  var mapBox = form.querySelector('[data-gps-map]');
  var miniMap = null, marker = null;

  var setState = function (state, heading, detail, showRetry) {
    gps.dataset.state = state;
    title.textContent = heading;
    text.textContent = detail;
    retry.hidden = !showRetry;
  };

  var showOnMap = function (lat, lng) {
    if (!window.L || !mapBox) return;
    mapBox.hidden = false;
    if (!miniMap) {
      miniMap = L.map(mapBox, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
      }).addTo(miniMap);
    }
    miniMap.setView([lat, lng], 17);
    if (marker) marker.setLatLng([lat, lng]);
    else marker = L.circleMarker([lat, lng], { radius: 9, color: '#fff', weight: 3, fillColor: '#2563a8', fillOpacity: 1 }).addTo(miniMap);
    setTimeout(function () { miniMap.invalidateSize(); }, 50);
  };

  var ERRORS = {
    1: ['Location permission denied', 'Allow location access for this site in your browser settings and try again — or describe a landmark below.'],
    2: ['Location unavailable', 'Your device could not determine where you are. Move to an open area and try again, or add a landmark below.'],
    3: ['Location timed out', 'It took too long to get a fix. Try again, or add a landmark below.']
  };

  var locate = function () {
    if (!('geolocation' in navigator)) {
      setState('error', 'Location not supported', 'This browser cannot share its location. Please describe a landmark below so the ward office can find the spot.', false);
      return;
    }
    if (!window.isSecureContext) {
      setState('error', 'Location needs a secure connection', 'Browsers only share location over HTTPS. Please add a landmark below.', false);
      return;
    }
    setState('pending', 'Finding your location…', 'Your browser may ask for permission. Stand close to the issue for best accuracy.', false);
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = pos.coords.latitude, lng = pos.coords.longitude;
        latField.value = lat.toFixed(6);
        lngField.value = lng.toFixed(6);
        var accuracy = Math.round(pos.coords.accuracy);
        setState('ok', 'Location captured', lat.toFixed(5) + ', ' + lng.toFixed(5) + ' · accurate to about ' + accuracy + ' m' +
                 (accuracy > 100 ? ' — a landmark below will help.' : ''), true);
        retry.lastChild.textContent = 'Update location';
        showOnMap(lat, lng);
      },
      function (err) {
        // Never submit stale or made-up coordinates.
        latField.value = '';
        lngField.value = '';
        var msg = ERRORS[err.code] || ['Location unavailable', 'Please add a landmark below.'];
        setState('error', msg[0], msg[1], err.code !== 1);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  };

  retry.addEventListener('click', locate);

  var startup = function () {
    if (mode === 'create') {
      locate();
    } else if (gps.dataset.initialLat) {
      showOnMap(Number(gps.dataset.initialLat), Number(gps.dataset.initialLng));
    }
  };
  // Leaflet is loaded with defer before this script, so it is ready here.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startup);
  else startup();

  /* ── Submit: tell the user when no location is attached ─ */
  form.addEventListener('submit', function (e) {
    if (mode !== 'create' || latField.value || form.dataset.noLocationOk === 'yes') return;
    var address = form.querySelector('[name="address"]');
    if (address && !address.value.trim()) {
      e.preventDefault();
      e.stopImmediatePropagation();
      form.dataset.noLocationOk = 'yes';
      gps.scrollIntoView({ behavior: 'smooth', block: 'center' });
      address.focus();
      if (window.NS) NS.toast('No GPS location is attached. Add a landmark so the ward office can find the spot — or submit again to send it without one.', 'warning');
    }
  }, true);
})();
