/* ================= NAGAR AI · Ward Control Room =================
   Redesigned client. Talks to the same-origin /api (FastAPI) when the
   server is reachable; falls back to a bundled demo dataset + local
   pipeline (clearly marked) so every module still works offline. */
(function () {
  "use strict";

  /* ---------- constants ---------- */
  var API = "/api";
  var DEMO_STORE_KEY = "nagarai_demo_store_v1";
  var VIEW_KEY = "nagarai_view_v1";

  var DEPARTMENTS = {
    pothole: "Roads & Pavements Dept",
    garbage: "Solid Waste Management Dept",
    broken_streetlight: "Electrical / Street Lighting Dept",
    streetlight: "Electrical / Street Lighting Dept",
    waterlogging: "Storm Water Drain Dept",
    other: "General Administration"
  };
  var SLA_HOURS = { pothole: 72, garbage: 48, broken_streetlight: 96, streetlight: 96, waterlogging: 48, other: 168 };
  var CAT_LABEL = { pothole: "Pothole", garbage: "Garbage", broken_streetlight: "Streetlight", streetlight: "Streetlight", waterlogging: "Waterlogging", other: "Other" };
  var AREA_GEOCODE = {
    "t nagar": [13.0418, 80.2341], "panagal park": [13.0418, 80.2341],
    "adyar": [13.0067, 80.2570], "velachery": [12.9756, 80.2207], "anna nagar": [13.0850, 80.2101],
    "tambaram": [12.9249, 80.1000], "mylapore": [13.0339, 80.2619], "pallikaranai": [12.9345, 80.2129],
    "guindy": [13.0067, 80.2206], "perambur": [13.1179, 80.2453], "nungambakkam": [13.0603, 80.2417],
    "kodambakkam": [13.0510, 80.2277], "vadapalani": [13.0503, 80.2121], "porur": [13.0381, 80.1564],
    "ambattur": [13.1143, 80.1548], "chromepet": [12.9516, 80.1462], "koyambedu": [13.0718, 80.2123],
    "mount road": [13.061, 80.246], "usman road": [13.041, 80.234]
  };
  var CAT_COLOR = { pothole: "#E8503A", garbage: "#2FA84F", broken_streetlight: "#F2B705", streetlight: "#F2B705", waterlogging: "#2B7FF5", other: "#5A6472" };
  var CAT_CSS = { pothole: "pothole", garbage: "garbage", broken_streetlight: "streetlight", streetlight: "streetlight", waterlogging: "waterlogging", other: "other" };
  /* dynamic categories: prefer AI-picked label/color from the server, fall back to the static map */
  function catLabel(issue) { return (issue && issue.category_label) || CAT_LABEL[issue && issue.category] || (issue ? String(issue.category).replace(/_/g, " ") : "Other"); }
  function catColor(issue) { return (issue && issue.category_color) || CAT_COLOR[issue && issue.category] || "#7A877A"; }
  function catCss(issue) { return CAT_CSS[issue && issue.category] || "other"; }
  var TRACK_STEPS = ["open", "assigned", "in_progress", "resolved"];

  /* ---------- state ---------- */
  var DEMO = false;
  var issues = [];
  var catF = "", statF = "", sortF = "priority", areaF = "";
  var captchaEnabled = false;
  var captchaWidgetId = null;
  var map = null, markerLayer = null, activeHighlight = null, mapInited = false, mapSizedOnce = false;
  var adminAuthed = false;
  var currentTab = "text";
  var uploadedPhoto = null, voiceTranscript = "";
  var trackedIssueId = null;
  var judgingRunning = false;

  /* ---------- helpers ---------- */
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]); }); }

  function $(id) { return document.getElementById(id); }

  function toast(msg, isErr) {
    var wrap = $("toastWrap");
    var el = document.createElement("div");
    el.className = "toast" + (isErr ? " toast--err" : "");
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 4600);
  }

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  function guessLocation(text) {
    var low = (text || "").toLowerCase();
    var keys = Object.keys(AREA_GEOCODE);
    for (var i = 0; i < keys.length; i++) {
      if (low.indexOf(keys[i]) !== -1) return { name: keys[i], coords: AREA_GEOCODE[keys[i]] };
    }
    return null;
  }

  /* ---------- HTTP with demo fallback ---------- */
  function j(method, path, body) {
    var opts = { method: method, headers: {} };
    if (body instanceof FormData) opts.body = body;
    else if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    var ctrl = new AbortController();
    opts.signal = ctrl.signal;
    var t = setTimeout(function () { ctrl.abort(); }, 60000);
    return fetch(API + path, opts).then(function (r) {
      clearTimeout(t);
      if (!r.ok) throw new Error(r.status + " " + r.statusText);
      return r.json();
    });
  }

  function setDemo(on, msg) {
    DEMO = on;
    var banner = $("demoBanner");
    if (on) {
      banner.hidden = false;
      $("demoBannerTxt").textContent = msg || "OFFLINE DEMO — live server unreachable. Showing simulated ward data; every module still works.";
      $("liveChipTxt").textContent = "DEMO";
      $("liveChip").classList.add("chip--demo");
      $("liveChip").classList.remove("chip--live");
    } else {
      banner.hidden = true;
      $("liveChipTxt").textContent = "LIVE";
      $("liveChip").classList.remove("chip--demo");
      $("liveChip").classList.add("chip--live");
    }
  }

  /* ================= DEMO DATASET + LOCAL PIPELINE ================= */
  function demoSeed() {
    function d(id, category, summary, severity, status, affected, days, lat, lng, members, prox) {
      var proxM = prox ? 1.5 : 1.0;
      var raw = severity * Math.sqrt(affected) * Math.min(days, 30) * proxM;
      var priority = Math.max(1, Math.min(100, Math.round(raw * 0.9)));
      var created = new Date(Date.now() - days * 86400000).toISOString();
      var r = { P: Number((Math.sqrt(affected)).toFixed(2)), T: Number((Math.min(days, 30)).toFixed(2)), L: prox ? 1.5 : 1.0, band: Math.max(1, Math.min(5, Math.ceil(priority / 20))) };
      var mList = (members || []).map(function (m) {
        return { complaint_id: m.id, text_score: m.t, geo_score: m.g, vision_score: m.v, sim_total: m.s };
      });
      return {
        id: id, category: category, summary: summary, severity: severity, status: status,
        affected_count: affected, created_at: created, priority_score: priority,
        priority_reason: JSON.stringify(r), dept: DEPARTMENTS[category], centroid_lat: lat, centroid_lng: lng,
        members: mList, school_hospital_prox: prox ? JSON.stringify([{ name: prox }]) : "[]"
      };
    }
    return [
      d(41, "pothole", "Large pothole at Panagal Park bus stop; a two-wheeler has already fallen in.", 4, "open", 6, 6, 13.0418, 80.2341,
        [{ id: 41, t: 0.92, g: 0.9, v: 0.1, s: 0.84 }, { id: 42, t: 0.95, g: 0.88, v: 0.15, s: 0.86 }]),
      d(43, "garbage", "Garbage bin near Adyar signal not cleared for 10 days; strong smell daily.", 3, "open", 5, 10, 13.0067, 80.2570,
        [{ id: 43, t: 0.9, g: 0.85, v: 0.1, s: 0.8 }, { id: 44, t: 0.93, g: 0.82, v: 0.2, s: 0.83 }]),
      d(45, "streetlight", "Streetlight on Anna Nagar 2nd Avenue off for a week; unsafe for women walking at night.", 5, "in_progress", 9, 7, 13.0850, 80.2101,
        [{ id: 45, t: 0.96, g: 0.9, v: 0.12, s: 0.87 }, { id: 55, t: 0.88, g: 0.84, v: 0.1, s: 0.79 }]),
      d(46, "waterlogging", "Velachery main road waterlogged; water knee-deep and buses stuck.", 4, "open", 12, 2, 12.9756, 80.2207,
        [{ id: 46, t: 0.91, g: 0.86, v: 0.1, s: 0.82 }, { id: 47, t: 0.94, g: 0.83, v: 0.15, s: 0.84 }]),
      d(48, "pothole", "Large pothole outside Tambaram govt hospital gate; ambulance access is affected.", 5, "open", 3, 4, 12.9252, 80.1002, [], "Government Hospital"),
      d(49, "garbage", "Garbage dump growing near Perambur market; rats are increasing badly.", 3, "open", 4, 12, 13.1179, 80.2453, []),
      d(50, "streetlight", "Three streetlights down on Nungambakkam High Road; accident risk at night.", 4, "open", 7, 9, 13.0603, 80.2417, []),
      d(51, "pothole", "Pothole near Porur signal filled with water; depth is not visible.", 3, "open", 2, 14, 13.0381, 80.1564, []),
      d(52, "waterlogging", "Chromepet subway fully waterlogged; no vehicle can pass.", 5, "open", 15, 3, 12.9516, 80.1462, []),
      d(53, "garbage", "Garbage not collected near Velachery Corporation school for two weeks.", 3, "open", 6, 14, 12.9800, 80.2250, [], "Corporation School"),
      d(54, "pothole", "Deep pothole on Ambattur Estate road; two-wheelers falling daily near the junction.", 4, "open", 8, 8, 13.1143, 80.1548, [])
    ];
  }

  function demoLoadStore() {
    try {
      var raw = localStorage.getItem(DEMO_STORE_KEY);
      if (raw) {
        var arr = JSON.parse(raw);
        if (Array.isArray(arr) && arr.length) return arr;
      }
    } catch (e) { /* ignore */ }
    var seed = demoSeed();
    try { localStorage.setItem(DEMO_STORE_KEY, JSON.stringify(seed)); } catch (e) { /* ignore */ }
    return seed;
  }

  function demoSaveStore(store) {
    try { localStorage.setItem(DEMO_STORE_KEY, JSON.stringify(store)); } catch (e) { /* ignore */ }
  }

  function demoNextId(store) {
    var max = 41;
    for (var i = 0; i < store.length; i++) max = Math.max(max, store[i].id);
    return max + 1;
  }

  var CAT_HINTS = [
    { cat: "pothole", re: /pothole|road|kulunthu|ambattur|vizhuntha|broken road/i },
    { cat: "garbage", re: /garbage|trash|smell|kuppai|bin|dump|rats|waste/i },
    { cat: "streetlight", re: /streetlight|street light|light|lamp|dark|vela seyala|not working|pole/i },
    { cat: "waterlogging", re: /water|waterlog|thanni|logging|flood|stuck|subway|rain/i }
  ];

  function demoExtract(text, lat, lng) {
    var cat = "other";
    for (var i = 0; i < CAT_HINTS.length; i++) {
      if (CAT_HINTS[i].re.test(text)) { cat = CAT_HINTS[i].cat; break; }
    }
    var sev = 3;
    if (/ambulance|accident|emergency|knee deep|dangerous/i.test(text)) sev = 5;
    else if (/romba|not working|since 1 week|week|two weeks|daily/i.test(text)) sev = 4;
    var area = guessLocation(text);
    var resolvedLat = lat, resolvedLng = lng;
    if (isNaN(resolvedLat) && area) {
      resolvedLat = area.coords[0] + (Math.random() - 0.5) * 0.002;
      resolvedLng = area.coords[1] + (Math.random() - 0.5) * 0.002;
    }
    var summary = String(text || "").trim().replace(/\s+/g, " ");
    return { category: cat, severity: sev, area: area, lat: resolvedLat, lng: resolvedLng, summary: summary };
  }

  function demoComputePriority(issue) {
    var sev = Math.max(1, Math.min(5, Math.round(issue.severity || 3)));
    var affected = Math.max(1, issue.affected_count || 1);
    var days = 0;
    if (issue.created_at) days = Math.max(0, (Date.now() - new Date(issue.created_at).getTime()) / 86400000);
    var prox = 1.0;
    try { if (JSON.parse(issue.school_hospital_prox || "[]").length) prox = 1.5; } catch (e) { /* ignore */ }
    var raw = sev * Math.sqrt(affected) * Math.min(days, 30) * prox;
    var priority = Math.max(1, Math.min(100, Math.round(raw * 0.9)));
    return { severity: sev, affected: affected, days: days, proximity: prox, priority: priority, band: Math.max(1, Math.min(5, Math.ceil(priority / 20))) };
  }

  function demoDedup(store, cat, text, lat, lng) {
    var low = (text || "").toLowerCase();
    for (var i = 0; i < store.length; i++) {
      var it = store[i];
      if (it.status === "resolved" || it.category !== cat) continue;
      var dLat = Math.abs((it.centroid_lat || 0) - (lat || 0));
      var dLng = Math.abs((it.centroid_lng || 0) - (lng || 0));
      var near = dLat < 0.02 && dLng < 0.02;
      var tokens = (it.summary || "").toLowerCase();
      var overlap = 0;
      var words = low.split(/\W+/);
      for (var w = 0; w < words.length; w++) {
        if (words[w].length > 3 && tokens.indexOf(words[w]) !== -1) overlap++;
      }
      if (near && overlap >= 1) {
        var sim = Math.min(0.97, 0.5 + overlap * 0.09);
        return { merged: true, issue_id: it.id, scores: { sim: sim } };
      }
    }
    return null;
  }

  function demoIntake(text, lat, lng, extra) {
    var store = demoLoadStore();
    var ex = demoExtract(text, lat, lng);
    var dedup = demoDedup(store, ex.category, text, ex.lat, ex.lng);
    var complaint;
    if (dedup) {
      complaint = {
        id: demoNextId(store), category: ex.category, severity: ex.severity, lat: ex.lat, lng: ex.lng,
        summary: ex.summary, location_text: ex.area ? ex.area.name : "", status: "open",
        affected_count: 1, created_at: new Date().toISOString(), dedup_merged: true
      };
    } else {
      var prox = null;
      if (/school|hospital/i.test(text)) prox = /school/i.test(text) ? "Corporation School" : "Government Hospital";
      var issue = {
        id: demoNextId(store), category: ex.category, summary: ex.summary, severity: ex.severity,
        status: "open", affected_count: 1, created_at: new Date().toISOString(),
        centroid_lat: ex.lat, centroid_lng: ex.lng, dept: DEPARTMENTS[ex.category],
        members: [], school_hospital_prox: prox ? JSON.stringify([{ name: prox }]) : "[]", priority_reason: "{}"
      };
      store.push(issue);
      demoSaveStore(store);
      complaint = { id: issue.id, category: ex.category, severity: ex.severity, lat: ex.lat, lng: ex.lng, summary: ex.summary, location_text: ex.area ? ex.area.name : "", photo_meta: {} };
    }
    return Promise.resolve({ complaint: complaint, dedup: dedup ? { merged: true, issue_id: dedup.issue_id, scores: dedup.scores } : { merged: false, issue_id: complaint.id } });
  }

  /* ================= ISSUES / RENDER ================= */
  function apiIssues() {
    var q = (typeof searchQ === "undefined" ? "" : searchQ).trim();
    if (q) {
      var qs = new URLSearchParams();
      qs.set("q", q);
      if (catF) { var c = catF === "streetlight" ? "broken_streetlight" : catF; qs.set("category", c); }
      if (areaF) qs.set("area", areaF);
      if (statF) qs.set("status", statF);
      if (sortF) qs.set("sort", sortF);
      return j("GET", "/search?" + qs);
    }
    var qs = new URLSearchParams();
    if (catF) {
      // UI label uses 'streetlight'; server stores 'broken_streetlight'
      var c = catF === "streetlight" ? "broken_streetlight" : catF;
      qs.set("category", c);
    }
    if (areaF) qs.set("area", areaF);
    if (statF) { qs.set("status", statF === "progress" ? "in_progress" : statF); }
    if (sortF) qs.set("sort", sortF);
    return j("GET", "/issues?" + qs);
  }

  function loadIssues() {
    if (DEMO) {
      issues = demoLoadStore().filter(function (i) {
        if (catF) {
          var c = catF === "streetlight" ? "broken_streetlight" : catF;
          if (i.category !== c) return false;
        }
        if (areaF) {
          var hay = (i.location_text || "") + " " + (i.summary || "");
          if (hay.toLowerCase().indexOf(areaF.toLowerCase()) === -1) return false;
        }
        if (statF && i.status !== statF) return false;
        return true;
      });
      refresh(); return;
    }
    apiIssues().then(function (data) {
      issues = data || [];
      refresh();
      loadCategories();
      loadAreas();
    }).catch(function () {
      setDemo(true);
      issues = demoLoadStore();
      toast("Server unreachable — switched to offline demo data.");
      refresh();
    });
  }

  /* Dynamic category dropdown + color legend: populate from /api/categories so
     AI-created types (open_manhole, stray_cattle, …) and spam appear automatically. */
  function loadCategories() {
    var legend = $("mapLegend");
    if (DEMO) {
      // offline demo: static legend for the known categories
      if (legend) {
        legend.innerHTML = ["pothole", "garbage", "broken_streetlight", "waterlogging", "other"].map(function (k) {
          return '<span class="legend-item"><span class="legend-dot" style="background:' + (CAT_COLOR[k] || "#7A877A") + '"></span>' + (CAT_LABEL[k] || k) + "</span>";
        }).join("");
      }
      return;
    }
    var sel = $("fCategory");
    if (!sel && !legend) return;
    var current = sel ? sel.value : "";
    j("GET", "/categories").then(function (cats) {
      if (!cats || !cats.length) return;
      if (sel) {
        var kept = ['<option value="">All categories</option>'];
        cats.forEach(function (c) {
          var key = c.key === "streetlight" ? "streetlight" : c.key; // keep UI alias
          kept.push('<option value="' + esc(key) + '"' + (current === key ? " selected" : "") + ">" + esc(c.label) + "</option>");
        });
        sel.innerHTML = kept.join("");
      }
      if (legend) {
        // render legend from live categories (colors auto-update as new types appear)
        var items = cats.map(function (c) {
          return '<span class="legend-item"><span class="legend-dot" style="background:' + esc(c.color) + '"></span>' + esc(c.label) + "</span>";
        }).join("");
        legend.innerHTML = items;
      }
    }).catch(function () { /* keep static options on failure */ });
  }

  /* Area dropdown: populate from /api/areas so new areas appear automatically. */
  function loadAreas() {
    var sel = $("fArea");
    if (DEMO) {
      // offline demo: build from demo store locations
      if (sel) {
        var areas = {};
        demoLoadStore().forEach(function (i) {
          var a = (i.location_text || "").split(",")[0].trim();
          if (a) areas[a] = 1;
        });
        var kept = ['<option value="">All areas</option>'];
        Object.keys(areas).forEach(function (a) {
          kept.push('<option value="' + esc(a) + '">' + esc(a) + "</option>");
        });
        sel.innerHTML = kept.join("");
      }
      return;
    }
    if (!sel) return;
    var current = sel.value;
    j("GET", "/areas").then(function (areas) {
      if (!areas || !areas.length) return;
      var kept = ['<option value="">All areas</option>'];
      areas.forEach(function (a) {
        kept.push('<option value="' + esc(a.key) + '"' + (current === a.key ? " selected" : "") + ">" + esc(a.key) + " (" + a.count + ")</option>");
      });
      sel.innerHTML = kept.join("");
    }).catch(function () { /* keep static on failure */ });
  }

  /* Google reCAPTCHA: loads the script only when the server says it's enabled
     (keys configured). Otherwise the captcha box stays hidden and submissions
     proceed normally (demo mode). */
  function loadCaptcha() {
    var box = $("captchaBox");
    if (!box) return;
    if (DEMO) return;
    j("GET", "/captcha/config").then(function (cfg) {
      if (!cfg || !cfg.enabled || !cfg.site_key) return;
      captchaEnabled = true;
      box.style.display = "block";
      $("captchaStatus").style.display = "block";
      $("captchaStatus").textContent = "Human verification — proves you're not a bot.";
      if (typeof grecaptcha !== "undefined" && grecaptcha.render) {
        captchaWidgetId = grecaptcha.render(box, { sitekey: cfg.site_key });
      } else {
        var s = document.createElement("script");
        s.src = "https://www.google.com/recaptcha/api.js?onload=onCaptchaLoaded&render=explicit";
        window.onCaptchaLoaded = function () {
          if (captchaEnabled && box && box.childElementCount === 0) {
            captchaWidgetId = grecaptcha.render(box, { sitekey: cfg.site_key });
          }
        };
        document.head.appendChild(s);
      }
    }).catch(function () { /* captcha unavailable → stay disabled */ });
  }

  function clusterMetrics(issue) {
    // prefer the server-computed priority/band; fall back to demo formula only in offline mode
    var m = (typeof DEMO !== "undefined" && DEMO) ? demoComputePriority(issue) : null;
    var category = issue.category || "other";
    var status = issue.status || "open";
    var slaHours = SLA_HOURS[category] || 168;
    var days = 0;
    if (issue.created_at) {
      var ts = new Date(issue.created_at.replace(" ", "T") + "Z").getTime();
      if (!isNaN(ts)) days = Math.max(0, (Date.now() - ts) / 86400000);
    }
    var slaBreached = (days * 24) > slaHours;
    var dept = issue.dept || DEPARTMENTS[category] || "General Administration";
    var priorityRaw = m ? m.priority : parseFloat(issue.priority_score || 0);
    var priority = Math.round(priorityRaw); // display stamp
    var band = m ? m.band : (function () { try { return JSON.parse(issue.priority_reason || "{}").band || 3; } catch (e) { return 3; } })();
    var severity = m ? m.severity : Math.round(issue.severity || 3);
    var affected = m ? m.affected : (issue.affected_count || 1);
    var proximity = m ? m.proximity : 1.0;
    return { severity: severity, affected: affected, days: days, proximity: proximity, nearName: null, priority: priority, priorityRaw: priorityRaw, category: category, status: status, slaHours: slaHours, slaBreached: slaBreached, dept: dept, lat: issue.centroid_lat, lng: issue.centroid_lng, band: band };
  }

  function renderStats() {
    var open = issues.filter(function (i) { return i.status !== "resolved"; });
    var affected = open.reduce(function (s, i) { return s + (i.affected_count || 1); }, 0);
    var merged = issues.reduce(function (s, i) { return s + Math.max(0, ((i.members || []).length || 0) - 1); }, 0);
    var sla = open.filter(function (i) { return clusterMetrics(i).slaBreached; }).length;
    $("hdrPeople").textContent = affected;
    $("hdrOpen").textContent = open.length;
    $("kpiOpen").textContent = open.length;
    $("kpiPeople").textContent = affected;
    $("kpiMerged").textContent = merged;
    $("kpiSla").textContent = sla;
  }

  function renderMap() {
    var panel = $("mapPanel");
    if (!panel || panel.offsetParent === null) return; // map only when admin visible
    if (!map) initMap();
    if (!map) return;
    markerLayer.clearLayers();
    var matchedPts = [];
    var hasFilter = !!(catF || statF || areaF);
    issues.forEach(function (issue) {
      var m = clusterMetrics(issue);
      if (!m.lat) return;
      var mk = L.circleMarker([m.lat, m.lng], {
        radius: 3 + Math.min(4, (m.affected || 1) * 0.5),
        color: "#FFFFFF", fillColor: CAT_COLOR[m.category], fillOpacity: 0.9, weight: 1.5
      });
      mk.bindPopup("<b>" + catLabel(issue) + "</b><br>PRT " + m.priority + " · " + m.affected + " affected<br>" + esc(issue.summary || "").slice(0, 90) + "<br><i>" + esc(m.dept) + "</i>");
      mk.addTo(markerLayer);
      // when filtering by area, highlight the matching markers with a ring
      if (hasFilter) {
        L.circleMarker([m.lat, m.lng], {
          radius: 10 + Math.min(5, (m.affected || 1) * 0.5),
          color: "#FFD54F", weight: 2, fillColor: "transparent", fillOpacity: 0
        }).addTo(markerLayer);
      }
      matchedPts.push([m.lat, m.lng]);
    });
    if (activeHighlight) { map.removeLayer(activeHighlight); activeHighlight = null; }
    if (hasFilter) {
      if (matchedPts.length === 1) map.flyTo(matchedPts[0], 15, { duration: 1.1 });
      else if (matchedPts.length > 1) map.flyToBounds(L.latLngBounds(matchedPts), { padding: [60, 60], maxZoom: 14, duration: 1.1 });
    } else {
      map.flyTo([13.03, 80.22], 11, { duration: 1.1 });
    }
  }

  function renderCards() {
    var rows = issues.map(function (i) { return { issue: i, m: clusterMetrics(i) }; });
    if (sortF === "affected") rows.sort(function (a, b) { return b.m.affected - a.m.affected; });
    else if (sortF === "days") rows.sort(function (a, b) { return b.m.days - a.m.days; });
    else rows.sort(function (a, b) { return (b.m.priorityRaw || 0) - (a.m.priorityRaw || 0); });
    $("cardCount").textContent = rows.length + " clusters";
    var wrap = $("cardsWrap");
    wrap.innerHTML = "";
    rows.forEach(function (row) {
      var issue = row.issue, m = row.m;
      var el = document.createElement("div");
      el.className = "ccard cat-" + catCss(issue);
      el.setAttribute("data-od-id", "cluster-card-" + catCss(issue) + "-" + issue.id);
      el.style.borderLeftColor = catColor(issue);
      var badges = '<span class="badge badge--' + m.status + '">' + esc(m.status.replace(/_/g, " ")) + '</span>' +
        '<span class="badge">' + m.affected + " affected</span>" +
        '<span class="badge">' + Math.round(m.days) + "d pending</span>" +
        (m.proximity > 1 ? '<span class="badge badge--amber">near facility</span>' : "") +
        '<span class="badge">band ' + m.band + "</span>";
      var actions = m.status !== "resolved"
        ? '<div class="actions">' +
          (m.status === "open" ? '<button class="btn btn--ghost btn--dark" data-id="' + issue.id + '" data-status="assigned">Assign</button>' : '') +
          '<button class="btn btn--ghost btn--dark" data-id="' + issue.id + '" data-status="in_progress">In progress</button>' +
          '<button class="btn btn--green" data-id="' + issue.id + '" data-status="resolved">Resolve</button></div>'
        : "";
      el.innerHTML = '<div class="top"><div><h4>' + catLabel(issue) + '</h4>' +
        '<div class="meta">' + esc(m.dept) + "</div>" +
        '<div class="id">CR-' + ("000" + issue.id).slice(-4) + "</div></div>" +
        '<div class="stamp"><b>' + m.priority + "</b><span>PRT</span></div></div>" +
        "<p>" + esc(issue.summary) + "</p>" +
        '<div class="badges">' + badges + "</div>" +
        '<div class="foot"><span class="sla' + (m.slaBreached ? " breach" : "") + '">SLA ' + m.slaHours + "h" + (m.slaBreached ? " · BREACHED" : "") + "</span>" + actions + "</div>";
      wrap.appendChild(el);
    });
    wrap.querySelectorAll("[data-status]").forEach(function (btn) {
      btn.addEventListener("click", function () { setIssueStatus(btn.dataset.id, btn.dataset.status); });
    });
  }

  function setIssueStatus(id, status) {
    if (DEMO) {
      var store = demoLoadStore();
      var issue = store.filter(function (i) { return String(i.id) === String(id); })[0];
      if (issue) { issue.status = status; demoSaveStore(store); }
      toast(status === "resolved" ? "Citizens of issue #" + id + ' notified — "' + (catLabel(issue) || "") + ' marked RESOLVED."' : "Status → " + status.replace(/_/g, " ") + " · routed to " + (issue.dept || ""));
      loadIssues();
      return;
    }
    var tgt = issues.filter(function (i) { return String(i.id) === String(id); })[0];
    var dept = (tgt && DEPARTMENTS[tgt.category]) || "General Administration";
    j("POST", "/issues/" + id + "/status?status=" + encodeURIComponent(status) + "&dept=" + encodeURIComponent(dept))
      .then(function () {
        toast(status === "resolved" ? "Citizens of issue #" + id + ' notified — "resolved."' : "Status → " + status.replace(/_/g, " "));
        loadIssues();
      })
      .catch(function (e) { toast("Error: " + e.message, true); });
  }

  function renderDedupExplain() {
    var wrap = $("dedupExplain");
    var merged = issues.filter(function (i) { return ((i.members || []).length || 0) > 1; });
    if (!merged.length) {
      wrap.innerHTML = '<div class="hint" style="color:var(--faint)">Live server dedup — merged clusters appear here with their similarity breakdowns.</div>';
      $("workedExample").textContent = "Worked example appears when merged clusters load.";
      return;
    }
    var html = '<div class="cluster-explain"><div class="ch"><span>LIVE MERGED CLUSTERS (' + merged.length + ")</span><span>server similarity scores</span></div>";
    merged.forEach(function (i) {
      var members = (i.members || []).map(function (m) {
        return '<div class="pair">complaint #' + m.complaint_id + " — sim " + Math.round((m.sim_total || 0) * 100) + "% <span class=\"score-lo\">(t " + (+m.text_score || 0).toFixed(2) + " g " + (+m.geo_score || 0).toFixed(2) + " v " + (+m.vision_score || 0).toFixed(2) + ")</span></div>";
      }).join("");
      html += '<div class="pair" style="border-left:none;padding-left:0;margin-top:8px"><b>' + (catLabel(i) || i.category) + "</b> — issue #" + i.id + " · " + i.affected_count + " affected</div>" + members;
    });
    html += "</div>";
    wrap.innerHTML = html;
    var open = issues.filter(function (i) { return i.status !== "resolved"; }).map(function (i) { return { issue: i, m: clusterMetrics(i) }; }).sort(function (a, b) { return (b.m.priorityRaw || 0) - (a.m.priorityRaw || 0); });
    if (open.length) {
      var top = open[0];
      var r = {};
      try { r = JSON.parse(top.issue.priority_reason || "{}"); } catch (e) { /* ignore */ }
      var proxNote = top.m.proximity > 1 ? " (within 200m of a facility)" : "";
      $("workedExample").innerHTML =
        '<b>Worked example</b> — top issue "' + CAT_LABEL[top.m.category] + '" (affected ' + top.m.affected + '):<br>' +
        "severity S=" + top.m.severity + " · P=" + (typeof r.P === "number" ? r.P.toFixed(2) : (Math.sqrt(top.m.affected)).toFixed(2)) + " (affected) · T=" + (typeof r.T === "number" ? r.T.toFixed(2) : (Math.min(top.m.days, 30)).toFixed(2)) + " (days " + Math.round(top.m.days) + ") · L=" + (typeof r.L === "number" ? r.L.toFixed(2) : "1.00") + proxNote + "<br>" +
        'band ' + (r.band || top.m.band) + " → <b style=\"color:#e8a93a\">PRT " + top.m.priority + "/100</b>";
    }
  }

  function refresh() { renderStats(); renderMap(); renderCards(); renderDedupExplain(); }

  /* ================= MAP ================= */
  function initMap() {
    if (mapInited) return;
    var panel = $("mapPanel");
    if (!panel || panel.offsetParent === null) return; // container hidden — defer until admin visible
    mapInited = true;
    map = L.map("map", { scrollWheelZoom: false }).setView([13.03, 80.22], 11);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", { attribution: "&copy; OpenStreetMap &copy; CARTO", maxZoom: 19 }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
  }

  function flyToAndMark(lat, lng, areaName, category) {
    var nlat = parseFloat(lat), nlng = parseFloat(lng);
    if (isNaN(nlat) || isNaN(nlng)) return;
    var panel = $("mapPanel");
    if (!panel || panel.offsetParent === null) return; // map not visible — nothing to fly
    if (!map) initMap();
    if (!map) return;
    map.flyTo([nlat, nlng], 15, { duration: 1.1 });
    if (activeHighlight) { map.removeLayer(activeHighlight); activeHighlight = null; }
    var icon = L.divIcon({ className: "pulse-marker", iconSize: [16, 16] });
    activeHighlight = L.marker([lat, lng], { icon: icon }).addTo(map);
    activeHighlight.bindPopup("<b>" + (CAT_LABEL[category] || category) + "</b> complaint located" + (areaName ? " — " + esc(areaName) : "")).openPopup();
  }

  function setMapFullscreen(on) {
    $("mapPanel").classList.toggle("fullscreen", on);
    document.body.classList.toggle("map-fullscreen-active", on);
    $("fsTxt").textContent = on ? "Exit fullscreen" : "Fullscreen";
    var mapEl = $("map");
    setTimeout(function () {
      if (!mapEl) return;
      if (on) {
        // give Leaflet a real pixel height = viewport minus head+legend
        var head = $("mapPanel").querySelector(".panel-head");
        var legend = $("mapPanel").querySelector(".map-legend");
        var filters = $("mapPanel").querySelector(".map-filters");
        var used = (head ? head.offsetHeight : 0) + (legend ? legend.offsetHeight : 0)
                 + (filters ? filters.offsetHeight : 0);
        mapEl.style.height = Math.max(220, window.innerHeight - used - 28) + "px";
      } else {
        mapEl.style.height = "";
      }
      if (map) map.invalidateSize();
    }, 90);
  }

  /* ================= VIEWS ================= */
  function setView(v, persist) {
    document.body.dataset.view = v;
    document.querySelectorAll(".view-btn").forEach(function (b) {
      var active = b.dataset.view === v;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });
    $("viewNote").textContent = v === "citizen"
      ? "Public intake — anyone can file an issue."
      : (v === "status"
        ? "Public tracking — check a filed complaint by its ID."
        : "Ward staff view — map, clusters, priority scoring & status controls.");
    if (v === "admin" && !mapSizedOnce) {
      setTimeout(function () { if (!map) initMap(); if (map) map.invalidateSize(); mapSizedOnce = true; refresh(); }, 80);
    }
    // replay entrance animation on the shown view
    ["citizenView", "statusView", "adminView"].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      if (v === id.replace("View", "")) {
        el.classList.remove("view-in");
        void el.offsetWidth; /* force reflow to restart animation */
        el.classList.add("view-in");
      }
    });
    if (persist !== false) {
      try { localStorage.setItem(VIEW_KEY, v); } catch (e) { /* ignore */ }
    }
  }

  document.querySelectorAll(".view-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var v = b.dataset.view;
      if (v === "admin" && !adminAuthed) { openAdminLogin(); return; }
      setView(v);
    });
  });

  /* ================= ADMIN LOGIN ================= */
  var ADMIN_PASSWORD = "admin@nagarai";
  var overlay = $("adminLoginOverlay");
  var pwInput = $("adminPasswordInput");
  var captchaAnswer = 0;
  function newAdminCaptcha() {
    var a = 2 + Math.floor(Math.random() * 8);
    var b = 2 + Math.floor(Math.random() * 8);
    captchaAnswer = a + b;
    $("adminCaptchaQ").textContent = a + " + " + b + " = ?";
    $("adminCaptchaInput").value = "";
  }
  function openAdminLogin() {
    $("adminLoginErr").textContent = "";
    pwInput.value = "";
    newAdminCaptcha();
    overlay.classList.add("show");
    setTimeout(function () { pwInput.focus(); }, 50);
  }
  function closeAdminLogin() { overlay.classList.remove("show"); }
  function attemptAdminLogin() {
    var human = parseInt($("adminCaptchaInput").value.trim(), 10);
    if (isNaN(human) || human !== captchaAnswer) {
      $("adminLoginErr").textContent = "Human check failed — answer the sum correctly.";
      newAdminCaptcha();
      $("adminCaptchaInput").focus();
      return;
    }
    if (pwInput.value === ADMIN_PASSWORD) {
      adminAuthed = true;
      closeAdminLogin();
      setView("admin");
      loadIssues();
      initMap();
    } else {
      $("adminLoginErr").textContent = "Incorrect password. Try again.";
      pwInput.value = "";
      pwInput.focus();
    }
  }
  $("adminLoginSubmit").addEventListener("click", attemptAdminLogin);
  $("adminLoginCancel").addEventListener("click", closeAdminLogin);
  pwInput.addEventListener("keydown", function (e) { if (e.key === "Enter") attemptAdminLogin(); });
  $("adminCaptchaInput").addEventListener("keydown", function (e) { if (e.key === "Enter") attemptAdminLogin(); });
  overlay.addEventListener("click", function (e) { if (e.target === overlay) closeAdminLogin(); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay.classList.contains("show")) closeAdminLogin();
    if (e.key === "Escape" && $("mapPanel").classList.contains("fullscreen")) setMapFullscreen(false);
  });

  /* ================= CLOCK ================= */
  function tickClock() {
    // IST = UTC + 5:30 — always correct regardless of the browser's timezone:
    // take the absolute UTC ms, add 5.5h, read its UTC clock fields.
    var ist = new Date(Date.now() + 5.5 * 3600000);
    $("hdrClock").textContent = pad2(ist.getUTCHours()) + ":" + pad2(ist.getUTCMinutes()) + ":" + pad2(ist.getUTCSeconds());
  }

  /* ================= VOICE ================= */
  /* ================= VOICE (exact Web Speech API method) ================= */
  var micBtn = $("micBtn"), micStatus = $("micStatus"), micLang = $("micLang");
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var recognition = null;
  var silenceTimer = null;
  var userStopped = false;
  var voiceAccum = ""; // accumulated transcript across auto-end restarts
  var SILENCE_MS = 30000;

  function initSpeechRecognition() {
    if (SpeechRecognition) {
      recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
    }
  }

  // Reset the inactivity countdown on every speech result.
  function resetSilenceTimer() {
    clearTimeout(silenceTimer);
    silenceTimer = setTimeout(function () {
      // No speech for 30s → genuinely done; stop for real.
      userStopped = true;
      stopVoiceIntake();
    }, SILENCE_MS);
  }

  function startVoiceIntake(langCode, onInterim, onFinal, onError) {
    if (!recognition) {
      if (onError) onError("Browser Web Speech API not supported on this browser.");
      return null;
    }
    recognition.lang = langCode;

    recognition.onresult = function (event) {
      var interimTranscript = "";
      var finalTranscript = "";
      for (var i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }
      if (finalTranscript) {
        // keep every completed segment so pauses don't reset the text
        voiceAccum += finalTranscript + " ";
      }
      if (interimTranscript && onInterim) onInterim(voiceAccum + interimTranscript);
      else if (finalTranscript && onFinal) onFinal(voiceAccum);
      else if (onInterim) onInterim(voiceAccum);
      resetSilenceTimer();
    };

    recognition.onerror = function (err) { if (onError) onError(err); };

    recognition.onend = function () {
      clearTimeout(silenceTimer);
      // If the user tapped stop (or the 30s silence gap fired) — finalize.
      if (userStopped) {
        $("micBtnTxt").textContent = "Start recording";
        micBtn.classList.remove("recording");
        var t = $("inVoice").value.trim();
        voiceTranscript = t;
        if (t) {
          micStatus.innerHTML = '<span style="color:var(--route-green);font-weight:700">Transcribed:</span> ' + esc(t);
        } else {
          micStatus.textContent = "Heard nothing clear — try again, or type it below.";
        }
        return;
      }
      // The browser auto-ended (short pause, continuous mode quirk) — restart
      // transparently so the recording keeps going while the user is speaking.
      if (micBtn.classList.contains("recording")) {
        try { recognition.start(); } catch (e) {}
        resetSilenceTimer();
      }
    };

    try {
      recognition.start();
      resetSilenceTimer();
    } catch (e) {
      console.warn("Speech recognition already active or error:", e);
    }
  }

  function stopVoiceIntake() {
    userStopped = true;
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
    }
  }

  initSpeechRecognition();

  micBtn.addEventListener("click", function () {
    if (!recognition) {
      micStatus.textContent = "Browser Web Speech API not supported — type the transcript below.";
      return;
    }
    if (micBtn.classList.contains("recording")) { stopVoiceIntake(); return; }

    userStopped = false;
    var lang = micLang.value || "en-IN";
    voiceAccum = "";
    $("inVoice").value = "";
    voiceTranscript = "";

    startVoiceIntake(
      lang,
      // On interim: stream partial words live (on top of what's already final)
      function (interim) {
        $("inVoice").value = interim;
        micStatus.innerHTML = '<span class="mic-dot"></span>Transcribing live<span style="color:var(--faint)"> (interim)</span> — stop to keep';
      },
      // On final: speech complete → keep the accumulated text
      function (final) {
        $("inVoice").value = final;
        micStatus.innerHTML = '<span style="color:var(--route-green);font-weight:700">Transcribed:</span> ' + esc(final);
      },
      function (err) {
        if (err && err.error === "not-allowed") {
          micStatus.textContent = "Microphone blocked — allow the mic in the address bar, then try again.";
        }
      }
    );
    $("micBtnTxt").textContent = "Stop recording";
    micBtn.classList.add("recording");
    micStatus.innerHTML = '<span class="mic-dot"></span>Speak now — text appears live in your language';
  });

  /* ================= INTAKE TABS ================= */
  document.querySelectorAll("#intakeTabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#intakeTabs button").forEach(function (x) {
        x.classList.remove("is-active");
        x.setAttribute("aria-selected", "false");
      });
      b.classList.add("is-active");
      b.setAttribute("aria-selected", "true");
      currentTab = b.dataset.tab;
      document.querySelectorAll("#citizenView .tabpane").forEach(function (p) { p.hidden = true; });
      $("tab-" + currentTab).hidden = false;
    });
  });

  /* ================= PHOTO EXIF ================= */
  $("photoDrop").addEventListener("click", function () { $("photoInput").click(); });
  $("photoInput").addEventListener("change", function (e) {
    var file = e.target.files[0];
    if (!file) return;
    uploadedPhoto = { file: file, meta: {} };
    var reader = new FileReader();
    reader.onload = function () { $("photoPreviewWrap").innerHTML = '<img src="' + reader.result + '" alt="Uploaded issue photo">'; };
    reader.readAsDataURL(file);
    var st = $("exifStatus");
    st.textContent = "Reading photo metadata...";
    if (typeof EXIF === "undefined") { st.textContent = ""; return; }
    EXIF.getData(file, function () {
      var toDec = function (dms, ref) { var dec = dms[0] + dms[1] / 60 + dms[2] / 3600; if (ref === "S" || ref === "W") dec = -dec; return dec; };
      var lat = EXIF.getTag(this, "GPSLatitude"), latRef = EXIF.getTag(this, "GPSLatitudeRef");
      var lng = EXIF.getTag(this, "GPSLongitude"), lngRef = EXIF.getTag(this, "GPSLongitudeRef");
      var dateRaw = EXIF.getTag(this, "DateTimeOriginal") || EXIF.getTag(this, "DateTime");
      var make = EXIF.getTag(this, "Make"), model = EXIF.getTag(this, "Model");
      var parts = [];
      if (lat && lng) {
        var dLat = toDec(lat, latRef), dLng = toDec(lng, lngRef);
        $("inLat").value = dLat.toFixed(6);
        $("inLng").value = dLng.toFixed(6);
        uploadedPhoto.meta.lat = dLat; uploadedPhoto.meta.lng = dLng;
        parts.push("GPS auto-filled");
      } else {
        parts.push("no GPS tag");
        // photo has no embedded GPS -> auto-fill from the browser's location
        if (!autoLocated && !$("inLat").value) requestGps(true);
      }
      if (dateRaw) {
        var iso = dateRaw.replace(/^(\d{4}):(\d{2}):(\d{2})/, "$1-$2-$3");
        var d = new Date(iso);
        if (!isNaN(d)) { uploadedPhoto.meta.takenAt = d.toISOString(); parts.push("taken " + d.toLocaleString()); }
      }
      if (make || model) { uploadedPhoto.meta.camera = [make, model].filter(Boolean).join(" ").trim(); parts.push(uploadedPhoto.meta.camera); }
      st.textContent = parts.length ? parts.join(" · ") : "No EXIF metadata found in this photo.";
    });
  });

  /* ================= GPS (auto-locate) ================= */
  var autoLocated = false;
  function locStatus(msg) {
    var el = $("locStatus");
    if (el) el.textContent = msg;
  }
  function useGps(pos) {
    $("inLat").value = pos.coords.latitude.toFixed(6);
    $("inLng").value = pos.coords.longitude.toFixed(6);
    autoLocated = true;
    locStatus("\u{1F4CD} Auto-located: " + pos.coords.latitude.toFixed(5) + ", " + pos.coords.longitude.toFixed(5) + " (\u00B1" + Math.round(pos.coords.accuracy || 0) + "m)");
  }
  function requestGps(silent) {
    if (!navigator.geolocation) { if (!silent) toast("Geolocation not supported.", true); return; }
    navigator.geolocation.getCurrentPosition(useGps, function () {
      if (!silent) toast("Could not read GPS — type the area name instead.", true);
      if (!autoLocated) locStatus("\u26A0 Enable location for a precise map pin \u2014 or type the area name below.");
    }, { enableHighAccuracy: true, timeout: 9000, maximumAge: 15000 });
  }
  // auto-locate once when the citizen view loads (skip on admin/status)
  if (document.body.dataset.view !== "admin") { requestGps(true); }
  $("gpsBtn").addEventListener("click", function () {
    $("gpsBtn").disabled = true;
    requestGps(false);
    setTimeout(function () { $("gpsBtn").disabled = false; }, 9000);
  });
  // when a photo has no EXIF GPS, auto-fill from browser GPS instead
  var _origExif = null;
  var _exifGpsHandler = null;

  /* ================= INTAKE LOG ================= */
  function logIntake(text) {
    var log = $("intakeLog");
    var el = document.createElement("div");
    el.className = "log-item";
    el.innerHTML = '<span class="t">' + new Date().toLocaleTimeString([], { hour12: false }) + "</span> " + text;
    log.prepend(el);
    $("intakeCount").textContent = log.children.length + " filed";
  }

  /* ================= SUBMIT ================= */
  $("submitBtn").addEventListener("click", function () {
    var btn = $("submitBtn");
    btn.disabled = true;
    $("submitBtnTxt").textContent = "Running AI intake...";
    var latRaw = $("inLat").value.trim(), lngRaw = $("inLng").value.trim();
    var lat = parseFloat(latRaw), lng = parseFloat(lngRaw);

    function fail(msg) { toast(msg, true); btn.disabled = false; $("submitBtnTxt").textContent = "Submit & run AI intake"; }

    var raw = "";
    if (currentTab === "photo") {
      if (!uploadedPhoto) { fail("Upload a photo first."); return; }
      var extra = $("inPhotoText").value.trim();
      raw = extra || "Photo upload — " + (uploadedPhoto.meta.camera || "no camera info");
    } else if (currentTab === "voice") {
      raw = voiceTranscript || $("inVoice").value;
      if (!raw.trim()) { fail("Record a voice note or type a transcript first."); return; }
    } else {
      raw = $("inText").value;
      if (!raw.trim()) { fail("Type something first."); return; }
    }

    if (DEMO) {
      demoIntake(raw, isNaN(lat) ? null : lat, isNaN(lng) ? null : lng, currentTab === "photo" ? $("inPhotoText").value : "")
        .then(function (resp) {
          renderResult(resp, raw);
          btn.disabled = false;
          $("submitBtnTxt").textContent = "Submit & run AI intake";
        });
      return;
    }

    var fd = new FormData();
    if (currentTab === "photo") {
      fd.append("image", uploadedPhoto.file, uploadedPhoto.file.name);
      fd.append("text", $("inPhotoText").value.trim());
    } else {
      fd.append("text", raw);
    }
    fd.append("language", micLang.value);
    if (!isNaN(lat) && !isNaN(lng)) { fd.append("lat", lat); fd.append("lng", lng); }
    if (captchaEnabled) {
      var tok = (typeof grecaptcha !== "undefined" && captchaWidgetId != null)
        ? grecaptcha.getResponse(captchaWidgetId) : "";
      if (!tok) { fail("Please complete the human verification first."); return; }
      fd.append("captcha_token", tok);
      if (typeof grecaptcha !== "undefined" && captchaWidgetId != null) grecaptcha.reset(captchaWidgetId);
    }
    j("POST", "/complaints", fd).then(function (resp) {
      renderResult(resp, raw);
    }).catch(function (e) {
      setDemo(true);
      toast("Server unreachable — filed through offline demo pipeline.");
      demoIntake(raw, isNaN(lat) ? null : lat, isNaN(lng) ? null : lng)
        .then(function (resp) { renderResult(resp, raw); });
    }).then(function () {
      btn.disabled = false;
      $("submitBtnTxt").textContent = "Submit & run AI intake";
    });
  });

  function renderResult(resp, raw) {
    var c = resp.complaint, d = resp.dedup;
    var area = guessLocation(c.location_text || c.summary || raw);
    var lat = parseFloat(c.lat), lng = parseFloat(c.lng);
    if (isNaN(lat) && area) {
      lat = area.coords[0] + (Math.random() - 0.5) * 0.001;
      lng = area.coords[1] + (Math.random() - 0.5) * 0.001;
    }
    $("resultStamp").classList.add("show");
    $("rCat").textContent = (c.category || "other").replace(/_/g, " ");
    $("rSev").textContent = (c.severity || 3) + "/5";
    var rLat = parseFloat(lat), rLng = parseFloat(lng);
    $("rLoc").textContent = (!isNaN(rLat) && !isNaN(rLng) && isFinite(rLat) && isFinite(rLng))
      ? rLat.toFixed(4) + ", " + rLng.toFixed(4) + (c.loc_source === "photo_exif" ? " (from photo EXIF)" : "")
      : (area ? area.name : "needs pin");
    $("rDesc").textContent = c.summary || raw;
    var pm = c.photo_meta || {};
    var parts = [];
    if (pm.make || pm.model) parts.push([pm.make, pm.model].filter(Boolean).join(" "));
    if (pm.captured_at) parts.push(pm.captured_at.replace("T", " "));
    if (pm.gps) parts.push("GPS " + pm.gps.lat.toFixed(6) + ", " + pm.gps.lng.toFixed(6));
    if (pm.altitude_m != null) parts.push(pm.altitude_m + "m");
    if (pm.orientation) parts.push("orientation " + pm.orientation);
    $("rPhotoMeta").textContent = parts.length ? parts.join(" · ") : "no EXIF metadata";
    var dedupNote = d && d.merged
      ? "merged with issue #" + d.issue_id + " (sim " + Math.round(((d.scores || {}).sim || 0) * 100) + "%)"
      : "new distinct issue #" + (c.id || (d && d.issue_id));
    $("rDedup").textContent = dedupNote;
    logIntake("<b>#" + c.id + "</b> " + (c.category || "other") + " · sev " + (c.severity || 3) + " · " + (c.location_text || "area unresolved") + " — " + dedupNote);
    toast("Filed #" + (c.id || (d && d.issue_id)) + " → routed to " + (DEPARTMENTS[c.category] || "General Admin"));
    if (!isNaN(lat) && !isNaN(lng)) flyToAndMark(lat, lng, c.location_text, c.category);
    $("inText").value = ""; $("inVoice").value = ""; $("inPhotoText").value = "";
    $("inLat").value = ""; $("inLng").value = "";
    uploadedPhoto = null; voiceTranscript = "";
    $("photoPreviewWrap").innerHTML = ""; $("exifStatus").textContent = "";
    loadIssues();
  }

  /* ================= JUDGING SET ================= */
  var JUDGING_SET = [
    { area: "Panagal Park, T Nagar", text: "Periya pothole near Panagal Park bus stop, bike vizhunthadhu already", lat: 13.0418, lng: 80.2341 },
    { area: "Panagal Park, T Nagar", text: "Pothole Panagal Park bus stand-la, romba periyathu, 2 accidents nadanthuchu", lat: 13.0421, lng: 80.2345 },
    { area: "Adyar", text: "Garbage bin near Adyar signal not cleared for 10 days, smell romba bad", lat: 13.0067, lng: 80.2570 },
    { area: "Adyar", text: "Trash near Adyar signal overflowing, kalla smell varudhu everyday", lat: 13.0070, lng: 80.2575 },
    { area: "Anna Nagar 2nd Ave", text: "Streetlight 2nd avenue not working since 1 week, dark area la women thani ah walk pandra", lat: 13.0850, lng: 80.2101 },
    { area: "Velachery Main Rd", text: "Velachery main road full ah thanni thanginu irukku, buses stuck", lat: 12.9756, lng: 80.2207 },
    { area: "Velachery bus depot", text: "Water logging near Velachery bus depot, knee deep water everywhere", lat: 12.9759, lng: 80.2210 },
    { area: "Tambaram", text: "Large pothole outside Tambaram govt hospital gate, ambulance problem aagudhu", lat: 12.9252, lng: 80.1002 },
    { area: "Perambur", text: "Garbage dump growing near Perambur market, rats increasing badly", lat: 13.1179, lng: 80.2453 },
    { area: "Nungambakkam", text: "3 streetlights down on Nungambakkam high road, accident risk night time", lat: 13.0603, lng: 80.2417 },
    { area: "Porur", text: "Pothole near Porur signal, water filled, cant see how deep it is", lat: 13.0381, lng: 80.1564 },
    { area: "Chromepet", text: "Chromepet subway fully waterlogged, no vehicle can pass through", lat: 12.9516, lng: 80.1462 },
    { area: "Velachery school", text: "Garbage not collected near Velachery Corporation school for 2 weeks now", lat: 12.9800, lng: 80.2250 },
    { area: "Ambattur estate", text: "Deep pothole Ambattur estate road, two-wheelers falling daily near junction", lat: 13.1143, lng: 80.1548 },
    { area: "Anna Nagar 2nd Ave", text: "Anna Nagar 2nd avenue light pole dark since many days, safety issue at night", lat: 13.0855, lng: 80.2107 }
  ];

  $("loadJudging").addEventListener("click", function () {
    if (judgingRunning) return;
    judgingRunning = true;
    var btn = $("loadJudging");
    btn.disabled = true;
    btn.textContent = "Loading 15 complaints (5 parallel)...";
    $("intakeLog").innerHTML = "";
    $("intakeCount").textContent = "";
    var rows = JUDGING_SET.slice();
    var pending = rows.length;
    var CONCURRENCY = 3;

    function submitRow(row) {
      if (DEMO) {
        demoIntake(row.text, row.lat, row.lng).then(function (resp) {
          var c = resp.complaint, d = resp.dedup;
          logIntake("<b>#" + c.id + "</b> " + c.category + " · sev " + c.severity + " · " + row.area + " — " + (d.merged ? "merged" : "new issue #" + d.issue_id));
          done();
        }).catch(done);
        return;
      }
      var fd = new FormData();
      fd.append("text", row.text);
      fd.append("lat", row.lat); fd.append("lng", row.lng);
      fd.append("language", "auto");
      var tries = 0;
      function attempt() {
        tries++;
        j("POST", "/complaints", fd).then(function (resp) {
          var c = resp.complaint, d = resp.dedup;
          logIntake("<b>#" + c.id + "</b> " + c.category + " · sev " + c.severity + " · " + row.area + " — " + (d.merged ? "merged" : "new issue #" + d.issue_id));
          done();
        }).catch(function () {
          if (tries < 3) { setTimeout(attempt, 1500); }
          else { setDemo(true); done(); }
        });
      }
      attempt();
    }

    function done() {
      pending--;
      if (rows.length) submitRow(rows.shift());
      if (pending <= 0) {
        judgingRunning = false;
        btn.disabled = false;
        btn.textContent = "Load 15-complaint set";
        loadIssues();
        toast("Loaded 15 raw judging-set complaints" + (DEMO ? " through the offline pipeline." : " through server intake."));
      }
    }

    for (var i = 0; i < CONCURRENCY && rows.length; i++) submitRow(rows.shift());
  });

  $("resetAll").addEventListener("click", function () {
    var btn = $("resetAll");
    btn.disabled = true;
    var orig = btn.textContent;
    btn.textContent = "Resetting...";
    var finish = function () { btn.disabled = false; btn.textContent = orig; };
    if (DEMO) {
      try { localStorage.removeItem(DEMO_STORE_KEY); } catch (e) {}
      issues = [];
      $("intakeLog").innerHTML = "";
      $("intakeCount").textContent = "";
      if (activeHighlight) { map.removeLayer(activeHighlight); activeHighlight = null; }
      refresh();
      toast("Board reset (offline demo store cleared).");
      finish();
      return;
    }
    j("POST", "/reset").then(function () {
      issues = [];
      $("intakeLog").innerHTML = "";
      $("intakeCount").textContent = "";
      if (activeHighlight) { map.removeLayer(activeHighlight); activeHighlight = null; }
      loadIssues();
      toast("Board reset — all complaints cleared from the server.");
    }).catch(function (e) {
      toast("Reset error: " + e.message, true);
    }).then(finish);
  });

  /* ================= REPORT (view + download) ================= */
  /* Minimal self-hosted markdown → HTML renderer (headings, tables, lists,
     bold, code, hr, links). Covers the structure emitted by /api/report. */
  function mdEscape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function mdInline(s) {
    return mdEscape(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }
  function mdRender(src) {
    var lines = String(src || "").split("\n");
    var html = [];
    var inTable = false;
    var table = [];
    var i = 0;

    function flushTable() {
      if (!inTable) return;
      inTable = false;
      var out = "<table>";
      for (var r = 0; r < table.length; r++) {
        out += "<tr>" + table[r].map(function (c) {
          var tag = r === 0 ? "th" : "td";
          return "<" + tag + ">" + mdInline(c) + "</" + tag + ">";
        }).join("") + "</tr>";
      }
      html.push(out + "</table>");
      table = [];
    }

    for (; i < lines.length; i++) {
      var ln = lines[i];
      var t = ln.trim();

      if (!t) { flushTable(); html.push(""); continue; }

      // table separator row like |---|---|
      if (/^\|[\s:|-]+\|$/.test(t) && inTable) { continue; }

      // table row
      if (t.charAt(0) === "|" && t.charAt(t.length - 1) === "|") {
        if (!inTable) { inTable = true; table = []; }
        table.push(t.slice(1, -1).split("|").map(function (c) { return c.trim(); }));
        continue;
      }
      flushTable();

      if (/^###\s/.test(t)) html.push("<h4>" + mdInline(t.replace(/^###\s*/, "")) + "</h4>");
      else if (/^##\s/.test(t)) html.push("<h3>" + mdInline(t.replace(/^##\s*/, "")) + "</h3>");
      else if (/^#\s/.test(t)) html.push("<h2>" + mdInline(t.replace(/^#\s*/, "")) + "</h2>");
      else if (/^[-*]\s/.test(t)) html.push("<li>" + mdInline(t.replace(/^[-*]\s*/, "")) + "</li>");
      else if (/^\d+\.\s/.test(t)) html.push("<li>" + mdInline(t.replace(/^\d+\.\s*/, "")) + "</li>");
      else if (/^---+\s*$/.test(t)) html.push("<hr>");
      else html.push("<p>" + mdInline(t) + "</p>");
    }
    flushTable();
    return html.join("\n");
  }

  function fetchReport(fmt) {
    return fetch(API + "/report?fmt=" + fmt).then(function (r) {
      if (!r.ok) throw new Error(r.status + " " + r.statusText);
      return r.text();
    });
  }

  var reportBtn = $("downloadReport");
  if (reportBtn) { reportBtn.remove(); }

  /* View report: renders the markdown inside the admin panel. */
  var viewReportBtn = $("viewReport");
  var lastReportMd = "";
  if (viewReportBtn) {
    viewReportBtn.addEventListener("click", function () {
      if (DEMO) {
        toast("Report is only available with the live server.", true);
        return;
      }
      var btn = viewReportBtn;
      btn.disabled = true;
      var orig = btn.textContent;
      btn.textContent = "Loading...";
      fetchReport("markdown").then(function (md) {
        lastReportMd = md;
        var body = $("reportBody");
        if (!body) throw new Error("report viewer missing");
        body.innerHTML = mdRender(md);
        $("reportOverlay").classList.add("show");
      }).catch(function (e) {
        toast("Report error: " + e.message, true);
      }).then(function () {
        btn.disabled = false;
        btn.textContent = orig;
      });
    });
  }
  $("reportClose").addEventListener("click", function () { $("reportOverlay").classList.remove("show"); });

  /* Download the report as a .md file (uses the last fetched report). */
  var reportDownloadBtn = $("reportDownloadBtn");
  if (reportDownloadBtn) {
    reportDownloadBtn.addEventListener("click", function () {
      if (!lastReportMd) {
        toast("Open the report first, then download.", true);
        return;
      }
      var d = new Date();
      var pad = function (n) { return n < 10 ? "0" + n : n; };
      var blob = new Blob([lastReportMd], { type: "text/markdown" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "nagarai-report-" + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + ".md";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
      toast("Report downloaded.");
    });
  }

  /* Share the report via email (mailto with the markdown as the body). */
  var shareEmailBtn = $("reportShareEmail");
  if (shareEmailBtn) {
    shareEmailBtn.addEventListener("click", function () {
      if (!lastReportMd) {
        toast("Open the report first, then share.", true);
        return;
      }
      var d = new Date();
      var pad = function (n) { return n < 10 ? "0" + n : n; };
      var subject = "NagarAI civic intake report — " + d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
      var body = encodeURIComponent(lastReportMd);
      window.location.href = "mailto:?subject=" + encodeURIComponent(subject) + "&body=" + body;
      toast("Email app opened with the report.");
    });
  }

  $("reportOverlay").addEventListener("click", function (e) {
    if (e.target === $("reportOverlay")) $("reportOverlay").classList.remove("show");
  });

  var searchQ = "";
  var searchTimer = null;
  var searchEl = $("fSearch");
  if (searchEl) {
    searchEl.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        searchQ = searchEl.value;
        loadIssues();
      }, 300);
    });
  }

  ["fCategory", "fStatus", "fSort", "fArea"].forEach(function (id) {
    $(id).addEventListener("change", function () {
      if (id === "fSort") { sortF = $(id).value; loadIssues(); }
      else if (id === "fArea") { areaF = $("fArea").value; loadIssues(); }
      else { catF = $("fCategory").value; statF = $("fStatus").value; loadIssues(); }
    });
  });

  $("mapFullscreenBtn").addEventListener("click", function () {
    setMapFullscreen(!$("mapPanel").classList.contains("fullscreen"));
  });

  /* ================= TRACK STATUS ================= */
  $("trackBtn").addEventListener("click", trackStatus);
  $("trackId").addEventListener("keydown", function (e) { if (e.key === "Enter") trackStatus(); });

  function trackStatus() {
    var id = $("trackId").value.trim();
    var wrap = $("trackResult");
    if (!id) { toast("Enter a complaint ID."); return; }
    wrap.innerHTML = '<div class="hint" style="color:var(--faint);margin-top:10px">Looking up complaint #' + esc(id) + "...</div>";

    function render(data) {
      if (!data || data.error) {
        wrap.innerHTML = '<div class="hint" style="color:var(--signal-red);margin-top:10px">Complaint #' + esc(id) + " not found.</div>";
        return;
      }
      trackedIssueId = data.issue ? data.issue.id : null;
      var cat = data.category || "other";
      var stepIdx = TRACK_STEPS.indexOf(data.status);
      var resolved = data.status === "resolved";
      var steps = TRACK_STEPS.map(function (s, i) {
        var done = i <= stepIdx || resolved;
        return '<div class="track-step' + (done ? " done" : "") + '"><div class="dot">' + (i < stepIdx || resolved ? "✓" : (i + 1)) + "</div><div class=\"lbl\">" + s.replace(/_/g, " ") + "</div></div>";
      }).join('<div class="track-conn' + (stepIdx > 0 ? " done" : "") + '" aria-hidden="true"></div>');
      var pois = "";
      if (data.issue && data.issue.school_hospital_prox) {
        try {
          var pl = JSON.parse(data.issue.school_hospital_prox || "[]");
          if (pl.length) pois = '<div class="hint" style="margin-top:8px">📍 near ' + esc(pl[0].name) + "</div>";
        } catch (e) { /* ignore */ }
      }
      var banner = resolved
        ? '<div class="resolve-banner">✓ RESOLVED by the corporation</div>'
        : "";
      wrap.innerHTML = '<div class="track-detail">' +
        '<div class="row"><span>Category</span><b>' + esc(cat.replace(/_/g, " ")) + "</b></div>" +
        '<div class="row"><span>Severity</span><b>' + (data.severity || "—") + "/5</b></div>" +
        '<div class="row"><span>Department</span><b>' + esc(data.dept || DEPARTMENTS[cat] || "Pending routing") + "</b></div>" +
        (data.issue ? '<div class="row"><span>Issue #' + data.issue.id + "</span><b>👥 " + (data.issue.affected_count || 1) + " citizens</b></div>" : "") +
        '<div class="sum">' + esc(data.summary) + "</div>" +
        '<div style="display:flex;align-items:flex-start">' + steps + "</div>" + pois + banner +
        "</div>";
    }

    if (DEMO) {
      var store = demoLoadStore();
      var found = store.filter(function (i) { return String(i.id) === String(id); })[0];
      if (!found) { render({ error: true }); return; }
      render({
        issue: found, category: found.category, status: found.status, severity: found.severity,
        dept: found.dept || DEPARTMENTS[found.category], summary: found.summary
      });
      return;
    }
    j("GET", "/status/" + id).then(render).catch(function (e) {
      wrap.innerHTML = '<div class="hint" style="color:var(--signal-red);margin-top:10px">Track error: ' + esc(e.message) + "</div>";
    });
  }

  /* ================= INIT ================= */
  /* map inits lazily on first admin render */
  var saved = null;
  try { saved = localStorage.getItem(VIEW_KEY); } catch (e) { /* ignore */ }
  if (saved === "status") setView("status", false);
  else if (saved === "admin") { adminAuthed = true; setView("admin", false); initMap(); }
  else setView("citizen", false);
  tickClock();
  setInterval(tickClock, 1000);
  loadIssues();
  loadCategories();
  loadAreas();
  loadCaptcha();
})();
