#!/usr/bin/env python3
"""Zero-dependency static site generator for Grandma Mary's Recipes."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

CATEGORY_ORDER = [
    "Appetizers",
    "Beverages",
    "Breads & Rolls",
    "Cakes",
    "Condiments",
    "Confection",
    "Cookies",
    "Desserts",
    "Frosting",
    "Meats",
    "Pasta",
    "Pies",
    "Poultry",
    "Quiche",
    "Salads",
    "Seafood",
    "Soups",
    "Vegetables",
]

SITE_TITLE = "Grandma Mary's Recipes"
SITE_URL = "https://recipes.plona.family"


@dataclass
class IngredientBlock:
    heading: str | None = None
    items: list[str] = field(default_factory=list)
    subnotes: list[str] = field(default_factory=list)


@dataclass
class RecipeDoc:
    title: str
    slug: str
    categories: list[str]
    primary_cat_slug: str
    author: str
    prep_time: str
    servings: str
    source: str
    missing: bool
    ingredient_blocks: list[IngredientBlock]
    instructions: list[str]
    notes: list[str]
    missing_text: str

    @property
    def url_path(self) -> str:
        return f"/recipes/{self.primary_cat_slug}/{self.slug}/"

    @property
    def search_blob(self) -> str:
        parts = [self.title, *self.categories, self.author, self.source]
        for blk in self.ingredient_blocks:
            if blk.heading:
                parts.append(blk.heading)
            parts.extend(blk.items)
        parts.extend(self.instructions)
        parts.extend(self.notes)
        return " ".join(p for p in parts if p).lower()


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    text = re.sub(r"['\".,]", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", text)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_markdown_recipe(path: Path) -> RecipeDoc:
    raw = path.read_text(encoding="utf-8")
    header_part, _, body_part = raw.partition("\n\n")
    meta: dict[str, str] = {}
    for line in header_part.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()

    title = meta["Title"]
    categories = [c.strip() for c in meta["Categories"].split(",") if c.strip()]
    author = meta.get("Author", "Mary C. Plona")
    prep_time = meta.get("Prep Time", "")
    servings = meta.get("Servings", "")
    source = meta.get("Source", "")
    missing = meta.get("Missing", "false").lower() == "true"

    sections: dict[str, list[str]] = {}
    cur_sec: str | None = None
    for line in body_part.splitlines():
        if line.startswith("## "):
            cur_sec = line[3:].strip()
            sections[cur_sec] = []
        elif cur_sec is not None:
            sections[cur_sec].append(line)

    ingredient_blocks: list[IngredientBlock] = []
    if "Ingredients" in sections:
        cur_blk = IngredientBlock()
        for line in sections["Ingredients"]:
            s = line.strip()
            if not s:
                continue
            if s.startswith("### "):
                if cur_blk.heading or cur_blk.items or cur_blk.subnotes:
                    ingredient_blocks.append(cur_blk)
                cur_blk = IngredientBlock(heading=s[4:].strip())
            elif s.startswith("- "):
                cur_blk.items.append(s[2:].strip())
            elif s.startswith("*") and s.endswith("*") and len(s) > 2:
                cur_blk.subnotes.append(s[1:-1].strip())
        if cur_blk.heading or cur_blk.items or cur_blk.subnotes:
            ingredient_blocks.append(cur_blk)

    instructions = [
        p.strip()
        for p in "\n".join(sections.get("Instructions", [])).split("\n\n")
        if p.strip()
    ]
    notes = [
        p.strip()
        for p in "\n".join(sections.get("Notes", [])).split("\n\n")
        if p.strip()
    ]
    missing_text = "\n".join(sections.get("Missing Card", [])).strip()

    return RecipeDoc(
        title=title,
        slug=path.stem,
        categories=categories,
        primary_cat_slug=slugify(categories[0]),
        author=author,
        prep_time=prep_time,
        servings=servings,
        source=source,
        missing=missing,
        ingredient_blocks=ingredient_blocks,
        instructions=instructions,
        notes=notes,
        missing_text=missing_text,
    )


def format_subtitle(author: str) -> str:
    if author.lower().endswith("recipe"):
        return author
    return f"From the kitchen of {author}"


def render_head(title: str, description: str, canonical_path: str) -> str:
    full_title = title if title == SITE_TITLE else f"{title} — {SITE_TITLE}"
    canon = f"{SITE_URL}{canonical_path}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(full_title)}</title>
  <meta name="description" content="{esc(description)}">
  <meta property="og:title" content="{esc(full_title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{esc(canon)}">
  <link rel="canonical" href="{esc(canon)}">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/style.css">
</head>"""


def render_ingredients_html(blocks: list[IngredientBlock], interactive: bool = True) -> str:
    chunks: list[str] = []
    for blk in blocks:
        if blk.heading:
            chunks.append(f'<h3 class="ingredient-group">{esc(blk.heading)}</h3>')
        if blk.items:
            chunks.append('<ul class="ingredient-list">')
            for item in blk.items:
                if interactive:
                    chunks.append(
                        '<li class="ingredient-item">'
                        '<label class="ingredient-check">'
                        '<input type="checkbox">'
                        f"<span>{esc(item)}</span>"
                        "</label>"
                        "</li>"
                    )
                else:
                    chunks.append(f'<li class="ingredient-item"><span>{esc(item)}</span></li>')
            chunks.append("</ul>")
        for sn in blk.subnotes:
            chunks.append(f'<p class="ingredient-subnote"><em>{esc(sn)}</em></p>')
    return "\n        ".join(chunks)


def render_recipe_article(r: RecipeDoc, interactive: bool = True, heading_tag: str = "h1", anchor_id: str = "") -> str:
    id_attr = f' id="{esc(anchor_id)}"' if anchor_id else ""
    subtitle = format_subtitle(r.author)

    meta_items: list[str] = []
    cat_links = ", ".join(
        f'<a href="/#cat-{esc(slugify(c))}">{esc(c)}</a>' if interactive else esc(c)
        for c in r.categories
    )
    meta_items.append(f"<div><dt>Category</dt><dd>{cat_links}</dd></div>")
    if r.prep_time:
        meta_items.append(f"<div><dt>Prep time</dt><dd>{esc(r.prep_time)}</dd></div>")
    if r.servings:
        meta_items.append(f"<div><dt>Servings</dt><dd>{esc(r.servings)}</dd></div>")
    if r.source:
        meta_items.append(f"<div><dt>Recipe from</dt><dd>{esc(r.source)}</dd></div>")

    if r.missing:
        body_html = f"""
      <div class="missing-card-body">
        <p class="missing-badge-lg">Missing Recipe Card</p>
        <p>{esc(r.missing_text)}</p>
        <p class="missing-prompt">Part of the family mystery! If anyone has Grandma Mary's physical index card for this recipe, let us know so we can add it to the collection.</p>
      </div>"""
    else:
        ings_html = render_ingredients_html(r.ingredient_blocks, interactive=interactive)
        inst_html = "\n        ".join(f"<p>{esc(p)}</p>" for p in r.instructions)
        notes_html = ""
        if r.notes:
            notes_ps = "\n          ".join(f"<p>{esc(n)}</p>" for n in r.notes)
            notes_html = f"""
      <aside class="recipe-notes">
        <h2>Family Note</h2>
        {notes_ps}
      </aside>"""
        body_html = f"""
      <div class="recipe-columns">
        <section class="ingredients-col">
          <h2>Ingredients</h2>
          {ings_html}
        </section>
        <section class="instructions-col">
          <h2>Instructions</h2>
          {inst_html}
          {notes_html}
        </section>
      </div>"""

    return f"""<article class="recipe-card{' is-missing' if r.missing else ''}"{id_attr}>
    <header class="card-header">
      <{heading_tag}>{esc(r.title)}</{heading_tag}>
      <p class="card-subtitle">{esc(subtitle)}</p>
      <dl class="card-meta">
        {''.join(meta_items)}
      </dl>
    </header>
    {body_html}
  </article>"""


def render_recipe_page(r: RecipeDoc) -> str:
    desc = (
        f"Missing recipe card from Grandma Mary's collection ({', '.join(r.categories)})."
        if r.missing
        else f"{r.title} recipe from the kitchen of {r.author} ({', '.join(r.categories)})."
    )
    primary_cat_slug = r.primary_cat_slug
    article = render_recipe_article(r, interactive=True, heading_tag="h1")
    return f"""{render_head(r.title, desc, r.url_path)}
<body class="page-recipe">
  <nav class="top-nav no-print" aria-label="Breadcrumb and actions">
    <div class="nav-links">
      <a class="nav-back" href="/">&larr; All Recipes</a>
      <a class="nav-cat" href="/#cat-{esc(primary_cat_slug)}">{esc(r.categories[0])}</a>
    </div>
    <div class="nav-actions">
      <button type="button" class="btn-secondary" id="wake-lock-btn" hidden>Keep screen on</button>
      <button type="button" class="btn-secondary" onclick="window.print()">Print</button>
    </div>
  </nav>
  <main class="container">
    {article}
  </main>
  <footer class="site-footer no-print">
    <p><a href="/">Plona Family Recipe Collection</a> &middot; <a href="/all/">View / Print All Cards</a></p>
  </footer>
  <script src="/assets/app.js" defer></script>
</body>
</html>
"""


def render_index_page(recipes: list[RecipeDoc]) -> str:
    by_cat: dict[str, list[RecipeDoc]] = {c: [] for c in CATEGORY_ORDER}
    for r in recipes:
        for c in r.categories:
            by_cat.setdefault(c, []).append(r)

    for c in by_cat:
        by_cat[c].sort(key=lambda x: x.title.lower())

    pill_html = ['<button type="button" class="cat-pill is-active" data-cat="all">All <span class="pill-count">' f"{len(recipes)}</span></button>"]
    for c in CATEGORY_ORDER:
        cnt = len(by_cat.get(c, []))
        if cnt:
            c_slug = slugify(c)
            pill_html.append(
                f'<button type="button" class="cat-pill" data-cat="{esc(c_slug)}">'
                f'{esc(c)} <span class="pill-count">{cnt}</span></button>'
            )

    sections_html: list[str] = []
    for c in CATEGORY_ORDER:
        cat_recipes = by_cat.get(c, [])
        if not cat_recipes:
            continue
        c_slug = slugify(c)
        cards_html: list[str] = []
        for r in cat_recipes:
            all_cat_slugs = " ".join(slugify(cat) for cat in r.categories)
            badges: list[str] = []
            if r.missing:
                badges.append('<span class="badge badge-missing">Missing card</span>')
            else:
                if r.prep_time:
                    badges.append(f'<span class="badge">{esc(r.prep_time)}</span>')
                if r.servings:
                    badges.append(f'<span class="badge">Serves {esc(r.servings)}</span>')
                if r.source:
                    badges.append(f'<span class="badge badge-source">From {esc(r.source)}</span>')
                elif r.author != "Mary C. Plona":
                    badges.append(f'<span class="badge badge-source">{esc(r.author)}</span>')
                if len(r.categories) > 1:
                    other = [x for x in r.categories if x != c]
                    badges.append(f'<span class="badge">Also in {esc(", ".join(other))}</span>')

            cards_html.append(
                f'<li class="recipe-link-card{" is-missing" if r.missing else ""}" '
                f'data-recipe-id="{esc(r.url_path)}" data-cats="{esc(all_cat_slugs)}">'
                f'<a href="{esc(r.url_path)}">'
                f'<span class="recipe-link-title">{esc(r.title)}</span>'
                f'<span class="recipe-link-meta">{"".join(badges)}</span>'
                f"</a></li>"
            )
        sections_html.append(
            f'<section class="category-section" id="cat-{esc(c_slug)}" data-cat-section="{esc(c_slug)}">'
            f'<div class="section-head"><h2>{esc(c)}</h2><span class="section-count">{len(cat_recipes)}</span></div>'
            f'<ul class="recipe-grid">'
            + "\n        ".join(cards_html)
            + "</ul></section>"
        )

    search_index = {
        r.url_path: {
            "t": r.title,
            "c": [slugify(c) for c in r.categories],
            "b": r.search_blob,
        }
        for r in recipes
    }
    search_json = json.dumps(search_index, separators=(",", ":")).replace("</", "<\\/")

    complete_cnt = sum(1 for r in recipes if not r.missing)
    missing_cnt = len(recipes) - complete_cnt

    return f"""{render_head(SITE_TITLE, "Grandma Mary's family recipe collection — digitized from her original Microsoft Works recipe cards.", "/")}
<body class="page-home">
  <header class="hero">
    <div class="hero-inner">
      <p class="hero-kicker">Plona Family Recipe Collection</p>
      <h1>{esc(SITE_TITLE)}</h1>
      <p class="hero-sub">From the kitchen of Mary C. Plona &middot; {complete_cnt} digitized cards &amp; {missing_cnt} missing mysteries</p>
      <div class="hero-links">
        <a href="/all/" class="btn-outline">Print / View All Cards</a>
      </div>
    </div>
  </header>

  <main class="container">
    <section class="controls no-print" aria-label="Search and filter recipes">
      <div class="search-box">
        <label for="recipe-search" class="sr-only">Search recipes or ingredients</label>
        <input type="search" id="recipe-search" placeholder="Search {len(recipes)} recipes, ingredients, or categories&hellip;" autocomplete="off">
        <button type="button" id="clear-search" class="clear-btn" aria-label="Clear search" hidden>&times;</button>
      </div>
      <div class="filter-status">
        <span id="result-count">Showing all {len(recipes)} recipes</span>
      </div>
      <div class="category-pills" id="category-pills" role="group" aria-label="Filter by category">
        {"".join(pill_html)}
      </div>
    </section>

    <p id="no-results" class="empty-state" hidden>No recipes matched your search. Try another ingredient or clear the filter.</p>

    <div id="catalog">
      {"".join(sections_html)}
    </div>
  </main>

  <footer class="site-footer">
    <p>Converted from Grandma Mary's original Microsoft Works (<code>.wdb</code>) recipe cards &middot; <a href="/all/">Full Printable Edition</a></p>
  </footer>

  <script id="search-data" type="application/json">{search_json}</script>
  <script src="/assets/app.js" defer></script>
</body>
</html>
"""


def render_all_page(recipes: list[RecipeDoc]) -> str:
    by_cat: dict[str, list[RecipeDoc]] = {c: [] for c in CATEGORY_ORDER}
    for r in recipes:
        for c in r.categories:
            by_cat.setdefault(c, []).append(r)
    for c in by_cat:
        by_cat[c].sort(key=lambda x: x.title.lower())

    toc_groups: list[str] = []
    for c in CATEGORY_ORDER:
        cat_recipes = by_cat.get(c, [])
        if not cat_recipes:
            continue
        links = []
        for r in cat_recipes:
            anchor = f"recipe-{r.primary_cat_slug}-{r.slug}"
            if r.missing:
                links.append(f'<li><a href="{esc(r.url_path)}">{esc(r.title)}</a> <span class="badge badge-missing">Missing card</span></li>')
            else:
                links.append(f'<li><a href="#{esc(anchor)}">{esc(r.title)}</a></li>')
        toc_groups.append(
            f'<div class="toc-group"><h3>{esc(c)}</h3><ul>{"".join(links)}</ul></div>'
        )

    complete = [r for r in recipes if not r.missing]
    complete.sort(key=lambda r: (CATEGORY_ORDER.index(r.categories[0]), r.title.lower()))
    cards_html = [
        render_recipe_article(r, interactive=False, heading_tag="h2", anchor_id=f"recipe-{r.primary_cat_slug}-{r.slug}")
        for r in complete
    ]

    missing_list = [r for r in recipes if r.missing]
    missing_items = "".join(
        f'<li><a href="{esc(r.url_path)}">{esc(r.title)}</a> ({esc(r.categories[0])})</li>'
        for r in missing_list
    )

    return f"""{render_head("All Recipes (Printable Edition)", "All 144 complete Grandma Mary recipes in one printable view.", "/all/")}
<body class="page-all">
  <nav class="top-nav no-print">
    <div class="nav-links">
      <a class="nav-back" href="/">&larr; Back to Search</a>
    </div>
    <div class="nav-actions">
      <button type="button" class="btn-secondary" onclick="window.print()">Print All</button>
    </div>
  </nav>

  <main class="container">
    <header class="all-header">
      <h1>{esc(SITE_TITLE)}</h1>
      <p class="card-subtitle">From the kitchen of Mary C. Plona &middot; Complete Printable Edition ({len(complete)} recipes)</p>
    </header>

    <section class="toc-panel">
      <h2>Table of Contents</h2>
      <div class="toc-grid">
        {"".join(toc_groups)}
      </div>
    </section>

    <div class="all-cards">
      {"".join(cards_html)}
    </div>

    <section class="recipe-card is-missing">
      <header class="card-header">
        <h2>Missing Recipe Cards ({len(missing_list)})</h2>
        <p class="card-subtitle">Empty (0-byte) files from the Sept. 2001 collection</p>
      </header>
      <ul class="missing-list">
        {missing_items}
      </ul>
    </section>
  </main>
</body>
</html>
"""


def render_recipes_redirect() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=/">
  <link rel="canonical" href="https://recipes.plona.family/">
  <title>Redirecting — Grandma Mary's Recipes</title>
</head>
<body>
  <p>Redirecting to <a href="/">Grandma Mary's Recipes</a>&hellip;</p>
</body>
</html>
"""


STYLE_CSS = """\
:root {
  --bg: #f6f1e7;
  --surface: #fffdf8;
  --surface-muted: #efe7d8;
  --ink: #241f1a;
  --muted: #665c52;
  --accent: #8b3a2b;
  --accent-soft: #f5e5df;
  --border: #dfd4c2;
  --rule: #d3b8a8;
  --shadow: 0 2px 10px rgba(36, 31, 26, 0.06);
  --radius: 10px;
}

*, *::before, *::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  font-size: 17px;
  line-height: 1.6;
  -webkit-text-size-adjust: 100%;
}

a {
  color: var(--accent);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 1rem 1rem 3rem;
}

/* Hero */
.hero {
  background: var(--surface);
  border-bottom: 2px solid var(--border);
  padding: 2rem 1rem 1.75rem;
  text-align: center;
}

.hero-inner {
  max-width: 760px;
  margin: 0 auto;
}

.hero-kicker {
  margin: 0 0 0.35rem;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--accent);
}

.hero h1 {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.9rem, 4.5vw, 2.75rem);
  line-height: 1.15;
}

.hero-sub {
  margin: 0.55rem 0 1rem;
  color: var(--muted);
  font-size: 0.98rem;
}

.hero-links {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn-outline, .btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0.45rem 0.9rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-size: 0.9rem;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}

.btn-outline:hover, .btn-secondary:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-secondary[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

/* Top Nav */
.top-nav {
  max-width: 960px;
  margin: 0 auto;
  padding: 0.85rem 1rem 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.nav-back, .nav-cat {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--border);
  text-decoration: none;
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--ink);
}

.nav-back:hover, .nav-cat:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.nav-actions {
  display: flex;
  gap: 0.5rem;
}

/* Search & Filter Controls */
.controls {
  margin-top: 0.5rem;
  margin-bottom: 1.5rem;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

#recipe-search {
  width: 100%;
  min-height: 50px;
  padding: 0.7rem 2.75rem 0.7rem 1rem;
  font: inherit;
  font-size: 1rem;
  color: var(--ink);
  background: var(--surface);
  border: 2px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

#recipe-search:focus {
  outline: none;
  border-color: var(--accent);
}

.clear-btn {
  position: absolute;
  right: 0.5rem;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: var(--surface-muted);
  color: var(--ink);
  font-size: 1.3rem;
  line-height: 1;
  cursor: pointer;
}

.filter-status {
  margin: 0.5rem 0 0.75rem;
  font-size: 0.9rem;
  color: var(--muted);
}

.category-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.cat-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 36px;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
}

.cat-pill:hover {
  border-color: var(--accent);
}

.cat-pill.is-active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.pill-count {
  opacity: 0.75;
  font-weight: 500;
  font-size: 0.82rem;
}

/* Category Sections & Grid */
.category-section {
  margin-bottom: 2rem;
}

.section-head {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  border-bottom: 2px solid var(--rule);
  padding-bottom: 0.35rem;
  margin-bottom: 0.85rem;
}

.section-head h2 {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.45rem;
  color: var(--accent);
}

.section-count {
  font-size: 0.88rem;
  color: var(--muted);
  font-weight: 600;
}

.recipe-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 0.7rem;
}

.recipe-link-card a {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 0.45rem;
  height: 100%;
  padding: 0.85rem 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-decoration: none;
  color: var(--ink);
  box-shadow: var(--shadow);
  transition: border-color 0.12s ease, transform 0.12s ease;
}

.recipe-link-card a:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
}

.recipe-link-card.is-missing a {
  background: #fbf7ef;
  border-style: dashed;
}

.recipe-link-title {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.08rem;
  font-weight: 700;
  line-height: 1.28;
}

.recipe-link-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.badge {
  display: inline-block;
  padding: 0.12rem 0.5rem;
  border-radius: 999px;
  background: var(--surface-muted);
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 600;
}

.badge-source {
  background: var(--accent-soft);
  color: var(--accent);
}

.badge-missing {
  background: #ebe3d3;
  color: #6b5b49;
}

.empty-state {
  padding: 2rem 1rem;
  text-align: center;
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--muted);
}

/* Individual Recipe Card */
.recipe-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top: 5px solid var(--accent);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 1.35rem 1.25rem 1.65rem;
  margin-bottom: 1.5rem;
}

.recipe-card.is-missing {
  border-top-color: #9b8c7b;
}

.card-header {
  border-bottom: 2px solid var(--rule);
  padding-bottom: 0.9rem;
  margin-bottom: 1.25rem;
}

.card-header h1, .card-header h2 {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(1.55rem, 4vw, 2.2rem);
  line-height: 1.18;
}

.card-subtitle {
  margin: 0.3rem 0 0.75rem;
  font-style: italic;
  color: var(--muted);
}

.card-meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 1.25rem;
  font-size: 0.92rem;
}

.card-meta div {
  display: flex;
  gap: 0.35rem;
}

.card-meta dt {
  font-weight: 700;
  color: var(--accent);
}

.card-meta dt::after {
  content: ":";
}

.card-meta dd {
  margin: 0;
}

.recipe-columns {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
}

@media (min-width: 720px) {
  .recipe-card {
    padding: 1.85rem 2rem 2rem;
  }
  .recipe-columns {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr);
    gap: 2.25rem;
    align-items: start;
  }
}

.ingredients-col h2,
.instructions-col h2 {
  margin: 0 0 0.75rem;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.2rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent);
}

.ingredient-group {
  margin: 1rem 0 0.35rem;
  font-size: 0.96rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink);
}

.ingredient-group:first-of-type {
  margin-top: 0.2rem;
}

.ingredient-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.ingredient-item {
  border-bottom: 1px dashed #ece3d5;
}

.ingredient-item:last-child {
  border-bottom: 0;
}

.ingredient-check {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  min-height: 40px;
  padding: 0.42rem 0.25rem;
  cursor: pointer;
}

.ingredient-check input[type="checkbox"] {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  margin-top: 0.2rem;
  accent-color: var(--accent);
  cursor: pointer;
}

.ingredient-check input:checked + span {
  text-decoration: line-through;
  opacity: 0.55;
}

.ingredient-subnote {
  margin: 0.35rem 0 0.75rem;
  font-size: 0.94rem;
  color: var(--muted);
}

.instructions-col p {
  margin: 0 0 0.95rem;
}

.instructions-col p:last-child {
  margin-bottom: 0;
}

.recipe-notes {
  margin-top: 1.35rem;
  padding: 0.85rem 1rem;
  background: var(--accent-soft);
  border-left: 4px solid var(--accent);
  border-radius: 6px;
  font-size: 0.95rem;
}

.recipe-notes h2 {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.recipe-notes p {
  margin: 0;
}

.missing-card-body {
  padding: 0.5rem 0 0.25rem;
}

.missing-badge-lg {
  display: inline-block;
  margin: 0 0 0.75rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: #ebe3d3;
  color: #5c4e3e;
  font-size: 0.88rem;
  font-weight: 700;
}

.missing-prompt {
  color: var(--muted);
  font-style: italic;
}

/* Printable / All View */
.all-header {
  text-align: center;
  margin-bottom: 1.5rem;
}

.all-header h1 {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
}

.toc-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem 1.5rem;
  margin-bottom: 2rem;
}

.toc-panel h2 {
  margin: 0 0 1rem;
  font-family: Georgia, "Times New Roman", serif;
  color: var(--accent);
}

.toc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1.15rem;
}

.toc-group h3 {
  margin: 0 0 0.35rem;
  font-size: 1rem;
  color: var(--accent);
  border-bottom: 1px solid var(--border);
}

.toc-group ul {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.92rem;
}

.missing-list {
  margin: 0;
  padding-left: 1.25rem;
}

/* Footer */
.site-footer {
  text-align: center;
  padding: 1rem 1rem 2.5rem;
  color: var(--muted);
  font-size: 0.9rem;
}

@media print {
  body {
    background: #fff;
    font-size: 11pt;
    line-height: 1.45;
  }
  .no-print {
    display: none !important;
  }
  .container {
    max-width: none;
    padding: 0;
  }
  .recipe-card {
    box-shadow: none;
    border: 1px solid #bbb;
    border-top: 3px solid #333;
    break-inside: avoid;
    page-break-inside: avoid;
    margin-bottom: 14pt;
    padding: 12pt 14pt;
  }
  .recipe-columns {
    grid-template-columns: 1fr 1.25fr;
    gap: 16pt;
  }
  .ingredient-list {
    list-style: disc;
    padding-left: 14pt;
  }
  .ingredient-item {
    border-bottom: 0;
  }
  .ingredient-check {
    display: inline;
    min-height: 0;
    padding: 0;
  }
  .ingredient-check input[type="checkbox"] {
    display: none;
  }
  a {
    color: inherit;
    text-decoration: none;
  }
}
"""

APP_JS = """\
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
      const terms = q ? q.split(/\\s+/).filter(Boolean) : [];
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
"""

FAVICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="6" y="10" width="52" height="44" rx="6" fill="#fffdf8" stroke="#8b3a2b" stroke-width="4"/>
  <line x1="6" y1="22" x2="58" y2="22" stroke="#8b3a2b" stroke-width="3"/>
  <line x1="14" y1="32" x2="50" y2="32" stroke="#d3b8a8" stroke-width="2.5"/>
  <line x1="14" y1="40" x2="46" y2="40" stroke="#d3b8a8" stroke-width="2.5"/>
  <line x1="14" y1="48" x2="40" y2="48" stroke="#d3b8a8" stroke-width="2.5"/>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    root = args.root
    content_dir = root / "content"
    recipes = [parse_markdown_recipe(p) for p in sorted(content_dir.rglob("*.md"))]
    if not recipes:
        raise RuntimeError(f"No recipe Markdown files found under {content_dir}")

    # Clean generated directories before rebuilding
    for rel_dir in ("recipes", "all", "assets"):
        target = root / rel_dir
        if target.exists():
            shutil.rmtree(target)

    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "assets" / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    (root / "assets" / "app.js").write_text(APP_JS, encoding="utf-8")
    (root / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    (root / ".nojekyll").write_text("", encoding="utf-8")

    # Home page
    (root / "index.html").write_text(render_index_page(recipes), encoding="utf-8")

    # Individual recipe pages
    for r in recipes:
        out_dir = root / "recipes" / r.primary_cat_slug / r.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_recipe_page(r), encoding="utf-8")

    # Printable all-recipes page
    (root / "all").mkdir(parents=True, exist_ok=True)
    (root / "all" / "index.html").write_text(render_all_page(recipes), encoding="utf-8")

    # Legacy /recipes/ redirect
    (root / "recipes" / "index.html").write_text(render_recipes_redirect(), encoding="utf-8")

    print(f"Built static site: {len(recipes)} recipe pages + /index.html + /all/index.html + /recipes/index.html")


if __name__ == "__main__":
    main()
