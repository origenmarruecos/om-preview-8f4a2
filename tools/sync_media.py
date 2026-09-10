import io
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIR = ROOT / "assets" / "products"
LOGO_DIR = ROOT / "assets" / "logos"
PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
LOGO_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152 Safari/537.36 ORIGEN-MARRUECOS-preview/1.0",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
})

DATA_URLS = [
    "https://raw.githubusercontent.com/origenmarruecos/origenmarruecos.github.io/main/data-1.js",
    "https://raw.githubusercontent.com/origenmarruecos/origenmarruecos.github.io/main/data-2.js",
    "https://raw.githubusercontent.com/origenmarruecos/origenmarruecos.github.io/main/data-3.js",
]

LOGOS = {
    "mercadona": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Mercadona.svg", "svg"),
    "carrefour": ("https://upload.wikimedia.org/wikipedia/commons/5/5b/Carrefour_logo.svg", "svg"),
    "alcampo": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Alcampo.png", "png"),
    "lidl": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Lidl-Logo.svg", "svg"),
    "aldi": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/AldiNord-WorldwideLogo.svg", "svg"),
    "dia": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Dia_2019.svg", "svg"),
}

SOURCE_OVERRIDES = {
    "mercadona-anchoas": "https://radarsuper.com/mercadona/p/filetes-anchoa-aceite-oliva-hacendado-bandeja",
    "mercadona-cherry": "https://radarsuper.com/mercadona/p/tomates-cherry-bandeja",
}

CANVAS = 1000
MAX_CONTENT = 850
BACKGROUND = (255, 255, 255, 255)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def fetch(url, *, timeout=25):
    r = SESSION.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def load_products():
    rows = []
    for url in DATA_URLS:
        text = fetch(url).text
        m = re.search(r"window\.data\.push\(\.\.\.(\[.*\])\);?\s*$", text, flags=re.S)
        if not m:
            raise RuntimeError(f"No pude interpretar {url}")
        rows.extend(json.loads(m.group(1)))
    return rows


def meta_images(html, base):
    out = []
    patterns = [
        r'<meta[^>]+(?:property|name)=["\'](?:og:image|og:image:secure_url|twitter:image)["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|og:image:secure_url|twitter:image)["\']',
    ]
    for pat in patterns:
        for u in re.findall(pat, html, flags=re.I):
            out.append(urljoin(base, u.replace("&amp;", "&")))

    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, flags=re.I | re.S):
        try:
            obj = json.loads(block.strip())
        except Exception:
            continue
        stack = obj if isinstance(obj, list) else [obj]
        for item in stack:
            if not isinstance(item, dict):
                continue
            image = item.get("image")
            if isinstance(image, str):
                out.append(urljoin(base, image))
            elif isinstance(image, list):
                out.extend(urljoin(base, x) for x in image if isinstance(x, str))
            elif isinstance(image, dict) and isinstance(image.get("url"), str):
                out.append(urljoin(base, image["url"]))

    # Último recurso: imágenes con alt/producto, evitando iconos minúsculos.
    for tag in re.findall(r'<img\b[^>]*>', html, flags=re.I):
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)', tag, flags=re.I)
        if m:
            out.append(urljoin(base, m.group(1).replace("&amp;", "&")))

    seen = set()
    clean = []
    for u in out:
        if not u or u.startswith("data:") or u in seen:
            continue
        seen.add(u)
        clean.append(u)
    return clean


def off_candidates(product):
    name = product.get("product", "")
    brand = product.get("brand", "")
    query = f"{brand} {name}".strip()
    if not query:
        return []
    params = (
        "search_simple=1&action=process&json=1&page_size=8&"
        "fields=code,product_name,brands,image_front_url,image_url&search_terms=" + quote_plus(query)
    )
    url = "https://world.openfoodfacts.org/cgi/search.pl?" + params
    try:
        data = fetch(url, timeout=20).json()
    except Exception:
        return []

    words = [w for w in re.findall(r"[a-z0-9]+", norm(name)) if len(w) > 3]
    brand_n = norm(brand)
    scored = []
    for p in data.get("products", []):
        img = p.get("image_front_url") or p.get("image_url")
        if not img:
            continue
        hay = norm((p.get("product_name") or "") + " " + (p.get("brands") or ""))
        score = sum(2 for w in words[:8] if w in hay)
        if brand_n and brand_n not in {"fresco", "fruta", "variable", "producto alcampo"} and brand_n in hay:
            score += 5
        scored.append((score, img))
    return [img for score, img in sorted(scored, reverse=True) if score >= 2]


def source_candidates(product):
    url = SOURCE_OVERRIDES.get(product["id"]) or product.get("url", "")
    if not url:
        return []
    host = urlparse(url).netloc.lower()
    # Para artículos y PDFs priorizamos OFF o un override, no la portada editorial.
    if url.lower().endswith(".pdf") or "as.com" in host or "coag" in host:
        return []
    try:
        r = fetch(url)
        return meta_images(r.text, r.url)
    except Exception as exc:
        print(f"WARN page {product['id']}: {exc}")
        return []


def image_bytes(url):
    r = fetch(url, timeout=30)
    ct = (r.headers.get("content-type") or "").lower()
    if "svg" in ct or url.lower().split("?")[0].endswith(".svg"):
        return None
    if len(r.content) < 2000:
        return None
    return r.content


def normalize_product_image(raw, dst):
    with Image.open(io.BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im).convert("RGBA")
        if im.width < 140 or im.height < 140:
            raise ValueError("imagen demasiado pequeña")
        # Elimina sólo bordes transparentes; no recorta el propio envase.
        alpha = im.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            im = im.crop(bbox)
        im.thumbnail((MAX_CONTENT, MAX_CONTENT), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (CANVAS, CANVAS), BACKGROUND)
        x = (CANVAS - im.width) // 2
        y = (CANVAS - im.height) // 2
        canvas.alpha_composite(im, (x, y))
        canvas.convert("RGB").save(dst, "WEBP", quality=88, method=6)


def choose_product_image(product):
    candidates = source_candidates(product)
    candidates += off_candidates(product)
    errors = []
    for u in candidates[:14]:
        try:
            raw = image_bytes(u)
            if not raw:
                continue
            dst = PRODUCT_DIR / f"{product['id']}.webp"
            normalize_product_image(raw, dst)
            return u
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        print(f"WARN image {product['id']}: {errors[-1]}")
    return None


def sync_logos():
    ok = 0
    for name, (url, ext) in LOGOS.items():
        dst = LOGO_DIR / f"{name}.{ext}"
        try:
            r = fetch(url, timeout=25)
            if ext == "svg":
                txt = r.text
                if "<svg" not in txt.lower():
                    raise ValueError("respuesta no SVG")
                dst.write_text(txt, encoding="utf-8")
            else:
                with Image.open(io.BytesIO(r.content)) as im:
                    ImageOps.exif_transpose(im).convert("RGBA").save(dst, "PNG", optimize=True)
            ok += 1
            print(f"LOGO OK {name}")
        except Exception as exc:
            print(f"LOGO FAIL {name}: {exc}")
    return ok


def main():
    products = load_products()
    print(f"Productos encontrados: {len(products)}")
    logo_ok = sync_logos()
    ok = 0
    missing = []
    for i, product in enumerate(products, 1):
        print(f"[{i}/{len(products)}] {product['id']} - {product.get('product','')}")
        src = choose_product_image(product)
        if src:
            ok += 1
            print(f"  OK {src}")
        else:
            missing.append(product["id"])
            print("  FAIL sin imagen fiable")

    manifest = {
        "canvas": [CANVAS, CANVAS],
        "products_total": len(products),
        "products_with_image": ok,
        "missing": missing,
        "logos_ok": logo_ok,
    }
    (ROOT / "assets" / "media-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    # No fallamos el job por imágenes ausentes: se puede completar manualmente después.
    return 0


if __name__ == "__main__":
    sys.exit(main())
