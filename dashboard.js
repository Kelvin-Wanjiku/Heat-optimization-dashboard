(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Theme
  // ---------------------------------------------------------------------
  var themeBtn = document.getElementById("themeToggle");
  function applyTheme(mode) {
    document.documentElement.setAttribute("data-theme", mode === "dark" ? "dark" : "light");
    var radios = document.querySelectorAll('input[name="appearance"]');
    radios.forEach(function (r) { r.checked = r.value === (mode === "dark" ? "dark" : "light"); });
  }
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  var savedTheme = null;
  try { savedTheme = localStorage.getItem("hd-theme"); } catch (e) {}
  applyTheme(savedTheme === "dark" ? "dark" : "light");

  function setTheme(mode) {
    applyTheme(mode);
    try { localStorage.setItem("hd-theme", mode); } catch (e) {}
    renderAll();
  }
  themeBtn.addEventListener("click", function () {
    setTheme(currentTheme() === "dark" ? "light" : "dark");
  });
  document.querySelectorAll('input[name="appearance"]').forEach(function (r) {
    r.addEventListener("change", function () { if (r.checked) setTheme(r.value); });
  });

  // ---------------------------------------------------------------------
  // Units (°C / °F)
  // ---------------------------------------------------------------------
  var unit = "c";
  try { unit = localStorage.getItem("hd-unit") || "c"; } catch (e) {}
  document.querySelectorAll('input[name="unit"]').forEach(function (r) {
    r.checked = r.value === unit;
    r.addEventListener("change", function () {
      if (!r.checked) return;
      unit = r.value;
      try { localStorage.setItem("hd-unit", unit); } catch (e) {}
      renderAll();
    });
  });
  function toUnit(c) { return unit === "f" ? (c * 9) / 5 + 32 : c; }
  function unitLabel() { return unit === "f" ? "°F" : "°C"; }
  function fmtTemp(c, decimals) {
    var d = decimals === undefined ? 1 : decimals;
    return toUnit(c).toFixed(d) + unitLabel();
  }

  // ---------------------------------------------------------------------
  // Nav / section switching
  // ---------------------------------------------------------------------
  var sectionTitles = { weekly: "Weekly temperature", control: "Control panel", settings: "Settings", about: "About" };
  document.getElementById("mainNav").addEventListener("click", function (e) {
    var btn = e.target.closest(".nav-item");
    if (!btn) return;
    var section = btn.getAttribute("data-section");
    document.querySelectorAll(".nav-item").forEach(function (b) {
      b.setAttribute("aria-current", b === btn ? "true" : "false");
    });
    document.querySelectorAll(".view").forEach(function (v) { v.hidden = true; });
    document.getElementById("view-" + section).hidden = false;
    document.getElementById("pageTitle").textContent = sectionTitles[section];
    if (section === "weekly" && DATA) { renderWeekly(); renderWeatherFx(); }
    closeSidebar();
  });
  document.querySelector('.nav-item[data-section="control"]').setAttribute("aria-current", "true");

  // Mobile sidebar toggle
  var sidebarEl = document.getElementById("sidebar");
  var backdropEl = document.getElementById("sidebarBackdrop");
  function openSidebar() { sidebarEl.classList.add("open"); backdropEl.classList.add("open"); }
  function closeSidebar() { sidebarEl.classList.remove("open"); backdropEl.classList.remove("open"); }
  document.getElementById("menuToggle").addEventListener("click", openSidebar);
  backdropEl.addEventListener("click", closeSidebar);

  // ---------------------------------------------------------------------
  // State & data load
  // ---------------------------------------------------------------------
  var DATA = null;
  var rangeDays = 7;
  var currentView = "charts";

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  fetch("data/dashboard_data.json")
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (json) {
      DATA = json;
      document.getElementById("subtitle").textContent =
        "Last " + Math.round(DATA.timeseries.length / 24) + " days · " +
        fmtDate(DATA.meta.period_start) + " – " + fmtDate(DATA.meta.period_end);
      var scopeEl = document.getElementById("scenarioScope");
      if (scopeEl && DATA.meta.scenario_scope) scopeEl.textContent = DATA.meta.scenario_scope;
      renderAll();renderAll();
setLiveWeather(DATA.timeseries[DATA.timeseries.length - 1].outdoor_temp_c); // shown until/unless live weather loads
    })
    .catch(function (err) {
      document.getElementById("subtitle").innerHTML =
        "Could not load <code>data/dashboard_data.json</code> (" + escapeHtml(String(err.message)) +
        "). If you opened this file directly, serve the folder instead: " +
        "<code>python3 -m http.server</code>, then open the localhost URL.";
    });
  function setLiveWeather(c) {
    document.getElementById("weatherVal").textContent = fmtTemp(c, 0);
    var el = document.getElementById("controlOutdoor");
    if (el) el.textContent = fmtTemp(c, 0);
  }

  // Open-Meteo's current_weather field is built specifically for "right now"
  // (not a forecast time series to search through), free, keyless, and has
  // no CORS restriction for browser fetches — unlike weather.com, which has
  // no public API and blocks cross-origin requests, so its page can't be
  // read directly from client-side JS.
  fetch("https://api.open-meteo.com/v1/forecast?latitude=58.283&longitude=12.285&current_weather=true")
    .then(function (r) { return r.json(); })
    .then(function (wx) {
      if (wx.current_weather && typeof wx.current_weather.temperature === "number") {
        setLiveWeather(wx.current_weather.temperature);
      }
    })
    .catch(function () {
  if (DATA && DATA.timeseries && DATA.timeseries.length) {
    setLiveWeather(DATA.timeseries[DATA.timeseries.length - 1].outdoor_temp_c);
  }
});
  function fmtDate(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  function fmtDateTime(iso) {
    var d = new Date(iso);
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) +
      ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Filters (weekly view)
  // ---------------------------------------------------------------------
  document.getElementById("rangeSeg").addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    if (!btn) return;
    rangeDays = parseInt(btn.getAttribute("data-days"), 10);
    Array.prototype.forEach.call(this.querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b === btn ? "true" : "false");
    });
    renderWeekly();
  });

  document.getElementById("viewSeg").addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    if (!btn) return;
    currentView = btn.getAttribute("data-view");
    Array.prototype.forEach.call(this.querySelectorAll("button"), function (b) {
      b.setAttribute("aria-pressed", b === btn ? "true" : "false");
    });
    document.getElementById("chartsView").style.display = currentView === "charts" ? "" : "none";
    document.getElementById("tableView").style.display = currentView === "table" ? "" : "none";
  });

  // ---------------------------------------------------------------------
  // Render orchestration
  // ---------------------------------------------------------------------
  function getSlice() {
    var all = DATA.timeseries;
    var n = rangeDays * 24;
    return all.slice(0, Math.min(n, all.length));
  }

  function renderAll() {
    if (!DATA) return;
    renderWeatherChip();
    renderWeatherFx();
    renderWeekly();
    renderBuildings();
    renderBenchmarks();
    renderParamTable();
    renderForecast();
  }

  // ---------------------------------------------------------------------
  // Heat-usage forecast (preview) — a teammate is training a short-horizon
  // model (SINTEF COFACTOR-SBHUB Oslo school dataset) but hasn't shared
  // trained output yet. DATA.forecast.status === "illustrative" means these
  // numbers are a stand-in, not real predictions, so every render keeps the
  // "illustrative" badge visible rather than letting it read like live output.
  // ---------------------------------------------------------------------
  function renderForecast() {
    var f = DATA.forecast;
    var row = document.getElementById("forecastRow");
    if (!row || !f) return;

    row.innerHTML = f.horizons.map(function (h) {
      return '<div class="kpi">' +
        '<div class="label">' + escapeHtml(h.label) + '</div>' +
        '<div class="value" style="font-size:19px;">' + fmtNum(h.predicted_kwh) + ' kWh</div>' +
        '<div class="sub">illustrative, not model output</div>' +
        '</div>';
    }).join("");

    var featEl = document.getElementById("forecastFeatures");
    if (featEl) {
      featEl.textContent = "Features: " + f.features.join(", ") + ". History window: " + f.history_windows.join(" or ") + ".";
    }
  }

  // ---------------------------------------------------------------------
  // Settings — validation benchmarks + model parameters (from the
  // teammate's classroom-twin parameter research, data/params_research.md).
  // Static per load: reuses the .kpi tile and .data-table markup already
  // styled for the Weekly temperature page, so nothing new to theme.
  // ---------------------------------------------------------------------
  function renderBenchmarks() {
    var el = document.getElementById("benchmarkRow");
    if (!el || !DATA.benchmarks) return;
    el.innerHTML = DATA.benchmarks.map(function (b) {
      return '<div class="kpi">' +
        '<div class="label">' + escapeHtml(b.label) + '</div>' +
        '<div class="value" style="font-size:19px;">' + escapeHtml(b.value) + '</div>' +
        '<div class="sub">' + escapeHtml(b.source) + '</div>' +
        '</div>';
    }).join("");
  }

  function renderParamTable() {
    var tbody = document.querySelector("#paramTable tbody");
    if (!tbody || !DATA.model_parameters) return;
    tbody.innerHTML = DATA.model_parameters.map(function (p) {
      return '<tr>' +
        '<td><span class="b-type-tag">' + escapeHtml(p.group) + '</span></td>' +
        '<td>' + escapeHtml(p.parameter) + '</td>' +
        '<td>' + escapeHtml(p.value) + '</td>' +
        '<td><span class="confidence-pill ' + escapeHtml(p.confidence) + '">' + escapeHtml(p.confidence) + '</span></td>' +
        '<td>' + escapeHtml(p.source) + '</td>' +
        '</tr>';
    }).join("");

    var hintEl = document.getElementById("paramOpenItems");
    if (hintEl && DATA.open_items && DATA.open_items.length) {
      hintEl.innerHTML = "<strong>Open items:</strong> " + DATA.open_items.map(escapeHtml).join(" &middot; ");
    }
  }

  function renderWeatherChip() {

  }

  // Decorative weather effect behind the Weekly temperature page, based on
  // today's outdoor reading: <=0C snow, 0-8C rain, warmer is sunny. There's
  // no precipitation field in the data, so this is a temperature-based
  // stand-in rather than a real forecast condition.
  function renderWeatherFx() {
    var fx = document.getElementById("weatherFx");
    if (!fx) return;
    var temp = DATA.timeseries[DATA.timeseries.length - 1].outdoor_temp_c;
    var kind = temp <= 0 ? "snow" : (temp <= 8 ? "rain" : "sunny");
    fx.innerHTML = "";

    function rand(min, max) { return min + Math.random() * (max - min); }

    if (kind === "snow") {
      for (var i = 0; i < 44; i++) {
        var flake = document.createElement("div");
        flake.className = "flake";
        var size = rand(3, 7);
        flake.style.left = rand(0, 100) + "%";
        flake.style.width = size + "px";
        flake.style.height = size + "px";
        flake.style.opacity = rand(0.35, 0.9).toFixed(2);
        var fall = rand(7, 14);
        var sway = rand(3, 6);
        flake.style.animationDuration = fall + "s, " + sway + "s";
        flake.style.animationDelay = "-" + rand(0, fall).toFixed(1) + "s, -" + rand(0, sway).toFixed(1) + "s";
        fx.appendChild(flake);
      }
    } else if (kind === "rain") {
      for (var j = 0; j < 60; j++) {
        var drop = document.createElement("div");
        drop.className = "drop";
        drop.style.left = rand(0, 100) + "%";
        drop.style.height = rand(12, 22) + "px";
        drop.style.opacity = rand(0.4, 0.9).toFixed(2);
        var dur = rand(0.45, 0.9);
        drop.style.animationDuration = dur + "s";
        drop.style.animationDelay = "-" + rand(0, dur).toFixed(2) + "s";
        fx.appendChild(drop);
      }
    } else {
      var glow = document.createElement("div");
      glow.className = "sun-glow";
      fx.appendChild(glow);
      for (var k = 0; k < 14; k++) {
        var sp = document.createElement("div");
        sp.className = "sparkle";
        sp.style.left = rand(5, 95) + "%";
        sp.style.top = rand(5, 70) + "%";
        sp.style.animationDelay = "-" + rand(0, 3).toFixed(1) + "s";
        fx.appendChild(sp);
      }
    }
  }

  function renderWeekly() {
    var rows = getSlice();
    renderKpis(rows);
    renderTempChart(rows);
    renderPowerChart(rows);
    renderCumChart(rows);
    renderTable(rows);
  }

  // ---------------------------------------------------------------------
  // KPI tiles (recomputed per selected range)
  // ---------------------------------------------------------------------
  function renderKpis(rows) {
    var baseTotal = 0, optTotal = 0, basePeak = 0, optPeak = 0;
    var baseViol = 0, optViol = 0;
    var baseCostSek = 0, optCostSek = 0, hasRealCost = false;
    var lo = DATA.meta.comfort_band_c[0], hi = DATA.meta.comfort_band_c[1];
    rows.forEach(function (r) {
      baseTotal += r.baseline_energy_kwh;
      optTotal += r.optimized_energy_kwh;
      basePeak = Math.max(basePeak, r.baseline_heating_power_kw);
      optPeak = Math.max(optPeak, r.optimized_heating_power_kw);
      if (typeof r.baseline_cost_sek === "number") {
        hasRealCost = true;
        baseCostSek += r.baseline_cost_sek;
        optCostSek += r.optimized_cost_sek;
      }
      if (r.occupied) {
        if (r.baseline_indoor_temp_c < lo || r.baseline_indoor_temp_c > hi) baseViol++;
        if (r.optimized_indoor_temp_c < lo || r.optimized_indoor_temp_c > hi) optViol++;
      }
    });
    var savingsPct = baseTotal > 0 ? (1 - optTotal / baseTotal) * 100 : 0;
    var peakPct = basePeak > 0 ? (1 - optPeak / basePeak) * 100 : 0;

    // Cost tile — prefers the real per-hour cost_total_SEK the digital twin
    // already computed (heat + electricity, at its own sourced prices).
    // Falls back to kWh totals × the midpoint of a sourced heat-price range
    // when real cost isn't in the data (e.g. an older/synthetic export).
    var costSub;
    if (!hasRealCost) {
      var priceRange = (DATA.meta.heat_price_sek_per_kwh) || [1.10, 1.35];
      var priceMid = (priceRange[0] + priceRange[1]) / 2;
      baseCostSek = baseTotal * priceMid;
      optCostSek = optTotal * priceMid;
      costSub = "vs " + fmtNum(baseCostSek) + " kr baseline · at " + priceRange[0].toFixed(2) + "–" + priceRange[1].toFixed(2) + " kr/kWh";
    } else {
      var hp = DATA.meta.heat_price_sek_per_kwh ? DATA.meta.heat_price_sek_per_kwh[0] : null;
      var ep = DATA.meta.electricity_price_sek_per_kwh;
      costSub = "vs " + fmtNum(baseCostSek) + " kr baseline · district heat + electricity" +
        (hp && ep ? " at " + hp.toFixed(2) + " / " + ep.toFixed(2) + " kr/kWh" : "");
    }
    var costSavingsSek = baseCostSek - optCostSek;

    var tiles = [
      {
        label: "Total energy use",
        value: fmtNum(optTotal) + " kWh",
        sub: "vs " + fmtNum(baseTotal) + " kWh baseline",
        delta: (savingsPct >= 0 ? "↓ " : "↑ ") + Math.abs(savingsPct).toFixed(1) + "% " + (savingsPct >= 0 ? "savings" : "more"),
        good: savingsPct >= 0
      },
      {
        label: "Estimated heating cost",
        value: fmtNum(optCostSek) + " kr",
        sub: costSub,
        delta: (costSavingsSek >= 0 ? "↓ " : "↑ ") + fmtNum(Math.abs(costSavingsSek)) + " kr " + (costSavingsSek >= 0 ? "saved" : "more"),
        good: costSavingsSek >= 0
      },
      {
        label: "Peak heating demand",
        value: fmtNum(optPeak) + " kW",
        sub: "vs " + fmtNum(basePeak) + " kW baseline",
        delta: (peakPct >= 0 ? "↓ " : "↑ ") + Math.abs(peakPct).toFixed(1) + "% " + (peakPct >= 0 ? "lower peak" : "higher"),
        good: peakPct >= 0
      },
      {
        label: "Comfort violations",
        value: optViol + " hrs",
        sub: "vs " + baseViol + " hrs baseline",
        delta: baseViol - optViol >= 0 ? "↓ " + (baseViol - optViol) + " fewer" : "↑ " + (optViol - baseViol) + " more",
        good: optViol <= baseViol
      },
      {
        label: "Occupied hours in range",
        value: rows.filter(function (r) { return r.occupied; }).length + " hrs",
        sub: rows.length + " hrs total in range",
        delta: null,
        good: true
      }
    ];

    var html = tiles.map(function (t) {
      return '<div class="kpi">' +
        '<div class="label">' + escapeHtml(t.label) + '</div>' +
        '<div class="value">' + t.value + '</div>' +
        (t.delta ? '<div class="delta ' + (t.good ? 'good' : '') + '">' + escapeHtml(t.delta) + '</div>' : '') +
        '<div class="sub">' + escapeHtml(t.sub) + '</div>' +
        '</div>';
    }).join("");
    document.getElementById("kpiRow").innerHTML = html;
  }

  function fmtNum(n) {
    if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + "K";
    return n.toFixed(0);
  }

  // ---------------------------------------------------------------------
  // Shared SVG chart helpers
  // ---------------------------------------------------------------------
  var MARGIN = { top: 10, right: 16, bottom: 24, left: 40 };

  function niceTicks(min, max, count) {
    var range = max - min || 1;
    var rough = range / count;
    var mag = Math.pow(10, Math.floor(Math.log10(rough)));
    var norm = rough / mag;
    var step;
    if (norm < 1.5) step = 1 * mag;
    else if (norm < 3) step = 2 * mag;
    else if (norm < 7) step = 5 * mag;
    else step = 10 * mag;
    var ticks = [];
    var t = Math.ceil(min / step) * step;
    for (; t <= max + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
    return ticks;
  }

  function buildLineChart(opts) {
    var wrap = document.getElementById(opts.wrapId);
    wrap.innerHTML = "";
    var width = opts.width || wrap.clientWidth || 1100;
    var height = opts.height || 220;
    var innerW = width - MARGIN.left - MARGIN.right;
    var innerH = height - MARGIN.top - MARGIN.bottom;

    var rows = opts.rows;
    var n = rows.length;
    if (n === 0) return;

    var allVals = [];
    opts.series.forEach(function (s) {
      rows.forEach(function (r) { allVals.push(r[s.key]); });
    });
    var yMin = Math.min.apply(null, allVals);
    var yMax = Math.max.apply(null, allVals);
    if (opts.yMinFloor !== undefined) yMin = Math.min(yMin, opts.yMinFloor);
    if (opts.yMaxCeil !== undefined) yMax = Math.max(yMax, opts.yMaxCeil);
    var pad = (yMax - yMin) * 0.1 || 1;
    yMin -= pad; yMax += pad;

    function x(i) { return MARGIN.left + (innerW * i) / Math.max(1, n - 1); }
    function y(v) { return MARGIN.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH; }

    var svgNS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("preserveAspectRatio", "none");

    if (opts.occupancyBand) {
      var i = 0;
      while (i < n) {
        if (rows[i].occupied) {
          var start = i;
          while (i < n && rows[i].occupied) i++;
          var rect = document.createElementNS(svgNS, "rect");
          rect.setAttribute("class", "occ-band");
          rect.setAttribute("x", x(start));
          rect.setAttribute("y", MARGIN.top);
          rect.setAttribute("width", Math.max(0, x(i - 1) - x(start)));
          rect.setAttribute("height", innerH);
          svg.appendChild(rect);
        } else { i++; }
      }
    }

    if (opts.comfortBand) {
      var band = document.createElementNS(svgNS, "rect");
      band.setAttribute("class", "comfort-band");
      band.setAttribute("x", MARGIN.left);
      band.setAttribute("y", y(opts.comfortBand[1]));
      band.setAttribute("width", innerW);
      band.setAttribute("height", Math.max(0, y(opts.comfortBand[0]) - y(opts.comfortBand[1])));
      svg.appendChild(band);
    }

    var yTicks = niceTicks(yMin, yMax, 5);
    yTicks.forEach(function (t) {
      var ly = y(t);
      var line = document.createElementNS(svgNS, "line");
      line.setAttribute("class", "grid-line");
      line.setAttribute("x1", MARGIN.left); line.setAttribute("x2", width - MARGIN.right);
      line.setAttribute("y1", ly); line.setAttribute("y2", ly);
      svg.appendChild(line);
      var label = document.createElementNS(svgNS, "text");
      label.setAttribute("class", "axis-text");
      label.setAttribute("x", MARGIN.left - 6);
      label.setAttribute("y", ly + 3);
      label.setAttribute("text-anchor", "end");
      label.textContent = t;
      svg.appendChild(label);
    });

    var dayBoundaries = [];
    var lastDay = null;
    rows.forEach(function (r, i) {
      var d = new Date(r.timestamp);
      var dayKey = d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate();
      if (dayKey !== lastDay && d.getHours() === 0) {
        lastDay = dayKey;
        dayBoundaries.push({ i: i, d: d });
      } else if (dayKey !== lastDay) {
        lastDay = dayKey;
      }
    });
    var minLabelSpacing = 56;
    var maxLabels = Math.max(1, Math.floor(innerW / minLabelSpacing));
    var labelStride = Math.max(1, Math.ceil(dayBoundaries.length / maxLabels));
    dayBoundaries.forEach(function (b, bi) {
      var lx = x(b.i);
      var vline = document.createElementNS(svgNS, "line");
      vline.setAttribute("x1", lx); vline.setAttribute("x2", lx);
      vline.setAttribute("y1", MARGIN.top); vline.setAttribute("y2", MARGIN.top + innerH);
      vline.setAttribute("stroke", cssVar("--grid"));
      vline.setAttribute("stroke-width", "1");
      svg.appendChild(vline);
      if (bi % labelStride === 0) {
        var tick = document.createElementNS(svgNS, "text");
        tick.setAttribute("class", "axis-text");
        tick.setAttribute("x", lx);
        tick.setAttribute("y", height - 6);
        tick.setAttribute("text-anchor", "start");
        tick.textContent = b.d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
        svg.appendChild(tick);
      }
    });

    opts.series.forEach(function (s) {
      var d = "";
      rows.forEach(function (r, i) {
        var cmd = i === 0 ? "M" : "L";
        d += cmd + x(i).toFixed(2) + "," + y(r[s.key]).toFixed(2) + " ";
      });
      var path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", d.trim());
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", cssVar(s.color));
      path.setAttribute("stroke-width", "2");
      if (s.dashed) path.setAttribute("stroke-dasharray", "4 3");
      path.setAttribute("stroke-linejoin", "round");
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("opacity", s.dashed ? "0.8" : "1");
      svg.appendChild(path);
    });

    if (opts.violationKey && opts.comfortBand) {
      rows.forEach(function (r, i) {
        if (!r.occupied) return;
        var v = r[opts.violationKey];
        if (v < opts.comfortBand[0] || v > opts.comfortBand[1]) {
          var dot = document.createElementNS(svgNS, "circle");
          dot.setAttribute("class", "violation-dot");
          dot.setAttribute("cx", x(i));
          dot.setAttribute("cy", y(v));
          dot.setAttribute("r", "2.5");
          dot.setAttribute("opacity", "0.6");
          svg.appendChild(dot);
        }
      });
    }

    var crosshair = document.createElementNS(svgNS, "line");
    crosshair.setAttribute("class", "crosshair");
    crosshair.setAttribute("y1", MARGIN.top);
    crosshair.setAttribute("y2", MARGIN.top + innerH);
    svg.appendChild(crosshair);

    var hoverDots = opts.series.map(function (s) {
      var g = document.createElementNS(svgNS, "g");
      g.setAttribute("class", "hover-dot");
      var c = document.createElementNS(svgNS, "circle");
      c.setAttribute("r", "4");
      c.setAttribute("fill", cssVar(s.color));
      g.appendChild(c);
      svg.appendChild(g);
      return g;
    });

    var hit = document.createElementNS(svgNS, "rect");
    hit.setAttribute("x", MARGIN.left); hit.setAttribute("y", MARGIN.top);
    hit.setAttribute("width", innerW); hit.setAttribute("height", innerH);
    hit.setAttribute("fill", "transparent");
    svg.appendChild(hit);

    wrap.appendChild(svg);

    var tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    wrap.style.position = "relative";
    wrap.appendChild(tooltip);

    function handleMove(evt) {
      var rect = svg.getBoundingClientRect();
      var px = (evt.clientX - rect.left) * (width / rect.width);
      var i = Math.round(((px - MARGIN.left) / innerW) * (n - 1));
      i = Math.max(0, Math.min(n - 1, i));
      var cx = x(i);
      crosshair.setAttribute("x1", cx); crosshair.setAttribute("x2", cx);
      crosshair.style.opacity = "1";

      var rowsHtml = '<div class="t-time">' + escapeHtml(fmtDateTime(rows[i].timestamp)) + '</div>';
      opts.series.forEach(function (s, si) {
        var val = rows[i][s.key];
        hoverDots[si].setAttribute("transform", "translate(" + cx + "," + y(val) + ")");
        hoverDots[si].style.opacity = "1";
        rowsHtml += '<div class="t-row"><span class="t-key' + (s.dashed ? ' dash' : '') + '"' +
          (s.dashed ? '' : ' style="background:' + cssVar(s.color) + '"') + '></span>' +
          '<span class="t-val">' + val.toFixed(1) + (opts.unit || '') + '</span> ' +
          '<span class="t-name">' + escapeHtml(s.label) + '</span></div>';
      });
      tooltip.innerHTML = rowsHtml;
      tooltip.style.opacity = "1";

      var tw = tooltip.offsetWidth;
      var leftPx = (cx / width) * rect.width;
      var placeLeft = leftPx + 14;
      if (leftPx + tw + 24 > rect.width) placeLeft = leftPx - tw - 14;
      tooltip.style.left = placeLeft + "px";
      tooltip.style.top = "8px";
    }
    function handleLeave() {
      crosshair.style.opacity = "0";
      hoverDots.forEach(function (g) { g.style.opacity = "0"; });
      tooltip.style.opacity = "0";
    }
    hit.addEventListener("pointermove", handleMove);
    hit.addEventListener("pointerleave", handleLeave);
  }

  function renderTempChart(rows) {
    // Convert to the selected display unit for this chart only.
    var dRows = rows.map(function (r) {
      return {
        timestamp: r.timestamp,
        occupied: r.occupied,
        outdoor_temp_c: toUnit(r.outdoor_temp_c),
        baseline_indoor_temp_c: toUnit(r.baseline_indoor_temp_c),
        optimized_indoor_temp_c: toUnit(r.optimized_indoor_temp_c)
      };
    });
    var band = [toUnit(DATA.meta.comfort_band_c[0]), toUnit(DATA.meta.comfort_band_c[1])];
    buildLineChart({
      wrapId: "tempChartWrap",
      rows: dRows,
      height: 240,
      unit: unitLabel(),
      occupancyBand: true,
      comfortBand: band,
      violationKey: "optimized_indoor_temp_c",
      series: [
        { key: "outdoor_temp_c", color: "--series-outdoor", dashed: true, label: "Outdoor" },
        { key: "baseline_indoor_temp_c", color: "--series-baseline", label: "Baseline indoor" },
        { key: "optimized_indoor_temp_c", color: "--series-optimized", label: "Optimized indoor" }
      ]
    });
  }

  function renderPowerChart(rows) {
    buildLineChart({
      wrapId: "powerChartWrap",
      rows: rows,
      height: 200,
      unit: " kW",
      occupancyBand: true,
      yMinFloor: 0,
      series: [
        { key: "baseline_heating_power_kw", color: "--series-baseline", label: "Baseline" },
        { key: "optimized_heating_power_kw", color: "--series-optimized", label: "Optimized" }
      ]
    });
  }

  function renderCumChart(rows) {
    var cumBase = 0, cumOpt = 0;
    var cumRows = rows.map(function (r) {
      cumBase += r.baseline_energy_kwh;
      cumOpt += r.optimized_energy_kwh;
      return {
        timestamp: r.timestamp,
        occupied: r.occupied,
        cum_baseline: Math.round(cumBase * 10) / 10,
        cum_optimized: Math.round(cumOpt * 10) / 10
      };
    });
    buildLineChart({
      wrapId: "cumChartWrap",
      rows: cumRows,
      height: 200,
      unit: " kWh",
      occupancyBand: false,
      yMinFloor: 0,
      series: [
        { key: "cum_baseline", color: "--series-baseline", label: "Baseline cumulative" },
        { key: "cum_optimized", color: "--series-optimized", label: "Optimized cumulative" }
      ]
    });
  }

  // ---------------------------------------------------------------------
  // Table view
  // ---------------------------------------------------------------------
  function renderTable(rows) {
    var cols = [
      { key: "timestamp", label: "Time", fmt: fmtDateTime, align: "left" },
      { key: "occupied", label: "Occ.", fmt: function (v) { return v ? "●" : "—"; } },
      { key: "outdoor_temp_c", label: "Outdoor " + unitLabel(), fmt: function (v) { return toUnit(v).toFixed(1); } },
      { key: "baseline_indoor_temp_c", label: "Base indoor " + unitLabel(), fmt: function (v) { return toUnit(v).toFixed(1); } },
      { key: "optimized_indoor_temp_c", label: "Opt indoor " + unitLabel(), fmt: function (v) { return toUnit(v).toFixed(1); } },
      { key: "baseline_heating_power_kw", label: "Base kW" },
      { key: "optimized_heating_power_kw", label: "Opt kW" },
      { key: "baseline_energy_kwh", label: "Base kWh" },
      { key: "optimized_energy_kwh", label: "Opt kWh" }
    ];
    var table = document.getElementById("dataTable");
    var thead = table.querySelector("thead");
    var tbody = table.querySelector("tbody");
    thead.innerHTML = "<tr>" + cols.map(function (c) {
      return '<th style="' + (c.align === "left" ? "text-align:left" : "") + '">' + escapeHtml(c.label) + "</th>";
    }).join("") + "</tr>";

    var frag = document.createDocumentFragment();
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      cols.forEach(function (c) {
        var td = document.createElement("td");
        if (c.align === "left") td.style.textAlign = "left";
        var val = r[c.key];
        td.textContent = c.fmt ? c.fmt(val) : (typeof val === "number" ? val.toFixed(1) : val);
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    });
    tbody.innerHTML = "";
    tbody.appendChild(frag);
    document.getElementById("tableSub").textContent = rows.length + " rows";
  }

  // ---------------------------------------------------------------------
  // Control panel — building list
  // ---------------------------------------------------------------------
  var overrides = {}; // per-building user overrides this session: { [id]: { mode, heater_on } }
  try { overrides = JSON.parse(localStorage.getItem("hd-overrides") || "{}"); } catch (e) { overrides = {}; }
  function saveOverrides() {
    try { localStorage.setItem("hd-overrides", JSON.stringify(overrides)); } catch (e) {}
  }

  function buildingState(b) {
    var o = overrides[b.id];
    var mode = o && o.mode ? o.mode : b.mode;
    var heaterOn = o && typeof o.heater_on === "boolean" ? o.heater_on : b.heater_on;
    var status = mode === "manual" ? (heaterOn ? "heating" : "idle") : b.status;
    return { mode: mode, heaterOn: heaterOn, status: status, attention: effective(b).attention };
  }

  var WARN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 16.5h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>';

  function flaggedRooms(b) {
    return (effective(b).rooms || []).filter(function (r) { return r.status !== "normal"; });
  }

  // ---------------------------------------------------------------------
  // Live room/indoor-temperature simulation — when a building's heater is
  // actually running (auto already heating, or a manual override turned on),
  // its rooms warm toward the target over time instead of staying frozen at
  // the data file's snapshot. Once a room is back within tolerance, its
  // "needs attention" flag clears on its own, same as a real BMS would.
  // Persisted so progress survives a reload.
  // ---------------------------------------------------------------------
  var roomSim = {}; // { [buildingId]: { indoor_c, rooms: [{name,temp_c,occupied,status}] } }
  try { roomSim = JSON.parse(localStorage.getItem("hd-roomsim") || "{}"); } catch (e) { roomSim = {}; }
  function saveRoomSim() {
    try { localStorage.setItem("hd-roomsim", JSON.stringify(roomSim)); } catch (e) {}
  }

  function roomStatus(tempC, targetC) {
    var tolerance = 1.8;
    var delta = tempC - targetC;
    if (delta > tolerance) return "high";
    if (delta < -tolerance) return "low";
    return "normal";
  }

  function getSim(b) {
    if (!roomSim[b.id]) {
      roomSim[b.id] = {
        indoor_c: b.indoor_c,
        rooms: (b.rooms || []).map(function (r) {
          return { name: r.name, temp_c: r.temp_c, occupied: r.occupied, status: r.status };
        })
      };
    }
    return roomSim[b.id];
  }

  // The "live" view of a building: static data overlaid with simulated
  // progress, so every place that reads indoor_c/rooms/attention sees the
  // same up-to-date picture.
  function effective(b) {
    var sim = getSim(b);
    var rooms = sim.rooms;
    var attention = rooms.some(function (r) { return r.status !== "normal"; });
    return { indoor_c: sim.indoor_c, rooms: rooms, attention: attention };
  }

  function moveToward(value, target, step) {
    if (Math.abs(target - value) <= step) return target;
    return value + (target > value ? step : -step);
  }

  var ROOM_WARM_STEP_C = 0.3; // per tick

  function roomSimTick() {
    if (!DATA || !DATA.buildings) return;
    var anyChange = false;
    DATA.buildings.forEach(function (b) {
      var st = buildingState(b);
      if (!st.heaterOn) return; // frozen until the heater is actually running
      var sim = getSim(b);
      var before = JSON.stringify(sim);
      sim.indoor_c = Math.round(moveToward(sim.indoor_c, b.target_c, ROOM_WARM_STEP_C) * 10) / 10;
      sim.rooms.forEach(function (r) {
        r.temp_c = Math.round(moveToward(r.temp_c, b.target_c, ROOM_WARM_STEP_C) * 10) / 10;
        r.status = roomStatus(r.temp_c, b.target_c);
      });
      if (JSON.stringify(sim) !== before) anyChange = true;
    });
    if (anyChange) {
      saveRoomSim();
      renderBuildings();
      if (activeBuildingId) renderDetail();
    }
  }

  // ---------------------------------------------------------------------
  // Control panel — summary grid ("glance" tiles above the building list)
  // and the building-type filter. Summary counts always reflect ALL
  // buildings regardless of the active type filter, since the point is a
  // quick system-wide read before narrowing the list below.
  // ---------------------------------------------------------------------
  var typeFilter = "all";

  function buildingSummaryStats(list) {
    var groups = { heating: [], idle: [], manual: [], auto: [], attention: [] };
    list.forEach(function (b) {
      var st = buildingState(b);
      var entry = { id: b.id, name: b.name };
      if (st.status === "heating") groups.heating.push(entry);
      else groups.idle.push(entry);
      if (st.mode === "manual") groups.manual.push(entry);
      else groups.auto.push(entry);
      if (st.attention) groups.attention.push(entry);
    });
    return groups;
  }

  // One glyph per tile, echoing its meaning (flame = actively heating,
  // sliders = under manual override, refresh = following Auto, triangle =
  // the one that needs a human). Drawn at a consistent 24x24 viewBox so
  // they can share one CSS rule for size/position.
  var SUMMARY_ICONS = {
    heating: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5-2 1.6-3 3.5-3 5.5a7 7 0 0 0 7 7Z"/></svg>',
    idle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="10" y1="9" x2="10" y2="15"/><line x1="14" y1="9" x2="14" y2="15"/></svg>',
    manual: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><line x1="4" y1="7" x2="20" y2="7"/><circle cx="14" cy="7" r="2" fill="currentColor" stroke="none"/><line x1="4" y1="17" x2="20" y2="17"/><circle cx="9" cy="17" r="2" fill="currentColor" stroke="none"/></svg>',
    auto: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>',
    attention: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 16.5h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>'
  };

  var SUMMARY_TILES = [
    { key: "heating", label: "Heating" },
    { key: "idle", label: "Idle" },
    { key: "manual", label: "Manual" },
    { key: "auto", label: "Auto" },
    { key: "attention", label: "Needs attention" }
  ];

  function renderSummary() {
    if (!DATA || !DATA.buildings) return;
    var groups = buildingSummaryStats(DATA.buildings);
    var grid = document.getElementById("summaryGrid");
    if (!grid) return;
    grid.innerHTML = SUMMARY_TILES.map(function (t) {
      var names = groups[t.key] || [];
      var urgent = t.key === "attention" && names.length > 0;
      return '<button type="button" class="summary-tile ' + t.key + (urgent ? ' urgent' : '') + '" data-category="' + t.key + '">' +
        '<span class="st-icon">' + SUMMARY_ICONS[t.key] + '</span>' +
        '<span class="st-label"><span class="dot"></span>' + escapeHtml(t.label) + '</span>' +
        '<span class="st-value">' + names.length + '</span>' +
        '</button>';
    }).join("");
    grid.querySelectorAll(".summary-tile").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var cat = btn.getAttribute("data-category");
        var tileDef = SUMMARY_TILES.filter(function (t) { return t.key === cat; })[0];
        showSummaryPopover(tileDef ? tileDef.label : cat, groups[cat] || [], btn);
      });
    });
  }

  var summaryPopover = document.getElementById("summaryPopover");
  var summaryPopoverTitle = document.getElementById("summaryPopoverTitle");
  var summaryPopoverList = document.getElementById("summaryPopoverList");
  var summaryPopoverClose = document.getElementById("summaryPopoverClose");

  function showSummaryPopover(title, entries, anchorEl) {
    if (!summaryPopover) return;
    summaryPopoverTitle.textContent = title + " (" + entries.length + ")";
    summaryPopoverList.innerHTML = entries.length
      ? entries.map(function (e) { return '<li data-id="' + escapeHtml(e.id) + '">' + escapeHtml(e.name) + '</li>'; }).join("")
      : '<li class="empty">No buildings</li>';
    // Clicking a name jumps straight to that building's detail drawer
    // (rooms, HVAC, alarms, etc.) instead of leaving the person to scroll
    // the full list to find it.
    summaryPopoverList.querySelectorAll("li[data-id]").forEach(function (li) {
      li.addEventListener("click", function () {
        closeSummaryPopover();
        openDetail(li.getAttribute("data-id"));
      });
    });
    summaryPopover.hidden = false;

    // Position just below the clicked tile, nudged left if it would overflow
    // the viewport's right edge.
    var rect = anchorEl.getBoundingClientRect();
    var top = rect.bottom + 8;
    var left = rect.left;
    var popW = summaryPopover.offsetWidth || 240;
    if (left + popW > window.innerWidth - 12) left = window.innerWidth - popW - 12;
    if (left < 12) left = 12;
    summaryPopover.style.top = top + "px";
    summaryPopover.style.left = left + "px";
  }
  function closeSummaryPopover() {
    if (summaryPopover) summaryPopover.hidden = true;
  }
  if (summaryPopoverClose) summaryPopoverClose.addEventListener("click", closeSummaryPopover);
  document.addEventListener("click", function (e) {
    if (!summaryPopover || summaryPopover.hidden) return;
    if (summaryPopover.contains(e.target)) return;
    if (e.target.closest(".summary-tile")) return;
    closeSummaryPopover();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSummaryPopover();
  });

  var typeSelectWired = false;
  function renderTypeFilter() {
    if (!DATA || !DATA.buildings) return;
    var sel = document.getElementById("typeSelect");
    if (!sel) return;
    var types = [];
    DATA.buildings.forEach(function (b) {
      if (types.indexOf(b.type) === -1) types.push(b.type);
    });
    var options = [{ value: "all", label: "All buildings" }].concat(types.map(function (t) {
      return { value: t, label: t };
    }));
    // Rebuild options only when the set actually changed, so an open
    // dropdown or mid-interaction selection isn't disturbed by re-renders
    // triggered elsewhere (mode toggles, the room-sim tick, etc).
    var wanted = options.map(function (o) { return o.value; }).join("|");
    var have = Array.prototype.map.call(sel.options, function (o) { return o.value; }).join("|");
    if (wanted !== have) {
      sel.innerHTML = options.map(function (o) {
        return '<option value="' + escapeHtml(o.value) + '">' + escapeHtml(o.label) + '</option>';
      }).join("");
    }
    sel.value = typeFilter;
    if (!typeSelectWired) {
      typeSelectWired = true;
      sel.addEventListener("change", function () {
        typeFilter = sel.value;
        renderBuildings();
      });
    }
  }

  function renderBuildings() {
    if (!DATA || !DATA.buildings) return;
    renderSummary();
    renderTypeFilter();
    var list = typeFilter === "all"
      ? DATA.buildings
      : DATA.buildings.filter(function (b) { return b.type === typeFilter; });

    var container = document.getElementById("buildingList");
    // remove previously rendered rows (keep the header row)
    Array.prototype.slice.call(container.querySelectorAll(".b-row:not(.b-head)")).forEach(function (el) { el.remove(); });

    list.forEach(function (b) {
      var st = buildingState(b);
      var flagged = flaggedRooms(b);
      var row = document.createElement("div");
      row.className = "b-row" + (st.attention ? " attention" : "");
      row.setAttribute("data-id", b.id);
      row.setAttribute("tabindex", "0");
      row.setAttribute("role", "button");
      row.setAttribute("aria-label", "Open details for " + b.name);

      var pillClass = st.attention ? "attention" : st.status;
      var pillLabel = st.attention ? "Needs attention" : (st.status === "heating" ? "Heating" : "Idle");

      row.innerHTML =
        '<div class="b-id"><span class="b-name"></span><span class="b-code"></span></div>' +
        '<div class="b-type"><span class="b-type-tag"></span></div>' +
        '<div class="b-temp"></div>' +
        '<div class="b-status"><span class="status-pill ' + pillClass + '"></span></div>' +
        '<div class="b-mode">' +
          '<div class="seg mode-seg" role="group" aria-label="Mode for ' + escapeHtml(b.name) + '">' +
            '<button type="button" data-mode="auto">Auto</button>' +
            '<button type="button" data-mode="manual">Manual</button>' +
          '</div>' +
        '</div>' +
        '<div class="b-power"><button type="button" class="power-toggle" role="switch"></button></div>';

      row.querySelector(".b-name").textContent = b.name;
      row.querySelector(".b-code").textContent = b.code;
      row.querySelector(".b-type-tag").textContent = b.type;
      row.querySelector(".status-pill").textContent = pillLabel;

      if (flagged.length) {
        var alertLine = document.createElement("div");
        alertLine.className = "b-alert-line";
        var label = flagged.length === 1
          ? flagged[0].name + " needs attention"
          : flagged.length + " rooms need attention";
        alertLine.innerHTML = WARN_ICON + "<span></span>";
        alertLine.querySelector("span").textContent = label;
        row.querySelector(".b-id").appendChild(alertLine);
      }

      var tempEl = row.querySelector(".b-temp");
      tempEl.textContent = fmtTemp(effective(b).indoor_c);
      var targetSpan = document.createElement("span");
      targetSpan.className = "b-target";
      targetSpan.textContent = "target " + fmtTemp(b.target_c);
      tempEl.appendChild(targetSpan);

      var modeSeg = row.querySelector(".mode-seg");
      modeSeg.querySelectorAll("button").forEach(function (btn) {
        btn.setAttribute("aria-pressed", btn.getAttribute("data-mode") === st.mode ? "true" : "false");
      });
      modeSeg.addEventListener("click", function (e) {
        e.stopPropagation();
        var btn = e.target.closest("button");
        if (!btn) return;
        var mode = btn.getAttribute("data-mode");
        overrides[b.id] = overrides[b.id] || {};
        overrides[b.id].mode = mode;
        if (mode === "manual" && typeof overrides[b.id].heater_on !== "boolean") {
          overrides[b.id].heater_on = b.heater_on;
        }
        saveOverrides();
        renderBuildings();
      });

      var powerBtn = row.querySelector(".power-toggle");
      powerBtn.setAttribute("aria-checked", st.heaterOn ? "true" : "false");
      powerBtn.disabled = st.mode !== "manual";
      powerBtn.title = st.mode === "manual" ? "Turn heater " + (st.heaterOn ? "off" : "on") : "Switch to Manual to control directly";
      powerBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        if (st.mode !== "manual") return;
        overrides[b.id] = overrides[b.id] || {};
        overrides[b.id].heater_on = !st.heaterOn;
        saveOverrides();
        renderBuildings();
      });

      row.addEventListener("click", function () { openDetail(b.id); });
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(b.id); }
      });

      container.appendChild(row);
    });
  }

  // ---------------------------------------------------------------------
  // Building detail drawer
  // ---------------------------------------------------------------------
  var detailDrawer = document.getElementById("detailDrawer");
  var detailBackdrop = document.getElementById("detailBackdrop");
  var activeBuildingId = null;
  var activeTab = "hvac";

  var OK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  var ALARM_WARN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 16.5h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>';

  function openDetail(id) {
    activeBuildingId = id;
    activeTab = "hvac";
    document.querySelectorAll("#detailTabs button").forEach(function (b) {
      b.setAttribute("aria-selected", b.getAttribute("data-tab") === "hvac" ? "true" : "false");
    });
    renderDetail();
    detailDrawer.classList.add("open");
    detailBackdrop.classList.add("open");
    detailDrawer.setAttribute("aria-hidden", "false");
  }
  function closeDetail() {
    detailDrawer.classList.remove("open");
    detailBackdrop.classList.remove("open");
    detailDrawer.setAttribute("aria-hidden", "true");
    activeBuildingId = null;
  }
  document.getElementById("detailClose").addEventListener("click", closeDetail);
  detailBackdrop.addEventListener("click", closeDetail);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && activeBuildingId) closeDetail();
  });
  document.getElementById("detailTabs").addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    if (!btn) return;
    activeTab = btn.getAttribute("data-tab");
    document.querySelectorAll("#detailTabs button").forEach(function (b) {
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    });
    renderDetailTab();
  });

  function findBuilding(id) {
    return (DATA.buildings || []).filter(function (b) { return b.id === id; })[0];
  }

  function buildingAlarms(b, st) {
    var alarms = [];
    var flagged = flaggedRooms(b);
    var anyAhuRunning = st.heaterOn;
    flagged.forEach(function (r) {
      alarms.push({ level: "warn", text: r.name + " temperature " + r.status.toUpperCase() + " — " + fmtTemp(r.temp_c) });
    });
    var ahuLabel = b.ahus && b.ahus.length > 1 ? b.ahus.length + " AHUs" : "AHU";
    if (flagged.length && !anyAhuRunning) {
      alarms.push({ level: "warn", text: ahuLabel + " not responding to demand — check unit before relying on Auto" });
    } else if (anyAhuRunning) {
      alarms.push({ level: "ok", text: ahuLabel + " running, " + (flagged.length ? "space hasn't caught up yet" : "operating normally") });
    } else {
      alarms.push({ level: "ok", text: ahuLabel + " idle, no heating demand" });
    }
    if (b.co2_ppm > 800) {
      alarms.push({ level: "warn", text: "CO₂ levels elevated — " + b.co2_ppm + " ppm" });
    } else {
      alarms.push({ level: "ok", text: "CO₂ levels normal" });
    }
    return alarms;
  }

  function renderDetail() {
    var b = findBuilding(activeBuildingId);
    if (!b) return;
    var st = buildingState(b);
    var attention = st.attention;

    document.getElementById("detailName").textContent = b.name;
    document.getElementById("detailCode").textContent = b.code + " · " + b.type;
    var statusEl = document.getElementById("detailStatus");
    statusEl.className = "detail-status " + (attention ? "attention" : "normal");
    statusEl.textContent = attention ? "NEEDS ATTENTION" : "NORMAL";

    renderDetailControlStrip(b, st);

    var metrics = [
      { label: "TEMPERATURE", value: fmtTemp(effective(b).indoor_c), warn: st.status === "heating" },
      { label: "ENERGY", value: b.energy_kw + " kW", warn: false },
      { label: "CO₂", value: b.co2_ppm + " ppm", warn: b.co2_ppm > 800 }
    ];
    document.getElementById("detailMetrics").innerHTML = metrics.map(function (m) {
      return '<div class="detail-metric' + (m.warn ? ' warn' : '') + '">' +
        '<div class="dm-label">' + m.label + '</div>' +
        '<div class="dm-value">' + escapeHtml(m.value) + '</div></div>';
    }).join("");

    renderDetailTab();
  }

  function renderDetailControlStrip(b, st) {
    var strip = document.getElementById("detailControlStrip");
    // The heater control is a labeled button with its state spelled out in
    // text ("HEATER ON" / "HEATER OFF"), not just a color/position cue —
    // that way the state is never ambiguous even on a small screen or a
    // partially-loaded stylesheet.
    strip.innerHTML =
      '<div>' +
        '<div class="detail-control-label">MODE</div>' +
        '<div class="seg" id="detailModeSeg" role="group" aria-label="Mode">' +
          '<button type="button" data-mode="auto">Auto</button>' +
          '<button type="button" data-mode="manual">Manual</button>' +
        '</div>' +
      '</div>' +
      '<div class="detail-control-right">' +
        '<button type="button" class="power-toggle-btn" id="detailPowerToggle" role="switch">' +
          '<span class="pt-dot"></span><span class="pt-label"></span>' +
        '</button>' +
      '</div>';

    var modeSeg = strip.querySelector("#detailModeSeg");
    modeSeg.querySelectorAll("button").forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.getAttribute("data-mode") === st.mode ? "true" : "false");
    });
    modeSeg.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      var mode = btn.getAttribute("data-mode");
      overrides[b.id] = overrides[b.id] || {};
      overrides[b.id].mode = mode;
      if (mode === "manual" && typeof overrides[b.id].heater_on !== "boolean") {
        overrides[b.id].heater_on = b.heater_on;
      }
      saveOverrides();
      renderDetail();
      renderBuildings();
    });

    var powerBtn = strip.querySelector("#detailPowerToggle");
    var isManual = st.mode === "manual";
    powerBtn.setAttribute("aria-checked", st.heaterOn ? "true" : "false");
    powerBtn.classList.toggle("on", st.heaterOn);
    powerBtn.classList.toggle("locked", !isManual);
    powerBtn.querySelector(".pt-label").textContent = isManual
      ? "HEATER " + (st.heaterOn ? "ON — tap to turn off" : "OFF — tap to turn on")
      : "HEATER " + (st.heaterOn ? "ON" : "OFF") + " (Auto — switch to Manual to control)";
    powerBtn.title = isManual ? "Turn heater " + (st.heaterOn ? "off" : "on") : "Switch to Manual to control directly";
    powerBtn.addEventListener("click", function () {
      if (st.mode !== "manual") return;
      overrides[b.id] = overrides[b.id] || {};
      overrides[b.id].heater_on = !st.heaterOn;
      saveOverrides();
      renderDetail();
      renderBuildings();
    });

    var hintText = st.mode === "auto"
      ? "Auto follows today's outdoor reading. Switch to Manual to force this building's heaters on or off directly."
      : "Manual override active — this building will ignore the outdoor-temperature schedule until switched back to Auto.";
    document.getElementById("detailHint").textContent = hintText;

    // Always open scrolled to the top so the mode/heater controls and the
    // metric tiles are visible immediately, rather than wherever a
    // previous building's panel happened to be scrolled to.
    var bodyEl = document.querySelector(".detail-body");
    if (bodyEl) bodyEl.scrollTop = 0;
  }

  // The HVAC tab reflects the live Auto/Manual + heater state, not just the
  // static snapshot in the data file — so flipping the heater toggle actually
  // shows the AHUs responding, instead of a toggle that looks disconnected
  // from the equipment underneath it.
  function liveAhus(b, st) {
    var running = st.heaterOn;
    var indoorC = effective(b).indoor_c;
    var fanPct = running ? 78 : 12;
    var supplyC = running ? Math.round((indoorC + 5.0) * 10) / 10 : Math.round((indoorC - 0.3) * 10) / 10;
    var returnC = running ? Math.round((indoorC + 0.3) * 10) / 10 : Math.round((indoorC - 0.1) * 10) / 10;
    return (b.ahus || []).map(function (a) {
      return { id: a.id, running: running, fan_pct: fanPct, supply_c: supplyC, return_c: returnC };
    });
  }

  function renderDetailTab() {
    var b = findBuilding(activeBuildingId);
    if (!b) return;
    var st = buildingState(b);
    var el = document.getElementById("detailTabContent");

    if (activeTab === "hvac") {
      var ahuHtml = liveAhus(b, st).map(function (a) {
        return '<div class="ahu-row">' +
          '<div class="ahu-line1"><span class="ahu-id">' + escapeHtml(a.id) + '</span>' +
          '<span class="' + (a.running ? 'ahu-run' : 'ahu-idle-label') + '">' + (a.running ? "RUNNING" : "IDLE") + '</span></div>' +
          '<div class="fan-bar"><div class="fan-bar-fill" style="width:' + a.fan_pct + '%"></div></div>' +
          '<div class="ahu-temps"><span>Supply ' + fmtTemp(a.supply_c) + '</span><span>Return ' + fmtTemp(a.return_c) + '</span></div>' +
          '</div>';
      }).join("");
      var roomHtml = (effective(b).rooms || []).map(function (r) {
        var flag = r.status !== "normal"
          ? '<span class="room-flag">' + WARN_ICON + (r.status === "low" ? "LOW" : "HIGH") + '</span>' : "";
        return '<div class="room-row">' +
          '<span class="room-name">' + escapeHtml(r.name) + '</span>' +
          '<span class="room-right"><span class="room-temp">' + fmtTemp(r.temp_c) + '</span>' +
          '<span class="room-occ">' + (r.occupied ? "Occupied" : "Empty") + '</span>' + flag + '</span>' +
          '</div>';
      }).join("");
      el.innerHTML =
        '<div class="detail-section"><div class="detail-section-title">HVAC</div>' + ahuHtml + '</div>' +
        '<div class="detail-section"><div class="detail-section-title">ROOMS</div>' + roomHtml + '</div>';
    } else if (activeTab === "lighting") {
      el.innerHTML = '<div class="detail-section"><div class="detail-section-title">LIGHTING</div>' +
        '<p class="lighting-stub">Lighting control isn\'t wired into this prototype yet — this tab is a placeholder for where occupancy-based lighting schedules would live alongside heating.</p></div>';
    } else if (activeTab === "energy") {
      el.innerHTML = '<div class="detail-section"><div class="detail-section-title">ENERGY CONSUMPTION — TODAY</div>' +
        '<div class="energy-graph" id="energyGraphWrap"></div></div>';
      renderEnergySpark(b);
    } else if (activeTab === "alarms") {
      var alarms = buildingAlarms(b, st);
      el.innerHTML = '<div class="detail-section"><div class="detail-section-title">ALARMS</div>' +
        alarms.map(function (a) {
          return '<div class="alarm-row ' + a.level + '">' + (a.level === "warn" ? ALARM_WARN_ICON : OK_ICON) +
            '<span>' + escapeHtml(a.text) + '</span></div>';
        }).join("") + '</div>';
    }
  }

  // Deterministic pseudo-random 24h energy curve, seeded from the building id
  // so it's stable across renders without needing per-building time series data.
  function seededSeries(seedStr, n, base, spread) {
    var seed = 0;
    for (var i = 0; i < seedStr.length; i++) seed = (seed * 31 + seedStr.charCodeAt(i)) >>> 0;
    function rand() {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    }
    var out = [];
    var v = base;
    for (var h = 0; h < n; h++) {
      v += (rand() - 0.5) * spread;
      v = Math.max(base * 0.4, Math.min(base * 1.6, v));
      out.push(Math.round(v * 10) / 10);
    }
    return out;
  }

  function renderEnergySpark(b) {
    var wrap = document.getElementById("energyGraphWrap");
    if (!wrap) return;
    var series = seededSeries(b.id, 24, b.energy_kw, b.energy_kw * 0.18);
    var width = wrap.clientWidth || 420;
    var height = 90;
    var pad = 6;
    var min = Math.min.apply(null, series), max = Math.max.apply(null, series);
    var range = (max - min) || 1;
    function x(i) { return pad + ((width - pad * 2) * i) / (series.length - 1); }
    function y(v) { return height - pad - ((v - min) / range) * (height - pad * 2); }
    var d = series.map(function (v, i) { return (i === 0 ? "M" : "L") + x(i).toFixed(1) + "," + y(v).toFixed(1); }).join(" ");
    var areaD = d + " L" + x(series.length - 1).toFixed(1) + "," + (height - pad) + " L" + x(0).toFixed(1) + "," + (height - pad) + " Z";
    var svgNS = "http://www.w3.org/2000/svg";
    wrap.innerHTML =
      '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none">' +
      '<path d="' + areaD + '" fill="#2ea8e0" opacity="0.12" stroke="none"></path>' +
      '<path d="' + d + '" fill="none" stroke="#2ea8e0" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>' +
      '</svg>';
  }

  window.addEventListener("resize", function () {
    if (!document.getElementById("view-weekly").hidden) renderWeekly();
    if (activeBuildingId && activeTab === "energy") renderDetailTab();
  });

  setInterval(roomSimTick, 2500);
})();
