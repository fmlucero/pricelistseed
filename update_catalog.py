"""
Regenera catalogo.js con los precios actuales de el-sembrador.com.ar.

Usa la WooCommerce Store API pública (no requiere credenciales), por eso
este script sí se commitea y lo corre GitHub Actions una vez por día.

Uso:
    python update_catalog.py
"""
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://el-sembrador.com.ar"
API = f"{BASE}/wp-json/wc/store/v1/products"

PER_PAGE = 100
REQUEST_DELAY = 0.5  # segundos entre requests
TIMEOUT = 30

OUT_CATALOG_JS = Path(__file__).parent / "catalogo.js"


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    })
    return s


def fetch_all(session: requests.Session) -> list[dict]:
    r = session.get(API, params={"per_page": PER_PAGE, "page": 1}, timeout=TIMEOUT)
    r.raise_for_status()
    total = int(r.headers.get("X-WP-Total", 0))
    total_pages = int(r.headers.get("X-WP-TotalPages", 1))
    print(f"Total productos: {total} en {total_pages} páginas (de {PER_PAGE})")

    products = list(r.json())
    for page in range(2, total_pages + 1):
        time.sleep(REQUEST_DELAY)
        r = session.get(API, params={"per_page": PER_PAGE, "page": page}, timeout=TIMEOUT)
        r.raise_for_status()
        batch = r.json()
        products.extend(batch)
        print(f"  página {page}/{total_pages} — {len(batch)} productos (acumulado {len(products)})")

    return products


def clean_text(raw: str) -> str:
    """HTML → texto plano: saca tags, decodifica entities, colapsa espacios."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def catalog_entry(p: dict) -> dict:
    """Versión reducida para el visor web — solo lo necesario para mostrar."""
    prices = p.get("prices", {}) or {}
    minor = int(prices.get("currency_minor_unit", 0) or 0)

    def to_num(key: str):
        v = prices.get(key)
        if v in (None, "", "null"):
            return None
        try:
            return int(v) / (10 ** minor) if minor else int(v)
        except (ValueError, TypeError):
            return None

    images = p.get("images") or []
    img = ""
    if images:
        img = images[0].get("src") or images[0].get("thumbnail") or ""

    cats = [html.unescape(c.get("name", "")) for c in (p.get("categories") or [])]

    # Presentación (unidad / kg) y origen — atributos pa_presentacion / pa_origen
    presentacion = ""
    origen = ""
    for a in (p.get("attributes") or []):
        tax = a.get("taxonomy")
        terms = a.get("terms") or []
        if tax == "pa_presentacion" and terms:
            presentacion = terms[0].get("name", "")
        elif tax == "pa_origen" and terms:
            origen = terms[0].get("name", "")

    entry = {
        "id": p.get("id"),
        "n": html.unescape(p.get("name", "")),
        "p": to_num("price"),
        "pr": to_num("regular_price"),
        "po": to_num("sale_price") if p.get("on_sale") else None,
        "s": bool(p.get("is_in_stock")),
        "c": cats,
        "i": img,
        "u": p.get("permalink", ""),
        "un": presentacion,
        "o": origen,
    }

    # Descripción (solo ~50 productos la tienen; se omite si está vacía para no engordar el archivo)
    desc = clean_text(p.get("short_description") or p.get("description") or "")
    if desc:
        entry["d"] = desc

    return entry


def write_catalog(raw: list[dict], path: Path = OUT_CATALOG_JS) -> int:
    catalog = [catalog_entry(p) for p in raw]
    catalog_json = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.CATALOG={catalog_json};\n", encoding="utf-8")
    return len(catalog)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    session = build_session()
    raw = fetch_all(session)
    count = write_catalog(raw)
    con_desc = sum(1 for p in raw if clean_text(p.get("short_description") or ""))
    print(f"\nListo: {count} productos ({con_desc} con descripción) → {OUT_CATALOG_JS.resolve()}")


if __name__ == "__main__":
    main()
