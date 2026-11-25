#!/usr/bin/env python3
"""Extract Grandma Mary's Microsoft Works (.wdb) recipes into clean Markdown files."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import unicodedata
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

CATEGORY_MAP = {
    "Appetizers": "Appetizers",
    "Beverages": "Beverages",
    "Breads & rolls": "Breads & Rolls",
    "CAKES": "Cakes",
    "CONDIMENTS": "Condiments",
    "CONFECTION": "Confection",
    "COOKIES": "Cookies",
    "DESSERTS": "Desserts",
    "FROSTING": "Frosting",
    "MEATS": "Meats",
    "PASTA": "Pasta",
    "PIES": "Pies",
    "Poultry": "Poultry",
    "QUICHE": "Quiche",
    "SEA FOOD": "Seafood",
    "SOUPS": "Soups",
    "Salads": "Salads",
    "VEGETABLES": "Vegetables",
}

SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}

SECTION_HEADERS = {
    "DIP:": "Dip",
    "VEGETABLES:": "Vegetables",
    "CRUST": "Crust",
    "CRUST:": "Crust",
    "TOPPING": "Topping",
    "TOPPING:": "Topping",
    "NUT MIXTURE - MIX WELL": "Nut Mixture (Mix Well)",
    "FILLING": "Filling",
    "FILLING:": "Filling",
    "SYRUP": "Syrup",
    "LAYER INGREDIENTS:": "Layer Ingredients",
    "DOUGH MIXTURE": "Dough Mixture",
}

SUBNOTE_LINES = {
    "Mix as for pie crust",
    "Mix above ingredients with FORK",
}

TYPO_REPLACEMENTS = [
    (r"\bPumpernickle\b", "Pumpernickel"),
    (r"\bFresh Peached for Garnish\b", "Fresh Peaches for Garnish"),
    (r"\b50 t0 60 min\b", "50 to 60 min"),
    (r"\bloosley\b", "loosely"),
    (r"\bconsistancy\b", "consistency"),
    (r"Butter,chop", "Butter, chop"),
    (r"\bSprinke\b", "Sprinkle"),
    (r"\bFenned Seed\b", "Fennel Seed"),
    (r"1//4", "1/4"),
    (r"1//3", "1/3"),
    (r"\(about 3 l/2 c\)", "(about 3 1/2 c)"),
    (r"\b1 /2 cup\b", "1/2 cup"),
    (r"\bSitr\b", "Stir"),
    (r"\breservered\b", "reserved"),
    (r"\bCHOCOLATLE\b", "CHOCOLATE"),
    (r"\bsiftted\b", "sifted"),
    (r"\buncoverd\b", "uncovered"),
    (r"vanilla\.Mix", "vanilla. Mix"),
    (r"browned\.Top", "browned. Top"),
    (r"oil\.Heat", "oil. Heat"),
    (r"night\.Top", "night. Top"),
    (r"pot\.Bring", "pot. Bring"),
    (r"potatoes\.Place", "potatoes. Place"),
    (r"onion \.Pour", "onion. Pour"),
    (r"apple,celery", "apple, celery"),
    (r"Flour,1/2 cup", "Flour, 1/2 cup"),
    (r"Mushrooms,slice & sautee", "Mushrooms, slice & saute"),
    (r"Cheese,Cube", "Cheese, Cubed"),
    (r"\b1cup\b", "1 cup"),
    (r"\bbotom\b", "bottom"),
    (r"\bcooled curst\b", "cooled crust"),
    (r"\bGranulateld\b", "Granulated"),
    (r"firm\., about", "firm, about"),
    (r"directions\.\.", "directions."),
    (r"\boccassionally\b", "occasionally"),
    (r"\bMIlk\b", "Milk"),
    (r"Milk`", "Milk"),
    (r"\bconbine\b", "combine"),
    (r"\blarlge\b", "large"),
    (r"\bAlll Purpose\b", "All Purpose"),
    (r"\(29 0z\)", "(29 oz)"),
    (r"pie shells Bake", "pie shells. Bake"),
    (r"425F Line", "425F. Line"),
    (r"\bYiedl:", "Yield:"),
    (r"\bhard-boilled\b", "hard-boiled"),
    (r"\bMayonaise\b", "Mayonnaise"),
    (r"\bwiiith\b", "with"),
    (r"\bmixtue\b", "mixture"),
    (r"\bChedar\b", "Cheddar"),
    (r"\bVelvetta\b", "Velveeta"),
    (r"\bMediumTomatoes\b", "Medium Tomatoes"),
]


@dataclass
class Recipe:
    title: str
    categories: list[str]
    author: str = "Mary C. Plona"
    prep_time: str = ""
    servings: str = ""
    source: str = ""
    missing: bool = False
    ingredients: list[tuple[str, list[str] | str]] = field(default_factory=list)
    # Each item in ingredients is ("header", "Crust") or ("item", "...") or ("note", "...")
    instructions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    clipart: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)

    @property
    def primary_category(self) -> str:
        return self.categories[0]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ")
    text = re.sub(r"['\".,]", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", text)


def fix_typos(text: str) -> str:
    for pattern, repl in TYPO_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def smart_title_word(word: str, is_first: bool) -> str:
    if not word:
        return word
    # Preserve things like (2)
    if re.fullmatch(r"\(\d+\)", word):
        return word
    # Split around leading/trailing punctuation
    m = re.match(r"^([^A-Za-z0-9]*)(.*?)([^A-Za-z0-9]*)$", word)
    if not m:
        return word
    prefix, core, suffix = m.groups()
    if not core:
        return word
    # Handle hyphenated words
    if "-" in core:
        parts = core.split("-")
        out_parts = []
        for idx, p in enumerate(parts):
            out_parts.append(smart_title_word(p, is_first=(is_first and idx == 0)))
        return f"{prefix}{'-'.join(out_parts)}{suffix}"
    # If word already has intentional mixed case, keep it
    if not core.isupper() and not core.islower():
        return word
    low = core.lower()
    if not is_first and not prefix and low in SMALL_WORDS:
        return f"{prefix}{low}{suffix}"
    # Capitalize first alpha char, lower the rest (so Amazin' -> Amazin', 1st stays 1st)
    chars = list(low)
    for idx, ch in enumerate(chars):
        if ch.isalpha():
            chars[idx] = ch.upper()
            break
    return f"{prefix}{''.join(chars)}{suffix}"


def format_title(raw_title: str) -> str:
    s = clean_spaces(fix_typos(raw_title))
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    # If entire title is uppercase (ignoring digits/punct), or has uppercase words like SOLE
    tokens = s.split(" ")
    out = []
    for idx, tok in enumerate(tokens):
        is_first = idx == 0 or (idx > 0 and tokens[idx - 1] in {"-", "/"})
        if tok.isupper() or s.isupper():
            out.append(smart_title_word(tok, is_first=is_first))
        else:
            out.append(tok)
    res = " ".join(out)
    # Capitalize first word inside parentheses if lowercase
    res = re.sub(r"\(([a-z])", lambda m: "(" + m.group(1).upper(), res)
    return res


def decode_rk(b4: bytes) -> str:
    v = struct.unpack("<I", b4)[0]
    if v & 2:
        iv = struct.unpack("<i", b4)[0] >> 2
        val: int | float = iv / 100.0 if (v & 1) else iv
    else:
        d = struct.unpack("<d", b"\x00\x00\x00\x00" + struct.pack("<I", v & ~3))[0]
        val = d / 100.0 if (v & 1) else d
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


def read_ole_archive(data: bytes) -> tuple[list[dict | None], callable]:
    if data[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError("Not an OLE2 compound file")
    sec_shift, mini_shift = struct.unpack_from("<HH", data, 0x1E)
    sec_size, mini_size = 1 << sec_shift, 1 << mini_shift
    dir_start, _, mini_cutoff, minifat_start = struct.unpack_from("<IIII", data, 0x30)
    difat = [s for s in struct.unpack_from("<109I", data, 0x4C) if s < 0xFFFFFFFE]
    fat: list[int] = []
    for s in difat:
        off = (s + 1) * sec_size
        fat.extend(struct.unpack_from(f"<{sec_size // 4}I", data, off))

    def read_chain(start: int) -> bytes:
        out = bytearray()
        cur = start
        seen: set[int] = set()
        while cur < 0xFFFFFFFE:
            if cur in seen:
                raise ValueError("Cycle in FAT chain")
            seen.add(cur)
            off = (cur + 1) * sec_size
            out.extend(data[off : off + sec_size])
            cur = fat[cur]
        return bytes(out)

    dir_bytes = read_chain(dir_start)
    minifat: list[int] = []
    if minifat_start < 0xFFFFFFFE:
        mf_bytes = read_chain(minifat_start)
        minifat = list(struct.unpack_from(f"<{len(mf_bytes) // 4}I", mf_bytes, 0))

    entries: list[dict | None] = []
    for i in range(0, len(dir_bytes), 128):
        ent = dir_bytes[i : i + 128]
        nlen = struct.unpack_from("<H", ent, 64)[0]
        if nlen == 0:
            entries.append(None)
            continue
        name = ent[: max(0, nlen - 2)].decode("utf-16le", errors="replace")
        etype = ent[66]
        left, right, child = struct.unpack_from("<iii", ent, 68)
        start, size = struct.unpack_from("<II", ent, 116)
        entries.append(
            {
                "name": name,
                "type": etype,
                "left": left,
                "right": right,
                "child": child,
                "start": start,
                "size": size,
            }
        )

    root_stream = read_chain(entries[0]["start"]) if entries and entries[0] and entries[0]["start"] < 0xFFFFFFFE else b""

    def get_bytes(e: dict) -> bytes:
        if e["type"] != 2:
            return b""
        if e["size"] < mini_cutoff:
            out = bytearray()
            cur = e["start"]
            seen_m: set[int] = set()
            while cur < 0xFFFFFFFE:
                if cur in seen_m:
                    raise ValueError("Cycle in miniFAT chain")
                seen_m.add(cur)
                off = cur * mini_size
                out.extend(root_stream[off : off + mini_size])
                cur = minifat[cur]
            return bytes(out[: e["size"]])
        return read_chain(e["start"])[: e["size"]]

    return entries, get_bytes


def extract_matador_wmfs(entries: list[dict | None], get_bytes: callable) -> dict[int, bytes]:
    wmfs: dict[int, bytes] = {}
    for e in entries:
        if not e or e["type"] != 1:
            continue
        m = re.fullmatch(r"MatadorObject(\d+)", e["name"])
        if not m:
            continue
        mo_id = int(m.group(1))
        if mo_id in (2, 8):
            continue

        def walk(idx: int) -> None:
            if idx < 0 or idx >= len(entries) or entries[idx] is None:
                return
            node = entries[idx]
            if node["name"] == "\x02OlePres000" and node["size"] > 500:
                b = get_bytes(node)
                w_idx = b.find(b"\x01\x00\x09\x00\x00\x03")
                if w_idx != -1 and w_idx + 18 <= len(b):
                    mt_size = struct.unpack_from("<I", b, w_idx + 6)[0] * 2
                    if 20 <= mt_size <= len(b) - w_idx + 64:
                        wmfs[mo_id] = b[w_idx : w_idx + mt_size]
            walk(node["left"])
            walk(node["right"])

        walk(e["child"])
    return wmfs


def png_chunk(ctype: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)


def dib_wmf_to_png(wmf: bytes) -> bytes:
    pos = 18
    while pos + 6 <= len(wmf):
        rsz = struct.unpack_from("<I", wmf, pos)[0] * 2
        rop = struct.unpack_from("<H", wmf, pos + 4)[0]
        rpay = wmf[pos + 6 : pos + rsz]
        if rop == 0x0F43:
            bi_size, bi_w, bi_h, _planes, bi_bpp, bi_comp, _bi_img, _, _, bi_clr_used, _ = struct.unpack_from(
                "<IiiHHIIIIII", rpay, 22
            )
            assert bi_size == 40, f"Unexpected BITMAPINFOHEADER size: {bi_size}"
            assert bi_bpp == 8, f"Expected 8bpp DIB, got {bi_bpp}bpp"
            assert bi_comp == 0, f"Expected BI_RGB (0), got {bi_comp}"
            num_colors = bi_clr_used or 256
            pal_off = 62
            plte = bytearray()
            for idx in range(num_colors):
                b, g, r, _a = rpay[pal_off + idx * 4 : pal_off + (idx + 1) * 4]
                plte.extend((r, g, b))
            pix_off = pal_off + num_colors * 4
            height = abs(bi_h)
            stride = (bi_w + 3) & ~3
            raw_rows = bytearray()
            for y in range(height):
                src_y = (height - 1 - y) if bi_h > 0 else y
                row_start = pix_off + src_y * stride
                raw_rows.append(0)
                raw_rows.extend(rpay[row_start : row_start + bi_w])
            ihdr = struct.pack(">IIBBBBB", bi_w, height, 8, 3, 0, 0, 0)
            return (
                b"\x89PNG\r\n\x1a\n"
                + png_chunk(b"IHDR", ihdr)
                + png_chunk(b"PLTE", bytes(plte))
                + png_chunk(b"IDAT", zlib.compress(bytes(raw_rows), 9))
                + png_chunk(b"IEND", b"")
            )
        if rop == 0 or rsz < 6:
            break
        pos += rsz
    raise ValueError("StretchDIB (0x0f43) record not found in DIB WMF")


def vec_wmf_to_svg(wmf: bytes) -> str:
    worg_x, worg_y = 0, 0
    wext_x, wext_y = 1000, 1000
    fill_rule = "evenodd"
    obj_table: list[dict | None] = []
    cur_pen: dict = {"kind": "pen", "stroke": "#000000", "width": 1}
    cur_brush: dict = {"kind": "brush", "fill": "#000000"}
    shapes: list[tuple] = []

    def add_obj(obj: dict) -> None:
        for i, existing in enumerate(obj_table):
            if existing is None:
                obj_table[i] = obj
                return
        obj_table.append(obj)

    pos = 18
    while pos + 6 <= len(wmf):
        rsz = struct.unpack_from("<I", wmf, pos)[0] * 2
        rop = struct.unpack_from("<H", wmf, pos + 4)[0]
        rp = wmf[pos + 6 : pos + rsz]
        if rop == 0:
            break
        if rop == 0x020B:
            worg_y, worg_x = struct.unpack_from("<hh", rp, 0)
        elif rop == 0x020C:
            wext_y, wext_x = struct.unpack_from("<hh", rp, 0)
        elif rop == 0x0106:
            mode = struct.unpack_from("<H", rp, 0)[0]
            fill_rule = "nonzero" if mode == 2 else "evenodd"
        elif rop == 0x02FA:
            style, pw, _, r, g, b = struct.unpack_from("<HHHBBB", rp, 0)
            stroke = "none" if (style & 0x0F) == 5 else f"#{r:02x}{g:02x}{b:02x}"
            add_obj({"kind": "pen", "stroke": stroke, "width": max(1, pw)})
        elif rop == 0x02FC:
            style, r, g, b = struct.unpack_from("<HBBB", rp, 0)
            fill = "none" if style == 1 else f"#{r:02x}{g:02x}{b:02x}"
            add_obj({"kind": "brush", "fill": fill})
        elif rop == 0x012D:
            idx = struct.unpack_from("<H", rp, 0)[0]
            obj = obj_table[idx] if idx < len(obj_table) else None
            if obj:
                if obj["kind"] == "pen":
                    cur_pen = obj
                elif obj["kind"] == "brush":
                    cur_brush = obj
        elif rop == 0x01F0:
            idx = struct.unpack_from("<H", rp, 0)[0]
            if idx < len(obj_table):
                obj_table[idx] = None
        elif rop in (0x0324, 0x0325):
            npts = struct.unpack_from("<H", rp, 0)[0]
            pts = [struct.unpack_from("<hh", rp, 2 + i * 4) for i in range(npts)]
            shapes.append((rop, pts, dict(cur_pen), dict(cur_brush), fill_rule))
        elif rop == 0x0538:
            np = struct.unpack_from("<H", rp, 0)[0]
            cnts = struct.unpack_from(f"<{np}H", rp, 2)
            off = 2 + 2 * np
            polys = []
            for cnt in cnts:
                polys.append([struct.unpack_from("<hh", rp, off + i * 4) for i in range(cnt)])
                off += cnt * 4
            shapes.append((rop, polys, dict(cur_pen), dict(cur_brush), fill_rule))
        elif rop == 0x041B:
            b, r, t, l = struct.unpack_from("<hhhh", rp, 0)
            shapes.append((rop, (l, t, r, b), dict(cur_pen), dict(cur_brush), fill_rule))
        if rsz < 6:
            break
        pos += rsz

    if wext_x == 0 or wext_y == 0:
        raise ValueError("Zero window extent in vector WMF")

    svg_w = 1000.0
    svg_h = round(1000.0 * abs(wext_y) / abs(wext_x), 2)
    scale = svg_w / abs(wext_x)

    def tx(x: int) -> float:
        return round((x - worg_x) / wext_x * svg_w, 2)

    def ty(y: int) -> float:
        return round((y - worg_y) / wext_y * svg_h, 2)

    elems: list[str] = []
    for shape in shapes:
        rop = shape[0]
        pen, brush, fr = shape[2], shape[3], shape[4]
        sw = round(max(1.0, pen["width"] * scale), 2)
        stroke_attr = f'stroke="{pen["stroke"]}"' + (f' stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"' if pen["stroke"] != "none" else "")
        if rop == 0x0324:
            pts_str = " ".join(f"{tx(x)},{ty(y)}" for x, y in shape[1])
            elems.append(f'<polygon points="{pts_str}" fill="{brush["fill"]}" fill-rule="{fr}" {stroke_attr}/>')
        elif rop == 0x0325:
            pts_str = " ".join(f"{tx(x)},{ty(y)}" for x, y in shape[1])
            elems.append(f'<polyline points="{pts_str}" fill="none" {stroke_attr}/>')
        elif rop == 0x0538:
            d_parts = []
            for poly in shape[1]:
                if not poly:
                    continue
                coords = " ".join(f"{'M' if idx == 0 else 'L'}{tx(x)},{ty(y)}" for idx, (x, y) in enumerate(poly))
                d_parts.append(coords + " Z")
            elems.append(f'<path d="{" ".join(d_parts)}" fill="{brush["fill"]}" fill-rule="{fr}" {stroke_attr}/>')
        elif rop == 0x041B:
            l, t, r, b = shape[1]
            x1, y1, x2, y2 = tx(l), ty(t), tx(r), ty(b)
            rx, ry = round(min(x1, x2), 2), round(min(y1, y2), 2)
            rw, rh = round(abs(x2 - x1), 2), round(abs(y2 - y1), 2)
            elems.append(f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" fill="{brush["fill"]}" {stroke_attr}/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-8 -8 {round(svg_w + 16, 2)} {round(svg_h + 16, 2)}">\n'
        + "\n".join(f"  {e}" for e in elems)
        + "\n</svg>\n"
    )


def parse_wdb_file(path: Path, clipart_dir: Path | None = None) -> dict | None:
    raw = path.read_bytes()
    if len(raw) == 0:
        return None
    entries, get_bytes = read_ole_archive(raw)
    mn0 = next((get_bytes(e) for e in entries if e and e["name"] == "MN0"), None)
    if mn0 is None:
        raise ValueError(f"MN0 stream not found in {path}")
    matador_wmfs = extract_matador_wmfs(entries, get_bytes)

    pos = 0
    cols: list[str] = []
    coords: dict[int, tuple[int, int]] = {}
    boxes3: list[tuple[int, int, int, int, int]] = []
    blob_items: list[tuple[str, int | bytes]] = []
    row0: dict[int, str] = {}
    in_data = False
    in_report = False
    eof_seen = False

    while pos + 4 <= len(mn0):
        rt, rl = struct.unpack_from("<HH", mn0, pos)
        pay = mn0[pos + 4 : pos + 4 + rl]
        pos += 4 + rl
        if rt == 0x5464 and rl == 4:
            blen = struct.unpack_from("<I", pay, 0)[0]
            blob = mn0[pos : pos + blen]
            bpos = 0
            while bpos + 4 <= len(blob):
                if blob[bpos : bpos + 2] == b"MO":
                    mo_id, mo_len = struct.unpack_from("<HI", blob, bpos + 2)
                    bpos += 10 + mo_len
                    if mo_id not in (2, 8) and mo_id in matador_wmfs:
                        blob_items.append(("vec", matador_wmfs[mo_id]))
                    else:
                        blob_items.append(("skip", mo_id))
                elif struct.unpack_from("<H", blob, bpos)[0] == 8:
                    w_idx = blob.find(b"\x01\x00\x09\x00\x00\x03", bpos)
                    if w_idx == -1:
                        break
                    w_sz = struct.unpack_from("<I", blob, w_idx + 6)[0] * 2
                    wmf = blob[w_idx : w_idx + w_sz]
                    bpos = w_idx + w_sz
                    blob_items.append(("dib", wmf))
                else:
                    break
            pos += blen
            continue
        if rt == 0x000B and not in_report:
            cols.append(pay.split(b"\x00", 1)[0].decode("cp1252"))
        elif rt == 0x545F and not in_report:
            ftype, x, y = struct.unpack_from("<HHH", pay, 0)
            if ftype == 1 and len(pay) >= 36:
                cidx = struct.unpack_from("<H", pay, 34)[0]
                coords[cidx] = (y, x)
            elif ftype == 3 and len(pay) >= 64:
                w, h = struct.unpack_from("<HH", pay, 36)
                slot_idx = struct.unpack_from("<H", pay, 62)[0]
                boxes3.append((x, y, w, h, slot_idx))
        elif rt == 0x5423 and not in_report:
            in_data = True
        elif rt == 0x5417:
            in_report = True
            in_data = False
        elif rt == 0x0001 and rl == 0:
            eof_seen = True
            break
        elif in_data and rt in (0x000F, 0x0036, 0x545B):
            c, r, _ = struct.unpack_from("<HHH", pay, 0)
            if r == 0:
                if rt == 0x545B:
                    row0[c] = decode_rk(pay[6:10])
                else:
                    row0[c] = row0.get(c, "") + pay[6:].split(b"\x00", 1)[0].decode("cp1252")

    if not eof_seen:
        raise ValueError(f"Did not reach 0x0001 EOF in {path}")

    # Pair clipart payloads with type=3 X coordinates for left-to-right ordering
    raw_clips = [(kind, payload) for kind, payload in blob_items if kind in ("vec", "dib")]
    clip_with_x: list[tuple[int, str, bytes]] = []
    if len(boxes3) == len(blob_items) and [b[4] for b in boxes3] == list(range(len(blob_items))):
        for idx, (kind, payload) in enumerate(blob_items):
            if kind in ("vec", "dib"):
                clip_with_x.append((boxes3[idx][0], kind, payload))
    else:
        non_layout_boxes = [b for b in boxes3 if b[2] < 4000 and b[3] < 4000]
        for idx, (kind, payload) in enumerate(raw_clips):
            bx = non_layout_boxes[idx][0] if idx < len(non_layout_boxes) else idx
            clip_with_x.append((bx, kind, payload))
    clip_with_x.sort(key=lambda item: item[0])

    clip_files: list[str] = []
    for _bx, kind, wmf in clip_with_x:
        h = hashlib.sha1(wmf).hexdigest()[:10]
        if kind == "dib":
            fname = f"clip-{h}.png"
            if clipart_dir is not None:
                out_f = clipart_dir / fname
                if not out_f.exists():
                    out_f.write_bytes(dib_wmf_to_png(wmf))
        else:
            fname = f"clip-{h}.svg"
            if clipart_dir is not None:
                out_f = clipart_dir / fname
                if not out_f.exists():
                    out_f.write_text(vec_wmf_to_svg(wmf), encoding="utf-8")
        clip_files.append(fname)

    ing_indices = sorted(
        [i for i, cname in enumerate(cols) if cname.startswith("Ingredient")],
        key=lambda c: coords.get(c, (99999, c)),
    )
    ings = [row0.get(i, "") for i in ing_indices if row0.get(i, "").strip()]
    meta = {cols[i]: row0.get(i, "") for i in range(len(cols)) if not cols[i].startswith("Ingredient")}
    return {"meta": meta, "ingredients": ings, "clipart": clip_files}


def split_instruction_paragraphs(raw_inst: str, rel_path: str) -> list[str]:
    text = fix_typos(raw_inst).strip()
    if rel_path == "CONDIMENTS/Tomato Chunky Salsa.wdb":
        text = re.sub(r"^PROCEDURE:\s*", "", text)
        text = text.replace("all ingredients  Makes", "all ingredients. Makes")
    if rel_path == "Breads & rolls/BananaBread.wdb":
        # Visual wrap before "50 to 60 min", real paragraph break before "Yield: 1 loaf"
        text = re.sub(r"Bake @ 350F\s+50 to 60 min", "Bake @ 350F 50 to 60 min.", text)
    if rel_path == "COOKIES/Choc Cherry Cookie 2 of 2.wdb":
        text = re.sub(r"^FROSTING:\s+", "FROSTING: ", text)
    parts = [clean_spaces(p) for p in re.split(r"\s{8,}", text) if clean_spaces(p)]
    return parts


def process_ingredients_and_notes(
    raw_ings: list[str], rel_path: str
) -> tuple[list[tuple[str, str]], list[str], str]:
    """Normalize wrapped ingredient lines, extract subheaders, notes, and source credits."""
    cleaned = [fix_typos(s) for s in raw_ings]
    items: list[tuple[str, str]] = []
    notes: list[str] = []
    source = ""

    # Pre-merge special multi-slot fragments before general wrap joining
    merged: list[str] = []
    i = 0
    while i < len(cleaned):
        cur = cleaned[i]
        cur_s = clean_spaces(cur)

        # Source attributions sitting in ingredient slots
        if rel_path in ("COOKIES/Peanut Butter Cookies.wdb", "COOKIES/Pressed Cookies.wdb") and cur_s.startswith("Recipe from:"):
            source = clean_spaces(cur_s.split(":", 1)[1])
            i += 1
            continue
        if rel_path == "FROSTING/Mock Whip Cream Icing.wdb" and cur_s.lower().startswith("from:"):
            source = clean_spaces(cur_s.split(":", 1)[1])
            i += 1
            continue
        if rel_path == "PIES/Apple Pie.wdb" and cur_s == "Recipe from Sisters of Notre Dame":
            source = "Sisters of Notre Dame"
            i += 1
            continue

        # Special pointers / notes in ingredient slots
        if rel_path == "DESSERTS/Blueberry Buckle.wdb" and cur_s == "Crumb Topping follows instructions":
            i += 1
            continue
        if rel_path == "CAKES/Pineapple Upside-Down.wdb" and cur_s.startswith("Duncan Hines Moist Deluxe Yellow"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            notes.append(f"{cur_s} {nxt}".strip() + ".")
            i += 2
            continue
        if rel_path == "DESSERTS/Crepes.wdb" and cur_s.startswith("Filling:"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            notes.append(f"{cur_s} {nxt}".strip())
            i += 2
            continue
        if rel_path == "DESSERTS/Miniature Cheesecakes.wdb" and cur_s.startswith("Option:"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            notes.append(f"{cur_s} {nxt}".strip() + ".")
            i += 2
            continue
        if rel_path == "Salads/Cranberry Salad.wdb" and cur_s.startswith("Dressing"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            combined = re.sub(r"Dressing\s*:\s*", "Dressing: ", f"{cur_s} {nxt}".strip())
            notes.append(combined + ".")
            i += 2
            continue
        if rel_path == "Breads & rolls/Challah 1 of 2.wdb" and cur_s.startswith("1 Egg beaten"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            if nxt == "for (Egg Wash)":
                merged.append(f"{cur_s} (for Egg Wash)")
                i += 2
                continue
        if rel_path == "PIES/Apple Pie.wdb" and cur_s == "6 Cups sliced apples":
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            if nxt.startswith("Use Jonathan"):
                merged.append(f"{cur_s} ({nxt})")
                i += 2
                continue
        if rel_path == "SOUPS/Pumpkin Soup.wdb" and cur_s == "2 cups Cooked Pumpkin":
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            if nxt == "from 2 1/2# Pumpkin":
                merged.append(f"{cur_s} ({nxt})")
                i += 2
                continue
        if rel_path == "DESSERTS/Rum-Kissed Pineapple.wdb" and cur_s.endswith("cored"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            merged.append(f"{cur_s}, cut {nxt}" if not nxt.startswith("into") else f"{cur_s} & cut {nxt}")
            i += 2
            continue
        if rel_path == "MEATS/Crockpot Beef.wdb" and cur_s.startswith("16oz can Whole Tomatoes"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            merged.append(f"{cur_s} {nxt}")
            i += 2
            continue
        if rel_path == "MEATS/Lamb Shanks.wdb" and cur_s.startswith("3 cup Diced Vegetables"):
            base = re.sub(r"[- ]+$", "", cur_s).strip()
            p1 = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            p2 = clean_spaces(cleaned[i + 2]) if i + 2 < len(cleaned) else ""
            merged.append(f"{base}: {p1} {p2}".strip())
            i += 3
            continue
        if rel_path == "VEGETABLES/Red Potatoes & Rosemary.wdb" and cur_s.endswith("OR"):
            nxt = clean_spaces(cleaned[i + 1]) if i + 1 < len(cleaned) else ""
            merged.append(f"{cur_s} {nxt}")
            i += 2
            continue
        if rel_path == "PASTA/Lasagna.wdb" and cur_s.startswith("2 cups Kraft Mozzarella"):
            base = re.sub(r"-+$", "", cur_s).strip()
            p1 = re.sub(r"-+$", "", clean_spaces(cleaned[i + 1])).strip()
            p2 = clean_spaces(cleaned[i + 2])
            merged.append(f"{base}, {p1} {p2}".strip())
            i += 3
            continue
        if rel_path == "Appetizers/Vegetable Pizza.wdb" and cur_s == "2 Tubes Crescent Rolls":
            merged.append("CRUST")
            merged.append(cur_s)
            i += 1
            continue

        merged.append(cur_s)
        i += 1

    # General dash-leader & continuation joining
    joined: list[str] = []
    for line in merged:
        if line in SECTION_HEADERS or line in SUBNOTE_LINES:
            joined.append(line)
            continue
        has_dash_leader = bool(re.search(r"-{3,}\s*$", line))
        clean_line = re.sub(r"\s*-{3,}\s*$", "", line).strip()
        if joined:
            prev = joined[-1]
            prev_had_dash = prev.endswith("\x00DASH")
            prev_clean = prev[:-5] if prev_had_dash else prev
            should_join = False
            if prev_had_dash:
                clean_line = re.sub(r"^--\s*", "", clean_line)
                should_join = True
            elif prev_clean not in SECTION_HEADERS and prev_clean not in SUBNOTE_LINES:
                if (
                    clean_line
                    and (
                        clean_line[0].islower()
                        or clean_line.startswith("(")
                        or prev_clean.endswith(",")
                        or prev_clean.endswith(" or")
                        or prev_clean.endswith(" Red")
                        or prev_clean.endswith(" unflavored")
                        or prev_clean.endswith(" Deluxe")
                        or prev_clean.endswith(" Shortbread")
                        or prev_clean.endswith(" Cherry or")
                        or prev_clean.endswith(" Golden")
                    )
                ):
                    should_join = True
                elif rel_path == "Appetizers/Cheese Ball.wdb" and clean_line == "cheese, shredded":
                    should_join = True
                elif rel_path == "DESSERTS/Rainbow 7 Layer Dessert.wdb" and clean_line.startswith("yellow & orange"):
                    should_join = True
                elif rel_path == "DESSERTS/Broccoli Casserole.wdb":
                    should_join = True
                elif rel_path == "VEGETABLES/Broccoli Casserole.wdb" and (
                    clean_line.startswith("chopped Broccoli") or clean_line.startswith("& drained")
                ):
                    should_join = True
                elif rel_path == "PIES/Raspberry Yogurt Pie.wdb" and clean_line in {"pie crust", "Raspberries, thawed", "Gelatin"}:
                    should_join = True
                elif rel_path == "CAKES/Pineapple Upside-Down.wdb" and clean_line == "Pineapple Supreme Cake Mix":
                    should_join = True
                elif rel_path == "Salads/Seven-Layer Salad.wdb" and clean_line == "or Cheddar)":
                    should_join = True
                elif rel_path == "DESSERTS/Apple Dumplings.wdb" and clean_line == "Apples, Butter":
                    should_join = True

            if should_join:
                sep = ", " if prev_had_dash and not prev_clean.endswith(",") and not clean_line.startswith(("(", "in ", "about ")) else " "
                joined[-1] = clean_spaces(f"{prev_clean}{sep}{clean_line}") + ("\x00DASH" if has_dash_leader else "")
                continue
        joined.append(clean_line + ("\x00DASH" if has_dash_leader else ""))

    for entry in joined:
        entry = entry[:-5] if entry.endswith("\x00DASH") else entry
        if entry in SECTION_HEADERS:
            items.append(("header", SECTION_HEADERS[entry]))
        elif entry in SUBNOTE_LINES:
            items.append(("note", entry))
        else:
            items.append(("item", entry))
    return items, notes, source


def build_recipes(wdb_root: Path, clipart_dir: Path | None = None) -> list[Recipe]:
    parsed: dict[str, dict | None] = {}
    for p in sorted(wdb_root.rglob("*.wdb")):
        rel = p.relative_to(wdb_root).as_posix()
        parsed[rel] = parse_wdb_file(p, clipart_dir=clipart_dir)

    recipes: list[Recipe] = []

    # 1. Merge 2-card recipes
    ch1 = parsed.pop("Breads & rolls/Challah 1 of 2.wdb")
    ch2 = parsed.pop("Breads & rolls/Challa 2 of 2.wdb")
    assert ch1 and ch2
    ch1_ings, ch1_notes, ch1_src = process_ingredients_and_notes(ch1["ingredients"], "Breads & rolls/Challah 1 of 2.wdb")
    ch2_para1 = clean_spaces(fix_typos(" ".join(clean_spaces(x) for x in ch2["ingredients"])))
    ch2_para2 = split_instruction_paragraphs(ch2["meta"].get("Instructions", ""), "Breads & rolls/Challa 2 of 2.wdb")
    recipes.append(
        Recipe(
            title="Challah",
            categories=["Breads & Rolls"],
            author="Mary C. Plona",
            prep_time=clean_spaces(ch1["meta"].get("Prep time", "")),
            servings=clean_spaces(ch1["meta"].get("Servings", "")),
            source=ch1_src,
            ingredients=ch1_ings,
            instructions=[ch2_para1] + ch2_para2,
            notes=ch1_notes,
            clipart=ch1["clipart"],
            source_files=["Breads & rolls/Challah 1 of 2.wdb", "Breads & rolls/Challa 2 of 2.wdb"],
        )
    )

    cc1 = parsed.pop("COOKIES/Choc Cherry Cookie 1of 2.wdb")
    cc2 = parsed.pop("COOKIES/Choc Cherry Cookie 2 of 2.wdb")
    assert cc1 and cc2
    cc1_ings, cc1_notes, cc1_src = process_ingredients_and_notes(cc1["ingredients"], "COOKIES/Choc Cherry Cookie 1of 2.wdb")
    cc2_para1 = clean_spaces(fix_typos(" ".join(clean_spaces(x) for x in cc2["ingredients"])))
    cc2_para2 = split_instruction_paragraphs(cc2["meta"].get("Instructions", ""), "COOKIES/Choc Cherry Cookie 2 of 2.wdb")
    recipes.append(
        Recipe(
            title="Choc. Cherry Cookie",
            categories=["Cookies"],
            author="Mary C. Plona",
            prep_time=clean_spaces(cc1["meta"].get("Prep time", "")),
            servings=clean_spaces(cc1["meta"].get("Servings", "")),
            source=cc1_src,
            ingredients=cc1_ings,
            instructions=[cc2_para1] + cc2_para2,
            notes=cc1_notes + [
                "Grandma's card omits the butter measurement from the ingredient list "
                "(and skips adding the egg & vanilla in the directions) — standard Chocolate "
                "Cherry Thumbprint recipes of this type use 1/2 cup butter."
            ],
            clipart=cc1["clipart"],
            source_files=["COOKIES/Choc Cherry Cookie 1of 2.wdb", "COOKIES/Choc Cherry Cookie 2 of 2.wdb"],
        )
    )

    # 2. Deduplicate German Potato Salad
    gps_sal = parsed.pop("Salads/German Potato Salad.wdb")
    gps_veg = parsed.pop("VEGETABLES/German Potato Salad.wdb")
    assert gps_sal and gps_veg
    gps_ings, gps_notes, gps_src = process_ingredients_and_notes(gps_sal["ingredients"], "Salads/German Potato Salad.wdb")
    recipes.append(
        Recipe(
            title=format_title(gps_sal["meta"]["Recipe Name"]),
            categories=["Salads", "Vegetables"],
            author=clean_spaces(gps_sal["meta"].get("Author", "Mary C. Plona")),
            prep_time=clean_spaces(gps_sal["meta"].get("Prep time", "")),
            servings=clean_spaces(gps_sal["meta"].get("Servings", "")),
            source=gps_src,
            ingredients=gps_ings,
            instructions=split_instruction_paragraphs(gps_sal["meta"].get("Instructions", ""), "Salads/German Potato Salad.wdb"),
            notes=gps_notes,
            clipart=gps_sal["clipart"],
            source_files=["Salads/German Potato Salad.wdb", "VEGETABLES/German Potato Salad.wdb"],
        )
    )

    # 3. Remaining 145 files (141 non-empty + 4 missing 0-byte)
    missing_titles = {
        "Beverages/Strawberry Smoothie.wdb": "Strawberry Smoothie",
        "Breads & rolls/OvernightFrenchToast.wdb": "Overnight French Toast",
        "Poultry/Chicken Livers & Mushrooms.wdb": "Chicken Livers & Mushrooms",
        "Salads/Apricot Mold.wdb": "Apricot Mold",
    }

    for rel, data in sorted(parsed.items()):
        folder = rel.split("/", 1)[0]
        cat_name = CATEGORY_MAP[folder]
        if data is None:
            recipes.append(
                Recipe(
                    title=missing_titles[rel],
                    categories=[cat_name],
                    missing=True,
                    source_files=[rel],
                )
            )
            continue

        meta = data["meta"]
        raw_ings = list(data["ingredients"])
        raw_inst = meta.get("Instructions", "")
        title = format_title(meta.get("Recipe Name", Path(rel).stem))
        author = clean_spaces(meta.get("Author", "Mary C. Plona")).replace("Mary C Plona", "Mary C. Plona")
        prep_time = clean_spaces(meta.get("Prep time", ""))
        servings = clean_spaces(meta.get("Servings", ""))

        # Handle special card-overflow recipes
        if rel == "CONDIMENTS/Tangy Barbecue Sauce.wdb":
            raw_ings = [
                re.sub(r"\s+1/4 tsp Hot Pepper\s*$", "", x) if "Catsup" in x else x
                for x in raw_ings
            ]
            lead, _, rest = raw_inst.partition("INSTRUCTIONS")
            extra = [clean_spaces(x).lstrip("& ").rstrip(".") for x in lead.split(",") if clean_spaces(x)]
            raw_ings.extend(extra)
            ing_items, notes, source = process_ingredients_and_notes(raw_ings, rel)
            inst_paras = split_instruction_paragraphs(rest, rel)
        elif rel == "DESSERTS/Jello Jigglers.wdb":
            split_idx = next(i for i, x in enumerate(raw_ings) if clean_spaces(x) == "INSTRUCTIONS")
            ing_items, notes, source = process_ingredients_and_notes(raw_ings[:split_idx], rel)
            overflow = " ".join(clean_spaces(x) for x in raw_ings[split_idx + 1 :])
            inst_paras = split_instruction_paragraphs(f"{overflow} {raw_inst}", rel)
        elif rel == "PASTA/Macaroni & Cheese.wdb":
            split_idx = next(i for i, x in enumerate(raw_ings) if clean_spaces(x) == "INSTRUCTIONS")
            ing_items, notes, source = process_ingredients_and_notes(raw_ings[:split_idx], rel)
            overflow = " ".join(clean_spaces(x) for x in raw_ings[split_idx + 1 :])
            inst_paras = split_instruction_paragraphs(f"{overflow} {raw_inst}", rel)
        elif rel == "PIES/Pecan Tarts.wdb":
            split_idx = next(i for i, x in enumerate(raw_ings) if clean_spaces(x) == "INSTRUCTIONS")
            ing_items, notes, source = process_ingredients_and_notes(raw_ings[:split_idx], rel)
            overflow = " ".join(clean_spaces(x) for x in raw_ings[split_idx + 1 :])
            inst_paras = split_instruction_paragraphs(f"{overflow} {raw_inst}", rel)
        elif rel == "DESSERTS/Rainbow 7 Layer Dessert.wdb":
            ing_items, notes, source = process_ingredients_and_notes(raw_ings[:10], rel)
            overflow = " ".join(clean_spaces(x) for x in raw_ings[10:])
            inst_paras = split_instruction_paragraphs(f"{overflow} {raw_inst}", rel)
        elif rel == "COOKIES/Xmas Date-Nut Pinwheels.wdb":
            ing_items, notes, source = process_ingredients_and_notes(raw_ings[:8], rel)
            filling = (
                "FILLING: Cook 3/4# pitted chopped dates or prunes with 1/3 cup sugar "
                "& 1/3 cup water until slightly thick. Stir constantly. Cool. Add 1/2 cup nuts."
            )
            inst_paras = [filling] + split_instruction_paragraphs(raw_inst, rel)
        elif rel == "DESSERTS/Choc 4 Layer Desrt.wdb":
            ing_items = [
                ("header", "Layer 1 - Crust"),
                ("item", "1 Cup Flour"),
                ("item", "1/2 cup Ground Walnuts"),
                ("item", "1 stick Butter or Margarine"),
                ("header", "Layer 2"),
                ("item", "8 oz Cr Cheese, softened"),
                ("item", "1 cup Conf. Sugar"),
                ("item", "6 oz Cool Whip"),
                ("header", "Layer 3"),
                ("item", "2 1/2 cups Milk"),
                ("item", "2 sml pkgs Chocolate Instant Pudding"),
                ("header", "Layer 4"),
                ("item", "6 oz Cool Whip"),
                ("item", "Walnuts"),
            ]
            notes = []
            source = ""
            inst_paras = [
                "Layer 1 - Crust: Bake in 9 x 13 pan @ 350F for 10 min. Cool.",
                "Layer 2: Mix ingredients & spread over crust.",
                "Layer 3: Into 2 1/2 cups milk, mix 2 sml pkgs Chocolate Instant Pudding until set. Spread & refrigerate over night.",
                "Layer 4: Spread Cool Whip & sprinkle with Walnuts.",
            ]
        else:
            ing_items, notes, source = process_ingredients_and_notes(raw_ings, rel)
            inst_paras = split_instruction_paragraphs(raw_inst, rel)

        recipes.append(
            Recipe(
                title=title,
                categories=[cat_name],
                author=author,
                prep_time=prep_time,
                servings=servings,
                source=source,
                ingredients=ing_items,
                instructions=inst_paras,
                notes=notes,
                clipart=data["clipart"],
                source_files=[rel],
            )
        )

    return recipes


def render_markdown(recipe: Recipe) -> str:
    lines = [
        f"Title: {recipe.title}",
        f"Categories: {', '.join(recipe.categories)}",
        f"Author: {recipe.author}",
        f"Prep Time: {recipe.prep_time}",
        f"Servings: {recipe.servings}",
        f"Source: {recipe.source}",
        f"Clipart: {', '.join(recipe.clipart)}",
        f"Missing: {'true' if recipe.missing else 'false'}",
        "",
    ]
    if not recipe.missing:
        lines.append("## Ingredients")
        for kind, val in recipe.ingredients:
            if kind == "header":
                lines.append(f"### {val}")
            elif kind == "note":
                lines.append(f"*{val}*")
            else:
                lines.append(f"- {val}")
        lines.append("")
        lines.append("## Instructions")
        lines.append("\n\n".join(recipe.instructions))
        if recipe.notes:
            lines.append("")
            lines.append("## Notes")
            lines.append("\n\n".join(recipe.notes))
    else:
        lines.append("## Missing Card")
        lines.append(
            "Grandma Mary's original computer file (Sept. 2001) for this recipe was empty (0 bytes)."
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wdb-dir", type=Path, default=Path("/tmp/grandma_mary_wdb"))
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent.parent / "content")
    args = parser.parse_args()

    clipart_dir = args.out_dir / "_clipart"
    if clipart_dir.exists():
        for old_clip in clipart_dir.iterdir():
            if old_clip.is_file():
                old_clip.unlink()
    clipart_dir.mkdir(parents=True, exist_ok=True)

    recipes = build_recipes(args.wdb_dir, clipart_dir=clipart_dir)

    # Clear existing content to avoid stale files if re-run
    if args.out_dir.exists():
        for old in args.out_dir.rglob("*.md"):
            old.unlink()

    used_paths: set[Path] = set()
    for r in recipes:
        cat_slug = slugify(r.primary_category)
        rec_slug = slugify(r.title)
        out_path = args.out_dir / cat_slug / f"{rec_slug}.md"
        if out_path in used_paths:
            raise RuntimeError(f"Duplicate output path collision: {out_path} ({r.source_files})")
        used_paths.add(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_markdown(r), encoding="utf-8")

    missing_cnt = sum(1 for r in recipes if r.missing)
    print(f"Extracted {len(recipes)} recipes ({len(recipes) - missing_cnt} complete, {missing_cnt} missing) -> {args.out_dir}")


if __name__ == "__main__":
    main()
