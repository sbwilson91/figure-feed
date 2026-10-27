// Figure Feed: reads data/feed.json, shows one card per paper, remembers what the
// reader kept or passed in this browser only.
(function () {
  "use strict";

  const $ = (s, el) => (el || document).querySelector(s);
  const main = $("#main");

  // ── Per-browser memory ──────────────────────────────────────────────────
  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem("ff:" + key); return v ? JSON.parse(v) : fallback; }
      catch (e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem("ff:" + key, JSON.stringify(value)); } catch (e) { /* private mode */ }
    },
  };
  // Links and images go into href and src, so only https URLs are used; anything else
  // (javascript:, data:) is dropped. A paper from storage or a backup file is rebuilt
  // from the fields the page reads, each of the type it expects.
  const safeUrl = (u) => {
    try { const url = new URL(String(u)); return url.protocol === "https:" && url.hostname ? url.href : null; }
    catch (e) { return null; }
  };
  const doiUrl = (doi) => "https://doi.org/" + encodeURI(doi);
  const str = (v) => (typeof v === "string" ? v : null);
  const isoDate = (v) => (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : null);
  function cleanPaper(p) {
    if (!p || typeof p !== "object" || !str(p.doi) || !str(p.title)) return null;
    const figures = (Array.isArray(p.figures) ? p.figures : [])
      .filter((f) => f && safeUrl(f.url))
      .map((f) => ({ url: safeUrl(f.url), label: str(f.label) || "Figure", caption: str(f.caption) }));
    return {
      doi: p.doi, journal: str(p.journal) || "", title: p.title,
      link: safeUrl(p.link) || doiUrl(p.doi), published: isoDate(p.published), week: isoDate(p.week),
      summary: str(p.summary), figures,
      figure_kind: !figures.length ? "none" : p.figure_kind === "preview" ? "preview" : "full",
      licence: str(p.licence), figures_added: isoDate(p.figures_added),
    };
  }
  function cleanKept(obj) {
    const out = {};
    if (!obj || typeof obj !== "object") return out;
    for (const [doi, p] of Object.entries(obj)) {
      const c = cleanPaper(p);
      if (c && c.doi === doi) out[doi] = c;
    }
    return out;
  }

  const kept = cleanKept(store.get("kept", {}));   // doi -> paper (so Saved works for archived weeks)
  const passed = {};                               // doi -> date passed
  for (const [doi, d] of Object.entries(store.get("passed", {}) || {})) if (isoDate(d)) passed[doi] = d;
  let tab = store.get("tab", "week");
  let journals = new Set(store.get("journals", []));
  let figsOnly = store.get("figsOnly", false);

  let feed = null;
  let colours = {};
  let shorts = {};
  let openWeek = null;
  // Where the reader was: the paper at the top of the screen, so the place survives a
  // feed update adding or dropping cards above it. The pixel offset is the fallback.
  let place = store.get("place", null);
  if (place && place.tab === tab && tab === "earlier") openWeek = place.week || null;
  const weekCache = {};

  // ── Helpers ─────────────────────────────────────────────────────────────
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => iso ? new Date(iso + "T00:00:00Z").toLocaleDateString(undefined,
    { day: "numeric", month: "short", timeZone: "UTC" }) : "";
  const weekLabel = (iso) => "Week of " + new Date(iso + "T00:00:00Z").toLocaleDateString(undefined,
    { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

  function visible(p) {
    if (journals.size && !journals.has(p.journal)) return false;
    if (figsOnly && p.figure_kind === "none") return false;
    return true;
  }

  // ── Cards ───────────────────────────────────────────────────────────────
  function figuresHtml(p) {
    const figures = (p.figures || []).filter((f) => safeUrl(f.url));
    if (!figures.length) {
      return `<div class="band" style="background:${esc(colours[p.journal] || "#334155")}"></div>`;
    }
    const n = figures.length;
    const slides = figures.map((f, i) => {
      const tag = p.figure_kind === "preview" ? "Preview"
        : `${esc(f.label)}${n > 1 ? ` · ${i + 1}/${n}` : ""}${f.caption ? " — " + esc(f.caption) : ""}`;
      return `<figure class="fig" style="margin:0">
        <img src="${esc(safeUrl(f.url))}" alt="${esc(f.label + (f.caption ? ": " + f.caption : ""))}"
             loading="lazy" decoding="async" referrerpolicy="no-referrer">
        <figcaption class="fig-tag">${tag}</figcaption></figure>`;
    }).join("");
    return `<div class="figs">${slides}</div>`;
  }

  function cardHtml(p) {
    const isKept = !!kept[p.doi];
    const link = esc(safeUrl(p.link) || doiUrl(p.doi));
    const cls = p.figure_kind === "none" ? "text-only" : p.figure_kind === "preview" ? "preview" : "";
    const credit = p.figure_kind === "full" && p.licence
      ? `<div class="credit">Figures: <a href="${link}" target="_blank" rel="noopener">${esc(p.journal)}</a>, ${esc(p.licence)}</div>`
      : "";
    const fresh = p.figures_added && tab === "figs" ? `<span class="new">figures added ${fmtDate(p.figures_added)}</span> ·` : "";
    return `<article class="card ${cls}" data-doi="${esc(p.doi)}">
      ${figuresHtml(p)}
      <div class="body">
        <div class="meta"><span class="dot" style="background:${esc(colours[p.journal] || "#334155")}"></span>
          ${fresh}<span>${esc(p.journal)}</span>${p.published ? `<span>· ${fmtDate(p.published)}</span>` : ""}</div>
        <h2 class="title"><a href="${link}" target="_blank" rel="noopener">${esc(p.title)}</a></h2>
        ${p.summary ? `<p class="summary">${esc(p.summary)}</p>` : ""}
        ${credit}
      </div>
      <div class="acts">
        <button class="pass" data-act="pass">Ignore</button>
        <a class="open" href="${link}" target="_blank" rel="noopener">Open</a>
        <button class="keep" data-act="keep" aria-pressed="${isKept}">${isKept ? "Stored" : "Store"}</button>
      </div>
    </article>`;
  }

  function list(papers, { group = true, hidePassed = true, emptyText = "Nothing here yet." } = {}) {
    const shown = papers.filter((p) => visible(p) && !(hidePassed && passed[p.doi]));
    if (!shown.length) return `<p class="empty">${esc(emptyText)}</p>`;
    let html = "", week = null;
    for (const p of shown) {
      if (group && p.week !== week) { week = p.week; html += `<h3 class="week-head">${weekLabel(week)}</h3>`; }
      html += cardHtml(p);
    }
    return html;
  }

  // ── Views ───────────────────────────────────────────────────────────────
  function render() {
    document.querySelectorAll(".tabs button").forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    const savedTab = $('[data-tab="saved"]');
    const nKept = Object.keys(kept).length;
    savedTab.innerHTML = "Saved" + (nKept ? `<span class="n">${nKept}</span>` : "");
    if (!feed) return;

    if (tab === "week") {
      const latest = feed.weeks[0];
      const papers = feed.papers.filter((p) => p.week === latest);
      main.innerHTML = list(papers, { emptyText: "You've been through this week. New papers arrive daily." });
    } else if (tab === "figs") {
      const papers = feed.papers.filter((p) => p.figures_added)
        .sort((a, b) => (b.figures_added || "").localeCompare(a.figures_added || ""));
      main.innerHTML = `<p class="empty" style="padding:4px 0 10px;text-align:left">Earlier papers whose open-access figures have just come through PubMed Central.</p>`
        + list(papers, { group: false, hidePassed: false, emptyText: "No new figures yet. They arrive two to five weeks after a paper does." });
    } else if (tab === "saved") {
      const papers = Object.values(kept).sort((a, b) => (b.week || "").localeCompare(a.week || ""));
      main.innerHTML = `<div class="backup"><span>Saved papers live in this app only.</span>`
        + `<button data-backup>Back up</button><button data-restore>Restore</button></div>`
        + list(papers, { hidePassed: false, emptyText: "Store a paper (or swipe it right) and it stays here." });
    } else if (tab === "earlier") {
      renderEarlier();
    }
  }

  async function renderEarlier() {
    if (openWeek) {
      let papers = feed.papers.filter((p) => p.week === openWeek);
      if (feed.archived.includes(openWeek)) {
        if (!weekCache[openWeek]) {
          main.innerHTML = `<p class="empty">Loading…</p>`;
          try { weekCache[openWeek] = await (await fetch(`data/weeks/${openWeek}.json`)).json(); }
          catch (e) { weekCache[openWeek] = []; }
        }
        papers = weekCache[openWeek];
        setTimeout(restorePlace);
      }
      main.innerHTML = `<button class="back" data-back>← All weeks</button>`
        + `<h3 class="week-head">${weekLabel(openWeek)}</h3>` + list(papers, { group: false, hidePassed: false });
      return;
    }
    const counts = {};
    feed.papers.forEach((p) => { counts[p.week] = (counts[p.week] || 0) + 1; });
    const items = feed.weeks.slice(1).map((w) =>
      `<li><button data-week="${esc(w)}">${weekLabel(w)}<span class="n">${counts[w] ? counts[w] + " papers" : "archive"}</span></button></li>`).join("");
    main.innerHTML = items ? `<ul class="weeks">${items}</ul>` : `<p class="empty">Earlier weeks appear here as the feed grows.</p>`;
  }

  function renderChips() {
    const chips = $("#chips");
    chips.innerHTML = `<button class="chip" data-j="" aria-pressed="${journals.size === 0}">All</button>` +
      feed.journals.map((j) => `<button class="chip" data-j="${esc(j.name)}" aria-pressed="${journals.has(j.name)}">
        <span class="dot" style="background:${esc(j.colour)}"></span>${esc(j.short)}</button>`).join("");
    $("#figsOnly").checked = figsOnly;
  }

  // ── Store / Ignore / Undo ────────────────────────────────────────────────
  let undo = null, toastTimer = null;
  function toast(msg, undoFn) {
    undo = undoFn;
    $("#toastMsg").textContent = msg;
    $("#undo").hidden = !undoFn;
    $("#toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("#toast").hidden = true; undo = null; }, 5000);
  }

  function findPaper(doi) {
    return feed.papers.find((p) => p.doi === doi) || kept[doi]
      || Object.values(weekCache).flat().find((p) => p.doi === doi);
  }

  function act(card, what) {
    const doi = card.dataset.doi;
    const p = findPaper(doi);
    if (!p) return;
    if (what === "keep" && kept[doi] && tab !== "week") {     // un-keep in place
      delete kept[doi]; store.set("kept", kept);
      render(); toast("Removed from Saved", () => { kept[doi] = p; store.set("kept", kept); render(); });
      return;
    }
    const before = { k: kept[doi], s: passed[doi] };
    if (what === "keep") { kept[doi] = cleanPaper(p) || p; delete passed[doi]; }
    else { passed[doi] = new Date().toISOString().slice(0, 10); delete kept[doi]; }
    store.set("kept", kept); store.set("passed", passed);
    const leaves = tab === "week";
    const finish = () => render();
    if (leaves) { card.classList.add("gone", what); setTimeout(finish, 240); } else finish();
    toast(what === "keep" ? "Stored" : "Ignored", () => {
      if (before.k) kept[doi] = before.k; else delete kept[doi];
      if (before.s) passed[doi] = before.s; else delete passed[doi];
      store.set("kept", kept); store.set("passed", passed); render();
    });
  }

  // ── Reading place ───────────────────────────────────────────────────────
  const headerH = () => $(".top").getBoundingClientRect().height;
  function savePlace() {
    if (!feed || place) return;                       // not until the last place is applied
    const top = headerH();
    const card = [...main.querySelectorAll(".card")].find((c) => c.getBoundingClientRect().bottom > top + 1);
    store.set("place", { tab, week: openWeek, y: Math.round(window.scrollY),
      doi: card ? card.dataset.doi : null, off: card ? Math.round(card.getBoundingClientRect().top - top) : 0 });
  }
  let anchorUntil = 0, anchor = null;
  function applyAnchor() {
    if (!anchor) return;
    const card = anchor.doi && main.querySelector(`.card[data-doi="${CSS.escape(anchor.doi)}"]`);
    if (card) window.scrollTo(0, window.scrollY + card.getBoundingClientRect().top - headerH() - anchor.off);
    else window.scrollTo(0, anchor.y);
  }
  function restorePlace() {
    if (!place) return;
    if (place.tab !== tab || (place.week || null) !== openWeek) { place = null; return; }
    if (tab === "earlier" && feed.archived.includes(openWeek) && !weekCache[openWeek]) return;   // still loading
    anchor = place; place = null;
    anchorUntil = Date.now() + 3000;                  // figures above may still be loading
    applyAnchor();
  }
  const letGo = () => { anchor = null; };
  ["touchstart", "wheel", "keydown"].forEach((ev) => window.addEventListener(ev, letGo, { passive: true }));
  let placeTimer = null;
  window.addEventListener("scroll", () => { clearTimeout(placeTimer); placeTimer = setTimeout(savePlace, 400); }, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") savePlace(); });
  window.addEventListener("pagehide", savePlace);

  // ── Back up / restore ────────────────────────────────────────────────────
  // Saved papers live in this browser's storage, which goes when the app is removed.
  // A backup is a JSON file the reader keeps (Files, Drive, email); Restore merges it back.
  async function backup() {
    const data = { app: "figure-feed", version: 1, exported: new Date().toISOString(), kept, passed };
    const name = `figure-feed-saved-${new Date().toISOString().slice(0, 10)}.json`;
    const file = new File([JSON.stringify(data)], name, { type: "application/json" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      try { await navigator.share({ files: [file], title: "Figure Feed: saved papers" }); return; }
      catch (e) { if (e.name === "AbortError") return; }
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(file); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  }

  function restore(file) {
    const reader = new FileReader();
    reader.onload = () => {
      let data;
      try { data = JSON.parse(reader.result); } catch (e) { data = null; }
      if (!data || data.app !== "figure-feed" || typeof data.kept !== "object" || !data.kept) {
        toast("Not a Figure Feed backup"); return;
      }
      const before = { k: { ...kept }, s: { ...passed } };
      let n = 0;
      for (const [doi, p] of Object.entries(cleanKept(data.kept))) {
        if (!kept[doi]) { kept[doi] = p; delete passed[doi]; n++; }
      }
      const restored = data.passed && typeof data.passed === "object" ? data.passed : {};
      for (const [doi, d] of Object.entries(restored)) {
        if (!kept[doi] && !passed[doi] && isoDate(d)) passed[doi] = d;
      }
      store.set("kept", kept); store.set("passed", passed); render();
      toast(n ? `Restored ${n} paper${n === 1 ? "" : "s"}` : "Nothing new in that backup", () => {
        for (const k of Object.keys(kept)) delete kept[k];
        for (const k of Object.keys(passed)) delete passed[k];
        Object.assign(kept, before.k); Object.assign(passed, before.s);
        store.set("kept", kept); store.set("passed", passed); render();
      });
    };
    reader.readAsText(file);
  }
  const picker = document.createElement("input");
  picker.type = "file"; picker.accept = ".json,application/json"; picker.hidden = true;
  picker.addEventListener("change", () => { if (picker.files[0]) restore(picker.files[0]); picker.value = ""; });
  document.body.appendChild(picker);

  // ── Events ──────────────────────────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const t = e.target;
    const tabBtn = t.closest(".tabs button");
    if (tabBtn) { tab = tabBtn.dataset.tab; openWeek = null; store.set("tab", tab); render(); window.scrollTo(0, 0); return; }
    const chip = t.closest(".chip");
    if (chip) {
      const j = chip.dataset.j;
      if (!j) journals.clear(); else if (journals.has(j)) journals.delete(j); else journals.add(j);
      store.set("journals", [...journals]); renderChips(); render(); return;
    }
    const actBtn = t.closest("[data-act]");
    if (actBtn) { act(actBtn.closest(".card"), actBtn.dataset.act); return; }
    const wk = t.closest("[data-week]");
    if (wk) { openWeek = wk.dataset.week; render(); window.scrollTo(0, 0); return; }
    if (t.closest("[data-back]")) { openWeek = null; render(); return; }
    if (t.closest("[data-backup]")) { backup(); return; }
    if (t.closest("[data-restore]")) { picker.click(); return; }
    const tag = t.closest(".fig-tag");
    if (tag) { tag.classList.toggle("open"); return; }
  });
  // Looks: technical (default), dark, light — the Plexus palette.
  const LOOKS = ["technical", "dark", "light"];
  const BARS = { technical: "#2b130b", dark: "#1a1210", light: "#993C1D" };
  let look = store.get("look", "technical");
  function applyLook() {
    if (!LOOKS.includes(look)) look = "technical";
    document.documentElement.dataset.look = look;
    $("#look").textContent = look[0].toUpperCase() + look.slice(1);
    document.querySelector('meta[name="theme-color"]').content = BARS[look];
  }
  applyLook();
  $("#look").addEventListener("click", () => {
    look = LOOKS[(LOOKS.indexOf(look) + 1) % LOOKS.length]; store.set("look", look); applyLook();
  });

  $("#figsOnly").addEventListener("change", (e) => { figsOnly = e.target.checked; store.set("figsOnly", figsOnly); render(); });
  $("#undo").addEventListener("click", () => { if (undo) undo(); undo = null; $("#toast").hidden = true; });

  // Swipe the text of a card: right keeps, left passes. The figure strip scrolls instead.
  let sx = 0, sy = 0, swCard = null;
  main.addEventListener("touchstart", (e) => {
    const body = e.target.closest(".body");
    swCard = body ? body.closest(".card") : null;
    if (swCard) { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }
  }, { passive: true });
  main.addEventListener("touchmove", (e) => {
    if (!swCard) return;
    const dx = e.touches[0].clientX - sx, dy = e.touches[0].clientY - sy;
    if (Math.abs(dx) > Math.abs(dy)) swCard.style.transform = `translateX(${dx * 0.6}px)`;
  }, { passive: true });
  main.addEventListener("touchend", (e) => {
    if (!swCard) return;
    const card = swCard; swCard = null;
    const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
    card.style.transform = "";
    if (Math.abs(dx) > 80 && Math.abs(dx) > 2 * Math.abs(dy)) act(card, dx > 0 ? "keep" : "pass");
  });

  // A strip is as tall as the figure on screen, not its tallest figure.
  function fitStrip(strip) {
    const i = Math.round(strip.scrollLeft / (strip.clientWidth || 1));
    const img = strip.children[i] && strip.children[i].querySelector("img");
    if (img && img.complete && img.naturalWidth) strip.style.height = img.offsetHeight + "px";
  }
  main.addEventListener("load", (e) => {
    if (e.target.tagName !== "IMG") return;
    const strip = e.target.closest(".figs");
    if (strip) fitStrip(strip);
    if (anchor && Date.now() < anchorUntil) applyAnchor();
  }, true);
  let fitTimer = null;
  main.addEventListener("scroll", (e) => {
    const strip = e.target.classList && e.target.classList.contains("figs") ? e.target : null;
    if (!strip) return;
    clearTimeout(fitTimer);
    fitTimer = setTimeout(() => fitStrip(strip), 80);
  }, true);

  // Broken figure links: drop the slide; a card with none left becomes a text card.
  main.addEventListener("error", (e) => {
    if (e.target.tagName !== "IMG") return;
    const strip = e.target.closest(".figs");
    e.target.closest(".fig").remove();
    if (strip && strip.children.length) fitStrip(strip);
    if (strip && !strip.children.length) {
      const card = strip.closest(".card");
      const p = findPaper(card.dataset.doi);
      strip.outerHTML = `<div class="band" style="background:${esc(colours[p && p.journal] || "#334155")}"></div>`;
      card.classList.add("text-only");
    }
  }, true);

  // ── Load ────────────────────────────────────────────────────────────────
  // Passed papers are forgotten after six months, like the feed itself.
  const cutoff = new Date(Date.now() - 183 * 864e5).toISOString().slice(0, 10);
  for (const d in passed) if (passed[d] < cutoff) delete passed[d];
  store.set("passed", passed);

  fetch("data/feed.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((data) => {
      feed = data;
      data.journals.forEach((j) => { colours[j.name] = j.colour; shorts[j.name] = j.short; });
      const nFigs = data.papers.filter((p) => p.figures_added).length;
      const figTab = $('[data-tab="figs"]');
      if (nFigs) figTab.innerHTML = `New figures<span class="n">${nFigs}</span>`;
      $("#stamp").textContent = "Updated " + new Date(data.generated).toLocaleDateString(undefined, { day: "numeric", month: "short" });
      if (openWeek && !data.weeks.includes(openWeek)) openWeek = null;   // aged out
      renderChips(); render();
      requestAnimationFrame(restorePlace);
    })
    .catch(() => { main.innerHTML = `<p class="empty">Couldn't load the feed. Check your connection and reload.</p>`; });

  // A phone keeps an installed app open in the background for days. When it comes back
  // to the front, check (at most every 30 minutes) whether a newer feed has been built,
  // and reload if so; the reload also picks up any new version of the app itself.
  let lastCheck = Date.now();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible" || !feed || Date.now() - lastCheck < 30 * 60e3) return;
    lastCheck = Date.now();
    fetch("data/feed.json", { cache: "no-cache" }).then((r) => r.json())
      .then((data) => { if (data.generated !== feed.generated) location.reload(); })
      .catch(() => {});
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
  }
})();
