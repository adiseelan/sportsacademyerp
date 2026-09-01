/* SportsAcademy ERP — progressive enhancement. No external deps. */
(function () {
  "use strict";

  // ---- Sidebar (mobile) --------------------------------------------
  var toggle = document.getElementById("menuToggle");
  var sidebar = document.getElementById("sidebar");
  var backdrop = document.getElementById("backdrop");
  function closeNav() {
    if (sidebar) sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("show");
  }
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
      if (backdrop) backdrop.classList.toggle("show");
    });
  }
  if (backdrop) backdrop.addEventListener("click", closeNav);

  // ---- Auto-dismiss flash messages ---------------------------------
  document.querySelectorAll(".messages .alert").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity .4s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 400);
    }, 7000);
  });

  // ---- Geo check-in ------------------------------------------------
  var geoForm = document.getElementById("checkinForm");
  if (geoForm) {
    var latEl = document.getElementById("lat");
    var lngEl = document.getElementById("lng");
    var statusEl = document.getElementById("geoStatus");
    var geoBtn = document.getElementById("geoCheckinBtn");
    var manualBox = document.getElementById("manualBox");

    function setStatus(msg, cls) {
      if (statusEl) { statusEl.textContent = msg; statusEl.className = "alert alert-" + (cls || "info"); }
    }
    function locate() {
      if (!navigator.geolocation) {
        setStatus("Location not supported on this device. Use manual check-in.", "warning");
        if (manualBox) manualBox.style.display = "block";
        return;
      }
      setStatus("Detecting your location…", "info");
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          latEl.value = pos.coords.latitude;
          lngEl.value = pos.coords.longitude;
          setStatus("Location captured. You can start the session.", "success");
          if (geoBtn) geoBtn.disabled = false;
        },
        function () {
          setStatus("Couldn't read GPS. Use manual check-in with a reason.", "warning");
          if (manualBox) manualBox.style.display = "block";
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
      );
    }
    var retry = document.getElementById("retryGeo");
    if (retry) retry.addEventListener("click", locate);
    locate();
  }

  // ---- Live session polling ----------------------------------------
  var live = document.getElementById("liveData");
  if (live) {
    var url = live.getAttribute("data-url");
    var countEl = document.getElementById("liveCount");
    var asOfEl = document.getElementById("liveAsOf");
    function render(data) {
      if (countEl) countEl.textContent = data.count;
      if (asOfEl) asOfEl.textContent = "Updated " + data.as_of;
      if (!data.sessions.length) {
        live.innerHTML = '<div class="empty"><div class="empty-ico">🟢</div>' +
          "<p>No sessions are live right now.</p></div>";
        return;
      }
      var rows = data.sessions.map(function (s) {
        return '<tr><td><span class="dot live"></span>' + esc(s.coach) + "</td>" +
          "<td>" + esc(s.venue) + "</td>" +
          "<td>" + esc(s.sport) + " · " + esc(s.batch) + "</td>" +
          "<td>" + esc(s.since) + (s.manual ? ' <span class="badge amber">manual</span>' : "") + "</td></tr>";
      }).join("");
      live.innerHTML = '<div class="table-wrap"><table class="data"><thead><tr>' +
        "<th>Coach</th><th>Venue</th><th>Batch</th><th>Since</th></tr></thead><tbody>" +
        rows + "</tbody></table></div>";
    }
    function esc(v) { var d = document.createElement("div"); d.textContent = v == null ? "" : v; return d.innerHTML; }
    function poll() {
      fetch(url, { headers: { "X-Requested-With": "fetch" } })
        .then(function (r) { return r.json(); })
        .then(render)
        .catch(function () {});
    }
    poll();
    setInterval(poll, 6000);
  }
})();
