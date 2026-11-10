(() => {
  const DATA_URL = "data/listings.json";
  const SHORTLIST_KEY = "tgsf-shortlist-v1";
  const THEME_KEY = "tgsf-theme";
  const LANG_KEY = "tgsf-lang";

  const I18N = {
    en: {
      title: "Thailand Gas Station Site Finder",
      subtitle: "Site-selection screening for high-traffic service stations",
      filters: "Filters", compare: "Compare", about: "About",
      kpi_listings: "Listings in this dataset", kpi_provinces: "Provinces covered",
      kpi_high: "High potential", kpi_high_sub: "Score 70 and above",
      kpi_price: "Avg. asking price / rai", kpi_price_sub: "Where price and area are known",
      kpi_updated: "Data last updated",
      search_filters: "Search filters", province: "Province", district: "District",
      area_rai: "Land area (rai)", price: "Asking price (THB)", ppr: "Price per rai (THB)",
      road_type: "Road type", min_frontage: "Minimum frontage (m)", traffic: "Traffic potential",
      min_score: "Minimum suitability score", max_comp: "Max competitors within",
      source: "Data source", has_photos: "Has photos",
      verified_only: "Verified coordinates & price only",
      shortlist_only: "Shortlist only", mapped_only: "Has map coordinates",
      weights: "Score weights",
      weights_help: "Drag to change emphasis. Weights are renormalised to 100. Factor scores stay the same; only the overall total changes.",
      reset_weights: "Reset default weights", reset: "Reset filters",
      export: "Export shortlist CSV",
      leg_high: "High potential (70+)", leg_med: "Medium (45–69)", leg_low: "Low (under 45)",
      leg_unmap: "No coordinates", show_rings: "Rings & competitors on select",
      back: "Back to list", sort_score: "Highest score", search_ph: "Search title, road, district…",
      compare_title: "Compare shortlisted sites (up to 4)",
    },
    th: {
      title: "เครื่องมือคัดเลือกที่ดินปั๊มน้ำมันประเทศไทย",
      subtitle: "คัดกรองแปลงที่ดินสำหรับสถานีบริการที่มีปริมาณรถสูง",
      filters: "ตัวกรอง", compare: "เปรียบเทียบ", about: "เกี่ยวกับ",
      kpi_listings: "รายการในชุดข้อมูลนี้", kpi_provinces: "จังหวัดที่ครอบคลุม",
      kpi_high: "ศักยภาพสูง", kpi_high_sub: "คะแนน 70 ขึ้นไป",
      kpi_price: "ราคาเฉลี่ยต่อไร่", kpi_price_sub: "เฉพาะรายการที่มีราคาและเนื้อที่",
      kpi_updated: "อัปเดตข้อมูลล่าสุด",
      search_filters: "ตัวกรองการค้นหา", province: "จังหวัด", district: "อำเภอ",
      area_rai: "เนื้อที่ (ไร่)", price: "ราคาเสนอขาย (บาท)", ppr: "ราคาต่อไร่ (บาท)",
      road_type: "ประเภทถนน", min_frontage: "หน้ากว้างขั้นต่ำ (ม.)", traffic: "ศักยภาพจราจร",
      min_score: "คะแนนความเหมาะสมขั้นต่ำ", max_comp: "คู่แข่งสูงสุดในรัศมี",
      source: "แหล่งข้อมูล", has_photos: "มีรูปภาพ",
      verified_only: "เฉพาะพิกัดและราคาที่ตรวจจากประกาศ",
      shortlist_only: "เฉพาะรายการที่บันทึกไว้", mapped_only: "มีพิกัดบนแผนที่",
      weights: "น้ำหนักคะแนน",
      weights_help: "ปรับน้ำหนักแล้วระบบจะปรับให้รวม 100 คะแนนย่อยไม่เปลี่ยน มีผลเฉพาะคะแนนรวม",
      reset_weights: "คืนค่าน้ำหนักตั้งต้น", reset: "ล้างตัวกรอง",
      export: "ส่งออกรายการที่บันทึก (CSV)",
      leg_high: "ศักยภาพสูง (70+)", leg_med: "ปานกลาง (45–69)", leg_low: "ต่ำ (ต่ำกว่า 45)",
      leg_unmap: "ไม่มีพิกัด", show_rings: "แสดงวงรัศมีและคู่แข่งเมื่อเลือกแปลง",
      back: "กลับไปที่รายการ", sort_score: "คะแนนสูงสุด", search_ph: "ค้นหาชื่อ ถนน อำเภอ…",
      compare_title: "เปรียบเทียบแปลงที่บันทึกไว้ (สูงสุด 4 แปลง)",
    },
  };

  const WEIGHT_LABELS = {
    traffic: "Traffic potential",
    road_access: "Road access & visibility",
    land_size: "Land size & suitability",
    competition: "Competition",
    demand: "Demand generators",
    price_value: "Land price / value",
  };

  let DATA = { meta: {}, listings: [] };
  let weights = { ...SiteScore.DEFAULT_WEIGHTS };
  let shortlist = new Set(JSON.parse(localStorage.getItem(SHORTLIST_KEY) || "[]"));
  let lang = localStorage.getItem(LANG_KEY) || "en";
  let selectedId = null;
  let map, cluster, osmLayer, satLayer, ringLayer, compLayer;
  let markersById = new Map();
  const roadTypes = new Set();

  const $ = (id) => document.getElementById(id);
  const val = (field) => (field && field.value != null ? field.value : null);
  const statusOf = (field) => (field && field.status) || (field && field.value != null ? "verified" : "unavailable");

  function applyI18n() {
    const dict = I18N[lang] || I18N.en;
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const k = el.getAttribute("data-i18n");
      if (dict[k]) el.textContent = dict[k];
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const k = el.getAttribute("data-i18n-placeholder");
      if (dict[k]) el.setAttribute("placeholder", dict[k]);
    });
    $("btn-lang").textContent = lang === "en" ? "TH" : "EN";
    document.documentElement.lang = lang;
  }

  function fmtMoney(n) {
    if (n == null || Number.isNaN(n)) return "Data not available";
    if (n >= 1e6) return "฿" + (n / 1e6).toFixed(n >= 1e7 ? 1 : 2).replace(/\.0$/, "") + "m";
    return "฿" + Math.round(n).toLocaleString("en-US");
  }
  function fmtMoneyFull(n) {
    if (n == null || Number.isNaN(n)) return "Data not available";
    return "฿" + Math.round(n).toLocaleString("en-US");
  }
  function fmtNum(n, d = 2) {
    if (n == null || Number.isNaN(n)) return "Data not available";
    return Number(n).toLocaleString("en-US", { maximumFractionDigits: d });
  }
  function coordsOf(rec) {
    const c = val(rec.coordinates);
    return c && c.lat != null ? c : null;
  }
  function scored(rec) {
    return Object.assign({ overall: rec.scores?.overall, band: rec.scores?.band, completeness: rec.scores?.completeness }, SiteScore.reweight(rec, weights));
  }

  function badge(field, extraNote) {
    const st = typeof field === "string" ? field : statusOf(field);
    const note = (typeof field === "object" && field && field.note) || extraNote || "";
    const label = st === "verified" ? "Verified" : st === "calculated" ? "Calculated" : st === "estimated" ? "Estimated" : "Data not available";
    const cls = st === "verified" ? "verified" : st === "calculated" ? "calculated" : st === "estimated" ? "estimated" : "unavailable";
    const title = note ? ` title="${escapeAttr(note)}"` : "";
    return `<span class="badge ${cls}"${title}>${label}</span>`;
  }
  function escapeAttr(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function fieldValue(field, formatter) {
    const v = val(field);
    if (v == null || v === "") return "Data not available";
    return formatter ? formatter(v) : escapeHtml(String(v));
  }

  /* ---------- filters ---------- */
  function currentFilters() {
    return {
      province: $("f-province").value,
      district: $("f-district").value,
      areaMin: num($("f-area-min").value),
      areaMax: num($("f-area-max").value),
      priceMin: num($("f-price-min").value),
      priceMax: num($("f-price-max").value),
      pprMin: num($("f-ppr-min").value),
      pprMax: num($("f-ppr-max").value),
      roads: new Set(roadTypes),
      frontage: num($("f-frontage").value),
      traffic: $("f-traffic").value,
      minScore: num($("f-score").value) || 0,
      compRadius: $("f-comp-radius").value,
      compMax: num($("f-comp-max").value),
      source: $("f-source").value,
      photos: $("f-photos").checked,
      verified: $("f-verified").checked,
      shortlistOnly: $("f-shortlist").checked,
      mapped: $("f-mapped").checked,
      q: ($("f-q").value || "").trim().toLowerCase(),
      sort: $("f-sort").value,
    };
  }
  function num(v) {
    if (v === "" || v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function matches(rec, f) {
    if (f.province && rec.province !== f.province) return false;
    if (f.district && rec.district !== f.district) return false;
    const area = val(rec.area_rai);
    if (f.areaMin != null && (area == null || area < f.areaMin)) return false;
    if (f.areaMax != null && (area == null || area > f.areaMax)) return false;
    const price = val(rec.price_thb);
    if (f.priceMin != null && (price == null || price < f.priceMin)) return false;
    if (f.priceMax != null && (price == null || price > f.priceMax)) return false;
    const ppr = val(rec.price_per_rai);
    if (f.pprMin != null && (ppr == null || ppr < f.pprMin)) return false;
    if (f.pprMax != null && (ppr == null || ppr > f.pprMax)) return false;
    if (f.roads.size) {
      const hw = val(rec.road?.highway) || "other";
      const group = ["motorway", "trunk", "primary", "secondary"].includes(hw) ? hw : "other";
      if (!f.roads.has(group)) return false;
    }
    if (f.frontage != null) {
      const fr = val(rec.frontage_m);
      if (fr == null || fr < f.frontage) return false;
    }
    if (f.traffic) {
      const band = rec.traffic_potential?.band;
      if (band !== f.traffic) return false;
    }
    const sc = scored(rec);
    if (sc.overall == null || sc.overall < f.minScore) return false;
    if (f.compMax != null) {
      const key = "km" + f.compRadius;
      const c = rec.competitors?.[key]?.count;
      if (c == null || c > f.compMax) return false;
    }
    if (f.source && rec.source !== f.source && !(rec.sources || []).includes(f.source)) return false;
    if (f.photos && !(rec.photos && rec.photos.length)) return false;
    if (f.verified) {
      if (statusOf(rec.coordinates) !== "verified") return false;
      if (statusOf(rec.price_thb) !== "verified") return false;
    }
    if (f.shortlistOnly && !shortlist.has(rec.id)) return false;
    if (f.mapped && !coordsOf(rec)) return false;
    if (f.q) {
      const blob = [rec.title, rec.address_text, rec.province, rec.province_th, rec.district, rec.subdistrict, rec.road?.name?.value, rec.description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!blob.includes(f.q)) return false;
    }
    return true;
  }

  function filtered() {
    const f = currentFilters();
    let rows = DATA.listings.filter((r) => matches(r, f));
    const key = f.sort;
    rows.sort((a, b) => {
      const sa = scored(a), sb = scored(b);
      if (key === "ppr") return (val(b.price_per_rai) || 0) - (val(a.price_per_rai) || 0);
      if (key === "price") return (val(b.price_thb) || 0) - (val(a.price_thb) || 0);
      if (key === "area") return (val(b.area_rai) || 0) - (val(a.area_rai) || 0);
      if (key === "comp") return (a.competitors?.km3?.count ?? 99) - (b.competitors?.km3?.count ?? 99);
      return (sb.overall || 0) - (sa.overall || 0);
    });
    return rows;
  }

  /* ---------- map ---------- */
  function initMap() {
    map = L.map("map", { zoomControl: true, attributionControl: true }).setView([13.5, 101.2], 6);
    osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    });
    satLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19,
      attribution: "Tiles © Esri",
    });
    osmLayer.addTo(map);
    cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 48, spiderfyOnMaxZoom: true });
    map.addLayer(cluster);
    ringLayer = L.layerGroup().addTo(map);
    compLayer = L.layerGroup().addTo(map);

    document.querySelectorAll(".basemap-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".basemap-toggle button").forEach((b) => b.classList.remove("on"));
        btn.classList.add("on");
        if (btn.dataset.base === "sat") {
          map.removeLayer(osmLayer);
          satLayer.addTo(map);
        } else {
          map.removeLayer(satLayer);
          osmLayer.addTo(map);
        }
      });
    });
  }

  function colorFor(band) {
    return band === "high" ? "#3dcc7a" : band === "medium" ? "#e0b33a" : band === "low" ? "#e15b4d" : "#7a8792";
  }

  function markerIcon(rec) {
    const sc = scored(rec);
    const color = colorFor(sc.band);
    const html = `<div class="score-marker" style="background:${color}"><span>${sc.overall != null ? Math.round(sc.overall) : "–"}</span></div>`;
    return L.divIcon({ className: "", html, iconSize: [28, 28], iconAnchor: [14, 26], popupAnchor: [0, -24] });
  }

  function refreshMap(rows) {
    cluster.clearLayers();
    markersById.clear();
    const bounds = [];
    rows.forEach((rec) => {
      const c = coordsOf(rec);
      if (!c) return;
      const m = L.marker([c.lat, c.lon], { icon: markerIcon(rec), title: rec.title });
      m.on("click", () => selectListing(rec.id, { fromMap: true }));
      cluster.addLayer(m);
      markersById.set(rec.id, m);
      bounds.push([c.lat, c.lon]);
    });
    if (bounds.length && !selectedId) {
      try { map.fitBounds(bounds, { padding: [30, 30], maxZoom: 10 }); } catch (e) {}
    }
  }

  function drawSelection(rec) {
    ringLayer.clearLayers();
    compLayer.clearLayers();
    const c = coordsOf(rec);
    if (!c || !$("f-rings").checked) return;
    const colors = { 1000: "#e15b4d", 3000: "#e0b33a", 5000: "#5b9fff", 10000: "#9aa8b5" };
    [1000, 3000, 5000, 10000].forEach((r) => {
      L.circle([c.lat, c.lon], { radius: r, color: colors[r], weight: 1, fillOpacity: 0.04 }).addTo(ringLayer);
    });
    const stations = rec.competitors?.km10?.stations || [];
    stations.forEach((s) => {
      if (s.distance_km == null) return;
      // We don't have competitor coordinates in the slim payload — skip pins if absent.
      if (s.lat == null) return;
      L.circleMarker([s.lat, s.lon], { radius: 5, color: "#333", fillColor: "#f5f0e6", fillOpacity: 1, weight: 1 })
        .bindTooltip((s.brand || s.name || "Station") + " · " + s.distance_km + " km")
        .addTo(compLayer);
    });
  }

  /* ---------- list & detail ---------- */
  function renderList(rows) {
    const el = $("list");
    $("list-count").textContent = rows.length.toLocaleString() + " shown";
    if (!rows.length) {
      el.innerHTML = `<div class="empty">No listings match these filters.</div>`;
      return;
    }
    const html = rows.slice(0, 400).map((rec) => {
      const sc = scored(rec);
      const thumb = rec.photos && rec.photos[0] ? `style="background-image:url('${escapeAttr(rec.photos[0])}')"` : "";
      const loc = [rec.subdistrict, rec.district, rec.province_th || rec.province].filter(Boolean).join(", ");
      const facts = [
        rec.area_display || (val(rec.area_rai) != null ? fmtNum(val(rec.area_rai), 2) + " rai" : null),
        val(rec.price_thb) != null ? fmtMoney(val(rec.price_thb)) : null,
      ].filter(Boolean).join(" · ");
      return `<article class="card ${rec.id === selectedId ? "active" : ""}" data-id="${escapeAttr(rec.id)}">
        <div class="thumb" ${thumb}></div>
        <div class="meta">
          <h3>${escapeHtml(rec.title)}</h3>
          <div class="loc">${escapeHtml(loc || rec.address_text || "")}</div>
          <div class="facts">${escapeHtml(facts)}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
          <div class="score-badge ${sc.band || "low"}">${sc.overall != null ? Math.round(sc.overall) : "–"}</div>
          <button type="button" class="star ${shortlist.has(rec.id) ? "on" : ""}" data-star="${escapeAttr(rec.id)}" aria-label="Shortlist">★</button>
        </div>
      </article>`;
    }).join("");
    el.innerHTML = html + (rows.length > 400 ? `<div class="empty">Showing the first 400 of ${rows.length.toLocaleString()}. Narrow the filters to see the rest in the list — all matching pins stay on the map.</div>` : "");
  }

  function normalizeField(field) {
    if (field == null) return { value: null, status: "unavailable" };
    if (typeof field !== "object") return { value: field, status: "verified" };
    if ("value" in field) return field;
    // Objects such as traffic_potential use score/band + status, not "value".
    const value = field.score != null || field.band
      ? [field.band, field.score != null ? Number(field.score).toFixed(1) : null].filter(Boolean).join(" · ")
      : null;
    return { value, status: field.status || "unavailable", note: field.note };
  }
  function kv(label, field, formatter) {
    const v = normalizeField(field);
    return `<div class="item"><div class="k">${escapeHtml(label)} ${badge(v)}</div><div class="v">${fieldValue(v, formatter)}</div></div>`;
  }

  function renderDetail(rec) {
    const sc = scored(rec);
    const c = coordsOf(rec);
    const photos = rec.photos || [];
    const loc = [rec.subdistrict, rec.district, rec.province, rec.province_th].filter(Boolean).join(" · ");
    const factors = rec.scores?.factors || {};
    const factorHtml = Object.keys(SiteScore.DEFAULT_WEIGHTS).map((k) => {
      const f = factors[k] || {};
      const label = f.label || WEIGHT_LABELS[k];
      const score = f.score;
      const band = SiteScore.band(score);
      const w = sc.weights ? sc.weights[k] : f.weight;
      return `<div class="factor" title="${escapeAttr(f.note || "")}">
        <div class="row"><span>${escapeHtml(label)} ${badge(f.status || "unavailable", f.note)}</span><span>${score != null ? fmtNum(score, 1) : "–"} · ${fmtNum(w, 0)}%</span></div>
        <div class="bar ${band || ""}"><span style="width:${score != null ? score : 0}%"></span></div>
      </div>`;
    }).join("");

    const allStations = rec.competitors?.km10?.stations || rec.competitors?.km5?.stations || rec.competitors?.km3?.stations || rec.competitors?.km1?.stations || [];
    const compRows = ["1", "3", "5", "10"].map((k) => {
      const b = rec.competitors?.["km" + k];
      const count = b && b.count != null ? b.count : "Data not available";
      const names = allStations.filter((s) => (s.distance_km ?? 99) <= Number(k)).slice(0, 6)
        .map((s) => `${s.brand || s.name || "Station"} (${s.distance_km} km)`).join("; ");
      return `<tr><td>${k} km</td><td>${count}</td><td>${escapeHtml(names || "—")}</td></tr>`;
    }).join("");

    const gen = rec.generators || {};
    const genLines = [
      ["Industrial (10 km)", gen.industrial_10km],
      ["Malls (5 km)", gen.malls_5km],
      ["Supermarkets (5 km)", gen.supermarkets_5km],
      ["Convenience (3 km)", gen.convenience_3km],
      ["Restaurants (3 km)", gen.restaurants_3km],
      ["EV chargers (5 km)", gen.ev_chargers_5km],
      ["Schools (5 km)", gen.schools_5km],
      ["Hospitals (5 km)", gen.hospitals_5km],
      ["Attractions (10 km)", gen.attractions_10km],
      ["Hotels (5 km)", gen.hotels_5km],
      ["Towns (10 km)", gen.towns_10km],
    ].map(([label, node]) => {
      if (!node) return `<div class="item"><div class="k">${label} ${badge("unavailable")}</div><div class="v">Data not available</div></div>`;
      const names = (node.items || []).slice(0, 4).map((x) => (x.name || "") + (x.distance_km != null ? ` (${x.distance_km} km)` : "")).join("; ");
      const count = node.count != null ? node.count : (node.items || []).length;
      return `<div class="item"><div class="k">${label} ${badge(gen)}</div><div class="v">${count}${names ? " — " + escapeHtml(names) : ""}</div></div>`;
    }).join("");

    const gps = c
      ? `${c.lat.toFixed(6)}, ${c.lon.toFixed(6)}`
      : "Data not available";
    const gallery = photos.length
      ? `<div class="gallery" id="gallery">
          <img id="gallery-img" src="${escapeAttr(photos[0])}" alt="" />
          ${photos.length > 1 ? `<button class="nav prev" type="button" data-dir="-1">‹</button><button class="nav next" type="button" data-dir="1">›</button>` : ""}
        </div>`
      : `<div class="gallery"><div class="empty">No photos in this listing.</div></div>`;

    const adv = (rec.advantages || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("") || "<li>No automatically generated advantages from the available facts.</li>";
    const risks = (rec.risks || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("");

    $("detail").innerHTML = `
      ${gallery}
      <div class="detail-body">
        <div class="detail-head">
          <h2>${escapeHtml(rec.title)}</h2>
          <div class="score-badge ${sc.band || "low"}">${sc.overall != null ? fmtNum(sc.overall, 1) : "–"}</div>
        </div>
        <div class="detail-loc">${escapeHtml(loc || rec.address_text || "")} · ${escapeHtml(rec.source || "")}</div>
        <div class="completeness"><span>Data completeness</span><div class="track"><span style="width:${Math.round((sc.completeness || 0) * 100)}%"></span></div><span>${Math.round((sc.completeness || 0) * 100)}%</span></div>
        <div class="actions">
          <button type="button" class="text-btn ${shortlist.has(rec.id) ? "primary" : ""}" id="detail-star">${shortlist.has(rec.id) ? "★ In shortlist" : "☆ Add to shortlist"}</button>
          <a class="text-btn primary" href="${escapeAttr(rec.source_url)}" target="_blank" rel="noopener">Open original listing</a>
          ${c ? `<a class="text-btn" href="https://www.google.com/maps?q=${c.lat},${c.lon}" target="_blank" rel="noopener">Google Maps</a>` : ""}
        </div>
        <div class="kv">
          ${kv("Asking price", rec.price_thb, fmtMoneyFull)}
          ${kv("Price per rai", rec.price_per_rai, fmtMoneyFull)}
          ${kv("Land area", rec.area_rai, (v) => rec.area_display || fmtNum(v, 2) + " rai")}
          ${kv("Road frontage", rec.frontage_m, (v) => fmtNum(v, 1) + " m")}
          ${kv("Road / highway", rec.road?.name)}
          ${kv("Road type (OSM)", rec.road?.highway)}
          ${kv("Lanes (OSM)", rec.road?.lanes)}
          ${kv("Distance to major road", rec.road?.distance_m, (v) => fmtNum(v, 0) + " m")}
          ${kv("Traffic potential (proxy)", rec.traffic_potential, (v) => (rec.traffic_potential?.band || "") + (v != null ? " · " + fmtNum(v, 1) : ""))}
          ${kv("Official traffic count", rec.official_traffic_volume)}
          <div class="item span"><div class="k">GPS coordinates ${badge(rec.coordinates)}</div><div class="v">${escapeHtml(gps)}${rec.coordinates?.precision ? " · " + escapeHtml(rec.coordinates.precision.replaceAll("_", " ")) : ""}</div></div>
          <div class="item span"><div class="k">Zoning / city plan ${badge(rec.zoning)}</div><div class="v">Data not available. Check the official DPT viewer: <a href="${escapeAttr((rec.zoning && rec.zoning.viewer_url) || "https://oneplan.dpt.go.th/")}" target="_blank" rel="noopener">oneplan.dpt.go.th</a></div></div>
        </div>
        <div class="side-title">Score breakdown</div>
        <div class="factors">${factorHtml}</div>
        <div class="side-title">Nearby competitors (OpenStreetMap)</div>
        <p class="muted">${escapeHtml(rec.competitors?.note || "Estimated from OSM amenity=fuel.")}</p>
        <table class="comp-table"><thead><tr><th>Radius</th><th>Count</th><th>Nearest named stations</th></tr></thead><tbody>${compRows}</tbody></table>
        <div class="side-title">Nearby traffic generators (OpenStreetMap)</div>
        <div class="kv">${genLines}</div>
        <div class="callout"><strong>Key advantages</strong><ul>${adv}</ul></div>
        <div class="callout risk"><strong>Key risks</strong><ul>${risks}</ul></div>
        ${(rec.also_listed_at || []).length ? `<p class="muted">Also listed at: ${(rec.also_listed_at || []).map((u) => `<a href="${escapeAttr(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a>`).join("<br>")}</p>` : ""}
      </div>`;

    $("detail").classList.add("open");
    $("list").classList.add("hidden");
    $("btn-back").style.display = "inline-flex";

    if (photos.length > 1) {
      let i = 0;
      $("detail").querySelectorAll(".nav").forEach((btn) => {
        btn.addEventListener("click", () => {
          i = (i + Number(btn.dataset.dir) + photos.length) % photos.length;
          $("gallery-img").src = photos[i];
        });
      });
    }
    $("detail-star").addEventListener("click", () => {
      toggleShort(rec.id);
      renderDetail(rec);
      apply();
    });
    const img = $("gallery-img");
    if (img) img.addEventListener("error", () => { img.replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: "Photo could not be loaded from the listing host." })); });
  }

  function selectListing(id, opts = {}) {
    selectedId = id;
    const rec = DATA.listings.find((r) => r.id === id);
    if (!rec) return;
    renderDetail(rec);
    drawSelection(rec);
    const c = coordsOf(rec);
    if (c && !opts.fromMap) {
      map.setView([c.lat, c.lon], Math.max(map.getZoom(), 12), { animate: true });
    }
    document.querySelectorAll(".card").forEach((el) => el.classList.toggle("active", el.dataset.id === id));
  }

  function showList() {
    selectedId = null;
    $("detail").classList.remove("open");
    $("list").classList.remove("hidden");
    $("btn-back").style.display = "none";
    ringLayer && ringLayer.clearLayers();
    compLayer && compLayer.clearLayers();
  }

  function toggleShort(id) {
    if (shortlist.has(id)) shortlist.delete(id);
    else shortlist.add(id);
    localStorage.setItem(SHORTLIST_KEY, JSON.stringify([...shortlist]));
  }

  /* ---------- compare & export ---------- */
  function openCompare() {
    const recs = [...shortlist].map((id) => DATA.listings.find((r) => r.id === id)).filter(Boolean).slice(0, 4);
    recs.sort((a, b) => (scored(b).overall || 0) - (scored(a).overall || 0));
    if (!recs.length) {
      $("compare-body").innerHTML = `<p class="empty">Star up to four sites, then compare them side by side.</p>`;
      $("compare-modal").classList.add("open");
      return;
    }
    const rows = [
      ["Suitability score", (r) => { const s = scored(r); return `${s.overall} (${s.band})`; }],
      ["Data completeness", (r) => Math.round((scored(r).completeness || 0) * 100) + "%"],
      ["Province / district", (r) => [r.province_th || r.province, r.district].filter(Boolean).join(", ")],
      ["Asking price", (r) => fmtMoneyFull(val(r.price_thb))],
      ["Price per rai", (r) => fmtMoneyFull(val(r.price_per_rai))],
      ["Land area", (r) => r.area_display || fmtNum(val(r.area_rai), 2) + " rai"],
      ["Frontage", (r) => val(r.frontage_m) != null ? fmtNum(val(r.frontage_m), 1) + " m" : "Data not available"],
      ["Road", (r) => val(r.road?.name) || "Data not available"],
      ["Road type", (r) => val(r.road?.highway) || "Data not available"],
      ["Traffic proxy", (r) => r.traffic_potential?.band || "Data not available"],
      ["Competitors 1 / 3 / 5 / 10 km", (r) => ["km1","km3","km5","km10"].map((k) => r.competitors?.[k]?.count ?? "–").join(" / ")],
      ["Coordinates", (r) => { const c = coordsOf(r); return c ? `${c.lat.toFixed(5)}, ${c.lon.toFixed(5)} (${statusOf(r.coordinates)})` : "Data not available"; }],
      ["Source", (r) => r.source],
      ["Listing", (r) => `<a href="${escapeAttr(r.source_url)}" target="_blank" rel="noopener">Open</a>`],
    ];
    const head = `<tr><th></th>${recs.map((r) => `<th>${escapeHtml(r.title)}<div class="score-badge ${scored(r).band}" style="margin-top:6px">${scored(r).overall}</div></th>`).join("")}</tr>`;
    const body = rows.map(([label, fn]) => `<tr><td class="row-label">${escapeHtml(label)}</td>${recs.map((r) => `<td>${fn(r)}</td>`).join("")}</tr>`).join("");
    $("compare-body").innerHTML = `<div style="overflow:auto"><table class="compare-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
    $("compare-modal").classList.add("open");
  }

  function exportCsv() {
    const recs = [...shortlist].map((id) => DATA.listings.find((r) => r.id === id)).filter(Boolean);
    const source = recs.length ? recs : filtered();
    const cols = ["id","title","province","district","subdistrict","score","band","completeness","price_thb","price_per_rai","area_rai","frontage_m","road","road_type","traffic_band","comp_1km","comp_3km","comp_5km","comp_10km","lat","lon","coord_status","source","source_url"];
    const lines = [cols.join(",")];
    source.forEach((r) => {
      const s = scored(r);
      const c = coordsOf(r);
      const row = [
        r.id, r.title, r.province, r.district, r.subdistrict, s.overall, s.band, s.completeness,
        val(r.price_thb), val(r.price_per_rai), val(r.area_rai), val(r.frontage_m),
        val(r.road?.name), val(r.road?.highway), r.traffic_potential?.band,
        r.competitors?.km1?.count, r.competitors?.km3?.count, r.competitors?.km5?.count, r.competitors?.km10?.count,
        c ? c.lat : "", c ? c.lon : "", statusOf(r.coordinates), r.source, r.source_url,
      ].map((x) => `"${String(x ?? "").replace(/"/g, '""')}"`);
      lines.push(row.join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "gas-station-sites-shortlist.csv";
    a.click();
  }

  /* ---------- populate & apply ---------- */
  function populateFilters() {
    const provinces = [...new Set(DATA.listings.map((r) => r.province).filter(Boolean))].sort();
    $("f-province").innerHTML = `<option value="">All</option>` + provinces.map((p) => {
      const th = DATA.listings.find((r) => r.province === p)?.province_th;
      return `<option value="${escapeAttr(p)}">${escapeHtml(th ? p + " — " + th : p)}</option>`;
    }).join("");
    const sources = [...new Set(DATA.listings.map((r) => r.source).filter(Boolean))].sort();
    $("f-source").innerHTML = `<option value="">All</option>` + sources.map((s) => `<option>${escapeHtml(s)}</option>`).join("");
    fillDistricts();
  }
  function fillDistricts() {
    const prov = $("f-province").value;
    const dists = [...new Set(DATA.listings.filter((r) => !prov || r.province === prov).map((r) => r.district).filter(Boolean))].sort();
    const prev = $("f-district").value;
    $("f-district").innerHTML = `<option value="">All</option>` + dists.map((d) => `<option>${escapeHtml(d)}</option>`).join("");
    if (dists.includes(prev)) $("f-district").value = prev;
  }

  function renderWeights() {
    $("weight-sliders").innerHTML = Object.keys(SiteScore.DEFAULT_WEIGHTS).map((k) => `
      <div class="weight">
        <div class="top"><span>${escapeHtml(WEIGHT_LABELS[k])}</span><span id="w-out-${k}">${weights[k]}%</span></div>
        <input type="range" min="0" max="60" value="${weights[k]}" data-w="${k}" />
      </div>`).join("");
    $("weight-sliders").querySelectorAll("input").forEach((inp) => {
      inp.addEventListener("input", () => {
        weights[inp.dataset.w] = Number(inp.value);
        $("w-out-" + inp.dataset.w).textContent = inp.value + "%";
        apply();
        if (selectedId) {
          const rec = DATA.listings.find((r) => r.id === selectedId);
          if (rec) renderDetail(rec);
        }
      });
    });
  }

  function apply() {
    const rows = filtered();
    renderList(rows);
    refreshMap(rows);
    if (selectedId && !rows.some((r) => r.id === selectedId)) showList();
  }

  function kpis() {
    const meta = DATA.meta || {};
    $("kpi-count").textContent = (meta.listings_count ?? DATA.listings.length).toLocaleString();
    const src = meta.sources || {};
    $("kpi-sources").textContent = Object.entries(src).map(([k, v]) => `${k} ${v}`).join(" · ");
    $("kpi-provinces").textContent = meta.province_count ?? "–";
    $("kpi-mapped").textContent = (meta.with_coordinates != null ? meta.with_coordinates.toLocaleString() + " with coordinates" : "");
    $("kpi-high").textContent = (meta.high_potential_count ?? "–").toLocaleString?.() || meta.high_potential_count;
    $("kpi-price").textContent = meta.average_price_per_rai != null ? fmtMoney(meta.average_price_per_rai) : "–";
    const ts = meta.generated_at;
    if (ts) {
      const d = new Date(ts);
      $("kpi-updated").textContent = isNaN(d) ? ts : d.toLocaleString("en-GB", { timeZone: "Asia/Bangkok", dateStyle: "medium", timeStyle: "short" });
    }
    if (meta.disclaimer) $("disclaimer").textContent = meta.disclaimer;
  }

  function bind() {
    ["f-province","f-district","f-area-min","f-area-max","f-price-min","f-price-max","f-ppr-min","f-ppr-max","f-frontage","f-traffic","f-comp-radius","f-comp-max","f-source","f-photos","f-verified","f-shortlist","f-mapped","f-q","f-sort","f-rings"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("change", () => { if (id === "f-province") fillDistricts(); apply(); });
      el.addEventListener("input", () => {
        if (id === "f-score") $("f-score-out").textContent = el.value;
        if (id === "f-q") apply();
      });
    });
    $("f-score").addEventListener("change", apply);
    $("f-score").addEventListener("input", () => { $("f-score-out").textContent = $("f-score").value; });
    $("f-road").addEventListener("click", (e) => {
      const chip = e.target.closest("[data-road]");
      if (!chip) return;
      const r = chip.dataset.road;
      if (roadTypes.has(r)) roadTypes.delete(r); else roadTypes.add(r);
      chip.classList.toggle("on", roadTypes.has(r));
      apply();
    });
    $("list").addEventListener("click", (e) => {
      const star = e.target.closest("[data-star]");
      if (star) { e.stopPropagation(); toggleShort(star.dataset.star); apply(); return; }
      const card = e.target.closest(".card");
      if (card) selectListing(card.dataset.id);
    });
    $("btn-back").addEventListener("click", showList);
    $("btn-reset").addEventListener("click", () => {
      ["f-province","f-district","f-area-min","f-area-max","f-price-min","f-price-max","f-ppr-min","f-ppr-max","f-frontage","f-traffic","f-comp-max","f-source","f-q"].forEach((id) => { $(id).value = ""; });
      $("f-comp-radius").value = "3";
      $("f-score").value = 0; $("f-score-out").textContent = "0";
      $("f-photos").checked = $("f-verified").checked = $("f-shortlist").checked = $("f-mapped").checked = false;
      roadTypes.clear();
      document.querySelectorAll("#f-road .chip").forEach((c) => c.classList.remove("on"));
      fillDistricts();
      apply();
    });
    $("btn-reset-weights").addEventListener("click", () => { weights = { ...SiteScore.DEFAULT_WEIGHTS }; renderWeights(); apply(); if (selectedId) renderDetail(DATA.listings.find((r) => r.id === selectedId)); });
    $("btn-export").addEventListener("click", exportCsv);
    $("btn-compare").addEventListener("click", openCompare);
    $("btn-close-compare").addEventListener("click", () => $("compare-modal").classList.remove("open"));
    $("compare-modal").addEventListener("click", (e) => { if (e.target.id === "compare-modal") $("compare-modal").classList.remove("open"); });
    $("btn-filters").addEventListener("click", () => $("sidebar").classList.toggle("open"));
    $("btn-lang").addEventListener("click", () => { lang = lang === "en" ? "th" : "en"; localStorage.setItem(LANG_KEY, lang); applyI18n(); });
    $("btn-theme").addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem(THEME_KEY, next);
    });
    const savedTheme = localStorage.getItem(THEME_KEY);
    if (savedTheme) document.documentElement.setAttribute("data-theme", savedTheme);
  }

  async function boot() {
    applyI18n();
    initMap();
    bind();
    renderWeights();
    $("list").innerHTML = `<div class="empty">Loading listings…</div>`;
    try {
      const res = await fetch(DATA_URL);
      if (!res.ok) throw new Error("HTTP " + res.status);
      DATA = await res.json();
    } catch (err) {
      $("list").innerHTML = `<div class="empty">Could not load data/listings.json (${escapeHtml(err.message)}). If you are opening this file locally, serve the docs folder over HTTP.</div>`;
      return;
    }
    kpis();
    populateFilters();
    apply();
    setTimeout(() => { try { map.invalidateSize(); } catch (e) {} }, 250);
    window.addEventListener("resize", () => { try { map.invalidateSize(); } catch (e) {} });
  }

  boot();
})();
