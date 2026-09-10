import io
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from PIL import Image, ImageOps, ImageChops

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIR = ROOT / "assets" / "products"
LOGO_DIR = ROOT / "assets" / "logos"
PRODUCT_DIR.mkdir(parents=True, exist_ok=True)
LOGO_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
})

DATA_URLS = [
    "https://raw.githubusercontent.com/origenmarruecos/origenmarruecos.github.io/main/data-1.js",
    "https://raw.githubusercontent.com/origenmarruecos/origenmarruecos.github.io/main/data-2.js",
    "https://raw.githubusercontent.com/origenmarruecos/origenmarruecos.github.io/main/data-3.js",
]

LOGOS = {
    "mercadona": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Mercadona.svg", "svg"),
    "carrefour": ("https://cdn.stocklear.com/storage/45974/1278px-logocarrefour.png", "png"),
    "alcampo": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Alcampo.png", "png"),
    "lidl": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Lidl-Logo.svg", "svg"),
    "aldi": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/AldiNord-WorldwideLogo.svg", "svg"),
    "dia": ("https://commons.wikimedia.org/wiki/Special:Redirect/file/Dia_2019.svg", "svg"),
}

SOURCE_OVERRIDES = {
    "mercadona-anchoas": "https://radarsuper.com/mercadona/p/filetes-anchoa-aceite-oliva-hacendado-bandeja",
    "mercadona-cherry": "https://radarsuper.com/mercadona/p/tomates-cherry-bandeja",
    "alcampo-belmonte-gourmet": "https://soysuper.com/p/anchoa-del-cantabrico-belmonte-60-gr",
    "carrefour-tapita": "https://radarsuper.com/carrefour/p/tapita-marinera-mediterranea-belmonte-gourmet-300-g-carrefour-carrefour",
}

DIRECT_IMAGE_OVERRIDES = {
    "alcampo-belmonte-23": "https://www.compraonline.alcampo.es/images-v3/37ea0506-72ec-4543-93c8-a77bb916ec12/1d4445a4-4454-417a-bdc9-0ff361ad1dc4/500x500.jpg",
    "alcampo-belmonte-gourmet": "https://www.compraonline.alcampo.es/images-v3/37ea0506-72ec-4543-93c8-a77bb916ec12/c93af348-6765-40db-9b08-1d2df9277cd0/500x500.jpg",
    "alcampo-belmonte-gildas": "https://www.compraonline.alcampo.es/images-v3/37ea0506-72ec-4543-93c8-a77bb916ec12/fea490be-9285-478e-886e-f84ba35be968/1120x1120.jpg",
    "alcampo-belmonte-tapitas": "https://sgfm.elcorteingles.es/SGFM/dctm/MEDIA03/201912/11/00118285202208____1__600x600.jpg",
    "carrefour-caracol": "https://static.carrefour.es/hd_510x_/img_pim_food/475196_00_1.jpg",
    "carrefour-tapita": "https://sgfm.elcorteingles.es/SGFM/dctm/MEDIA03/201912/11/00118285202208____1__600x600.jpg",
    "carrefour-ramiflor": "https://static.carrefour.es/hd_510x_/img_pim_food/366621_00_1.jpg",
    "carrefour-elmenu": "https://www.gastronomicspain.com/7385-large_default/anchoas-en-aceite-de-oliva.webp",
    "alcampo-calvo-girasol": "https://pamplona.e-leclerc.es/documents/10180/10815/8410090410412_G.jpg",
    "alcampo-calvo-oliva-baja-sal": "https://static.carrefour.es/hd_510x_/img_pim_food/486926_00_1.jpg",
    "alcampo-calvo-sardinillas-baja-sal": "https://sgfm.elcorteingles.es/SGFM/dctm/MEDIA03/202002/24/00118004700649____1__1200x1200.jpg",
    "alcampo-belmonte-banderillas": "https://sgfm.elcorteingles.es/SGFM/dctm/MEDIA03/201710/04/00118285201861____1__600x600.jpg",
    "alcampo-vanelli-anchoa": "https://www.compraonline.alcampo.es/images-v3/37ea0506-72ec-4543-93c8-a77bb916ec12/a596a573-6461-4b39-94a4-d85b90fdef8f/500x500.jpg",
    "alcampo-perejil-bio": "https://a0.soysuper.com/e5a724c4048cdc07fa1c6deb31df1ca7.500.0.0.0.wmark.3eb8b449.jpg",
    "alcampo-eneldo-bio": "https://www.compraonline.alcampo.es/images-v3/37ea0506-72ec-4543-93c8-a77bb916ec12/30ffec0d-f013-4b3d-be37-0b26ef34d804/500x500.jpg",
    "aldi-aguacate": "https://archivana.com/pics/09/8c/098c6129854123bb2a1090cd1c07fef9b7686c03.jpg",
}

FALLBACK_IMAGE_OVERRIDES = {
    "alcampo-pescadona-pulpo": "https://claire.global/static/media/catalog/products/1822-pata-de-pulpo-cocido-68-patas-congelado-f6195547537b40f68e61baa827c4a4b2-520x520.jpg",
    "alcampo-estragon-bio": "https://d3nqciqdbtzkc.cloudfront.net/articulos/articulos-105306.jpg",
}

CANVAS = 1000
TARGET = 880
BACKGROUND = (255, 255, 255, 255)
LAST_REQUEST = {}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def polite_wait(url):
    host = urlparse(url).netloc.lower()
    gap = 1.4 if "compraonline.alcampo.es" in host else 0.25
    previous = LAST_REQUEST.get(host, 0)
    remaining = gap - (time.monotonic() - previous)
    if remaining > 0:
        time.sleep(remaining)
    LAST_REQUEST[host] = time.monotonic()


def fetch(url, *, timeout=25, attempts=3):
    last = None
    for attempt in range(attempts):
        polite_wait(url)
        try:
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code in {403, 429, 500, 502, 503, 504} and attempt < attempts - 1:
                time.sleep(2.2 * (attempt + 1))
                last = requests.HTTPError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r
        except (requests.RequestException, requests.Timeout) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(1.8 * (attempt + 1))
    raise last or RuntimeError(f"No se pudo descargar {url}")


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
    for tag in re.findall(r'<img\b[^>]*>', html, flags=re.I):
        m = re.search(r'(?:src|data-src|data-original)=["\']([^"\']+)', tag, flags=re.I)
        if m:
            out.append(urljoin(base, m.group(1).replace("&amp;", "&")))
    seen = set()
    return [u for u in out if u and not u.startswith("data:") and not (u in seen or seen.add(u))]


def extract_object_after_key(text, key):
    idx = text.find(key)
    if idx < 0:
        return None
    start = text.find('{', idx + len(key))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def collect_image_strings(value, out):
    if isinstance(value, str):
        if "images-v3" in value and value.startswith("http"):
            out.append(value.replace('\\u0026', '&'))
    elif isinstance(value, dict):
        for v in value.values():
            collect_image_strings(v, out)
    elif isinstance(value, list):
        for v in value:
            collect_image_strings(v, out)


def alcampo_search_candidates(product):
    if product.get("chain") != "Alcampo":
        return []
    m = re.search(r'/([0-9]+)(?:[/?#]|$)', product.get("url", ""))
    product_id = m.group(1) if m else ""
    if not product_id:
        return []
    query = product.get("product", "").replace('·', ' ')
    try:
        html = fetch("https://www.compraonline.alcampo.es/search?q=" + quote_plus(query), timeout=30).text
        raw = extract_object_after_key(html, '"productEntities"')
        if not raw:
            return []
        entities = json.loads(raw)
    except Exception as exc:
        print(f"WARN search Alcampo {product['id']}: {exc}")
        return []
    matches = []
    for key, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        rid = str(entity.get("retailerProductId") or entity.get("id") or key)
        if product_id not in rid and product_id not in str(key):
            continue
        collect_image_strings(entity, matches)
    return sorted(set(matches), key=lambda u: ("1120x1120" in u, "500x500" in u, "300x300" in u), reverse=True)


def off_candidates(product):
    name = product.get("product", "")
    brand = product.get("brand", "")
    query = f"{brand} {name}".strip()
    if not query:
        return []
    url = "https://world.openfoodfacts.org/cgi/search.pl?search_simple=1&action=process&json=1&page_size=8&fields=code,product_name,brands,image_front_url,image_url&search_terms=" + quote_plus(query)
    try:
        data = fetch(url, timeout=20, attempts=2).json()
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
    if url.lower().endswith(".pdf") or "as.com" in host or "coag" in host:
        return []
    try:
        r = fetch(url, attempts=2)
        return meta_images(r.text, r.url)
    except Exception as exc:
        print(f"WARN page {product['id']}: {exc}")
        return []


def image_bytes(url):
    r = fetch(url, timeout=30, attempts=3)
    ct = (r.headers.get("content-type") or "").lower()
    if "svg" in ct or url.lower().split("?")[0].endswith(".svg"):
        return None
    if len(r.content) < 2000:
        return None
    return r.content


def content_bbox(im):
    """Detecta el contenido real ignorando el fondo blanco/casi blanco."""
    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 250:
        bbox = alpha.point(lambda p: 255 if p > 10 else 0).getbbox()
        if bbox and bbox != (0, 0, rgba.width, rgba.height):
            return bbox

    rgb = rgba.convert("RGB")
    white = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, white).convert("L")
    mask = diff.point(lambda p: 255 if p > 12 else 0)
    bbox = mask.getbbox()
    if not bbox:
        return (0, 0, rgba.width, rgba.height)

    # Un pequeño colchón evita afeitar sombras y bordes del envase.
    x0, y0, x1, y1 = bbox
    pad = max(4, round(max(x1-x0, y1-y0) * 0.035))
    return (max(0, x0-pad), max(0, y0-pad), min(rgba.width, x1+pad), min(rgba.height, y1+pad))


def normalize_product_image(raw, dst):
    with Image.open(io.BytesIO(raw)) as src:
        im = ImageOps.exif_transpose(src).convert("RGBA")
        if im.width < 80 or im.height < 80:
            raise ValueError("imagen demasiado pequeña")
        im = im.crop(content_bbox(im))
        if im.width < 20 or im.height < 20:
            raise ValueError("contenido visual inválido")

        scale = min(TARGET / im.width, TARGET / im.height)
        new_w = max(1, round(im.width * scale))
        new_h = max(1, round(im.height * scale))
        im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (CANVAS, CANVAS), BACKGROUND)
        x = (CANVAS - new_w) // 2
        y = (CANVAS - new_h) // 2
        canvas.alpha_composite(im, (x, y))
        canvas.convert("RGB").save(dst, "WEBP", quality=90, method=6)


def renormalize_cached(dst):
    """Reencuadra los WebP ya descargados sin tener que volver a pedirlos a la tienda."""
    raw = dst.read_bytes()
    normalize_product_image(raw, dst)


def try_candidate(url, dst):
    raw = image_bytes(url)
    if not raw:
        return False
    normalize_product_image(raw, dst)
    return True


def choose_product_image(product):
    dst = PRODUCT_DIR / f"{product['id']}.webp"
    if dst.exists() and dst.stat().st_size > 3000:
        try:
            renormalize_cached(dst)
            return "local-cache-reframed"
        except Exception as exc:
            print(f"WARN reframe {product['id']}: {exc}")

    direct = DIRECT_IMAGE_OVERRIDES.get(product["id"])
    if direct:
        try:
            if try_candidate(direct, dst):
                return direct
        except Exception as exc:
            print(f"WARN direct {product['id']}: {exc}")

    candidates = alcampo_search_candidates(product)
    candidates += source_candidates(product)
    candidates += off_candidates(product)
    fallback = FALLBACK_IMAGE_OVERRIDES.get(product["id"])
    if fallback:
        candidates.append(fallback)

    seen = set()
    for u in candidates[:20]:
        if u in seen:
            continue
        seen.add(u)
        try:
            if try_candidate(u, dst):
                return u
        except Exception as exc:
            print(f"WARN candidate {product['id']}: {exc}")
    return None


def sync_logos():
    ok = 0
    expected = {name: ext for name, (_, ext) in LOGOS.items()}
    for name, ext in expected.items():
        for old_ext in ("svg", "png", "jpg", "webp"):
            old = LOGO_DIR / f"{name}.{old_ext}"
            if old_ext != ext and old.exists():
                old.unlink()
    for name, (url, ext) in LOGOS.items():
        dst = LOGO_DIR / f"{name}.{ext}"
        if dst.exists() and dst.stat().st_size > 300:
            ok += 1
            continue
        try:
            r = fetch(url, timeout=25)
            if ext == "svg":
                txt = r.text
                if "<svg" not in txt.lower():
                    raise ValueError("respuesta no SVG")
                dst.write_text(txt, encoding="utf-8")
            else:
                with Image.open(io.BytesIO(r.content)) as im:
                    im = ImageOps.exif_transpose(im).convert("RGBA")
                    im.thumbnail((1200, 800), Image.Resampling.LANCZOS)
                    im.save(dst, "PNG", optimize=True)
            ok += 1
        except Exception as exc:
            print(f"LOGO FAIL {name}: {exc}")
    return ok


def main():
    products = load_products()
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
        "visual_target": TARGET,
        "products_total": len(products),
        "products_with_image": ok,
        "missing": missing,
        "logos_ok": logo_ok,
    }
    (ROOT / "assets" / "media-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
