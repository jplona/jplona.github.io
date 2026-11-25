(() => {
  const searchInput = document.getElementById("recipe-search");
  const clearBtn = document.getElementById("clear-search");
  const resultCount = document.getElementById("result-count");
  const noResults = document.getElementById("no-results");
  const pillsWrap = document.getElementById("category-pills");
  const searchDataEl = document.getElementById("search-data");

  if (searchInput && pillsWrap && searchDataEl) {
    const searchData = JSON.parse(searchDataEl.textContent);
    const sections = Array.from(document.querySelectorAll("[data-cat-section]"));
    const cards = Array.from(document.querySelectorAll("[data-recipe-id]"));
    let activeCat = "all";

    function applyFilter() {
      const q = searchInput.value.trim().toLowerCase();
      const terms = q ? q.split(/\s+/).filter(Boolean) : [];
      if (clearBtn) clearBtn.hidden = !q;

      const matchedIds = new Set();
      for (const card of cards) {
        const id = card.getAttribute("data-recipe-id");
        const sec = card.closest("[data-cat-section]");
        const secCat = sec ? sec.getAttribute("data-cat-section") : "";
        const entry = searchData[id];
        const catMatch = activeCat === "all" || secCat === activeCat;
        let textMatch = true;
        if (terms.length && entry) {
          textMatch = terms.every((t) => entry.b.includes(t));
        }
        const visible = catMatch && textMatch;
        card.hidden = !visible;
        if (visible) matchedIds.add(id);
      }

      for (const sec of sections) {
        const secCat = sec.getAttribute("data-cat-section");
        const visibleInSec = Array.from(sec.querySelectorAll("[data-recipe-id]")).filter((c) => !c.hidden);
        const showSec = (activeCat === "all" || secCat === activeCat) && visibleInSec.length > 0;
        sec.hidden = !showSec;
        const cntEl = sec.querySelector(".section-count");
        if (cntEl) cntEl.textContent = String(visibleInSec.length);
      }

      const n = matchedIds.size;
      if (resultCount) {
        if (!q && activeCat === "all") {
          resultCount.textContent = `Showing all ${Object.keys(searchData).length} recipes`;
        } else {
          resultCount.textContent = `Showing ${n} ${n === 1 ? "recipe" : "recipes"}`;
        }
      }
      if (noResults) noResults.hidden = n > 0;
    }

    searchInput.addEventListener("input", applyFilter);
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        searchInput.value = "";
        applyFilter();
        searchInput.focus();
      });
    }

    pillsWrap.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-cat]");
      if (!btn) return;
      activeCat = btn.getAttribute("data-cat") || "all";
      for (const p of pillsWrap.querySelectorAll(".cat-pill")) {
        p.classList.toggle("is-active", p === btn);
      }
      applyFilter();
    });

    // Support direct category anchors like /#cat-cookies
    const hash = window.location.hash;
    if (hash && hash.startsWith("#cat-")) {
      const targetCat = hash.slice(5);
      const pill = pillsWrap.querySelector(`[data-cat="${targetCat}"]`);
      if (pill) {
        activeCat = targetCat;
        for (const p of pillsWrap.querySelectorAll(".cat-pill")) {
          p.classList.toggle("is-active", p === pill);
        }
        applyFilter();
      }
    }
  }

  // Keep screen awake toggle on individual recipe pages
  const wakeBtn = document.getElementById("wake-lock-btn");
  if (wakeBtn && "wakeLock" in navigator) {
    let sentinel = null;
    wakeBtn.hidden = false;
    wakeBtn.setAttribute("aria-pressed", "false");

    async function toggleWakeLock() {
      if (sentinel) {
        await sentinel.release();
        sentinel = null;
        wakeBtn.setAttribute("aria-pressed", "false");
        wakeBtn.textContent = "Keep screen on";
        return;
      }
      try {
        sentinel = await navigator.wakeLock.request("screen");
        wakeBtn.setAttribute("aria-pressed", "true");
        wakeBtn.textContent = "Screen staying on";
        sentinel.addEventListener("release", () => {
          sentinel = null;
          wakeBtn.setAttribute("aria-pressed", "false");
          wakeBtn.textContent = "Keep screen on";
        });
      } catch (_err) {
        wakeBtn.hidden = true;
      }
    }

    wakeBtn.addEventListener("click", toggleWakeLock);
    document.addEventListener("visibilitychange", async () => {
      if (document.visibilityState === "visible" && wakeBtn.getAttribute("aria-pressed") === "true" && !sentinel) {
        try {
          sentinel = await navigator.wakeLock.request("screen");
        } catch (_err) {
          wakeBtn.setAttribute("aria-pressed", "false");
          wakeBtn.textContent = "Keep screen on";
        }
      }
    });
  }
})();
