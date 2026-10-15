/* 연결한의원 청주오창 — 공통 스크립트 */
(function () {
  "use strict";

  // ── 모바일 메뉴 ──────────────────────────────────────────────────────────
  var toggle = document.querySelector(".menu-toggle");
  var mobileNav = document.querySelector(".mobile-nav");
  if (toggle && mobileNav) {
    toggle.addEventListener("click", function () {
      var open = mobileNav.classList.toggle("open");
      toggle.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // ── 현재 페이지 내비 활성화 ───────────────────────────────────────────────
  var here = location.pathname.replace(/index\.html$/, "");
  document.querySelectorAll(".main-nav a").forEach(function (a) {
    var href = a.getAttribute("href");
    if (!href) return;
    var target = new URL(href, location.href).pathname.replace(/index\.html$/, "");
    if (target !== "/" && here.indexOf(target) === 0) a.classList.add("active");
  });

  // ── 스크롤 리빌 ─────────────────────────────────────────────────────────
  var reveals = document.querySelectorAll("[data-reveal]");
  if (/[?&]capture=1/.test(location.search)) {
    reveals.forEach(function (el) { el.classList.add("in"); });
  } else if ("IntersectionObserver" in window && reveals.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  // ── 카드 캐러셀 ─────────────────────────────────────────────────────────
  document.querySelectorAll("[data-carousel]").forEach(function (wrap) {
    var track = wrap.querySelector(".carousel");
    var prev = wrap.querySelector("[data-prev]");
    var next = wrap.querySelector("[data-next]");
    var dots = wrap.querySelector(".carousel-dots");
    var status = wrap.querySelector("[data-status]");
    if (!track) return;
    var items = Array.prototype.slice.call(track.children);

    function perView() {
      var first = items[0];
      if (!first) return 1;
      var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap) || 0;
      return Math.max(1, Math.round((track.clientWidth + gap) / (first.getBoundingClientRect().width + gap)));
    }
    function pages() { return Math.max(1, Math.ceil(items.length / perView())); }
    function current() {
      var first = items[0];
      var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap) || 0;
      var w = first.getBoundingClientRect().width + gap;
      return Math.round(track.scrollLeft / (w * perView()));
    }
    function goTo(page) {
      var first = items[0];
      var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap) || 0;
      var w = first.getBoundingClientRect().width + gap;
      track.scrollTo({ left: page * w * perView(), behavior: "smooth" });
    }
    function renderDots() {
      if (!dots) return;
      dots.innerHTML = "";
      var n = pages();
      for (var i = 0; i < n; i++) {
        var b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-label", (i + 1) + "페이지로 이동");
        (function (idx) { b.addEventListener("click", function () { goTo(idx); }); })(i);
        dots.appendChild(b);
      }
      update();
    }
    function update() {
      var c = current(), n = pages();
      if (dots) Array.prototype.forEach.call(dots.children, function (d, i) { d.classList.toggle("active", i === c); });
      if (prev) prev.disabled = c <= 0;
      if (next) next.disabled = c >= n - 1;
      if (status) status.textContent = (c + 1) + " / " + n + "페이지";
    }
    if (prev) prev.addEventListener("click", function () { goTo(Math.max(0, current() - 1)); });
    if (next) next.addEventListener("click", function () { goTo(Math.min(pages() - 1, current() + 1)); });
    var t;
    track.addEventListener("scroll", function () { clearTimeout(t); t = setTimeout(update, 80); });
    window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(renderDots, 120); });
    renderDots();
  });

  // ── 빠른 정보 검색 ───────────────────────────────────────────────────────
  var searchForm = document.querySelector("[data-search]");
  if (searchForm) {
    var input = searchForm.querySelector("input");
    var results = document.querySelector("[data-search-results]");
    var indexPromise;
    results.setAttribute("aria-live", "polite");
    function norm(s) { return (s || "").toLowerCase().replace(/\s+/g, ""); }
    function loadIndex() {
      if (!indexPromise) {
        indexPromise = fetch(searchForm.getAttribute("data-index-url"))
          .then(function (response) {
            if (!response.ok) throw new Error("Search index unavailable");
            return response.json();
          })
          .then(function (index) {
            if (!Array.isArray(index)) throw new Error("Invalid search index");
            return index;
          })
          .catch(function (error) {
            indexPromise = null;
            throw error;
          });
      }
      return indexPromise;
    }
    function message(text) {
      results.innerHTML = "";
      var p = document.createElement("p");
      p.className = "search-empty";
      p.textContent = text;
      results.appendChild(p);
    }
    function showHits(index, q) {
      results.innerHTML = "";
      var hits = index.filter(function (it) {
        return norm(it.title).indexOf(q) > -1 || norm(it.keywords).indexOf(q) > -1;
      }).slice(0, 8);
      if (!hits.length) {
        message("검색 결과가 없습니다. 전화(043-715-3688)로 문의해 주세요.");
        return;
      }
      hits.forEach(function (h) {
        var a = document.createElement("a"); a.href = h.url;
        var s1 = document.createElement("span"); s1.textContent = h.title;
        var s2 = document.createElement("span"); s2.textContent = h.type;
        a.appendChild(s1); a.appendChild(s2); results.appendChild(a);
      });
    }
    function run() {
      var q = norm(input.value);
      results.innerHTML = "";
      results.setAttribute("aria-busy", "false");
      if (!q) return;
      results.setAttribute("aria-busy", "true");
      message("검색 정보를 불러오는 중입니다.");
      loadIndex().then(function (index) {
        if (q !== norm(input.value)) return;
        showHits(index, q);
        results.setAttribute("aria-busy", "false");
      }).catch(function () {
        if (q !== norm(input.value)) return;
        results.setAttribute("aria-busy", "false");
        message("검색 정보를 불러오지 못했습니다. 잠시 후 다시 검색하거나 전화(043-715-3688)로 문의해 주세요.");
      });
    }
    searchForm.addEventListener("submit", function (e) { e.preventDefault(); run(); });
    input.addEventListener("input", run);
  }

  // ── 모바일: 긴 목록은 첫 분류만 펼치고 나머지는 접기 ─────────────────────
  var groups = document.querySelectorAll("details[data-group]");
  if (groups.length > 2 && window.innerWidth <= 900 && !/[?&]capture=1/.test(location.search)) {
    groups.forEach(function (g, i) { if (i > 0) g.removeAttribute("open"); });
  }
  // 분류 칩을 누르면 해당 그룹을 펼친 뒤 이동
  function openTarget() {
    var id = location.hash.slice(1);
    if (!id) return;
    var el = document.getElementById(id);
    if (el && el.tagName === "DETAILS") el.setAttribute("open", "");
  }
  if (groups.length) {
    document.querySelectorAll(".cat-nav a").forEach(function (a) {
      a.addEventListener("click", function () {
        var el = document.getElementById(a.getAttribute("href").slice(1));
        if (el && el.tagName === "DETAILS") el.setAttribute("open", "");
      });
    });
    window.addEventListener("hashchange", openTarget);
    openTarget();
  }

  // ── 맨 위로 버튼 (모바일) ────────────────────────────────────────────────
  if (window.innerWidth <= 900) {
    var top = document.createElement("button");
    top.type = "button";
    top.className = "to-top";
    top.setAttribute("aria-label", "맨 위로");
    top.textContent = "↑";
    top.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: "smooth" }); });
    document.body.appendChild(top);
    var tick;
    window.addEventListener("scroll", function () {
      clearTimeout(tick);
      tick = setTimeout(function () { top.classList.toggle("show", window.scrollY > 700); }, 80);
    }, { passive: true });
  }

  // ── 숫자 카운트업 ─────────────────────────────────────────────────────────
  var counters = document.querySelectorAll("[data-count]");
  function countUp(el) {
    var end = parseInt(el.getAttribute("data-count"), 10) || 0, start = 0, t0 = null, dur = 1400;
    function step(ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / dur), v = Math.round(start + (end - start) * (1 - Math.pow(1 - p, 3)));
      el.textContent = v.toLocaleString("ko-KR");
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  if (counters.length && "IntersectionObserver" in window && !/[?&]capture=1/.test(location.search)) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { countUp(e.target); cio.unobserve(e.target); } });
    }, { threshold: 0.4 });
    counters.forEach(function (el) { cio.observe(el); });
  }

  // ── FAQ: 하나 열면 나머지 닫기 (같은 그룹 내) ─────────────────────────────
  document.querySelectorAll(".faq[data-single]").forEach(function (group) {
    group.querySelectorAll("details").forEach(function (d) {
      d.addEventListener("toggle", function () {
        if (!d.open) return;
        group.querySelectorAll("details[open]").forEach(function (o) { if (o !== d) o.open = false; });
      });
    });
  });
})();
