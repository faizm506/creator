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
  document.querySelectorAll("[data-rows] .row").forEach(function (r, i) { r.style.setProperty("--i", Math.min(i, 12)); });
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
      f.setAttribute("allowfullscreen", ""); f.setAttribute("scrolling", "no");
      f.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      btn.replaceWith(f);
    });
  });

})();
