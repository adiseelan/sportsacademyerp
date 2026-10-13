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

  // ---- CSP-safe replacements for inline handlers -------------------
  // (script-src 'self' blocks onclick= / onchange= attributes in templates.)
  document.querySelectorAll("[data-print]").forEach(function (el) {
    el.addEventListener("click", function () { window.print(); });
  });
  document.querySelectorAll("select[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { if (el.form) el.form.submit(); });
  });

  // ---- Dropdowns (<details class="dropdown">) -----------------------
  // Native <details> opens/closes without JS; this adds: one open at a time,
  // close on outside click / Esc, scroll the selected period into view, and
  // pins row (⋮) menus to the viewport so the scrolling table can't clip them.
  // Delegated, so menus rendered later (live table rows) work too.
  function openDropdowns() { return document.querySelectorAll("details.dropdown[open]"); }
  function closeRowMenus() { document.querySelectorAll("details.row-menu[open]").forEach(function (d) { d.open = false; }); }
  function placeRowMenu(d) {
    var r = d.querySelector("summary").getBoundingClientRect();
    var panel = d.querySelector(".dropdown-panel");
    var w = panel.offsetWidth, h = panel.offsetHeight;
    var left = Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8));
    var top = r.bottom + 6;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
    panel.style.left = left + "px";
    panel.style.top = top + "px";
  }
  document.addEventListener("toggle", function (e) {
    var d = e.target;
    if (!d.classList || !d.classList.contains("dropdown")) return;
    var cell = d.classList.contains("row-menu") && d.closest("td");
    if (cell) cell.classList.toggle("menu-open", d.open);  // fallback for browsers without :has()
    if (!d.open) return;
    openDropdowns().forEach(function (o) { if (o !== d) o.open = false; });
    var sel = d.querySelector(".period-list .is-selected");
    if (sel && sel.offsetParent) {
      var list = sel.parentElement;
      list.scrollTop = Math.max(0, sel.offsetTop - list.offsetTop - 8);
    }
    if (d.classList.contains("row-menu")) placeRowMenu(d);
  }, true);
  document.addEventListener("click", function (e) {
    openDropdowns().forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    openDropdowns().forEach(function (d) {
      d.open = false;
      var s = d.querySelector("summary"); if (s) s.focus();
    });
  });
  // Keep an open row menu attached to its ⋮ while the table scrolls; close it
  // once the button scrolls out of the table's visible area.
  document.addEventListener("scroll", function () {
    document.querySelectorAll("details.row-menu[open]").forEach(function (d) {
      var box = d.closest(".table-wrap");
      var b = d.querySelector("summary").getBoundingClientRect();
      var v = box ? box.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };
      if (b.bottom < v.top || b.top > v.bottom) { d.open = false; } else { placeRowMenu(d); }
    });
  }, true);
  window.addEventListener("resize", closeRowMenus);

  // ---- Live list filter (Branches search box) -----------------------
  // Filters the list as you type; pressing Enter still runs the server-side search.
  document.querySelectorAll("[data-filter-input]").forEach(function (input) {
    var list = document.querySelector("[data-filter-list]");
    if (!list) return;
    var none = list.querySelector(".filter-empty");
    var echo = list.querySelector("[data-filter-echo]");
    input.addEventListener("input", function () {
      var term = input.value.trim().toLowerCase();
      var items = list.querySelectorAll("[data-filter-text]");
      var shown = 0;
      items.forEach(function (el) {
        var hit = !term || el.getAttribute("data-filter-text").toLowerCase().indexOf(term) !== -1;
        el.hidden = !hit;
        if (hit) shown++;
      });
      if (echo) echo.textContent = input.value.trim();
      if (none) none.hidden = shown !== 0 || !items.length;
    });
  });

  // ---- Notifications: grey ✕ dismisses in place ---------------------
  document.querySelectorAll("form[data-dismiss]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.fetch) return;            // old browser: normal POST + redirect
      e.preventDefault();
      fetch(form.action, {
        method: "POST", body: new FormData(form), credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" }
      })
        .then(function (r) { if (!r.ok) throw r; return r.json(); })
        .then(function (data) {
          var row = form.closest(".note");
          var list = row && row.parentElement;
          if (row) { row.classList.add("is-leaving"); setTimeout(function () {
            row.remove();
            if (list && !list.querySelector(".note")) {
              list.innerHTML = '<div class="empty"><div class="empty-ico">🔔</div><p>No notifications.</p></div>';
            }
          }, 200); }
          document.querySelectorAll("[data-unread-badge]").forEach(function (b) {
            if (data.unread > 0) { b.textContent = data.unread; } else { b.remove(); }
          });
        })
        .catch(function () { form.submit(); });
    });
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
          "<td>" + esc(s.since) + (s.manual ? ' <span class="badge amber">manual</span>' : "") + "</td>" +
          '<td class="row-actions">' + rowMenu(s) + "</td></tr>";
      }).join("");
      live.innerHTML = '<div class="table-wrap"><table class="data live-table"><thead><tr>' +
        '<th>Coach</th><th>Venue</th><th>Batch</th><th>Since</th><th class="col-actions"><span class="sr-only">Actions</span></th>' +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>";
    }
    // ⋮ (more_vert) menu for one row; items come from the server, per role.
    function rowMenu(s) {
      var items = (s.actions || []).map(function (a) {
        return '<a class="menu-item" href="' + esc(a.url) + '"><span class="menu-ico">' + esc(a.icon) + "</span>" +
          "<span>" + esc(a.label) + (a.sub ? "<small>" + esc(a.sub) + "</small>" : "") + "</span></a>";
      }).join("") || '<span class="menu-item muted">No actions</span>';
      return '<details class="dropdown row-menu"><summary class="kebab-sm" aria-label="More actions for ' + esc(s.coach) + '">' +
        '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="4.5" r="1.6" fill="currentColor"></circle>' +
        '<circle cx="10" cy="10" r="1.6" fill="currentColor"></circle><circle cx="10" cy="15.5" r="1.6" fill="currentColor"></circle></svg>' +
        '</summary><div class="dropdown-panel menu-panel">' + items + "</div></details>";
    }
    function esc(v) {
      var d = document.createElement("div"); d.textContent = v == null ? "" : v;
      return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function poll() {
      if (live.querySelector("details.row-menu[open]")) return;  // don't yank an open menu away
      fetch(url, { headers: { "X-Requested-With": "fetch" } })
        .then(function (r) { return r.json(); })
        .then(render)
        .catch(function () {});
    }
    poll();
    setInterval(poll, 6000);
  }
})();
