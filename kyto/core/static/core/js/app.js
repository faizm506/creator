/* Kyto front-end. One small file, no libraries.
   - Pages swap in place (no full reload), so moving around feels instant.
   - Chat, inbox and proposals update by themselves.
   - Works without JavaScript too: every link and form is a normal one underneath. */
(function () {
  "use strict";

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var norm = function (html) { return html.replace(/name="csrfmiddlewaretoken" value="[^"]*"/g, ""); };

  /* ---------- timers that stop when the page changes ---------- */
  var timers = [];
  function every(fn, ms) { timers.push(setInterval(fn, ms)); }
  function clearTimers() { timers.forEach(clearInterval); timers = []; }

  /* ---------- toast ---------- */
  function toast(msg, kind) {
    var box = $(".toasts");
    if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("role", "status"); document.body.appendChild(box); }
    var t = document.createElement("div");
    t.className = "toast" + (kind ? " toast-" + kind : "");
    t.textContent = msg;
    box.appendChild(t);
    fadeToast(t, 4500);
  }
  function fadeToast(t, ms) {
    setTimeout(function () { t.classList.add("out"); setTimeout(function () { t.remove(); }, 450); }, ms);
  }

  /* ---------- page start-up (runs on load and after every page swap) ---------- */
  var inits = [];
  function onPage(fn) { inits.push(fn); }
  function runInits() {
    clearTimers();
    inits.forEach(function (fn) { try { fn(); } catch (e) { if (window.console) console.error(e); } });
  }

  onPage(function () { $$(".toast").forEach(function (t, i) { fadeToast(t, 5000 + i * 600); }); });

  /* score ring + bars grow in */
  onPage(function () {
    var ring = $(".ring-fg");
    if (ring) {
      var C = 2 * Math.PI * 58, s = parseFloat(ring.dataset.score) || 0;
      ring.style.strokeDasharray = C; ring.style.strokeDashoffset = C;
      setTimeout(function () { ring.style.strokeDashoffset = C * (1 - Math.min(100, s) / 100); }, reduce ? 0 : 200);
    }
    $$("progress[data-anim]").forEach(function (el, i) {
      if (reduce) return;
      var v = el.value; el.value = 0;
      setTimeout(function () { el.value = v; }, 250 + i * 80);
    });
  });

  /* About page: Ahmedabad scene */
  onPage(function () {
    var scene = $("[data-scene]");
    if (!scene) return;
    var lms = $$(".lm", scene), cap = $(".scene-cap", scene), nameEl = $("[data-cap-name]", scene),
        noteEl = $("[data-cap-note]", scene), link = $("[data-cap-link]", scene), touched = false, idx = -1;
    var pick = function (g) {
      lms.forEach(function (x) { x.classList.toggle("on", x === g); });
      nameEl.textContent = g.dataset.name; noteEl.textContent = g.dataset.note;
      link.href = g.dataset.href; link.textContent = "See " + g.dataset.label + " creators";
      cap.classList.remove("swap"); void cap.offsetWidth; cap.classList.add("swap");
    };
    lms.forEach(function (g, i) {
      g.addEventListener("click", function () { touched = true; idx = i; pick(g); });
      g.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); touched = true; pick(g); } });
    });
    if (!reduce) {
      every(function () { if (touched || document.hidden) return; idx = (idx + 1) % lms.length; pick(lms[idx]); }, 4200);
      scene.addEventListener("pointermove", function (e) {
        var r = scene.getBoundingClientRect();
        scene.style.setProperty("--px", ((e.clientX - r.left) / r.width - 0.5).toFixed(3));
      });
      scene.addEventListener("pointerleave", function () { scene.style.setProperty("--px", 0); });
    }
  });

  /* Settings: highlight the section you are reading */
  var spy = null;
  onPage(function () {
    if (spy) { spy.disconnect(); spy = null; }
    var nav = $(".st-nav");
    if (!nav || !("IntersectionObserver" in window)) return;
    var links = {};
    $$("a", nav).forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        Object.keys(links).forEach(function (k) { links[k].classList.toggle("on", k === en.target.id); });
        var a = links[en.target.id];
        if (a && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: a.offsetLeft - 20, behavior: "smooth" });
      });
    }, { rootMargin: "-25% 0px -65% 0px" });
    $$(".st-sec").forEach(function (s) { spy.observe(s); });
  });

  /* Signup: labels and perks follow Creator / Brand */
  function syncSignup() {
    var su = $("[data-signup]");
    if (!su) return;
    var text = {
      creator: { name: "Your name", handle: "Your Instagram handle", ph: "e.g. Aarav Shah" },
      brand: { name: "Brand name", handle: "Brand's Instagram handle", ph: "e.g. Chai Corner Cafe" }
    };
    var r = $('input[name="role"]:checked', su), role = r ? r.value : "creator", t = text[role];
    if (!t) return;
    var nameL = $('label[for="id_display_name"]', su), handleL = $('label[for="id_username"]', su), nameIn = $("#id_display_name", su);
    if (nameL) nameL.textContent = t.name;
    if (handleL) handleL.textContent = t.handle;
    if (nameIn) nameIn.placeholder = t.ph;
    $$("[data-perks]", su).forEach(function (u) { u.hidden = u.dataset.perks !== role; });
  }
  onPage(syncSignup);

  /* Boost page (only when boosting is switched on) */
  function syncBoost() {
    var box = $("[data-boost]");
    if (!box) return;
    var chosen = $("input[data-plan]:checked", box);
    $$("[data-pay]", box).forEach(function (p) { p.hidden = !chosen || p.dataset.pay !== chosen.value; });
  }
  onPage(syncBoost);

  /* Character counters */
  function updateCounter(c) {
    var t = document.getElementById(c.dataset.countFor);
    if (t) c.textContent = t.value.length + " / " + (t.maxLength > 0 ? t.maxLength : "");
  }
  onPage(function () { $$("[data-count-for]").forEach(updateCounter); });

  /* ---------- chat: updates by itself, sends without reloading ---------- */
  var chatBusy = false;
  function chatEl() { return $("[data-chat]"); }
  function nearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 140 || el.scrollHeight <= el.clientHeight; }
  function toBottom(chat) {
    if (chat.scrollHeight > chat.clientHeight + 5) { chat.scrollTop = chat.scrollHeight; }
    else { var end = $("#end", chat); if (end) end.scrollIntoView({ block: "end" }); }
  }
  function lastId(chat) {
    var ids = $$(".bubble[data-id]", chat).map(function (b) { return +b.dataset.id || 0; });
    return ids.length ? Math.max.apply(null, ids) : 0;
  }
  function removePending(chat) { $$(".bubble.pending", chat).forEach(function (b) { b.remove(); }); }

  function pollChat() {
    var chat = chatEl();
    if (!chat || chatBusy || document.hidden) return Promise.resolve();
    chatBusy = true;
    return fetch(location.href, { credentials: "same-origin", headers: { "X-Kyto": "poll" } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var fresh = $("[data-chat]", doc), box = $(".chatbox"), freshBox = $(".chatbox", doc);
        if (!fresh || !box || !freshBox) return;
        if (freshBox.dataset.status !== box.dataset.status) { go(location.href, false, true); return; }
        var stick = nearBottom(chat), added = false, last = lastId(chat), endEl = $("#end", chat);
        $$(".bubble[data-id]", fresh).forEach(function (b) {
          if ((+b.dataset.id || 0) <= last) return;
          removePending(chat);
          var prev = b.previousElementSibling;
          if (prev && prev.classList.contains("day")) {
            var days = $$(".day", chat);
            if (!days.length || days[days.length - 1].textContent !== prev.textContent) chat.insertBefore(document.importNode(prev, true), endEl);
          }
          var n = document.importNode(b, true); n.classList.add("fresh");
          chat.insertBefore(n, endEl); added = true;
        });
        if (added && stick) toBottom(chat);
        var side = $("[data-side]"), freshSide = $("[data-side]", doc);
        if (side && freshSide && norm(side.innerHTML) !== norm(freshSide.innerHTML)) side.innerHTML = freshSide.innerHTML;
      })
      .catch(function () { /* offline for a moment: try again next time */ })
      .then(function () { chatBusy = false; });
  }

  function sendMessage(form) {
    var ta = $("textarea", form), chat = chatEl(), text = ta.value.trim();
    if (!text || !chat) return;
    var btn = $(".send", form); btn.disabled = true;
    var p = document.createElement("div");
    p.className = "bubble me pending fresh";
    var para = document.createElement("p"); para.textContent = text;
    var tm = document.createElement("time"); tm.textContent = "Sending…";
    p.appendChild(para); p.appendChild(tm);
    chat.insertBefore(p, $("#end", chat)); toBottom(chat);
    ta.value = ""; ta.style.height = "auto";
    fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { "X-Kyto": "chat" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
      .then(function (res) {
        btn.disabled = false;
        if (!res.ok) { removePending(chat); ta.value = text; toast(res.j.error || "Message not sent.", "error"); return; }
        ta.focus(); chatBusy = false; pollChat();
      })
      .catch(function () { btn.disabled = false; removePending(chat); ta.value = text; toast("Message not sent. Check your connection.", "error"); });
  }

  onPage(function () {
    var chat = chatEl();
    if (!chat) return;
    if ($$(".bubble", chat).length > 1) toBottom(chat);
    every(pollChat, 3500);
  });

  /* ---------- inbox, proposals: refresh themselves ---------- */
  var regionBusy = false;
  function pollRegions() {
    var regions = $$("[data-region]");
    if (!regions.length || regionBusy || document.hidden) return;
    regionBusy = true;
    fetch(location.href, { credentials: "same-origin", headers: { "X-Kyto": "poll" } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        regions.forEach(function (el) {
          var fresh = $('[data-region="' + el.dataset.region + '"]', doc);
          if (fresh && norm(fresh.innerHTML) !== norm(el.innerHTML)) el.innerHTML = fresh.innerHTML;
        });
      })
      .catch(function () {})
      .then(function () { regionBusy = false; });
  }
  onPage(function () { if ($$("[data-region]").length) every(pollRegions, 8000); });

  /* ---------- inbox badge: asks every 20s ---------- */
  function setBadge(n) {
    $$('.icon-btn[href$="/inbox/"]').forEach(function (a) {
      var b = $(".icon-n", a);
      if (n > 0) { if (!b) { b = document.createElement("i"); b.className = "badge-n icon-n"; a.appendChild(b); } b.textContent = n; }
      else if (b) b.remove();
    });
    $$(".tab-av").forEach(function (w) {
      var b = $(".tab-n", w);
      if (n > 0) { if (!b) { b = document.createElement("i"); b.className = "badge-n tab-n"; w.appendChild(b); } b.textContent = n; }
      else if (b) b.remove();
    });
  }
  setInterval(function () {
    if (document.hidden || !$("[data-menu]")) return;
    fetch("/api/unread/", { credentials: "same-origin", headers: { "X-Kyto": "poll" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) setBadge(j.count); })
      .catch(function () {});
  }, 20000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { pollChat(); pollRegions(); } });

  /* ---------- instant page changes ---------- */
  var bar = document.createElement("div");
  bar.id = "kbar";
  document.documentElement.appendChild(bar);
  var barTimer = null;
  function barStart() { clearTimeout(barTimer); bar.style.opacity = "1"; bar.style.width = "0"; requestAnimationFrame(function () { bar.style.width = "72%"; }); }
  function barDone() { bar.style.width = "100%"; barTimer = setTimeout(function () { bar.style.opacity = "0"; bar.style.width = "0"; }, 260); }

  var cache = {}, TTL = 30000, scrolls = {}, currentHref = location.href;
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  var PRIVATE = ["/inbox/", "/offers/", "/settings/", "/hire/", "/verify/", "/api/"];
  function cacheable(u) { return !PRIVATE.some(function (p) { return u.pathname.indexOf(p) === 0; }); }
  function adminPath() { return document.body.dataset.admin || "/admin/"; }

  function sameApp(u) {
    return u.origin === location.origin && u.pathname.indexOf(adminPath()) !== 0 &&
      u.pathname.indexOf("/media/") !== 0 && u.pathname.indexOf("/go/") !== 0 && !/\.txt$/.test(u.pathname);
  }
  function eligible(a, e) {
    if (!a || !a.href || (a.target && a.target !== "_self") || a.hasAttribute("download") || a.hasAttribute("data-no-turbo")) return false;
    if (e && (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button > 0)) return false;
    var u = new URL(a.href, location.href);
    if (!sameApp(u)) return false;
    if (u.pathname === location.pathname && u.search === location.search && u.hash) return false;
    return true;
  }

  function fetchPage(url, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    opts.headers = { "X-Kyto": "nav" };
    return fetch(url, opts).then(function (res) {
      if ((res.headers.get("content-type") || "").indexOf("text/html") === -1) throw new Error("not a page");
      return res.text().then(function (html) { return { html: html, url: res.url }; });
    });
  }

  function swap(v, push, keepScroll) {
    var doc = new DOMParser().parseFromString(v.html, "text/html");
    if (!doc.body) throw new Error("empty page");
    var y = keepScroll ? window.scrollY : 0;
    document.title = doc.title;
    document.body.className = doc.body.className;
    document.body.dataset.admin = doc.body.dataset.admin || "";
    document.body.innerHTML = doc.body.innerHTML;
    var target = new URL(v.url, location.href);
    if (push) history.pushState({}, "", target.href);
    else if (target.href !== location.href) history.replaceState({}, "", target.href);
    currentHref = target.href;
    runInits();
    if (target.hash && $(target.hash)) { $(target.hash).scrollIntoView(); }
    else { window.scrollTo({ top: keepScroll ? y : (scrolls[target.href] || 0), left: 0, behavior: "instant" }); }
    var m = $("main");
    if (m) { m.setAttribute("tabindex", "-1"); m.focus({ preventScroll: true }); }
  }

  function go(url, push, keepScroll) {
    var u = new URL(url, location.href), hit = cache[u.href];
    scrolls[currentHref] = window.scrollY;
    barStart();
    var p = (hit && Date.now() - hit.t < TTL) ? Promise.resolve(hit.v)
      : fetchPage(u.href).then(function (v) { if (cacheable(u)) cache[u.href] = { v: v, t: Date.now() }; return v; });
    return p.then(function (v) { swap(v, push, keepScroll); barDone(); })
      .catch(function () { barDone(); window.location.href = u.href; });
  }

  var prefetching = {};
  function prefetch(a) {
    if (!eligible(a)) return;
    var u = new URL(a.href, location.href);
    if (!cacheable(u) || prefetching[u.href] || (cache[u.href] && Date.now() - cache[u.href].t < TTL)) return;
    prefetching[u.href] = true;
    fetchPage(u.href).then(function (v) { cache[u.href] = { v: v, t: Date.now() }; }).catch(function () {}).then(function () { delete prefetching[u.href]; });
  }
  var hoverTimer = null;
  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(function () { prefetch(a); }, 70);
  });
  document.addEventListener("touchstart", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (a) prefetch(a);
  }, { passive: true });

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || !eligible(a, e)) return;
    e.preventDefault();
    go(a.href, true);
  });
  window.addEventListener("popstate", function () { go(location.href, false); });

  /* confirm dialogs first, then chat box, then every other form */
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f.matches && f.matches("form[data-confirm]") && !window.confirm(f.dataset.confirm)) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);

  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (e.defaultPrevented || !(f instanceof HTMLFormElement) || f.hasAttribute("data-no-turbo")) return;
    if (f.classList.contains("composer")) { e.preventDefault(); sendMessage(f); return; }
    var action = new URL(f.getAttribute("action") || location.href, location.href);
    if (!sameApp(action)) return;
    var method = (f.getAttribute("method") || "get").toLowerCase();
    e.preventDefault();
    var data = new FormData(f);
    if (e.submitter && e.submitter.name) data.append(e.submitter.name, e.submitter.value);
    if (method === "get") {
      var q = new URLSearchParams();
      data.forEach(function (v, k) { if (typeof v === "string") q.append(k, v); });
      action.search = q.toString();
      go(action.href, true);
      return;
    }
    var buttons = $$("button, input[type=submit]", f);
    buttons.forEach(function (b) { b.disabled = true; });
    barStart();
    fetchPage(action.href, { method: "POST", body: data })
      .then(function (v) { cache = {}; swap(v, true); barDone(); })
      .catch(function () {
        barDone();
        buttons.forEach(function (b) { b.disabled = false; });
        toast("Couldn't reach the server. Check your connection and try again.", "error");
      });
  });

  /* ---------- small helpers that work on any page ---------- */
  var KEY = "kyto-big-text", root = document.documentElement;
  function applyBig(on) {
    root.classList.toggle("big", on);
    var b = $("[data-textsize]");
    if (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); b.setAttribute("aria-label", on ? "Make text smaller" : "Make text bigger"); }
  }
  var big = false; try { big = localStorage.getItem(KEY) === "1"; } catch (e) { big = false; }
  onPage(function () { applyBig(big); });

  var logoClicks = 0, logoTimer = null;
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-textsize]");
    if (t) { big = !root.classList.contains("big"); applyBig(big); try { localStorage.setItem(KEY, big ? "1" : "0"); } catch (err) { /* private mode */ } return; }

    var logo = e.target.closest && e.target.closest(".logo");
    if (logo) {
      logoClicks += 1; clearTimeout(logoTimer); logoTimer = setTimeout(function () { logoClicks = 0; }, 3000);
      if (logoClicks >= 5) { logoClicks = 0; toast("You found the secret. There is no prize. Go post a reel.", ""); }
    }

    var share = e.target.closest && e.target.closest("[data-share]");
    if (share) {
      var url = new URL(share.dataset.share, location.origin).href, title = share.dataset.title || document.title;
      if (navigator.share) { navigator.share({ title: title, url: url }).catch(function () {}); }
      else if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(function () {
          var l = $("span", share), old = l ? l.textContent : "";
          if (l) { l.textContent = "Copied!"; setTimeout(function () { l.textContent = old; }, 1600); }
        });
      }
      return;
    }

    var copy = e.target.closest && e.target.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(location.href.split("#")[0]).then(function () {
        var old = copy.textContent; copy.textContent = "Link copied";
        setTimeout(function () { copy.textContent = old; }, 1800);
      });
      return;
    }

    var quick = e.target.closest && e.target.closest("[data-quick]");
    if (quick) {
      var ta = $(".composer textarea");
      if (ta) { ta.value = quick.dataset.quick; ta.focus(); ta.dispatchEvent(new Event("input", { bubbles: true })); }
      return;
    }

    var reel = e.target.closest && e.target.closest(".reel-face");
    if (reel) {
      var src = reel.dataset.embed || "";
      if (src.indexOf("https://www.instagram.com/") !== 0) return;
      var f = document.createElement("iframe");
      f.src = src; f.loading = "lazy"; f.title = reel.getAttribute("aria-label") || "Instagram reel";
      f.setAttribute("allowfullscreen", "");
      f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups allow-presentation");
      f.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      reel.replaceWith(f);
      return;
    }

    var mapBtn = e.target.closest && e.target.closest(".map-face");
    if (mapBtn) {
      var box = mapBtn.closest("[data-map]"), msrc = box ? box.dataset.embed || "" : "";
      if (msrc.indexOf("https://www.google.com/maps") !== 0) return;
      var mf = document.createElement("iframe");
      mf.src = msrc; mf.loading = "lazy"; mf.title = "Map of the shop";
      mf.setAttribute("referrerpolicy", "no-referrer-when-downgrade");
      mf.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
      mapBtn.replaceWith(mf);
      return;
    }

    var shot = e.target.closest && e.target.closest(".shot");
    var lb = $("[data-lightbox]");
    if (shot && lb && typeof lb.showModal === "function") { $("img", lb).src = shot.dataset.full; lb.showModal(); return; }
    if (lb && e.target.closest && (e.target.closest(".lb-close") || e.target === lb)) { lb.close(); return; }

    var tab = e.target.closest && e.target.closest("[data-tab]");
    if (tab) {
      var tabs = tab.closest("[data-tabs]");
      if (!tabs) return;
      $$("[data-tab]", tabs).forEach(function (x) { var on = x === tab; x.classList.toggle("on", on); x.setAttribute("aria-selected", on ? "true" : "false"); });
      $$("[data-panel]", tabs).forEach(function (p) { p.hidden = p.dataset.panel !== tab.dataset.tab; });
      return;
    }

    var menu = $("[data-menu]");
    if (menu && menu.open && !menu.contains(e.target)) menu.open = false;
  });

  document.addEventListener("keydown", function (e) {
    var menu = $("[data-menu]");
    if (e.key === "Escape" && menu) menu.open = false;
    var t = e.target;
    if (e.key === "Enter" && !e.shiftKey && t.matches && t.matches("[data-grow]") && window.matchMedia("(min-width: 821px)").matches) {
      e.preventDefault(); if (t.form) t.form.requestSubmit();
    }
  });

  document.addEventListener("input", function (e) {
    var t = e.target;
    if (t.matches && t.matches("[data-grow]")) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; }
    if (t.id) $$('[data-count-for="' + t.id + '"]').forEach(updateCounter);
    if (t.matches && t.matches("input[data-live]")) {
      var q = t.value.trim().toLowerCase();
      $$("[data-rows] .row").forEach(function (r) { r.hidden = q && (r.dataset.search || "").indexOf(q) === -1; });
    }
  });

  document.addEventListener("change", function (e) {
    var t = e.target;
    if (t.matches && t.matches('[data-signup] input[name="role"]')) syncSignup();
    if (t.matches && t.matches("input[data-plan]")) syncBoost();
  });

  /* go */
  runInits();
})();
