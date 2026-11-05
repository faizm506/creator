(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Hero: a sample leaderboard that re-ranks itself */
  var demo = document.querySelector("[data-demo]");
  if (demo) {
    var list = demo.querySelector(".demo-list");
    var H = 60;
    var people = [
      { name: "Aarav Shah", handle: "aarav.eats", score: 78.4, av: 3 },
      { name: "Neel Trivedi", handle: "neel.bites", score: 74.9, av: 8 },
      { name: "Diya Desai", handle: "diya.cooks", score: 71.2, av: 1 },
      { name: "Mira Patel", handle: "mira.tastes", score: 69.8, av: 9 },
      { name: "Kabir Mehta", handle: "kabir.snacks", score: 66.5, av: 4 },
      { name: "Anaya Joshi", handle: "anaya.dines", score: 63.1, av: 5 }
    ];
    list.style.setProperty("--n", people.length);
    people.forEach(function (p) {
      var r = document.createElement("div");
      r.className = "d-row";
      var n = document.createElement("span"); n.className = "n";
      var a = document.createElement("span"); a.className = "avatar av-" + p.av; a.textContent = p.name[0];
      a.style.width = a.style.height = "38px"; a.style.fontSize = "15px";
      var w = document.createElement("span"); w.className = "who";
      w.appendChild(document.createTextNode(p.name));
      var h = document.createElement("span"); h.textContent = "@" + p.handle; w.appendChild(h);
      var s = document.createElement("span"); s.className = "s";
      r.append(n, a, w, s);
      list.appendChild(r);
      p.el = r; p.n = n; p.s = s;
    });

    function render(animate) {
      var sorted = people.slice().sort(function (x, y) { return y.score - x.score; });
      sorted.forEach(function (p, i) {
        var moved = p.rank !== undefined && p.rank !== i;
        p.rank = i;
        p.el.style.transform = "translateY(" + i * H + "px)";
        p.n.textContent = i + 1;
        p.s.textContent = p.score.toFixed(1);
        if (animate && moved) {
          p.el.classList.add("moved");
          setTimeout(function () { p.el.classList.remove("moved"); }, 1400);
        }
      });
    }
    render(false);

    if (!reduce) {
      setInterval(function () {
        var i = Math.floor(Math.random() * people.length);
        var j = (i + 1 + Math.floor(Math.random() * (people.length - 1))) % people.length;
        people[i].score += 3 + Math.random() * 6;
        people[j].score -= 1 + Math.random() * 3;
        people.forEach(function (p) { p.score = Math.min(97, Math.max(45, p.score)); });
        render(true);
      }, 2600);
    }
  }

  /* Boost page: show the QR for the selected plan */
  var boost = document.querySelector("[data-boost]");
  if (boost) {
    var radios = boost.querySelectorAll("input[data-plan]");
    var panels = boost.querySelectorAll("[data-pay]");
    var sync = function () {
      var chosen = boost.querySelector("input[data-plan]:checked");
      panels.forEach(function (p) { p.hidden = !chosen || p.dataset.pay !== chosen.value; });
    };
    radios.forEach(function (r) { r.addEventListener("change", sync); });
    sync();
  }

  /* Toasts fade out on their own */
  document.querySelectorAll(".toast").forEach(function (t, i) {
    setTimeout(function () { t.classList.add("out"); setTimeout(function () { t.remove(); }, 450); }, 5000 + i * 600);
  });
})();

(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Interactive Ahmedabad scene */
  var scene = document.querySelector("[data-scene]");
  if (scene) {
    var lms = Array.prototype.slice.call(scene.querySelectorAll(".lm"));
    var cap = scene.querySelector(".scene-cap");
    var nameEl = scene.querySelector("[data-cap-name]");
    var noteEl = scene.querySelector("[data-cap-note]");
    var link = scene.querySelector("[data-cap-link]");
    var touched = false, idx = -1;
    var pick = function (g) {
      lms.forEach(function (x) { x.classList.toggle("on", x === g); });
      nameEl.textContent = g.dataset.name;
      noteEl.textContent = g.dataset.note;
      link.href = g.dataset.href;
      link.textContent = "See " + g.dataset.label + " creators";
      cap.classList.remove("swap"); void cap.offsetWidth; cap.classList.add("swap");
    };
    lms.forEach(function (g, i) {
      g.addEventListener("click", function () { touched = true; idx = i; pick(g); });
      g.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); touched = true; pick(g); }
      });
    });
    if (!reduce) {
      setInterval(function () {
        if (touched || document.hidden) return;
        idx = (idx + 1) % lms.length; pick(lms[idx]);
      }, 4200);
      scene.addEventListener("pointermove", function (e) {
        var r = scene.getBoundingClientRect();
        scene.style.setProperty("--px", ((e.clientX - r.left) / r.width - 0.5).toFixed(3));
      });
      scene.addEventListener("pointerleave", function () { scene.style.setProperty("--px", 0); });
    }
  }

  /* Count-up numbers when they scroll into view */
  var counters = document.querySelectorAll("[data-count]");
  var fmt = function (n, mode) {
    if (mode === "compact") {
      if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
      if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    }
    return Math.round(n).toLocaleString("en-IN");
  };
  if (counters.length && "IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        var el = en.target, to = +el.dataset.count, mode = el.dataset.format, t0 = null;
        var step = function (t) {
          t0 = t0 || t;
          var p = Math.min(1, (t - t0) / 1100), e = 1 - Math.pow(1 - p, 3);
          el.textContent = fmt(to * e, mode);
          if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }, { threshold: 0.4 });
    counters.forEach(function (c) { io.observe(c); });
  }

  /* Stagger rows, and live filter on the leaderboard */
  document.querySelectorAll("[data-rows] .row, [data-rows] .ccard, [data-rows] .thread").forEach(function (r, i) { r.style.setProperty("--i", Math.min(i, 12)); });
  var live = document.querySelector("[data-live]");
  if (live) {
    live.addEventListener("input", function () {
      var q = live.value.trim().toLowerCase();
      document.querySelectorAll("[data-rows] .row").forEach(function (r) {
        r.hidden = q && r.dataset.search.indexOf(q) === -1;
      });
    });
  }

  /* Copy profile link (every [data-copy] button) */
  document.querySelectorAll("[data-copy]").forEach(function (copy) {
    if (!navigator.clipboard) { copy.hidden = true; return; }
    copy.addEventListener("click", function () {
      navigator.clipboard.writeText(location.href.split("#")[0]).then(function () {
        var old = copy.textContent; copy.textContent = "Link copied";
        setTimeout(function () { copy.textContent = old; }, 1800);
      });
    });
  });
})();

(function () {
  "use strict";
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Score ring fills in; progress bars grow from zero */
  var ring = document.querySelector(".ring-fg");
  if (ring) {
    var C = 2 * Math.PI * 58, s = parseFloat(ring.dataset.score) || 0;
    ring.style.strokeDasharray = C;
    ring.style.strokeDashoffset = C;
    setTimeout(function () { ring.style.strokeDashoffset = C * (1 - Math.min(100, s) / 100); }, reduce ? 0 : 250);
  }
  document.querySelectorAll("progress[data-anim]").forEach(function (el, i) {
    if (reduce) return;
    var v = el.value; el.value = 0;
    setTimeout(function () { el.value = v; }, 300 + i * 90);
  });

  /* Reels load only when tapped: faster pages, and Instagram gets no data until you choose to play */
  document.querySelectorAll(".reel-face").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var src = btn.dataset.embed || "";
      if (src.indexOf("https://www.instagram.com/") !== 0) return;
      var f = document.createElement("iframe");
      f.src = src; f.loading = "lazy"; f.title = btn.getAttribute("aria-label") || "Instagram reel";
      f.setAttribute("allowfullscreen", ""); f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups allow-presentation"); f.setAttribute("scrolling", "no");
      f.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      btn.replaceWith(f);
    });
  });

})();

(function () {
  "use strict";

  /* Settings: highlight the section you're reading */
  var nav = document.querySelector(".st-nav");
  if (nav && "IntersectionObserver" in window) {
    var links = {};
    nav.querySelectorAll("a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        Object.keys(links).forEach(function (k) { links[k].classList.toggle("on", k === en.target.id); });
        var a = links[en.target.id];
        if (a && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: a.offsetLeft - 20, behavior: "smooth" });
      });
    }, { rootMargin: "-25% 0px -65% 0px" });
    document.querySelectorAll(".st-sec").forEach(function (s) { spy.observe(s); });
  }

  /* Confirm risky actions */
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!window.confirm(f.dataset.confirm)) e.preventDefault(); });
  });

  /* Chat: jump to newest message, grow the message box as you type */
  var chat = document.querySelector("[data-chat]");
  if (chat && chat.querySelectorAll(".bubble").length > 1) {
    if (chat.scrollHeight > chat.clientHeight + 5) { chat.scrollTop = chat.scrollHeight; }
    else { var end = document.getElementById("end"); if (end) end.scrollIntoView({ block: "end" }); }
  }
  document.querySelectorAll("[data-grow]").forEach(function (t) {
    var fit = function () { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; };
    t.addEventListener("input", fit);
    t.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && window.matchMedia("(min-width: 821px)").matches) { e.preventDefault(); t.form.requestSubmit(); }
    });
  });
})();

(function () {
  "use strict";
  /* Signup: switch labels and perks when you pick Creator or Brand */
  var su = document.querySelector("[data-signup]");
  if (!su) return;
  var text = {
    creator: { name: "Your name", handle: "Your Instagram handle", ph: "e.g. Aarav Shah" },
    brand: { name: "Brand name", handle: "Brand's Instagram handle", ph: "e.g. Chai Corner Cafe" }
  };
  var nameL = su.querySelector('label[for="id_display_name"]'), handleL = su.querySelector('label[for="id_username"]');
  var nameIn = su.querySelector("#id_display_name");
  var sync = function () {
    var r = su.querySelector('input[name="role"]:checked'), role = r ? r.value : "creator";
    if (!text[role]) return;
    if (nameL) nameL.textContent = text[role].name;
    if (handleL) handleL.textContent = text[role].handle;
    if (nameIn) nameIn.placeholder = text[role].ph;
    su.querySelectorAll("[data-perks]").forEach(function (u) { u.hidden = u.dataset.perks !== role; });
  };
  su.querySelectorAll('input[name="role"]').forEach(function (r) { r.addEventListener("change", sync); });
  sync();
})();

(function () {
  "use strict";

  /* Bigger text button (remembered on this device) */
  var KEY = "kyto-big-text", root = document.documentElement;
  var btn = document.querySelector("[data-textsize]");
  var read = function () { try { return localStorage.getItem(KEY) === "1"; } catch (e) { return false; } };
  var apply = function (on) {
    root.classList.toggle("big", on);
    if (btn) { btn.setAttribute("aria-pressed", on ? "true" : "false"); btn.setAttribute("aria-label", on ? "Make text smaller" : "Make text bigger"); }
  };
  apply(read());
  if (btn) btn.addEventListener("click", function () {
    var on = !root.classList.contains("big");
    apply(on);
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { /* storage blocked: still works for this visit */ }
  });

  /* Quick reply chips fill the message box (you still press send) */
  document.querySelectorAll("[data-quick]").forEach(function (b) {
    b.addEventListener("click", function () {
      var t = document.querySelector(".composer textarea");
      if (!t) return;
      t.value = b.dataset.quick; t.focus(); t.dispatchEvent(new Event("input"));
    });
  });

  /* Character counters */
  document.querySelectorAll("[data-count-for]").forEach(function (c) {
    var t = document.getElementById(c.dataset.countFor);
    if (!t) return;
    var up = function () { c.textContent = t.value.length + " / " + (t.maxLength > 0 ? t.maxLength : ""); };
    t.addEventListener("input", up); up();
  });

  /* About page: switch between creator and brand steps */
  var tabs = document.querySelector("[data-tabs]");
  if (tabs) {
    tabs.classList.add("js-tabs");
    var buttons = tabs.querySelectorAll("[data-tab]"), panels = tabs.querySelectorAll("[data-panel]");
    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        buttons.forEach(function (x) { var on = x === b; x.classList.toggle("on", on); x.setAttribute("aria-selected", on ? "true" : "false"); });
        panels.forEach(function (p) { p.hidden = p.dataset.panel !== b.dataset.tab; });
      });
    });
  }
})();

(function () {
  "use strict";

  /* Account menu closes when you tap elsewhere or press Escape */
  var menu = document.querySelector("[data-menu]");
  if (menu) {
    document.addEventListener("click", function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") menu.open = false; });
  }

  /* Google Map loads only when tapped (faster page, nothing sent to Google until you ask) */
  document.querySelectorAll("[data-map]").forEach(function (box) {
    var btn = box.querySelector(".map-face");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var src = box.dataset.embed || "";
      if (src.indexOf("https://www.google.com/maps") !== 0) return;
      var f = document.createElement("iframe");
      f.src = src; f.loading = "lazy"; f.title = "Map of the shop";
      f.setAttribute("referrerpolicy", "no-referrer-when-downgrade");
      f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
      btn.replaceWith(f);
    });
  });

  /* Tap a shop photo to see it big */
  var lb = document.querySelector("[data-lightbox]");
  if (lb && typeof lb.showModal === "function") {
    var big = lb.querySelector("img");
    document.querySelectorAll(".shot").forEach(function (s) {
      s.addEventListener("click", function () { big.src = s.dataset.full; lb.showModal(); });
    });
    lb.querySelector(".lb-close").addEventListener("click", function () { lb.close(); });
    lb.addEventListener("click", function (e) { if (e.target === lb) lb.close(); });
  }
})();

(function () {
  "use strict";
  /* Share: opens the phone's share sheet when it exists, otherwise copies the link */
  document.querySelectorAll("[data-share]").forEach(function (b) {
    b.addEventListener("click", function () {
      var url = new URL(b.dataset.share, window.location.origin).href, title = b.dataset.title || document.title;
      if (navigator.share) { navigator.share({ title: title, url: url }).catch(function () {}); return; }
      if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(function () {
          var l = b.querySelector("span"), old = l ? l.textContent : "";
          if (l) { l.textContent = "Copied!"; setTimeout(function () { l.textContent = old; }, 1600); }
        });
      }
    });
  });
})();
