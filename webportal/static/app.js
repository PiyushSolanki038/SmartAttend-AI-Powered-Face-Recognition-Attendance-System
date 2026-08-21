// Shared behavior injected into every webportal page: dark-mode toggle, notification bell,
// and (dashboard only) a live-refresh poll. Injected via DOM manipulation rather than editing
// every template's markup individually, since there's no shared base template here.
(function () {
  "use strict";

  var THEME_KEY = "sa-theme";
  var NOTIF_SEEN_KEY = "sa-notif-last-seen";

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setTheme(theme) {
    if (theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
    var btn = document.getElementById("sa-theme-toggle");
    if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
  }

  function injectThemeToggle(container) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.id = "sa-theme-toggle";
    btn.className = "theme-toggle";
    btn.title = "Toggle dark mode";
    btn.textContent = currentTheme() === "dark" ? "☀️" : "🌙";
    btn.addEventListener("click", function () {
      setTheme(currentTheme() === "dark" ? "light" : "dark");
    });
    container.appendChild(btn);
  }

  // ---------- Notification bell ----------

  function timeAgo(iso) {
    if (!iso) return "";
    var diffMs = Date.now() - new Date(iso).getTime();
    var mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    var hours = Math.floor(mins / 60);
    if (hours < 24) return hours + "h ago";
    return Math.floor(hours / 24) + "d ago";
  }

  function renderNotifPanel(panel, items) {
    panel.innerHTML = "";
    var title = document.createElement("div");
    title.className = "notif-panel-title";
    title.textContent = "Notifications";
    panel.appendChild(title);

    if (!items.length) {
      var empty = document.createElement("div");
      empty.className = "notif-empty";
      empty.textContent = "You're all caught up.";
      panel.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "notif-item";
      var t = document.createElement("div");
      t.className = "notif-title";
      t.textContent = (item.type === "announcement" ? "📣 " : "✅ ") + item.title;
      var s = document.createElement("div");
      s.className = "notif-sub";
      s.textContent = (item.sub ? item.sub + " · " : "") + timeAgo(item.created_at);
      row.appendChild(t);
      row.appendChild(s);
      panel.appendChild(row);
    });
  }

  function injectNotifBell(container) {
    var wrap = document.createElement("div");
    wrap.className = "notif-wrap";

    var bell = document.createElement("button");
    bell.type = "button";
    bell.className = "notif-bell";
    bell.title = "Notifications";
    bell.textContent = "🔔";

    var dot = document.createElement("span");
    dot.className = "notif-dot";
    dot.style.display = "none";
    bell.appendChild(dot);

    var panel = document.createElement("div");
    panel.className = "notif-panel";

    wrap.appendChild(bell);
    wrap.appendChild(panel);
    container.appendChild(wrap);

    var latestSeenAt = null;

    function refresh() {
      fetch("/api/notifications").then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.items) return;
          renderNotifPanel(panel, data.items);
          var lastSeen = 0;
          try { lastSeen = parseInt(localStorage.getItem(NOTIF_SEEN_KEY) || "0", 10); } catch (e) {}
          var newest = data.items.length ? new Date(data.items[0].created_at).getTime() : 0;
          latestSeenAt = newest;
          dot.style.display = newest > lastSeen ? "block" : "none";
        })
        .catch(function () {});
    }

    bell.addEventListener("click", function () {
      panel.classList.toggle("open");
      if (panel.classList.contains("open")) {
        dot.style.display = "none";
        if (latestSeenAt) {
          try { localStorage.setItem(NOTIF_SEEN_KEY, String(latestSeenAt)); } catch (e) {}
        }
      }
    });
    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) panel.classList.remove("open");
    });

    refresh();
    setInterval(refresh, 60000); // poll every 60s — notifications aren't as time-sensitive as attendance
  }

  // ---------- Dashboard live-refresh ----------

  function startDashboardLive() {
    var liveDot = document.getElementById("sa-live-dot");
    function fmtPct(n) { return Math.round(n) + "%"; }

    function poll() {
      fetch("/api/dashboard-live").then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          var byId = function (id) { return document.getElementById(id); };
          if (byId("sa-overall-big")) byId("sa-overall-big").textContent = fmtPct(d.overall_pct);
          if (byId("sa-overallpct")) byId("sa-overallpct").textContent = fmtPct(d.overall_pct);
          if (byId("sa-hero-value")) byId("sa-hero-value").textContent = d.total_present + " / " + d.total_sessions;
          if (byId("sa-present")) byId("sa-present").textContent = d.total_present;
          if (byId("sa-absent")) byId("sa-absent").textContent = d.total_sessions - d.total_present;
          if (byId("sa-late")) byId("sa-late").textContent = d.late_count;
          if (byId("sa-subjcount")) byId("sa-subjcount").textContent = d.subjects_count;
          if (byId("sa-rank")) byId("sa-rank").textContent = d.rank ? "#" + d.rank : "--";
          if (byId("sa-streak")) byId("sa-streak").textContent = d.streak;
          if (byId("sa-goal")) byId("sa-goal").textContent = d.is_low ? d.days_needed : "-";
          var donut = byId("sa-donut");
          if (donut) donut.style.setProperty("--pct", Math.floor(d.overall_pct));
          if (liveDot) liveDot.style.display = "inline";
        })
        .catch(function () {});
    }
    poll();
    setInterval(poll, 15000);
  }

  // ---------- Boot ----------

  document.addEventListener("DOMContentLoaded", function () {
    var topbar = document.querySelector(".topbar");
    if (topbar) {
      var controls = document.createElement("div");
      controls.style.display = "flex";
      controls.style.alignItems = "center";
      controls.style.gap = "10px";
      controls.style.marginLeft = "10px";
      injectThemeToggle(controls);
      injectNotifBell(controls);
      topbar.appendChild(controls);
    }
    if (document.querySelector('[data-sa-live="dashboard"]')) {
      startDashboardLive();
    }
  });
})();
