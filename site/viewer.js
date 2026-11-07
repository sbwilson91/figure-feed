// The full-screen figure viewer: swipe or arrow between a paper's figures, pinch, wheel
// or double-tap to zoom, drag to pan, swipe down or Back to close.
window.FigureViewer = (function () {
  "use strict";

  const MAX_ZOOM = 6, TAP_ZOOM = 2.5, DOUBLE_TAP_MS = 300;
  const $ = (id) => document.getElementById(id);
  const dlg = $("viewer"), stage = $("vStage"), img = $("vImg"), status = $("vStatus");
  const count = $("vCount"), link = $("vLink"), title = $("vTitle"), cap = $("vCap");
  const prev = $("vPrev"), next = $("vNext");

  let items = [], index = 0, onClose = null;
  let s = 1, x = 0, y = 0;            // the image's zoom and offset from the stage's centre
  const pts = new Map();              // pointers now down
  let pinch = null, drag = null, lastTap = 0, sliding = false;

  function paint(animate) {
    img.classList.toggle("anim", !!animate);
    img.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
    dlg.classList.toggle("zoomed", s > 1);
  }
  // How far the zoomed image may move and still fill as much of the stage as it can.
  function clampPan() {
    const box = stage.getBoundingClientRect();
    const mx = Math.max(0, (img.offsetWidth * s - box.width) / 2);
    const my = Math.max(0, (img.offsetHeight * s - box.height) / 2);
    x = Math.min(mx, Math.max(-mx, x));
    y = Math.min(my, Math.max(-my, y));
  }
  function reset(animate) { s = 1; x = 0; y = 0; paint(animate); }
  // Zoom to `to`, keeping the point under (cx, cy) in place.
  function zoomAt(to, cx, cy, animate) {
    to = Math.min(MAX_ZOOM, Math.max(1, to));
    const box = stage.getBoundingClientRect();
    const px = cx - box.left - box.width / 2, py = cy - box.top - box.height / 2;
    x = px - (px - x) * (to / s);
    y = py - (py - y) * (to / s);
    s = to;
    clampPan();
    paint(animate);
  }

  function loadImage(url, then) {
    const im = new Image();
    im.referrerPolicy = "no-referrer";
    if (then) im.onload = then;
    im.src = url;
  }
  // The image's box fills the stage whatever size of file is in it, so a small preview is
  // not left tiny and the full figure replaces the small one without anything moving.
  function fit() {
    if (!img.naturalWidth) return;
    const k = Math.min(stage.clientWidth / img.naturalWidth, stage.clientHeight / img.naturalHeight);
    img.style.width = Math.round(img.naturalWidth * k) + "px";
    img.style.height = Math.round(img.naturalHeight * k) + "px";
    clampPan();
    paint(false);
  }
  function show(i) {
    index = i;
    const f = items[i];
    reset(false);
    dlg.dataset.state = "loading";
    status.textContent = "Loading…";
    img.alt = f.label + (f.caption ? ": " + f.caption : "");
    img.src = f.small;
    if (f.small !== f.url) loadImage(f.url, () => { if (dlg.open && index === i) img.src = f.url; });
    count.textContent = items.length > 1 ? `${i + 1} / ${items.length}` : "";
    cap.textContent = f.label === "Preview" ? "Preview image from the publisher."
      : f.label + (f.caption ? ". " + f.caption : "");
    prev.hidden = i === 0;
    next.hidden = i === items.length - 1;
    [i + 1, i - 1].forEach((n) => { if (items[n]) loadImage(items[n].small); });
  }
  img.addEventListener("load", () => { fit(); dlg.dataset.state = "ready"; });
  window.addEventListener("resize", () => { if (dlg.open) fit(); });
  img.addEventListener("error", () => {
    if (!img.getAttribute("src")) return;              // cleared on closing
    if (img.getAttribute("src") !== items[index].url) { img.src = items[index].url; return; }
    dlg.dataset.state = "failed";
    status.textContent = "This figure didn't load. Open the paper to see it.";
  });

  // One figure slides out and the next slides in, or the image springs back at the ends.
  function go(dir) {
    const to = index + dir;
    if (sliding) return;
    if (!items[to]) { reset(true); return; }
    const w = stage.clientWidth;
    sliding = true;
    s = 1; y = 0; x = -dir * w; paint(true);
    setTimeout(() => {
      sliding = false;
      if (!dlg.open) return;
      show(to);
      x = dir * w; paint(false);
      void img.offsetWidth;           // settle the start position before animating from it
      x = 0; paint(true);
    }, 140);
  }

  // ── Gestures ──────────────────────────────────────────────────────────
  const gap = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  const mid = () => { const [a, b] = [...pts.values()]; return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };

  stage.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".v-nav")) return;
    stage.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2) {
      pinch = { d: gap(), s, m: mid() };
      drag = null;
    } else if (pts.size === 1) {
      drag = { sx: e.clientX, sy: e.clientY, ox: x, oy: y, axis: null, moved: false, t: Date.now(),
               onImage: e.target === img };
    }
  });
  stage.addEventListener("pointermove", (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pts.size === 2) {
      const m = mid();
      x += m.x - pinch.m.x; y += m.y - pinch.m.y;   // two fingers moving together pan too
      pinch.m = m;
      zoomAt(pinch.s * gap() / pinch.d, m.x, m.y, false);
      return;
    }
    if (!drag) return;
    const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) < 8) return;
    drag.moved = true;
    if (s > 1) {
      x = drag.ox + dx; y = drag.oy + dy;
      clampPan();
    } else {
      drag.axis = drag.axis || (Math.abs(dx) > Math.abs(dy) ? "x" : "y");
      if (drag.axis === "x") x = dx;
      else { y = Math.max(0, dy); dlg.style.setProperty("--fade", String(Math.max(0.3, 1 - y / 400))); }
    }
    paint(false);
  });
  function pointerEnd(e) {
    if (!pts.delete(e.pointerId)) return;
    if (pinch) {
      if (pts.size < 2) pinch = null;
      if (s < 1.05) reset(true);
      return;                         // a finger left over after a pinch does nothing
    }
    const d = drag;
    drag = null;
    if (!d || e.type === "pointercancel") { if (s === 1) reset(true); return; }
    dlg.style.removeProperty("--fade");
    if (!d.moved) { tap(e, d); return; }
    if (s > 1) return;
    const dt = Math.max(1, Date.now() - d.t);
    const quick = Math.abs(d.axis === "x" ? x : y) / dt > 0.5;
    if (d.axis === "x" && (Math.abs(x) > stage.clientWidth * 0.2 || quick)) go(x < 0 ? 1 : -1);
    else if (d.axis === "y" && (y > 110 || (quick && y > 30))) dlg.close();
    else reset(true);
  }
  stage.addEventListener("pointerup", pointerEnd);
  stage.addEventListener("pointercancel", pointerEnd);

  function tap(e, d) {
    const now = Date.now();
    if (now - lastTap < DOUBLE_TAP_MS) {
      lastTap = 0;
      if (s > 1) reset(true); else zoomAt(TAP_ZOOM, e.clientX, e.clientY, true);
    } else {
      lastTap = now;
      if (!d.onImage && s === 1) dlg.close();     // a tap beside the figure closes
    }
  }

  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomAt(s * Math.exp(-e.deltaY * 0.002), e.clientX, e.clientY, false);
  }, { passive: false });

  // ── Open and close ────────────────────────────────────────────────────
  $("vClose").addEventListener("click", () => dlg.close());
  prev.addEventListener("click", () => go(-1));
  next.addEventListener("click", () => go(1));
  dlg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
    else if (e.key === "+" || e.key === "=" || e.key === "-") {
      const box = stage.getBoundingClientRect();
      zoomAt(s * (e.key === "-" ? 0.7 : 1.4), box.left + box.width / 2, box.top + box.height / 2, true);
    }
  });
  // The phone's Back button closes the viewer rather than leaving the app.
  window.addEventListener("popstate", () => { if (dlg.open) dlg.close(); });
  dlg.addEventListener("close", () => {
    pts.clear(); pinch = null; drag = null;
    dlg.style.removeProperty("--fade");
    img.removeAttribute("src");
    if (history.state && history.state.ffViewer) history.back();
    if (onClose) onClose(index);
    onClose = null;
  });

  // figures: [{url, small, label, caption}]; `small` shows first. paper: {title, link}. done(index) runs on close.
  function open(figures, start, paper, done) {
    items = figures; onClose = done;
    title.textContent = paper.title;
    link.href = paper.link;
    dlg.showModal();
    history.pushState({ ffViewer: true }, "");
    show(start);
  }

  return { open };
})();
