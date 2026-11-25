# Plona Family Recipes (`recipes.plona.family`)

A zero-maintenance static website preserving **Grandma Mary's recipe collection**, digitized from her original Microsoft Works Database (`.wdb`) index-card files (`Sept. 2001`).

## How It Works

- **`content/<category>/<recipe>.md`** — Plain-text Markdown source files (144 complete recipes + 4 "missing card" entries from empty 0-byte `.wdb` files, with *German Potato Salad* listed under both `Salads` and `Vegetables`).
- **`scripts/extract_wdb.py`** — Zero-dependency Python 3 script that parses Microsoft Works OLE2 (`MN0`) streams directly (handling >255-byte string continuations, RK numbers, visual field coordinates, multi-card merges, card-overflow splits, and typo fixes) to generate `content/`.
- **`scripts/build.py`** — Zero-dependency Python 3 static site generator (stdlib only) that builds `/index.html`, `/recipes/<category>/<recipe>/index.html`, `/all/index.html`, `/recipes/index.html`, `/assets/style.css`, and `/assets/app.js`.
- **`.github/workflows/build.yml`** — Automatically runs `python3 scripts/build.py` when any file under `content/` or `scripts/build.py` is edited on `master` (for example, right in GitHub's web UI).

## Editing or Adding a Recipe

1. Edit any existing `.md` file in `content/` (or create a new `.md` file matching the header format) directly in GitHub's web UI or locally.
2. If editing locally, run:
   ```bash
   python3 scripts/build.py
   ```
   and commit the updated files. (On GitHub, the Action will rebuild automatically on push to `master`.)

## The 4 Missing Recipe Cards

Four `.wdb` files in Grandma Mary's original archive were 0 bytes even in the earliest 2001/2009 backups:

- `Beverages/Strawberry Smoothie.wdb`
- `Breads & rolls/OvernightFrenchToast.wdb`
- `Poultry/Chicken Livers & Mushrooms.wdb`
- `Salads/Apricot Mold.wdb`

Each appears on the site as a "Missing Recipe Card" placeholder in case a physical card turns up in the family!
