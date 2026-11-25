#!/usr/bin/env python3
"""Verify extracted Markdown recipes and generated static HTML site."""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class LinkAndTextValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.raw_text_errors: list[str] = []
        self.in_script_or_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag in ("script", "style"):
            self.in_script_or_style = True
        if "id" in attr_map and attr_map["id"]:
            self.ids.add(attr_map["id"])
        for key in ("href", "src"):
            val = attr_map.get(key)
            if val is not None:
                self.links.append(val)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.in_script_or_style = False

    def handle_data(self, data: str) -> None:
        if self.in_script_or_style:
            return
        if "&" in data:
            self.raw_text_errors.append(f"Unescaped ampersand in text: {data!r}")
        if "<" in data or ">" in data:
            self.raw_text_errors.append(f"Unescaped angle bracket in text: {data!r}")


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    content_dir = ROOT / "content"
    md_files = sorted(content_dir.rglob("*.md"))
    assert_true(len(md_files) == 148, f"Expected 148 Markdown files, found {len(md_files)}")

    missing_count = 0
    complete_count = 0
    for p in md_files:
        txt = p.read_text(encoding="utf-8")
        is_missing = "Missing: true" in txt
        if is_missing:
            missing_count += 1
            assert_true("## Missing Card" in txt, f"Missing recipe lacks ## Missing Card: {p}")
        else:
            complete_count += 1
            assert_true("## Ingredients" in txt, f"No ## Ingredients in {p}")
            assert_true("## Instructions" in txt, f"No ## Instructions in {p}")
            ing_block = txt.split("## Ingredients", 1)[1].split("## Instructions", 1)[0].strip()
            inst_block = txt.split("## Instructions", 1)[1].split("## Notes", 1)[0].strip()
            assert_true("- " in ing_block, f"Empty ingredients in {p}")
            assert_true(len(inst_block) > 10, f"Empty/too-short instructions in {p}")
            assert_true("SEE BACK SIDE OF CARD" not in txt, f"Unmerged card text in {p}")

    assert_true(complete_count == 144, f"Expected 144 complete recipes, got {complete_count}")
    assert_true(missing_count == 4, f"Expected 4 missing recipes, got {missing_count}")

    assert_true((ROOT / "CNAME").read_text(encoding="utf-8").strip() == "recipes.plona.family", "CNAME mismatch")
    assert_true((ROOT / ".nojekyll").exists(), ".nojekyll missing")

    # Verify index.html lists German Potato Salad in both Salads and Vegetables
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    salads_sec = re.search(r'<section[^>]*id="cat-salads".*?</section>', index_html, re.S)
    veg_sec = re.search(r'<section[^>]*id="cat-vegetables".*?</section>', index_html, re.S)
    assert_true(salads_sec is not None and veg_sec is not None, "Salads or Vegetables section missing on index.html")
    assert_true("German Potato Salad" in salads_sec.group(0), "German Potato Salad missing from Salads section")
    assert_true("German Potato Salad" in veg_sec.group(0), "German Potato Salad missing from Vegetables section")

    # Validate every generated HTML file for links and escaping
    html_files = sorted(ROOT.rglob("*.html"))
    assert_true(len(html_files) == 151, f"Expected 151 HTML files (148 recipes + index + all + recipes redirect), found {len(html_files)}")

    ids_by_file: dict[Path, set[str]] = {}
    links_by_file: dict[Path, list[str]] = {}
    for hp in html_files:
        content = hp.read_text(encoding="utf-8")
        parser = LinkAndTextValidator()
        parser.feed(content)
        parser.close()
        assert_true(not parser.raw_text_errors, f"{hp}: {parser.raw_text_errors[:3]}")
        ids_by_file[hp] = parser.ids
        links_by_file[hp] = parser.links

    for hp, links in links_by_file.items():
        for link in links:
            if link.startswith(("http://", "https://", "mailto:", "javascript:")):
                continue
            if link.startswith("#"):
                assert_true(link[1:] in ids_by_file[hp], f"Broken fragment {link} in {hp}")
                continue
            path_part, _, frag = link.partition("#")
            if path_part.startswith("/"):
                target = ROOT / path_part.lstrip("/")
            else:
                target = hp.parent / path_part
            if target.is_dir():
                target = target / "index.html"
            assert_true(target.exists(), f"Broken link {link} in {hp} -> {target}")
            if frag and target in ids_by_file:
                assert_true(frag in ids_by_file[target], f"Broken fragment {link} in {hp} -> {target}")

    # Spot-check tricky cards in generated HTML
    checks = {
        "recipes/breads-and-rolls/challah/index.html": [
            "Dissolve yeast in 1/2 cup water.",
            "loosely &amp; let rise",
            "Divide dough to half.",
            "1 Egg beaten with 1/4 cup water (for Egg Wash)",
        ],
        "recipes/cookies/choc-cherry-cookie/index.html": [
            "Drain cherries &amp; reserve juice.",
            "Stir in 4 tsps reserved cherry juice.",
            "Family Note",
            "1/2 cup butter",
        ],
        "recipes/condiments/tangy-barbecue-sauce/index.html": [
            "14 oz bottle Catsup",
            "1 tbsp Crushed Red Pepper Flakes",
            "1/4 tsp Hot Pepper Sauce",
            "Measure pickling spice",
        ],
        "recipes/condiments/chunky-tomato-salsa/index.html": [
            "1/2 tsp Salt",
            "In small bowl, combine all ingredients.",
        ],
        "recipes/desserts/jello-jigglers/index.html": [
            "Lightly wipe inside of mold",
            "Dip bottom of mold",
        ],
        "recipes/pasta/macaroni-and-cheese/index.html": [
            "Preheat oven 375F. Over med. heat, add onion &amp; half grated cheese to scalded milk.",
            "1/2 cup bread crumbs, tossed in 3 tbsp melted butter",
        ],
        "recipes/pies/pecan-tarts/index.html": [
            "Mix cream cheese, butter &amp; flour until thoroughly blended. Press dough onto bottom &amp; up sides of ungreased muffin cups",
        ],
        "recipes/desserts/rainbow-7-layer-dessert/index.html": [
            "4 - 3oz pkgs Jello - red, green, yellow &amp; orange",
            "Dissolve 1st pkg in 1 cup hot water. Add 1/2 c cold water. Pour into 9x13 glass dish",
        ],
        "recipes/desserts/chocolate-4-layer-dessert/index.html": [
            "Layer 1 - Crust",
            "1/2 cup Ground Walnuts",
            "Mix ingredients &amp; spread over crust.",
        ],
        "recipes/appetizers/vegetable-pizza/index.html": [
            "Dip",
            "Vegetables",
            "Crust",
            "2 Tubes Crescent Rolls",
            "End with cauliflower and broccoli on top.",
        ],
        "recipes/cakes/sour-cream-coffee-cake/index.html": [
            "Finish with remainder of batter.",
        ],
        "recipes/soups/chicken-soup/index.html": [
            '<p class="card-subtitle"><span class="author-script">Mom Plona&#x27;s Recipe</span></p>',
        ],
        "recipes/beverages/strawberry-smoothie/index.html": [
            "Missing Recipe Card",
            "empty (0 bytes)",
        ],
        "recipes/breads-and-rolls/overnight-french-toast/index.html": [
            "Missing Recipe Card",
        ],
        "recipes/poultry/chicken-livers-and-mushrooms/index.html": [
            "Missing Recipe Card",
        ],
        "recipes/salads/apricot-mold/index.html": [
            "Missing Recipe Card",
        ],
    }

    for rel, needles in checks.items():
        body = (ROOT / rel).read_text(encoding="utf-8")
        for needle in needles:
            assert_true(needle in body, f"{rel} missing expected text: {needle!r}")

    # Negative checks
    salsa_html = (ROOT / "recipes/condiments/chunky-tomato-salsa/index.html").read_text(encoding="utf-8")
    assert_true("etc." not in salsa_html, "Chunky Tomato Salsa still contains template row 'etc.'")
    chicken_html = (ROOT / "recipes/soups/chicken-soup/index.html").read_text(encoding="utf-8")
    assert_true("From the kitchen of Mom Plona" not in chicken_html, "Chicken Soup has redundant 'From the kitchen of'")
    tbbq_html = (ROOT / "recipes/condiments/tangy-barbecue-sauce/index.html").read_text(encoding="utf-8")
    assert_true("Catsup 1/4 tsp" not in tbbq_html, "Tangy Barbecue Sauce still has Catsup overflow fragment")

    # Classic Works Card theme & clipart checks
    for page in html_files:
        if page.relative_to(ROOT).as_posix() == "recipes/index.html":
            continue
        page_html = page.read_text(encoding="utf-8")
        assert_true(
            '<html lang="en" data-theme="classic">' in page_html,
            f"{page.relative_to(ROOT)} missing default data-theme=\"classic\"",
        )

    clipart_dir = ROOT / "assets/clipart"
    assert_true(clipart_dir.is_dir(), "Missing built assets/clipart directory")
    clipart_files = sorted(clipart_dir.iterdir())
    assert_true(len(clipart_files) == 98, f"Expected 98 built clipart files, found {len(clipart_files)}")
    for cf in clipart_files:
        raw = cf.read_bytes()
        if cf.suffix == ".png":
            assert_true(raw.startswith(b"\x89PNG\r\n\x1a\n"), f"Invalid PNG header in {cf.name}")
        elif cf.suffix == ".svg":
            svg_txt = raw.decode("utf-8")
            assert_true("<svg" in svg_txt, f"Missing <svg root in {cf.name}")
            assert_true(
                not re.search(r"(?<![a-z])(?:-?nan|-?inf)(?![a-z])", svg_txt.lower()),
                f"Non-finite coordinate in {cf.name}",
            )
        else:
            raise AssertionError(f"Unexpected clipart extension: {cf.name}")

    md_with_clipart = 0
    for md in md_files:
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("Clipart:") and line.split(":", 1)[1].strip():
                md_with_clipart += 1
                break
    assert_true(md_with_clipart == 143, f"Expected 143 recipe Markdown files with Clipart:, found {md_with_clipart}")

    multi_icon_slugs = [
        "peach-colada",
        "dill-mayonnaise",
        "pumpkin-cake-roll",
        "lemon-pineapple-pie",
        "strawberry-pie",
        "pumpkin-soup",
    ]
    for slug in multi_icon_slugs:
        matches = list((ROOT / "recipes").rglob(f"{slug}/index.html"))
        assert_true(len(matches) == 1, f"Expected 1 page for {slug}, found {len(matches)}")
        html = matches[0].read_text(encoding="utf-8")
        m = re.search(r'<div class="card-clipart">(.*?)</div>', html, re.S)
        assert_true(m is not None, f"{slug} missing .card-clipart container")
        imgs = re.findall(r"<img\b", m.group(1))
        assert_true(len(imgs) == 2, f"Expected 2 clipart imgs in {slug}, found {len(imgs)}")

    print(f"ALL VERIFICATION CHECKS PASSED: {len(md_files)} recipes ({complete_count} complete, {missing_count} missing), {len(html_files)} HTML pages, 0 broken links.")


if __name__ == "__main__":
    main()
