#!/usr/bin/env python3
"""Fetch Last Bottle's public Shopify product feed.

Writes two files:
  data/catalog.json   stable fields only; committed, so git history records every change
  site/products.json  same data plus a fetch timestamp; deployed to GitHub Pages
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STORE = "https://lastbottlewines.com"
ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
SITE_DATA = ROOT / "site" / "products.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (lb-catalog; GitHub Actions)", "Accept": "application/json"}
PAGE_SIZE = 250
MAX_PAGES = 40
STATUS_ORDER = ["dailyoffer", "pdp", "pastoffer", "upsell", "buyable"]
VINTAGE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


def fetch_page(page: int, attempts: int = 4) -> list[dict]:
    url = f"{STORE}/products.json?limit={PAGE_SIZE}&page={page}"
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)["products"]
        except urllib.error.HTTPError as err:
            if not (err.code == 429 or err.code >= 500) or attempt == attempts - 1:
                raise
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
        time.sleep(5 * 2**attempt)
    raise RuntimeError("unreachable")


def fetch_all() -> list[dict]:
    products: list[dict] = []
    seen: set[int] = set()
    for page in range(1, MAX_PAGES + 1):
        batch = fetch_page(page)
        fresh = [p for p in batch if p["id"] not in seen]
        if not fresh:  # empty page, or the store ignores ?page= and repeats page 1
            break
        products.extend(fresh)
        seen.update(p["id"] for p in fresh)
        if len(batch) < PAGE_SIZE:
            break
        time.sleep(1)
    return products


def parse_tags(raw) -> list[str]:
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return list(raw or [])


def status_of(tags: list[str]) -> str:
    statuses = {t.split(":", 1)[1] for t in tags if t.startswith("status:")}
    for status in STATUS_ORDER:
        if status in statuses:
            return status
    return "sample" if "SAMPLE" in tags else "other"


def free_ship_min(tags: list[str]) -> int | None:
    counts = [int(t.split(":", 1)[1]) for t in tags if re.fullmatch(r"freeship:\d+", t)]
    return min(counts) if counts else None


def money(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def pick_image(images: list[dict]) -> str | None:
    """Prefer the studio bottle shot; later images are usually the label or lifestyle photos."""
    srcs = [img.get("src") for img in sorted(images, key=lambda i: i.get("position") or 0) if img.get("src")]
    for src in srcs:
        name = src.rsplit("/", 1)[-1].lower()
        if "bottleshot" in name and "marathon" not in name:
            return src
    return srcs[0] if srcs else None


def normalize(p: dict) -> dict:
    tags = parse_tags(p.get("tags"))
    variants = p.get("variants") or [{}]
    in_stock = [v for v in variants if v.get("available")]
    v = (in_stock or variants)[0]
    price, retail = money(v.get("price")), money(v.get("compare_at_price"))
    discount = round(100 * (1 - price / retail)) if price and retail and retail > price else None
    vintages = VINTAGE.findall(p["title"])
    return {
        "id": p["id"],
        "title": p["title"].strip(),
        "handle": p["handle"],
        "url": f"{STORE}/products/{p['handle']}",
        "status": status_of(tags),
        "available": bool(in_stock),
        "price": price,
        "retail": retail,
        "discount": discount,
        "free_ship": free_ship_min(tags),
        "vintage": int(vintages[-1]) if vintages else None,
        "is_wine": "wine" in (p.get("product_type") or "").lower(),
        "vendor": p.get("vendor"),
        "sku": v.get("sku"),
        "variant_id": v.get("id"),
        "image": pick_image(p.get("images") or []),
        "published_at": p.get("published_at"),
        "tags": tags,
    }


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    raw = fetch_all()
    if not raw:
        print("The feed returned no products; keeping the previous data.", file=sys.stderr)
        return 1

    previous: dict[int, dict] = {}
    if CATALOG.exists():
        previous = {p["id"]: p for p in json.loads(CATALOG.read_text())["products"]}

    products = []
    for item in map(normalize, raw):
        prior = previous.get(item["id"])
        # On the very first run nothing counts as new; afterwards, unseen ids get a timestamp.
        item["first_seen"] = prior.get("first_seen") if prior else (now if previous else None)
        products.append(item)
    products.sort(key=lambda p: (p["published_at"] or "", p["id"]), reverse=True)

    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps({"products": products}, indent=1, ensure_ascii=False) + "\n")
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    SITE_DATA.write_text(json.dumps({"updated": now, "products": products}, ensure_ascii=False))

    counts: dict[str, int] = {}
    for p in products:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    print(f"{len(products)} products: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
