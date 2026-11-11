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
  function clearTimers() { timers.forEach(clearInterval); timers = []; if (typeof chatState !== "undefined") clearTimeout(chatState.timer); }

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

  /* ---------- chat: instant, grouped, live ---------- */
  var chatState = { busy: false, timer: null, lastTyping: 0, active: Date.now(), failures: 0, jump: 0 };
  var chatEl = function () { return $("[data-chat]"); };
  var boxEl = function () { return $(".chatbox"); };
  function nearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 140; }
  function toBottom(chat, smooth) { chat.scrollTo({ top: chat.scrollHeight, behavior: (smooth && !reduce) ? "smooth" : "auto" }); }
  function lastId(chat) {
    var ids = $$(".bubble[data-id]", chat).map(function (b) { return +b.dataset.id || 0; });
    return ids.length ? Math.max.apply(null, ids) : 0;
  }
  function csrf() { var i = $('input[name="csrfmiddlewaretoken"]'); return i ? i.value : ""; }
  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "m" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  /* neat groups: rounded ends, time only on the last bubble of a run, "Seen" under your newest message */
  function regroup(chat) {
    $$(".seen-note", chat).forEach(function (n) { n.remove(); });
    var bubbles = $$(".bubble", chat);
    bubbles.forEach(function (b) {
      var prev = b.previousElementSibling, next = b.nextElementSibling, me = b.classList.contains("me");
      var sameP = prev && prev.classList.contains("bubble") && prev.classList.contains("me") === me;
      var sameN = next && next.classList.contains("bubble") && next.classList.contains("me") === me;
      b.classList.remove("g-first", "g-mid", "g-last", "g-single");
      b.classList.add(sameP && sameN ? "g-mid" : sameP ? "g-last" : sameN ? "g-first" : "g-single");
    });
    var mine = bubbles.filter(function (b) {
      return b.classList.contains("me") && !b.classList.contains("pending") && !b.classList.contains("failed") && b.dataset.id && b.dataset.id !== "0";
    });
    var last = mine[mine.length - 1];
    if (last) {
      var n = document.createElement("div");
      n.className = "seen-note"; n.textContent = last.dataset.read === "1" ? "Seen" : "Sent";
      last.insertAdjacentElement("afterend", n);
    }
  }

  function buildBubble(m) {
    var b = document.createElement("div");
    b.className = "bubble " + (m.mine ? "me" : "them") + (m.heart ? " hearted" : "");
    b.dataset.id = m.id; b.dataset.read = m.read ? "1" : "0";
    var p = document.createElement("p"); p.textContent = m.body;
    var t = document.createElement("time"); t.textContent = m.time;
    b.appendChild(p); b.appendChild(t);
    if (!m.mine) {
      var h = document.createElement("button");
      h.type = "button"; h.className = "heart-btn"; h.setAttribute("data-heart", ""); h.setAttribute("aria-label", "Heart this message"); h.textContent = "♥";
      b.appendChild(h);
    }
    var hm = document.createElement("span");
    hm.className = "heart-mark"; hm.setAttribute("aria-hidden", "true"); hm.textContent = "♥";
    b.appendChild(hm);
    return b;
  }
  function appendMessage(chat, m) {
    if ($('.bubble[data-id="' + m.id + '"]', chat)) return false;
    if (m.mine) {   /* my own message arrived before the send answer: drop the grey "Sending…" copy */
      var dup = $$(".bubble.pending", chat).filter(function (x) { return x.dataset.text === m.body; })[0];
      if (dup) dup.remove();
    }
    var end = $("#end", chat), days = $$(".day", chat);
    if (m.day && (!days.length || days[days.length - 1].textContent !== m.day)) {
      var d = document.createElement("div"); d.className = "day"; d.textContent = m.day; chat.insertBefore(d, end);
    }
    var b = buildBubble(m); b.classList.add("fresh"); chat.insertBefore(b, end);
    return true;
  }
  function applyState(chat, d) {
    (d.read || []).forEach(function (id) { var b = $('.bubble[data-id="' + id + '"]', chat); if (b) b.dataset.read = "1"; });
    var hearts = {}; (d.hearts || []).forEach(function (id) { hearts[id] = true; });
    $$(".bubble[data-id]", chat).forEach(function (b) {
      var id = +b.dataset.id;
      if (id && id >= (d.since || 0)) b.classList.toggle("hearted", !!hearts[id]);
    });
  }

  function showJump(n) {
    var j = $("[data-jump]"); if (!j) return;
    chatState.jump += n; j.textContent = chatState.jump > 1 ? chatState.jump + " new messages ↓" : "New message ↓"; j.hidden = false;
  }
  function hideJump() { chatState.jump = 0; var j = $("[data-jump]"); if (j) j.hidden = true; }

  function pollChat() {
    var chat = chatEl(), bx = boxEl();
    if (!chat || !bx || chatState.busy) return Promise.resolve();
    chatState.busy = true;
    return fetch(bx.dataset.poll + "?after=" + lastId(chat), { credentials: "same-origin", cache: "no-store", headers: { "X-Kyto": "poll" } })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (d) {
        chatState.failures = 0;
        if (d.status !== bx.dataset.status) { go(location.href, false, true); return; }
        var stick = nearBottom(chat), added = 0, theirs = 0;
        (d.messages || []).forEach(function (m) { if (appendMessage(chat, m)) { added++; if (!m.mine) theirs++; } });
        applyState(chat, d);
        regroup(chat);
        if (added) {
          chatState.active = Date.now();
          if (stick) toBottom(chat, true); else if (theirs) showJump(theirs);
        }
        var tn = $("[data-typing-note]");
        if (tn) {
          tn.hidden = !d.typing;
          if (d.typing) { $("span", tn).textContent = (bx.dataset.other || "They") + " is typing…"; if (stick) toBottom(chat); }
        }
      })
      .catch(function () { chatState.failures += 1; })
      .then(function () { chatState.busy = false; });
  }

  /* checks quickly while the chat is active, slowly when idle or hidden, and backs off if the server is struggling */
  function scheduleChat() {
    clearTimeout(chatState.timer);
    if (!chatEl()) return;
    var idle = Date.now() - chatState.active;
    var wait = (document.hidden ? 15000 : idle < 30000 ? 2500 : 5000) * Math.min(6, 1 + chatState.failures);
    chatState.timer = setTimeout(function () { pollChat().then(scheduleChat); }, wait);
  }

  function makePending(text, cid) {
    var b = document.createElement("div");
    b.className = "bubble me pending fresh"; b.dataset.cid = cid; b.dataset.text = text; b.dataset.read = "0";
    var p = document.createElement("p"); p.textContent = text;
    var t = document.createElement("time"); t.textContent = "Sending…";
    b.appendChild(p); b.appendChild(t);
    return b;
  }
  function markFailed(b, msg) {
    b.classList.remove("pending"); b.classList.add("failed");
    $("time", b).textContent = (msg || "Not sent") + " Tap to retry.";
    regroup(chatEl());
  }

  function sendMessage(form, retry) {
    var ta = $("textarea", form), chat = chatEl(), bx = boxEl();
    var text = retry ? retry.dataset.text : ta.value.trim();
    var cid = retry ? retry.dataset.cid : uuid();
    if (!text || !chat || !bx) return;
    var data = new FormData(form);              /* build the message BEFORE clearing the box */
    data.set("body", text); data.set("cid", cid);
    var b = retry || makePending(text, cid);
    if (retry) { b.classList.remove("failed"); b.classList.add("pending"); $("time", b).textContent = "Sending…"; }
    else {
      chat.insertBefore(b, $("#end", chat));
      ta.value = ""; ta.style.height = "auto"; form.classList.remove("ready");
      var cc = $(".cc", form); if (cc) cc.hidden = true;
    }
    regroup(chat); toBottom(chat, true); hideJump(); chatState.active = Date.now();
    fetch(form.action, { method: "POST", body: data, credentials: "same-origin", headers: { "X-Kyto": "chat" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, status: r.status, j: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          if (res.status === 400 || res.status === 409) { b.remove(); regroup(chat); toast(res.j.error || "Message not sent.", "error"); }
          else markFailed(b, res.j.error || "Not sent.");
          return;
        }
        if ($('.bubble[data-id="' + res.j.id + '"]', chat)) { b.remove(); }
        else { b.classList.remove("pending"); b.dataset.id = res.j.id; $("time", b).textContent = res.j.time; }
        regroup(chat); chatState.busy = false; pollChat();
      })
      .catch(function () { markFailed(b, "No connection."); });
  }

  function toggleHeart(b) {
    var id = b.dataset.id, bx = boxEl();
    if (!id || id === "0" || !bx) return;
    var on = !b.classList.contains("hearted");
    b.classList.toggle("hearted", on);
    var d = new FormData(); d.append("csrfmiddlewaretoken", csrf());
    fetch(bx.dataset.hearts + id + "/", { method: "POST", body: d, credentials: "same-origin", headers: { "X-Kyto": "json" } })
      .then(function (r) { return r.json(); })
      .then(function (j) { if (j.ok) b.classList.toggle("hearted", j.heart); else b.classList.toggle("hearted", !on); })
      .catch(function () { b.classList.toggle("hearted", !on); });
  }

  document.addEventListener("dblclick", function (e) {
    var b = e.target.closest && e.target.closest(".bubble.them");
    if (b) toggleHeart(b);
  });
  document.addEventListener("scroll", function (e) {
    var t = e.target;
    if (t && t.matches && t.matches("[data-chat]") && nearBottom(t)) hideJump();
  }, true);
  document.addEventListener("input", function (e) {
    var t = e.target;
    if (!(t.matches && t.matches(".composer textarea"))) return;
    var f = t.form, len = t.value.length, cc = $(".cc", f);
    f.classList.toggle("ready", !!t.value.trim());
    if (cc) { cc.hidden = len < 800; cc.textContent = len + " / 1000"; }
    var bx = boxEl();
    if (t.value.trim() && bx && bx.dataset.typing && Date.now() - chatState.lastTyping > 3000) {
      chatState.lastTyping = Date.now();
      var d = new FormData(); d.append("csrfmiddlewaretoken", csrf());
      fetch(bx.dataset.typing, { method: "POST", body: d, credentials: "same-origin", headers: { "X-Kyto": "json" } }).catch(function () {});
    }
  });

  var vvHandler = null;
  onPage(function () {
    if (vvHandler && window.visualViewport) {
      visualViewport.removeEventListener("resize", vvHandler); visualViewport.removeEventListener("scroll", vvHandler); vvHandler = null;
    }
    var chat = chatEl();
    if (!chat) { document.documentElement.style.removeProperty("--vvh"); return; }
    chatState.active = Date.now(); chatState.failures = 0; chatState.busy = false; chatState.jump = 0;
    regroup(chat); toBottom(chat);
    scheduleChat();
    if (window.visualViewport) {      /* the phone keyboard shrinks the chat instead of covering the message box */
      vvHandler = function () {
        document.documentElement.style.setProperty("--vvh", visualViewport.height + "px");
        window.scrollTo(0, 0);
        var c = chatEl(); if (c && document.activeElement && document.activeElement.matches && document.activeElement.matches(".composer textarea")) toBottom(c);
      };
      visualViewport.addEventListener("resize", vvHandler); visualViewport.addEventListener("scroll", vvHandler); vvHandler();
    }
    var ta = $(".composer textarea");
    if (ta && window.matchMedia("(min-width: 821px)").matches) ta.focus({ preventScroll: true });
  });

  /* ---------- kudos: instant, no page change ---------- */
  function toggleKudos(f) {
    var btn = $("button", f), kc = $(".kc", btn), was = btn.classList.contains("on"), n0 = kc ? (+kc.textContent || 0) : 0;
    var paint = function (on, n) {
      btn.classList.toggle("on", on); btn.setAttribute("aria-pressed", on ? "true" : "false");
      if (kc) kc.textContent = Math.max(0, n);
    };
    paint(!was, n0 + (was ? -1 : 1));
    fetch(f.action, { method: "POST", body: new FormData(f), credentials: "same-origin", headers: { "X-Kyto": "json" } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) { paint(was, n0); toast(res.j.error || "Couldn't save that. Try again.", "error"); return; }
        paint(res.j.on, res.j.count);
      })
      .catch(function () { paint(was, n0); toast("Couldn't reach the server. Check your connection.", "error"); });
  }

  /* ---------- password: show/hide and strength ---------- */
  function strength(v) {
    if (!v) return 0;
    if (v.length < 10) return 1;
    var s = 0;
    if (v.length >= 14) s++;
    if (/[a-z]/.test(v) && /[A-Z]/.test(v)) s++;
    if (/\d/.test(v)) s++;
    if (/[^A-Za-z0-9]/.test(v)) s++;
    return s >= 2 ? 3 : 2;
  }
  var strengthText = ["Use 10 or more characters", "Too short. Keep going", "Okay. A bit longer is better", "Strong. Nice one"];
  function paintMeter(input) {
    var m = $("[data-meter]"); if (!m) return;
    var lvl = strength(input.value); m.dataset.level = lvl; $("span", m).textContent = strengthText[lvl];
  }

  /* ---------- message list, proposals: refresh themselves ---------- */
  var regionBusy = false;
  function pollRegions() {
    var regions = $$("[data-region]");
    if (!regions.length || regionBusy || document.hidden) return;
    regionBusy = true;
    Promise.all(regions.map(function (el) {
      var src = el.dataset.src;
      return fetch(src || location.href, { credentials: "same-origin", headers: { "X-Kyto": "poll" } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var tmp = document.createElement("div");
          if (src) { tmp.innerHTML = html; }
          else {
            var doc = new DOMParser().parseFromString(html, "text/html");
            var fresh = $('[data-region="' + el.dataset.region + '"]', doc);
            if (!fresh) return;
            tmp.innerHTML = fresh.innerHTML;
          }
          if (norm(tmp.innerHTML) !== norm(el.innerHTML)) el.innerHTML = tmp.innerHTML;
        })
        .catch(function () {});
    })).then(function () { regionBusy = false; });
  }
  onPage(function () { if ($$("[data-region]").length) every(pollRegions, 8000); });

  /* ---------- inbox badge: asks every 20s ---------- */
  function setBadge(n) {
    $$("[data-inbox-link]").forEach(function (a) {
      var b = $("[data-inbox-badge]", a), host = $(".ic", a) || a;
      if (n > 0) {
        if (!b) { b = document.createElement("i"); b.className = "badge-n " + ($(".ic", a) ? "nav-badge" : "icon-n"); b.setAttribute("data-inbox-badge", ""); host.appendChild(b); }
        b.textContent = n;
      } else if (b) { b.remove(); }
    });
  }
  setInterval(function () {
    if (document.hidden || !$("[data-inbox-link]")) return;
    fetch("/api/unread/", { credentials: "same-origin", headers: { "X-Kyto": "poll" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) setBadge(j.count); })
      .catch(function () {});
  }, 20000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { chatState.active = Date.now(); pollChat().then(scheduleChat); pollRegions(); } });

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
    if (f.classList.contains("kudos-form")) { e.preventDefault(); toggleKudos(f); return; }
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
    $$("[data-textsize]").forEach(function (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); });
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
        navigator.clipboard.writeText(url).then(function () { toast("Link copied"); });
      }
      return;
    }

    var copy = e.target.closest && e.target.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(location.href.split("#")[0]).then(function () {
        toast("Link copied");
        var m = copy.closest("[data-menu]"); if (m) m.open = false;
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

    var heartBtn = e.target.closest && e.target.closest("[data-heart]");
    if (heartBtn) { toggleHeart(heartBtn.closest(".bubble")); return; }

    var jumpBtn = e.target.closest && e.target.closest("[data-jump]");
    if (jumpBtn) { var cj = chatEl(); if (cj) toBottom(cj, true); hideJump(); return; }

    var failed = e.target.closest && e.target.closest(".bubble.failed");
    if (failed) { var cf = $(".composer"); if (cf) sendMessage(cf, failed); return; }

    var dmEl = $(".dm");
    if (dmEl) {
      if (e.target.closest && e.target.closest("[data-toggle-details]")) { dmEl.classList.toggle("details-open"); return; }
      if (dmEl.classList.contains("details-open") && !(e.target.closest && e.target.closest(".deal-side"))) dmEl.classList.remove("details-open");
    }

    var pw = e.target.closest && e.target.closest("[data-pw]");
    if (pw) {
      var inp = $("input", pw.parentNode), show = inp.type === "password";
      inp.type = show ? "text" : "password"; pw.textContent = show ? "Hide" : "Show";
      pw.setAttribute("aria-pressed", show ? "true" : "false"); pw.setAttribute("aria-label", show ? "Hide password" : "Show password");
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

    $$("[data-menu]").forEach(function (m) { if (m.open && !m.contains(e.target)) m.open = false; });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") $$("[data-menu]").forEach(function (m) { m.open = false; });
    var t = e.target;
    if (e.key === "Enter" && !e.shiftKey && t.matches && t.matches("[data-grow]") && window.matchMedia("(min-width: 821px)").matches) {
      e.preventDefault(); if (t.form) t.form.requestSubmit();
    }
  });

  document.addEventListener("input", function (e) {
    var t = e.target;
    if (t.matches && t.matches("[data-grow]")) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; }
    if (t.id) $$('[data-count-for="' + t.id + '"]').forEach(updateCounter);
    if (t.id === "id_password1") paintMeter(t);
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
