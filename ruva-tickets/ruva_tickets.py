#!/usr/bin/env python3
"""
RÜVA ticketing: signed QR tickets, print-ready PDF sheets, sales tracking and a gate scanner.

Commands
  python3 ruva_tickets.py generate [--singles 120] [--doubles 80]   make tickets + PDFs
  python3 ruva_tickets.py sell S-001 S-002 --buyer "Ama" --phone 024... --seller Kojo
  python3 ruva_tickets.py report                                    sales summary
  python3 ruva_tickets.py build                                     rebuild scanner.html
Edit config.json to change event name, date, venue, prices, then run generate/build again.
"""
import argparse, csv, hashlib, hmac, json, os, secrets, sys
from datetime import datetime

import cv2
import numpy as np
from PIL import Image
from reportlab.lib.colors import Color, white, black
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(HERE, *a)

CONFIG_FILE = P("config.json")
DB_FILE = P("tickets.csv")
KEY_FILE = P("secret.key")
LOGO_SRC = P("assets", "logo_source.jpg")
LOGO_PNG = P("assets", "logo.png")

GOLD = Color(0.784, 0.627, 0.290)
GREY = Color(0.62, 0.62, 0.62)

DEFAULT_CONFIG = {
    "brand": "RÜVA",
    "event_title": "POOL PARTY",
    "event_line": "Same Energy. Different Nights.",
    "date_text": "DATE TBA",
    "time_text": "TIME TBA",
    "venue_text": "VENUE TBA · KUMASI",
    "single": {"label": "SINGLE", "admits": 1, "price": 50},
    "double": {"label": "DOUBLE", "admits": 2, "price": 80},
    "terms": "Non-refundable · One entry per person · Void if copied",
}

FIELDS = ["serial", "type", "admits", "price", "sig", "check",
          "sold", "buyer", "phone", "seller", "sold_at"]


# ---------- config / keys / database ----------
def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def load_key():
    if not os.path.exists(KEY_FILE):
        with open(KEY_FILE, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(KEY_FILE, 0o600)
    with open(KEY_FILE) as f:
        return f.read().strip().encode()


def sign(key, serial):
    """64-bit signature that only someone holding secret.key can produce."""
    return hmac.new(key, f"RUVA|{serial}".encode(), hashlib.sha256).hexdigest()[:16]


def read_db():
    if not os.path.exists(DB_FILE):
        sys.exit("No tickets yet. Run: python3 ruva_tickets.py generate")
    with open(DB_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_db(rows):
    with open(DB_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def payload(row):
    # Upper-case letters/digits only, so the QR uses the compact "alphanumeric" mode
    # (21x21 dots instead of 25x25 = bigger, easier-to-scan dots when printed).
    return f"{row['serial']}.{row['sig'].upper()}"


# ---------- QR + logo ----------
def qr_image(text, module_px=10, quiet=4):
    enc = cv2.QRCodeEncoder.create()
    m = enc.encode(text)  # tiny image, 1 px per module (plus a small border)
    m = (m > 127).astype(np.uint8)
    # strip any white border the encoder added, then add our own quiet zone
    ys, xs = np.where(m == 0)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    m = np.pad(m, quiet, constant_values=1)
    big = np.kron(m, np.ones((module_px, module_px), dtype=np.uint8)) * 255
    return Image.fromarray(big.astype(np.uint8), "L")


def prepare_logo():
    os.makedirs(P("assets"), exist_ok=True)
    if not os.path.exists(LOGO_SRC):
        for cand in ("/mnt/user-data/uploads/photo_1_2026-10-03_12-47-32.jpg",):
            if os.path.exists(cand):
                Image.open(cand).convert("RGB").save(LOGO_SRC, quality=95)
    if not os.path.exists(LOGO_SRC):
        return None
    im = Image.open(LOGO_SRC).convert("RGB")
    s = im.size[0] / 1254
    box = tuple(int(v * s) for v in (140, 420, 1115, 800))
    im = im.crop(box)
    a = np.array(im).astype(np.int32)
    a[a.sum(axis=2) < 45] = 0  # clean near-black so it blends into a pure black card
    Image.fromarray(a.astype(np.uint8)).save(LOGO_PNG)
    return LOGO_PNG


# ---------- PDF ----------
PAGE_W, PAGE_H = 595.28, 841.89
COLS, ROWS = 2, 4
MARGIN, GAP_X, GAP_Y = 20, 14, 8
TW = (PAGE_W - 2 * MARGIN - GAP_X) / COLS
TH = (PAGE_H - 2 * MARGIN - GAP_Y * (ROWS - 1)) / ROWS


def draw_ticket(c, x, y, row, cfg, logo, qr_cache):
    kind = cfg["single"] if row["type"] == "S" else cfg["double"]
    # card
    c.setFillColor(black)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.roundRect(x, y, TW, TH, 9, fill=1, stroke=1)

    stub_w = 104
    split = x + TW - stub_w
    # perforation line
    c.setStrokeColor(GREY)
    c.setDash(2, 3)
    c.setLineWidth(0.6)
    c.line(split, y + 8, split, y + TH - 8)
    c.setDash()

    # logo
    lx = x + 14
    if logo:
        lw = 120
        lh = lw * 380 / 975
        c.drawImage(logo, lx, y + TH - 16 - lh, width=lw, height=lh, mask=None)
    # event title
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(lx, y + TH - 88, cfg["event_title"])
    # ticket type
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 11)
    admit = "ADMIT ONE" if kind["admits"] == 1 else f"ADMIT {kind['admits']}"
    c.drawString(lx, y + TH - 105, f"{kind['label']} · {admit}")
    # details
    c.setFillColor(white)
    c.setFont("Helvetica", 7.5)
    c.drawString(lx, y + 56, f"{cfg['date_text']}  ·  {cfg['time_text']}")
    c.drawString(lx, y + 45, cfg["venue_text"])
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(lx, y + 26, f"GHS {kind['price']}")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 5.6)
    c.drawString(lx, y + 10, cfg["terms"])

    # stub: QR on a white tile
    tile = stub_w - 16
    tx = split + 8
    ty = y + TH - 12 - tile
    c.setFillColor(white)
    c.roundRect(tx, ty, tile, tile, 4, fill=1, stroke=0)
    if row["serial"] not in qr_cache:
        qr_cache[row["serial"]] = ImageReader(qr_image(payload(row)))
    c.drawImage(qr_cache[row["serial"]], tx + 2, ty + 2, width=tile - 4, height=tile - 4)
    # serial + manual check code
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(split + stub_w / 2, ty - 15, row["serial"])
    c.setFillColor(GOLD)
    c.setFont("Helvetica", 7)
    c.drawCentredString(split + stub_w / 2, ty - 26, f"CODE {row['check']}")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 5.2)
    c.drawCentredString(split + stub_w / 2, y + 10, "SCANNED ONCE AT THE GATE")


def make_pdf(rows, cfg, out):
    if os.path.exists(DESIGN_JSON):
        return make_pdf_design(rows, cfg, out)
    logo = prepare_logo()
    c = canvas.Canvas(out, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"{cfg['brand']} tickets")
    per_page = COLS * ROWS
    qr_cache = {}
    for i, row in enumerate(rows):
        pos = i % per_page
        if pos == 0 and i:
            c.showPage()
        col, r = pos % COLS, pos // COLS
        x = MARGIN + col * (TW + GAP_X)
        y = PAGE_H - MARGIN - (r + 1) * TH - r * GAP_Y
        draw_ticket(c, x, y, row, cfg, logo, qr_cache)
    c.save()


# ---------- custom artwork (your designed ticket image) ----------
DESIGN_JSON = P("assets", "design.json")


def qr_matrix(text):
    """QR code as a boolean matrix (True = dark module), no border."""
    enc = cv2.QRCodeEncoder.create()
    m = enc.encode(text)
    m = (m > 127).astype(np.uint8)
    ys, xs = np.where(m == 0)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return m == 0


def prepare_design(src):
    """Cut the single + double tickets out of one design image and find the sample QR on each."""
    im = Image.open(src).convert("RGB")
    a = np.array(im)
    lum = a.astype(int).sum(axis=2)
    dark = (lum < 45).astype(np.uint8)
    _, lab = cv2.connectedComponents(dark, connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge = [e for e in edge if e != 0]
    outside = np.isin(lab, edge)
    inside = (~outside).astype(np.uint8)
    inside = cv2.morphologyEx(inside, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab2, stats, _ = cv2.connectedComponentsWithStats(inside, connectivity=8)
    comps = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 50000]
    comps.sort(key=lambda i: stats[i, cv2.CC_STAT_TOP])
    if len(comps) != 2:
        sys.exit(f"Expected 2 tickets in the design image, found {len(comps)}. "
                 "The image should contain the single ticket on top and the double ticket below.")
    meta = {}
    for kind, i in zip(("S", "D"), comps):
        x, y, w, h = (int(stats[i, k]) for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP,
                                                  cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        rgb = a[y:y + h, x:x + w]
        mask = (lab2[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        alpha = cv2.GaussianBlur(mask, (3, 3), 0)
        rgba = np.dstack([rgb, alpha])
        name = "ticket_single.png" if kind == "S" else "ticket_double.png"
        Image.fromarray(rgba, "RGBA").save(P("assets", name))
        # find the sample QR tile: biggest roughly-square white block in the right-hand stub
        x0 = int(w * 0.78)
        white = (rgb[:, x0:].min(axis=2) > 200).astype(np.uint8)
        white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        nn, _, st, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
        best = None
        for j in range(1, nn):
            bw, bh = st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT]
            if 80 < bw < 220 and 0.8 < bw / bh < 1.25:
                if best is None or bw * bh > best[0]:
                    best = (bw * bh, int(st[j, cv2.CC_STAT_LEFT]) + x0, int(st[j, cv2.CC_STAT_TOP]),
                            int(bw), int(bh))
        if best is None:
            sys.exit(f"Could not find the sample QR code on the {kind} ticket.")
        _, qx, qy, qw, qh = best
        meta[kind] = {"png": f"assets/{name}", "w": w, "h": h,
                      "qr_cx": qx + qw / 2, "qr_cy": qy + qh / 2,
                      "qr_size": max(qw, qh) + 24,       # real QR tile is a little bigger than the sample
                      "serial_y": qy + qh + 62}          # text line under "SCAN FOR ENTRY"
    with open(DESIGN_JSON, "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def make_pdf_design(rows, cfg, out):
    with open(DESIGN_JSON) as f:
        meta = json.load(f)
    kind = rows[0]["type"]
    m = meta[kind]
    img = ImageReader(P(m["png"]))
    W = 500.0                      # printed ticket width in points (one column, 5 per page)
    s = W / m["w"]
    TH_ = m["h"] * s
    GAP = 6.0
    per_page = max(1, int((PAGE_H - 36 + GAP) // (TH_ + GAP)))
    x0 = (PAGE_W - W) / 2
    top = PAGE_H - 18 - (PAGE_H - 36 - per_page * TH_ - (per_page - 1) * GAP) / 2
    c = canvas.Canvas(out, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"{cfg['brand']} {cfg['event_title']} tickets")
    for i, row in enumerate(rows):
        pos = i % per_page
        if pos == 0 and i:
            c.showPage()
        y = top - (pos + 1) * TH_ - pos * GAP
        c.drawImage(img, x0, y, width=W, height=TH_, mask="auto")
        # replace the sample QR with this ticket's real one
        tile = m["qr_size"] * s
        cx = x0 + m["qr_cx"] * s
        cy = y + TH_ - m["qr_cy"] * s
        c.setFillColor(white)
        c.roundRect(cx - tile / 2, cy - tile / 2, tile, tile, 2.5, fill=1, stroke=0)
        mat = qr_matrix(payload(row))
        n = mat.shape[0]
        pad = 12 * s
        mod = (tile - 2 * pad) / n
        c.setFillColor(black)
        qx0, qy0 = cx - tile / 2 + pad, cy + tile / 2 - pad
        for r_ in range(n):
            run = None
            for c_ in range(n + 1):
                dark = c_ < n and mat[r_, c_]
                if dark and run is None:
                    run = c_
                elif not dark and run is not None:
                    c.rect(qx0 + run * mod - 0.15, qy0 - (r_ + 1) * mod - 0.15,
                           (c_ - run) * mod + 0.3, mod + 0.3, fill=1, stroke=0)
                    run = None
        # serial + manual-check code under the QR
        ty = y + TH_ - m["serial_y"] * s
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawRightString(cx - 3, ty, row["serial"])
        c.setFillColor(Color(0.35, 0.65, 1.0))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(cx + 3, ty, f"CODE {row['check']}")
        # little cut marks in the margins between tickets
        c.setStrokeColor(GREY)
        c.setLineWidth(0.4)
        if pos < per_page - 1 and i < len(rows) - 1:
            gy = y - GAP / 2
            c.line(x0 - 14, gy, x0 - 4, gy)
            c.line(x0 + W + 4, gy, x0 + W + 14, gy)
    c.save()


# ---------- commands ----------
def cmd_design(a):
    meta = prepare_design(a.image)
    print("Design cut out and QR positions found:", {k: (v["w"], v["h"]) for k, v in meta.items()})
    cmd_render(a)


def cmd_render(_):
    cfg = load_config()
    rows = read_db()
    make_pdf([r for r in rows if r["type"] == "S"], cfg, P("tickets_singles.pdf"))
    make_pdf([r for r in rows if r["type"] == "D"], cfg, P("tickets_doubles.pdf"))
    build_pages(rows, cfg)
    print("Rebuilt tickets_singles.pdf, tickets_doubles.pdf, scanner.html and sell.html (same tickets, same secret key).")


def cmd_generate(a):
    cfg = load_config()
    if os.path.exists(DB_FILE) and not a.force:
        sys.exit("tickets.csv already exists. Use --force only if you have NOT printed or sold any tickets "
                 "(it makes brand-new ones and the old tickets stop working).")
    if a.force and os.path.exists(KEY_FILE):
        os.remove(KEY_FILE)
    key = load_key()
    rows = []
    for t, n, kind in (("S", a.singles, cfg["single"]), ("D", a.doubles, cfg["double"])):
        for i in range(1, n + 1):
            serial = f"{t}-{i:03d}"
            sig = sign(key, serial)
            rows.append({"serial": serial, "type": t, "admits": kind["admits"], "price": kind["price"],
                         "sig": sig, "check": sig[:4].upper(), "sold": "0", "buyer": "", "phone": "",
                         "seller": "", "sold_at": ""})
    write_db(rows)
    make_pdf([r for r in rows if r["type"] == "S"], cfg, P("tickets_singles.pdf"))
    make_pdf([r for r in rows if r["type"] == "D"], cfg, P("tickets_doubles.pdf"))
    build_pages(rows, cfg)
    print(f"Made {a.singles} singles + {a.doubles} doubles.")
    print("Files: tickets_singles.pdf, tickets_doubles.pdf, scanner.html, sell.html, tickets.csv")


def cmd_sell(a):
    rows = read_db()
    by = {r["serial"]: r for r in rows}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for s in a.serials:
        s = s.upper()
        if s not in by:
            sys.exit(f"Unknown ticket {s}")
        if by[s]["sold"] == "1":
            print(f"{s} was already sold to {by[s]['buyer'] or 'someone'} - skipped")
            continue
        by[s].update(sold="1", buyer=a.buyer or "", phone=a.phone or "", seller=a.seller or "", sold_at=now)
        print(f"{s} activated")
    write_db(rows)
    build_pages(rows, load_config())
    print("scanner.html and sell.html rebuilt. (The Sell page makes this command optional.)")


def cmd_report(_):
    rows = read_db()
    sold = [r for r in rows if r["sold"] == "1"]
    print(f"Sold {len(sold)} of {len(rows)} tickets")
    tot = 0
    for t, name in (("S", "Single"), ("D", "Double")):
        n_all = sum(1 for r in rows if r["type"] == t)
        n = [r for r in sold if r["type"] == t]
        rev = sum(int(r["price"]) for r in n)
        tot += rev
        print(f"  {name}: {len(n)}/{n_all}  GHS {rev}")
    print(f"Revenue so far: GHS {tot}")
    per = {}
    for r in sold:
        per.setdefault(r["seller"] or "(no seller)", [0, 0])
        per[r["seller"] or "(no seller)"][0] += 1
        per[r["seller"] or "(no seller)"][1] += int(r["price"])
    for s, (n, rev) in sorted(per.items()):
        print(f"  {s}: {n} tickets, GHS {rev} to hand in")


# ---------- scanner ----------
def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _build_page(template, out, data, cfg):
    """Fill a page template with the ticket data and inline shared.js (+ jsqr.js if you add it)."""
    html = _read(P(template))
    if not html:
        sys.exit(f"Missing {template}")
    html = (html.replace("__TICKETS__", json.dumps(data, separators=(",", ":")))
                .replace("__EVENT__", json.dumps(cfg["brand"] + " · " + cfg["event_title"], ensure_ascii=False))
                .replace("__BUILT__", json.dumps(datetime.now().strftime("%d %b %H:%M")))
                .replace("/*__SHARED__*/", _read(P("shared.js")))
                .replace("/*__JSQR__*/", _read(P("jsqr.js"))))
    with open(P(out), "w", encoding="utf-8") as f:
        f.write(html)


def build_scanner(rows, cfg):
    data = {}
    for r in rows:
        data[r["serial"]] = {
            "h": sha256(f"{r['serial']}|{r['sig']}"),
            "c": sha256(f"{r['serial']}|{r['check']}"),
            "t": r["type"], "a": int(r["admits"]), "s": int(r["sold"]),
        }
    _build_page("scanner_template.html", "scanner.html", data, cfg)


def build_sell(rows, cfg):
    data = {}
    for r in rows:
        data[r["serial"]] = {
            "h": sha256(f"{r['serial']}|{r['sig']}"),
            "t": r["type"], "p": int(r["price"]), "s": int(r["sold"]),
        }
    _build_page("sell_template.html", "sell.html", data, cfg)


def build_pages(rows, cfg):
    build_scanner(rows, cfg)
    build_sell(rows, cfg)


def cmd_build(_):
    build_pages(read_db(), load_config())
    print("scanner.html and sell.html rebuilt")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--singles", type=int, default=120)
    g.add_argument("--doubles", type=int, default=80)
    g.add_argument("--force", action="store_true")
    g.set_defaults(fn=cmd_generate)
    s = sub.add_parser("sell")
    s.add_argument("serials", nargs="+")
    s.add_argument("--buyer")
    s.add_argument("--phone")
    s.add_argument("--seller")
    s.set_defaults(fn=cmd_sell)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("render").set_defaults(fn=cmd_render)
    d = sub.add_parser("design")
    d.add_argument("image", help="image with the single ticket on top and the double ticket below")
    d.set_defaults(fn=cmd_design)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
