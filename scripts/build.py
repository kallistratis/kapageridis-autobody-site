"""
Write the business details from data/business.json into every page,
build the service pages, and regenerate sitemap.xml and robots.txt.

    python scripts/build.py

1. Service pages: for every service in data/services.json, writes
   <slug>/index.html from templates/service.html (edit those two, not the
   generated pages).

2. Every page stays plain HTML (works without JavaScript). Marked places are rewritten:

  <!-- biz:NAME --> ... <!-- /biz:NAME -->
      whole block regenerated: head, schema, header, footer, chat,
      footer-contact, footer-hours, footer-copy, map-info,
      reviews-static (data/reviews.json), services (data/services.json)

  data-biz="KEY"            the element's text becomes the value of KEY
  data-biz-attrs="a:KEY;b:KEY2"
                            sets attributes, e.g. href:tel;aria-label:callLabel

Keys: name, shortName, phone, tel, address, maps, directions, mapEmbed,
instagram, email, mailto, callLabel, phoneLabel, placeId, reviewsUrl,
writeReviewUrl, reviewsApiKey, reviewsMinRating, foundingYear, viber, viberUrl.

In data/services.json, {phone} and {viber} are replaced by the numbers above.

It also checks every page: one <h1>, <title> 50-60 characters,
meta description 140-160 characters, valid JSON-LD.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "business.json").read_text(encoding="utf-8"))


def _load(name: str, default):
    path = ROOT / "data" / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


SERVICES = _load("services.json", {"home": {}, "services": []})
SERVICE_IMAGES = _load("service-images.json", {})
REVIEWS = _load("reviews.json", {"items": []})
SKIP_DIRS = {"design-system", "scripts", "data", "templates", ".claude", ".git", "node_modules", "_upload"}
NOT_IN_SITEMAP = {"404.html"}
TODAY = dt.date.today()


# ---------------------------------------------------------------- values
def site_url(path: str = "/") -> str:
    return DATA["url"].rstrip("/") + path


def directions_url() -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={quote(DATA['address']['full'])}"
        f"&destination_place_id={DATA['maps']['placeId']}"
    )


def map_embed_url() -> str:
    # Google's keyless embed: the place query is base64url-encoded inside "pb"
    token = base64.urlsafe_b64encode(DATA["address"]["full"].encode()).decode().rstrip("=")
    return f"https://www.google.com/maps/embed?origin=mfe&pb=!1m3!2m1!1z{token}!6i16!3m1!1sel!5m1!1sel"


def place_feature_id(place_id: str) -> str:
    """Google's feature id ("0x…:0x…") stored inside a "ChIJ…" place id
    (base64 of a small protobuf with two 64-bit numbers). "" if it has another shape."""
    try:
        raw = base64.urlsafe_b64decode(place_id + "=" * (-len(place_id) % 4))
    except ValueError:
        return ""
    if len(raw) != 20 or raw[:3] != b"\x0a\x12\x09" or raw[11] != 0x11:
        return ""
    first = int.from_bytes(raw[3:11], "little")
    second = int.from_bytes(raw[12:20], "little")
    return f"0x{first:x}:0x{second:x}"


def reviews_url() -> str:
    """Google Maps link that opens the place straight on its "Reviews" tab (!9m1!1b1).
    The older search.google.com/local/reviews link only lands on a search page."""
    fid = place_feature_id(DATA["maps"]["placeId"])
    if not fid:
        return DATA["maps"]["url"]
    lat, lng = DATA["geo"]["lat"], DATA["geo"]["lng"]
    label = quote_plus(DATA.get("latinName") or DATA["shortName"])
    return (
        f"https://www.google.com/maps/place/{label}/@{lat},{lng},17z"
        f"/data=!4m7!3m6!1s{fid}!8m2!3d{lat}!4d{lng}!9m1!1b1"
    )


VALUES = {
    "name": DATA["name"],
    "shortName": DATA["shortName"],
    "phone": DATA["phone"]["display"],
    "tel": f"tel:{DATA['phone']['tel']}",
    "address": DATA["address"]["full"],
    "maps": DATA["maps"]["url"],
    "directions": directions_url(),
    "mapEmbed": map_embed_url(),
    "instagram": DATA["instagram"],
    "email": DATA["email"] or "[email]",
    "mailto": f"mailto:{DATA['email']}" if DATA["email"] else "mailto:",
    "callLabel": f"Καλέστε μας στο {DATA['phone']['display']}",
    "phoneLabel": f"Τηλέφωνο {DATA['phone']['display']}",
    "placeId": DATA["maps"]["placeId"],
    "reviewsUrl": reviews_url(),
    "writeReviewUrl": f"https://search.google.com/local/writereview?placeid={DATA['maps']['placeId']}",
    "reviewsApiKey": DATA.get("reviews", {}).get("apiKey", ""),
    "reviewsMinRating": str(DATA.get("reviews", {}).get("minRating", 1)),
    "foundingYear": DATA.get("foundingYear", ""),
}

GA4_ID = (DATA.get("analytics") or {}).get("ga4Id", "").strip()
if GA4_ID and not re.fullmatch(r"G-[A-Z0-9]{4,20}", GA4_ID):
    sys.exit(f"data/business.json: analytics.ga4Id must look like G-XXXXXXXXXX, got {GA4_ID!r}")
PRIVACY_PATH = "/politiki-aporritou/"
ESTIMATE_FORM = DATA.get("estimateForm") or {}
ESTIMATE_ENDPOINT = ESTIMATE_FORM.get("endpoint", "").strip()   # our own form -> Google Apps Script
TALLY_ID = "" if ESTIMATE_ENDPOINT else ESTIMATE_FORM.get("tallyId", "").strip()  # old form, fallback
HAS_ESTIMATE_FORM = bool(ESTIMATE_ENDPOINT or TALLY_ID)
ESTIMATE_PATH = "/dorean-ektimisi/"

VIBER = DATA.get("viber") or {}
VALUES["viber"] = VIBER.get("display", "") or "[Viber]"
VALUES["viberUrl"] = f"viber://chat?number={quote(VIBER['tel'])}" if VIBER.get("tel") else ""
# «Δωρεάν εκτίμηση» buttons: the form page if there is a form, else the contact details
VALUES["estimateUrl"] = ESTIMATE_PATH if HAS_ESTIMATE_FORM else "#epikoinonia"


def fill_tokens(value):
    """Put the phone and Viber numbers from business.json into texts that say {phone} / {viber}."""
    if isinstance(value, str):
        return value.replace("{phone}", VALUES["phone"]).replace("{viber}", VALUES["viber"])
    if isinstance(value, list):
        return [fill_tokens(v) for v in value]
    if isinstance(value, dict):
        return {k: fill_tokens(v) for k, v in value.items()}
    return value


SERVICES = fill_tokens(SERVICES)

esc = html.escape


# ---------------------------------------------------------------- schema
def business_schema() -> dict:
    a = DATA["address"]
    return {
        "@context": "https://schema.org",
        "@type": "AutoBodyShop",
        "@id": site_url("/#business"),
        "name": DATA["name"],
        "alternateName": [n for n in (DATA["shortName"], DATA.get("latinName")) if n],
        "url": site_url("/"),
        "logo": site_url(DATA["images"]["logo"]),
        "image": site_url(DATA["images"]["og"]),
        "telephone": DATA["phone"]["tel"],
        **({"email": DATA["email"]} if DATA["email"] else {}),
        "address": {
            "@type": "PostalAddress",
            "streetAddress": a["street"],
            "addressLocality": a["locality"],
            "postalCode": a["postalCode"],
            "addressRegion": a["city"],
            "addressCountry": a["country"],
        },
        "geo": {"@type": "GeoCoordinates", "latitude": DATA["geo"]["lat"], "longitude": DATA["geo"]["lng"]},
        "hasMap": DATA["maps"]["url"],
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": DATA["hours"]["weekdays"],
                "opens": DATA["hours"]["opens"],
                "closes": DATA["hours"]["closes"],
            }
        ],
        "areaServed": [{"@type": "Place", "name": place} for place in DATA["areaServed"]],
        "priceRange": DATA["priceRange"],
        **({"foundingDate": DATA["foundingYear"]} if DATA.get("foundingYear") else {}),
        **({"founder": {"@type": "Person", "name": DATA["owner"]}} if DATA.get("owner") else {}),
        "sameAs": [DATA["maps"]["url"], DATA["instagram"]],
        # The services this shop offers; each @id matches the Service on its own page
        **({"hasOfferCatalog": {
            "@type": "OfferCatalog",
            "name": "Υπηρεσίες",
            "itemListElement": [
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "@id": service_id(s),
                        "name": s["name"],
                        "url": site_url(f"/{s['slug']}/"),
                    },
                }
                for s in SERVICES["services"]
            ],
        }} if SERVICES.get("services") else {}),
    }


def service_id(service: dict) -> str:
    return site_url(f"/{service['slug']}/#service")


def json_ld(obj: dict) -> str:
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    return '<script type="application/ld+json">\n' + body + "\n</script>"


# ---------------------------------------------------------------- blocks
def block_head(page_path: str, title: str, description: str, is_404: bool) -> str:
    img = DATA["images"]
    lines = []
    if is_404:
        lines.append('<meta name="robots" content="noindex">')
    else:
        lines.append('<meta name="robots" content="index, follow">')
        lines.append(f'<link rel="canonical" href="{esc(site_url(page_path))}">')
    lines += [
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="el_GR">',
        f'<meta property="og:site_name" content="{esc(DATA["name"])}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
    ]
    if not is_404:
        lines.append(f'<meta property="og:url" content="{esc(site_url(page_path))}">')
    lines += [
        f'<meta property="og:image" content="{esc(site_url(img["og"]))}">',
        f'<meta property="og:image:width" content="{img["ogWidth"]}">',
        f'<meta property="og:image:height" content="{img["ogHeight"]}">',
        f'<meta property="og:image:alt" content="{esc(img["ogAlt"])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<link rel="icon" href="/favicon.ico" sizes="48x48">',
        '<link rel="icon" href="/images/brand/favicon-32.png" type="image/png" sizes="32x32">',
        '<link rel="apple-touch-icon" href="/images/brand/apple-touch-icon.png">',
        '<meta name="theme-color" content="#0e0c0b">',
    ]
    return "\n".join(lines)


def block_footer_contact() -> str:
    email_inner = (
        f'<a href="{esc(VALUES["mailto"])}">{esc(DATA["email"])}</a>' if DATA["email"] else "<span>[email]</span>"
    )
    return f"""<ul class="footer-contact">
  <li>
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>
    {email_inner}
  </li>
  <li>
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
    <a href="{esc(VALUES['tel'])}">{esc(VALUES['phone'])}</a>
  </li>
  <li>
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-7-6.1-7-11a7 7 0 0 1 14 0c0 4.9-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>
    <address class="footer-address"><a href="{esc(VALUES['maps'])}" target="_blank" rel="noopener">{esc(VALUES['address'])}</a></address>
  </li>
</ul>"""


def upper_no_accents(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text.upper())
    return unicodedata.normalize("NFC", "".join(c for c in decomposed if unicodedata.category(c) != "Mn"))


def block_footer_hours() -> str:
    rows = "\n".join(
        f"  <dt>{esc(upper_no_accents(line['days']))}:</dt><dd>{esc(upper_no_accents(line['time']))}</dd>"
        for line in DATA["hours"]["lines"]
    )
    return f'<dl class="footer-hours">\n{rows}\n</dl>'


def block_footer_copy() -> str:
    cookie_btn = (
        ' · <button class="footer-link-btn" type="button" data-consent-open>Ρυθμίσεις cookies</button>'
        if GA4_ID else ""
    )
    return (
        '<div class="footer-bottom">\n'
        f'  <p class="footer-copy">© {TODAY.year} {esc(DATA["name"])}. All rights reserved. '
        "Proudly serving Thessaloniki with precision and integrity.</p>\n"
        f'  <p class="footer-legal"><a href="{PRIVACY_PATH}">Πολιτική απορρήτου</a>{cookie_btn}</p>\n'
        "</div>"
    )


def short_name(full: str) -> str:
    """'Maria Ntotsika' -> 'Maria N.' (first name + initial). Same rule as js/reviews.js."""
    parts = full.split()
    if len(parts) < 2:
        return full
    return f"{parts[0]} {parts[-1][0].upper()}."


def greek_number(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def block_reviews_static() -> str:
    """Real reviews from data/reviews.json: overall score + a scrolling carousel.
    Plain HTML: without JavaScript it is a horizontally scrollable row."""
    path = ROOT / "data" / "reviews.json"
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [i for i in data.get("items", []) if i.get("text")]
    if not items:
        return ""
    use_short = data.get("nameStyle", "short") == "short"

    out = ['<div class="reviews-static">']

    summary = data.get("summary") or {}
    if summary.get("rating") and summary.get("count"):
        score = greek_number(float(summary["rating"]))
        full = round(float(summary["rating"]))
        out.append(
            f"""  <p class="reviews-summary-static">
    <span class="reviews-score">{score}</span><span class="reviews-outof">/5</span>
    <span class="review-stars" role="img" aria-label="{score} από 5 αστέρια">{"★" * full}{"☆" * (5 - full)}</span>
    <a class="reviews-count" href="{esc(VALUES['reviewsUrl'])}" target="_blank" rel="noopener">{int(summary["count"])} κριτικές στο Google</a>
  </p>"""
        )

    cards = []
    for item in items:
        rating = max(1, min(5, int(item.get("rating", 5))))
        name = short_name(item["author"]) if use_short else item["author"]
        text = "<br>".join(esc(line) for line in item["text"].split("\n"))
        date = f'\n          <p class="review-time">{esc(item["date"])}</p>' if item.get("date") else ""
        more = (
            f'\n      <a class="review-more" href="{esc(VALUES["reviewsUrl"])}" target="_blank" rel="noopener">'
            "Ολόκληρη η κριτική στο Google</a>"
            if item.get("truncated")
            else ""
        )
        cards.append(
            f"""    <li class="review-card">
      <div class="review-head">
        <span class="review-avatar" aria-hidden="true">{esc(name[:1].upper())}</span>
        <div>
          <p class="review-author"><span>{esc(name)}</span></p>{date}
        </div>
      </div>
      <span class="review-stars" role="img" aria-label="{rating} από 5 αστέρια">{"★" * rating}{"☆" * (5 - rating)}</span>
      <p class="review-text">{text}</p>{more}
    </li>"""
        )
    out.append(
        '  <div class="reviews-carousel" data-reviews-carousel>\n'
        '    <div class="reviews-viewport" tabindex="0" role="region" aria-label="Κριτικές πελατών από το Google">\n'
        '  <ul class="reviews-track">\n' + "\n".join(cards) + "\n  </ul>\n"
        "    </div>\n"
        "  </div>"
    )
    if data.get("note"):
        out.append(f'  <p class="reviews-note">{esc(data["note"])}</p>')
    out.append("</div>")
    return "\n".join(out)


# ---------------------------------------------------------------- shared header / footer / chat
ICON = {
    "instagram": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/></svg>',
    "phone": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    "mail": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
    "menu": '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18"/></svg>',
    "chat": '<svg class="icon-chat" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01" stroke-width="3"/></svg>',
    "close": '<svg class="icon-close" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
}

# Main menu: (label, link, which page it marks as current)
NAV = [
    ("Αρχική", "/", "home"),
    ("Σχετικά", "/#sxetika", None),
    ("Υπηρεσίες", "/#ypiresies", "services"),
    ("Πριν & Μετά", "/#prin-meta", None),
    ("Επικοινωνία", "#epikoinonia", None),
]


def section_of(page_path: str) -> str | None:
    if page_path == "/":
        return "home"
    if any(page_path == f"/{s['slug']}/" for s in SERVICES["services"]):
        return "services"
    return None


def logo_img(width: int, sizes: str, lazy: bool) -> str:
    height = round(width * 195 / 400)
    extra = ' loading="lazy" decoding="async"' if lazy else ""
    return (
        f'<img src="/images/brand/logo-{width}.webp" srcset="/images/brand/logo-400.webp 400w, '
        f'/images/brand/logo-800.webp 800w" sizes="{sizes}" alt="{esc(DATA["name"])}" '
        f'width="{width}" height="{height}"{extra}>'
    )


def block_header(page_path: str) -> str:
    current = section_of(page_path)
    links = []
    for label, href, key in NAV:
        mark = ""
        if key and key == current:
            mark = ' aria-current="page"' if key == "home" else ' aria-current="true"'
        links.append(f'    <a href="{href}"{mark}>{esc(label)}</a>')
    return f"""<header class="fb-header">
  <nav class="fb-nav" id="main-nav" aria-label="Κεντρικό μενού">
{chr(10).join(links)}
  </nav>
  <a class="fb-logo site-logo" href="/">
    {logo_img(400, "170px", lazy=False)}
  </a>
  <div class="fb-social">
    <a href="{esc(VALUES['instagram'])}" target="_blank" rel="noopener" aria-label="Instagram">{ICON['instagram']}</a>
    <a href="{esc(VALUES['tel'])}" aria-label="{esc(VALUES['phoneLabel'])}">{ICON['phone']}</a>
  </div>
  <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="main-nav" aria-label="Μενού">
    {ICON['menu']}
  </button>
</header>"""


def block_footer() -> str:
    menu = "\n".join(f'      <li><a href="{href}">{esc(upper_no_accents(label))}</a></li>' for label, href, _ in NAV)
    services = "\n".join(
        f'      <li><a href="/{s["slug"]}/">{esc(upper_no_accents(s.get("menuLabel") or s["name"]))}</a></li>'
        for s in SERVICES.get("services", [])
    )
    indent = lambda text, n: "\n".join(" " * n + line for line in text.split("\n"))  # noqa: E731
    return f"""<footer class="fb-footer" id="epikoinonia">
  <div class="footer-col">
    <h2 class="visually-hidden">Επικοινωνία</h2>
{indent(block_footer_contact(), 4)}
    <div class="fb-social">
      <a href="{esc(VALUES['instagram'])}" target="_blank" rel="noopener" aria-label="Instagram">{ICON['instagram']}</a>
    </div>
  </div>
  <div class="footer-col">
    <h2 class="footer-title">ΩΡΑΡΙΟ</h2>
{indent(block_footer_hours(), 4)}
  </div>
  <nav class="footer-col" aria-label="Υπηρεσίες">
    <h2 class="footer-title">ΥΠΗΡΕΣΙΕΣ</h2>
    <ul class="footer-menu">
{services}
    </ul>
  </nav>
  <nav class="footer-col" aria-label="Μενού στο κάτω μέρος">
    <h2 class="footer-title">ΜΕΝΟΥ</h2>
    <ul class="footer-menu">
{menu}
    </ul>
  </nav>
  <div class="footer-col footer-col-logo">
    <a class="footer-logo" href="/">
      {logo_img(800, "240px", lazy=True)}
    </a>
  </div>
  {block_footer_copy()}
</footer>"""


def block_chat() -> str:
    return f"""<div class="chat-float fb-chat">
  <div class="chat-menu" id="chat-menu" hidden>
    <a class="chat-option" href="{esc(VALUES['tel'])}">
      <span class="chat-option-icon">{ICON['phone'].replace('<svg ', '<svg width="20" height="20" ', 1)}</span>
      <span>Τηλέφωνο<small>{esc(VALUES['phone'])}</small></span>
    </a>
    <a class="chat-option" href="{esc(VALUES['mailto'])}">
      <span class="chat-option-icon">{ICON['mail']}</span>
      <span>Email<small>Στείλτε μας μήνυμα</small></span>
    </a>
  </div>
  <button class="fb-chat-btn" type="button" aria-expanded="false" aria-controls="chat-menu" aria-label="Επικοινωνία: τηλέφωνο ή email">
    {ICON['chat']}
    {ICON['close']}
  </button>
</div>{block_consent()}"""


def block_consent() -> str:
    """Cookie banner for the statistics (GA4). Written only when analytics.ga4Id is set;
    js/site.js shows it until the visitor chooses, and loads GA4 only after «Αποδοχή».
    Both buttons look the same: refusing must be as easy as accepting."""
    if not GA4_ID:
        return ""
    return f"""
<div class="consent" id="consent" data-ga-id="{esc(GA4_ID)}" role="region" aria-labelledby="consent-title" hidden>
  <h2 class="consent-title" id="consent-title">Cookies στατιστικών</h2>
  <p class="consent-text">Με το Google Analytics μετράμε πόσοι επισκέπτονται το site και ποιες σελίδες διαβάζουν, για να το κάνουμε καλύτερο. Ενεργοποιείται μόνο αν το επιτρέψετε. <a href="{PRIVACY_PATH}">Πολιτική απορρήτου</a></p>
  <div class="consent-actions">
    <button class="fb-btn fb-btn-outline" type="button" data-consent="denied">Απόρριψη</button>
    <button class="fb-btn fb-btn-outline" type="button" data-consent="granted">Αποδοχή</button>
  </div>
</div>"""


def estimate_form_html() -> str:
    """The site's own free estimate form. js/estimate.js shrinks the photos in the
    visitor's browser and sends everything to the Google Apps Script at
    estimateForm.endpoint, which writes the same Sheet row the old Tally form wrote.
    Same questions as before, on one page."""
    camera = ('<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8a2 2 0 0 1 2-2h2l2-2h6l2 2h2'
              'a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/></svg>')
    choices = "\n".join(
        f'      <label class="ef-choice"><input type="radio" name="insurance" value="{v}"><span>{v}</span></label>'
        for v in ("Ναι", "Όχι, ιδιωτικά", "Δεν ξέρω ακόμα")
    )
    return f"""<form class="ef" id="forma" novalidate data-estimate-form data-endpoint="{esc(ESTIMATE_ENDPOINT)}" data-phone="{esc(VALUES['phone'])}">
  <div class="ef-field">
    <label class="ef-label" for="ef-car">Αυτοκίνητο (μάρκα, μοντέλο, χρονιά) <span class="ef-req">*</span></label>
    <input class="ef-input" id="ef-car" name="car" type="text" maxlength="200" placeholder="π.χ. Toyota Yaris 2018" required>
  </div>
  <div class="ef-field">
    <label class="ef-label" for="ef-damage">Τι έπαθε το αυτοκίνητο; <span class="ef-req">*</span></label>
    <textarea class="ef-input ef-textarea" id="ef-damage" name="damage" rows="4" maxlength="3000" placeholder="π.χ. Με χτύπησαν στο πάρκινγκ, βαθούλωμα στην πίσω πόρτα" required></textarea>
  </div>
  <fieldset class="ef-field" data-group="insurance">
    <legend class="ef-label">Θα πάει μέσω ασφαλιστικής; <span class="ef-req">*</span></legend>
    <div class="ef-choices">
{choices}
    </div>
  </fieldset>
  <div class="ef-field" data-insurer hidden>
    <label class="ef-label" for="ef-insurer">Ποια ασφαλιστική;</label>
    <input class="ef-input" id="ef-insurer" name="insurer" type="text" maxlength="200">
  </div>
  <div class="ef-field" data-group="photos">
    <span class="ef-label" id="ef-photos-label">Φωτογραφίες της ζημιάς <span class="ef-req">*</span></span>
    <p class="ef-hint" id="ef-photos-hint">1 φωτογραφία από μακριά, να φαίνεται όλο το αυτοκίνητο, και 1–2 από κοντά στη ζημιά, με φως ημέρας. Έως 6.</p>
    <input class="ef-file" id="ef-photos" type="file" accept="image/*" multiple aria-labelledby="ef-photos-label" aria-describedby="ef-photos-hint">
    <label class="ef-drop" for="ef-photos">{camera}<span data-drop-text>Πατήστε για να προσθέσετε φωτογραφίες</span></label>
    <ul class="ef-thumbs" data-thumbs></ul>
  </div>
  <div class="ef-field">
    <label class="ef-label" for="ef-name">Ονοματεπώνυμο <span class="ef-req">*</span></label>
    <input class="ef-input" id="ef-name" name="name" type="text" autocomplete="name" maxlength="200" required>
  </div>
  <div class="ef-field">
    <label class="ef-label" for="ef-phone">Κινητό (για να σας απαντήσουμε σε Viber ή τηλέφωνο) <span class="ef-req">*</span></label>
    <input class="ef-input" id="ef-phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="69xx xxx xxx" required>
  </div>
  <div class="ef-field" data-group="consent">
    <label class="ef-check"><input type="checkbox" name="consent" required><span>Συμφωνώ να χρησιμοποιηθούν τα στοιχεία μου μόνο για την εκτίμηση (<a href="{PRIVACY_PATH}">πολιτική απορρήτου</a>).</span></label>
  </div>
  <div class="ef-hp" aria-hidden="true"><label>Αφήστε το κενό <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
  <p class="ef-error" role="alert" data-error hidden></p>
  <button class="fb-btn fb-btn-primary ef-submit" type="submit">Αποστολή</button>
  <noscript><p class="ef-error">Η φόρμα χρειάζεται JavaScript. Καλέστε μας στο {esc(VALUES['phone'])}.</p></noscript>
</form>
<div class="ef-done" data-done hidden tabindex="-1">
  <h2 class="ef-done-title">Ευχαριστούμε! Λάβαμε το αίτημά σας.</h2>
  <p>Θα δούμε τις φωτογραφίες και θα σας απαντήσουμε στο Viber ή στο τηλέφωνο.</p>
</div>"""


def block_estimate() -> str:
    """Body of /dorean-ektimisi/: three steps, the Tally form (loaded by js/site.js),
    and phone / Viber as the other way to ask."""
    phone = f'<a href="{esc(VALUES["tel"])}">{esc(VALUES["phone"])}</a>'
    viber = (
        f' ή στείλτε μήνυμα στο <a href="{esc(VALUES["viberUrl"])}">Viber {esc(VALUES["viber"])}</a>'
        if VALUES["viberUrl"] else ""
    )
    steps = """<ol class="estimate-steps">
  <li>Αυτοκίνητο και τι έπαθε</li>
  <li>2–3 φωτογραφίες της ζημιάς</li>
  <li>Σας απαντάμε σε Viber ή τηλέφωνο</li>
</ol>"""
    if ESTIMATE_ENDPOINT:
        note = f'<p class="estimate-note">Προτιμάτε να μιλήσετε; Καλέστε μας στο {phone}{viber}.</p>'
        return f"{steps}\n{estimate_form_html()}\n{note}"
    if not TALLY_ID:
        return f"{steps}\n<p>Καλέστε μας στο {phone}{viber}.</p>"
    form_page = f"https://tally.so/r/{quote(TALLY_ID)}"
    embed = f"https://tally.so/embed/{quote(TALLY_ID)}?alignLeft=1&hideTitle=1&transparentBackground=1&dynamicHeight=1"
    return f"""{steps}
<div class="estimate-form" id="forma">
  <iframe data-tally-src="{esc(embed)}" loading="lazy" width="100%" height="620" title="Φόρμα δωρεάν εκτίμησης ζημιάς"></iframe>
  <noscript><p><a href="{esc(form_page)}">Ανοίξτε τη φόρμα εκτίμησης</a></p></noscript>
</div>
<p class="estimate-note">Δεν ανοίγει η φόρμα; <a href="{esc(form_page)}" target="_blank" rel="noopener">Ανοίξτε τη σε νέα καρτέλα</a>. Προτιμάτε να μιλήσετε; Καλέστε μας στο {phone}{viber}.</p>
<p class="estimate-note">Τα στοιχεία σας τα χρησιμοποιούμε μόνο για την εκτίμηση. Περισσότερα στην <a href="{PRIVACY_PATH}">πολιτική απορρήτου</a>.</p>"""


def block_privacy() -> str:
    """Body of /politiki-aporritou/. Sections for statistics and live Google reviews
    appear only when those features are switched on in data/business.json."""
    a = DATA["address"]
    email = DATA["email"]
    contact = f'στο <a href="{esc(VALUES["tel"])}">{esc(VALUES["phone"])}</a>' + (
        f' ή στο <a href="{esc(VALUES["mailto"])}">{esc(email)}</a>' if email else ""
    )
    google_privacy = '<a href="https://policies.google.com/privacy?hl=el" target="_blank" rel="noopener">πολιτική απορρήτου της Google</a>'
    parts = [
        "<h2>Ποιοι είμαστε</h2>",
        f"<p>Υπεύθυνος για τα στοιχεία σας είναι η επιχείρηση <strong>{esc(DATA['name'])}</strong>, "
        f"{esc(a['full'])}. Για οτιδήποτε σχετικά με τα στοιχεία σας, επικοινωνήστε μαζί μας {contact}.</p>",
        "<h2>Όταν επικοινωνείτε μαζί μας</h2>",
        "<p>Όταν μας καλείτε, μας στέλνετε email ή μήνυμα στο Viber, χρησιμοποιούμε όσα μας δίνετε "
        "(όνομα, τηλέφωνο, email, φωτογραφίες της ζημιάς, στοιχεία του αυτοκινήτου) μόνο για να σας απαντήσουμε, "
        "να κάνουμε την εκτίμηση και την επισκευή. Δεν τα πουλάμε και δεν τα δίνουμε σε άλλους, εκτός αν "
        "χρειάζεται για την ασφαλιστική σας με δική σας συμφωνία ή αν το ζητά ο νόμος (π.χ. για την έκδοση παραστατικών).</p>",
        "<p>Τα μηνύματα στο Viber περνούν από την υπηρεσία Viber και τα email από τον πάροχο email μας, "
        "σύμφωνα με τους δικούς τους όρους.</p>",
        "<h2>Χάρτης Google</h2>",
        "<p>Στην αρχική σελίδα υπάρχει χάρτης από τους Χάρτες Google, για να βρίσκετε εύκολα το συνεργείο. "
        "Όταν φτάνετε κοντά στον χάρτη, ο browser σας τον φορτώνει απευθείας από την Google. Έτσι η Google "
        "λαμβάνει τη διεύθυνση IP σας και μπορεί να χρησιμοποιήσει δικά της cookies. Για αυτά ισχύει η "
        f"{google_privacy}. Αν δεν θέλετε να φορτώσει ο χάρτης, μην κατεβείτε μέχρι το τέλος της αρχικής σελίδας.</p>",
    ]
    if ESTIMATE_ENDPOINT:
        parts += [
            "<h2>Φόρμα δωρεάν εκτίμησης</h2>",
            f'<p>Όσα συμπληρώνετε στη φόρμα της σελίδας <a href="{ESTIMATE_PATH}">«Δωρεάν εκτίμηση»</a> (αυτοκίνητο, τι έπαθε, '
            "ασφαλιστική, φωτογραφίες, ονοματεπώνυμο, κινητό) αποθηκεύονται στον λογαριασμό μας στη Google: τα στοιχεία σε "
            "υπολογιστικό φύλλο Google Sheets και οι φωτογραφίες σε φάκελο Google Drive, με σύνδεσμο που δεν δημοσιεύεται πουθενά. "
            "Από εκεί μας στέλνονται αυτόματα, μέσω της υπηρεσίας αυτοματισμού Make, ως μήνυμα στο Telegram, για να δούμε γρήγορα "
            "το αίτημά σας. Πριν σταλούν, ο browser σας μικραίνει τις φωτογραφίες και αφαιρεί τα κρυφά τους στοιχεία (π.χ. την τοποθεσία).</p>",
            "<p>Για μια πρώτη ματιά, η περιγραφή της ζημιάς και μία φωτογραφία (όχι το όνομα και το κινητό σας) "
            "περνούν από το εργαλείο τεχνητής νοημοσύνης Gemini της Google, που μας γράφει μια σύντομη σύνοψη. "
            "Είναι μόνο βοήθημα: την εκτίμηση την κάνουμε εμείς.</p>",
            "<p>Χρησιμοποιούμε αυτά τα στοιχεία μόνο για την εκτίμηση και, αν μας αναθέσετε τη δουλειά, για την επισκευή, "
            "και τα κρατάμε μόνο όσο χρειάζεται γι' αυτό. Η Google και το Telegram μπορεί να επεξεργαστούν στοιχεία "
            "και εκτός ΕΕ. Μπορείτε να ζητήσετε οποιαδήποτε στιγμή να διαγράψουμε το αίτημά σας.</p>",
        ]
    elif TALLY_ID:
        parts += [
            "<h2>Φόρμα δωρεάν εκτίμησης</h2>",
            f'<p>Η φόρμα στη σελίδα <a href="{ESTIMATE_PATH}">«Δωρεάν εκτίμηση»</a> λειτουργεί μέσω της υπηρεσίας '
            "Tally (Tally BV, Βέλγιο). Όσα συμπληρώνετε (αυτοκίνητο, τι έπαθε, ασφαλιστική, φωτογραφίες, "
            "ονοματεπώνυμο, κινητό) αποθηκεύονται στο Tally και σε υπολογιστικό φύλλο Google Sheets (Google), "
            "και μας στέλνονται αυτόματα, μέσω της υπηρεσίας αυτοματισμού Make, ως μήνυμα στο Telegram, "
            "για να δούμε γρήγορα το αίτημά σας.</p>",
            "<p>Για μια πρώτη ματιά, η περιγραφή της ζημιάς και μία φωτογραφία (όχι το όνομα και το κινητό σας) "
            "περνούν από το εργαλείο τεχνητής νοημοσύνης Gemini της Google, που μας γράφει μια σύντομη σύνοψη. "
            "Είναι μόνο βοήθημα: την εκτίμηση την κάνουμε εμείς.</p>",
            "<p>Χρησιμοποιούμε αυτά τα στοιχεία μόνο για την εκτίμηση και, αν μας αναθέσετε τη δουλειά, για την επισκευή, "
            "και τα κρατάμε μόνο όσο χρειάζεται γι' αυτό. Η Google και το Telegram μπορεί να επεξεργαστούν στοιχεία "
            "και εκτός ΕΕ. Μπορείτε να ζητήσετε οποιαδήποτε στιγμή να διαγράψουμε το αίτημά σας.</p>",
        ]
    if GA4_ID:
        parts += [
            "<h2>Στατιστικά επισκεψιμότητας (Google Analytics)</h2>",
            "<p>Χρησιμοποιούμε το Google Analytics της Google Ireland Limited <strong>μόνο αν πατήσετε «Αποδοχή»</strong> "
            "στο μήνυμα για τα cookies. Μας δείχνει συγκεντρωτικά πόσοι επισκέπτονται το site, ποιες σελίδες διαβάζουν, "
            "από πού ήρθαν (π.χ. αναζήτηση στο Google), με τι συσκευή και από ποια περιοχή κατά προσέγγιση. "
            "Δεν μας λέει ποιος είστε και δεν αποθηκεύει τη διεύθυνση IP σας. Δεν το χρησιμοποιούμε για διαφημίσεις.</p>",
            '<ul class="service-list">'
            "<li><strong>Cookies</strong>: <code>_ga</code> και <code>_ga_…</code>, διάρκεια έως 2 χρόνια.</li>"
            "<li><strong>Πόσο κρατιούνται τα στατιστικά</strong>: έως 14 μήνες.</li>"
            "<li><strong>Πού</strong>: η Google μπορεί να επεξεργαστεί στοιχεία και εκτός ΕΕ (π.χ. ΗΠΑ), με τις εγγυήσεις "
            "του πλαισίου EU-US Data Privacy Framework.</li>"
            "</ul>",
            "<p>Μπορείτε να αλλάξετε την επιλογή σας οποιαδήποτε στιγμή: "
            '<button class="fb-btn fb-btn-primary privacy-consent-btn" type="button" data-consent-open>Ρυθμίσεις cookies</button></p>',
        ]
    if VALUES["reviewsApiKey"]:
        parts += [
            "<h2>Κριτικές Google</h2>",
            "<p>Οι κριτικές που φαίνονται στην αρχική σελίδα είναι γραμμένες στο ίδιο το site. Τις πιο πρόσφατες κριτικές "
            "από την Google τις φορτώνουμε <strong>μόνο αν πατήσετε «Εμφάνιση κριτικών Google»</strong>. Τότε ο browser σας "
            f"επικοινωνεί με την Google, που λαμβάνει τη διεύθυνση IP σας ({google_privacy}).</p>",
        ]
    stored = (
        "Η επιλογή σας για τα cookies στατιστικών αποθηκεύεται στη συσκευή σας για 12 μήνες, για να μη σας ρωτάμε σε κάθε σελίδα."
        if GA4_ID else "Το ίδιο το site δεν βάζει cookies."
    )
    parts += [
        "<h2>Τι αποθηκεύεται στη συσκευή σας</h2>",
        f"<p>{stored} Οι γραμματοσειρές φορτώνουν από το ίδιο το site, όχι από την Google.</p>",
        "<h2>Φιλοξενία του site</h2>",
        "<p>Όπως σε κάθε site, ο server που φιλοξενεί τις σελίδες καταγράφει τεχνικά στοιχεία των επισκέψεων "
        "(διεύθυνση IP, ώρα, σελίδα, browser) για λόγους ασφάλειας και λειτουργίας.</p>",
        "<h2>Τα δικαιώματά σας</h2>",
        "<p>Μπορείτε να ζητήσετε να δείτε, να διορθώσετε ή να διαγράψουμε τα στοιχεία σας, να περιορίσουμε ή να σταματήσουμε "
        f"τη χρήση τους, και να τα πάρετε σε ηλεκτρονική μορφή. Επικοινωνήστε μαζί μας {contact}. "
        "Αν πιστεύετε ότι δεν σεβαστήκαμε τα δικαιώματά σας, μπορείτε να κάνετε καταγγελία στην "
        '<a href="https://www.dpa.gr" target="_blank" rel="noopener">Αρχή Προστασίας Δεδομένων Προσωπικού Χαρακτήρα</a>.</p>',
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------- services
def md_inline(text: str) -> str:
    """Escape text and turn **bold** into <strong>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text, quote=False))


def md_plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def service_card(service: dict) -> str:
    """ServiceCard (design system): the whole card is one link to the service page."""
    name = service["image"]
    sizes = SERVICE_IMAGES.get(name)
    if sizes:
        w, h = sizes["800"]
        thumb = (
            f'<img src="/images/services/{name}-800.webp" '
            f'srcset="/images/services/{name}-800.webp {sizes["800"][0]}w, /images/services/{name}-1600.webp {sizes["1600"][0]}w" '
            f'sizes="(max-width: 767px) 100vw, (max-width: 1024px) 50vw, 360px" '
            f'alt="{esc(service["imageAlt"])}" width="{w}" height="{h}" loading="lazy" decoding="async">'
        )
    else:  # no photo yet: grey box with the service name
        thumb = f'<span class="service-thumb-label">{esc(service["cardTitle"])}</span>'
    dark = " fb-card-dark service-card--dark" if service.get("dark") else ""
    return f"""<a class="fb-card service-card{dark}" href="/{service['slug']}/">
  <span class="fb-thumb service-thumb">{thumb}</span>
  <h3 class="fb-card-title">{esc(service['cardTitle'])}</h3>
  <p class="fb-card-text">{md_inline(service['cardText'])}</p>
  <span class="service-more">Μάθετε περισσότερα <span aria-hidden="true">→</span></span>
</a>"""


def service_panel(service: dict) -> str:
    """Home page only: one tall photo panel per service, side by side across the whole
    screen width (like the reference's service band). The whole panel is one link.
    Uses homeImage (falls back to the card photo)."""
    name = service.get("homeImage") or service["image"]
    alt = service.get("homeImageAlt") or service["imageAlt"]
    sizes = SERVICE_IMAGES.get(name)
    img = ""
    if sizes:
        w, h = sizes["800"]
        img = (
            f'<img class="service-panel-img" src="/images/services/{name}-800.webp" '
            f'srcset="/images/services/{name}-800.webp {sizes["800"][0]}w, /images/services/{name}-1600.webp {sizes["1600"][0]}w" '
            f'sizes="(max-width: 1024px) 100vw, 34vw" alt="{esc(alt)}" width="{w}" height="{h}" '
            f'style="--focus: {esc(service.get("homeFocus", "50% 50%"))}" loading="lazy" decoding="async">'
        )
    return f"""<a class="service-panel" href="/{service['slug']}/">
  {img}
  <div class="service-panel-body">
    <h3 class="service-panel-title">{esc(service['cardTitle'])}</h3>
    <p class="service-panel-text">{md_inline(service['cardText'])}</p>
    <span class="service-more">Μάθετε περισσότερα <span aria-hidden="true">→</span></span>
  </div>
</a>"""


def block_services() -> str:
    """Home page «Υπηρεσίες»: title, the full-width band of three photo panels,
    the «Επίσης» strip. (The service pages keep the smaller cards: service_card.)"""
    home = SERVICES["home"]
    panels = "\n".join(service_panel(s) for s in SERVICES["services"])
    extras = "\n".join(f"      <li>{md_inline(x)}</li>" for x in home.get("extras", []))
    return f"""<div class="container">
  <div class="services-head" data-reveal="fade">
    <span class="fb-eyebrow">{esc(home['eyebrow'])}</span>
    <h2 class="fb-heading-xl" id="services-title">{esc(home['title'])}</h2>
    <p class="fb-descr">{esc(home['description'])}</p>
  </div>
</div>
<div class="services-band" data-reveal-group>
{panels}
</div>
<div class="container">
  <div class="services-extras">
    <p class="fb-eyebrow">{esc(home.get('extrasTitle', 'ΕΠΙΣΗΣ'))}</p>
    <ul>
{extras}
    </ul>
  </div>
</div>"""


def find_review(author: str) -> dict | None:
    return next((r for r in REVIEWS.get("items", []) if r.get("author") == author), None)


def review_html(author: str) -> str:
    review = find_review(author)
    if not review:
        return "<p>[κριτική πελάτη]</p>"
    name = short_name(review["author"]) if REVIEWS.get("nameStyle", "short") == "short" else review["author"]
    rating = max(1, min(5, int(review.get("rating", 5))))
    text = "<br>".join(esc(line) for line in review["text"].split("\n"))
    return f"""<figure class="service-review">
  <span class="review-stars" role="img" aria-label="{rating} από 5 αστέρια">{"★" * rating}{"☆" * (5 - rating)}</span>
  <blockquote><p>«{text}»</p></blockquote>
  <figcaption>— {esc(name)}, <a href="{esc(VALUES['reviewsUrl'])}" target="_blank" rel="noopener">κριτική στο Google</a></figcaption>
</figure>"""


def service_content(service: dict) -> str:
    parts = [f'<p class="service-lead">{md_inline(service["intro"])}</p>']
    for block in service["blocks"]:
        if "h2" in block:
            parts.append(f"<h2>{esc(block['h2'])}</h2>")
        elif "list" in block:
            items = "\n".join(f"  <li>{md_inline(i)}</li>" for i in block["list"])
            parts.append(f'<ul class="service-list">\n{items}\n</ul>')
        elif "steps" in block:
            items = "\n".join(f"  <li>{md_inline(i)}</li>" for i in block["steps"])
            parts.append(f'<ol class="service-steps">\n{items}\n</ol>')
        elif "p" in block:
            parts.append(f"<p>{md_inline(block['p'])}</p>")
    if service.get("review"):
        parts.append("<h2>Τι λένε οι πελάτες μας</h2>")
        parts.append(review_html(service["review"]))
    if service.get("faqs"):
        parts.append("<h2>Συχνές ερωτήσεις</h2>")
        for faq in service["faqs"]:
            parts.append(f'<h3>{esc(faq["q"])}</h3>\n<p>{md_inline(faq["a"])}</p>')
    return "\n".join(parts)


def service_cta(service: dict) -> str:
    viber_html = (
        f'<a class="fb-btn fb-btn-outline" href="{esc(VALUES["viberUrl"])}">Στείλτε φωτογραφία στο Viber</a>'
        if VALUES["viberUrl"]
        else '<span class="service-cta-pending">[Viber]</span>'
    )
    return f"""<section class="service-cta" id="ektimisi" aria-labelledby="cta-title">
  <div class="container">
    <div class="service-cta-box">
      <h2 class="service-cta-text" id="cta-title">{md_inline(service['cta'])}</h2>
      <div class="fb-row">
        <a class="fb-btn fb-btn-primary" href="{esc(VALUES['tel'])}">Καλέστε {esc(VALUES['phone'])}</a>
        {viber_html}
      </div>
    </div>
  </div>
</section>"""


def service_schemas(service: dict) -> str:
    url = site_url(f"/{service['slug']}/")
    graph = [
        {
            "@context": "https://schema.org",
            "@type": "Service",
            "@id": service_id(service),
            "name": service["name"],
            "serviceType": service["name"],
            "description": service["description"],
            "url": url,
            "image": site_url(f"/images/services/{service['image']}-1600.webp"),
            "provider": {"@id": site_url("/#business")},
            "areaServed": [{"@type": "Place", "name": p} for p in DATA["areaServed"]],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Αρχική", "item": site_url("/")},
                {"@type": "ListItem", "position": 2, "name": "Υπηρεσίες", "item": site_url("/#ypiresies")},
                {"@type": "ListItem", "position": 3, "name": service["cardTitle"], "item": url},
            ],
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": md_plain(f["a"])}}
                for f in service.get("faqs", [])
            ],
        },
    ]
    return "\n".join(json_ld(item) for item in graph)


def hero_picture(service: dict) -> str:
    """Top of a service page: the looping video (heroVideo) if it exists, else the photo.
    Same pattern as the home page hero: light file for portrait phones, poster frame
    until it plays, still with "reduce motion" (js/site.js), under the dark overlay."""
    video = service.get("heroVideo")
    if video and (ROOT / "assets" / "video" / f"service-{video}.mp4").exists():
        mobile = ROOT / "assets" / "video" / f"service-{video}-mobile.mp4"
        mobile_src = (
            f'<source src="/assets/video/service-{video}-mobile.mp4" type="video/mp4" '
            'media="(max-width: 760px) and (orientation: portrait)">'
            if mobile.exists() else ""
        )
        # heroFocus: which part of the frame stays visible in the wide, low hero (CSS object-position)
        focus = f' style="object-position: {esc(service["heroFocus"])}"' if service.get("heroFocus") else ""
        return (
            '<video class="hero-video parallax-media" autoplay muted loop playsinline preload="auto" '
            f'disablepictureinpicture aria-hidden="true" poster="/images/services/{video}-poster.webp"{focus}>'
            f'{mobile_src}<source src="/assets/video/service-{video}.mp4" type="video/mp4">'
            "</video>"
        )
    name = service["image"]
    sizes = SERVICE_IMAGES.get(name)
    if not sizes:
        return "<!-- no photo yet: dark background -->"
    w, h = sizes["1600"]
    return (
        '<picture class="section-bg parallax-media">'
        f'<img src="/images/services/{name}-1600.webp" '
        f'srcset="/images/services/{name}-800.webp {sizes["800"][0]}w, /images/services/{name}-1600.webp {w}w" '
        f'sizes="100vw" alt="{esc(service["imageAlt"])}" width="{w}" height="{h}" fetchpriority="high" decoding="async">'
        "</picture>"
    )


def generate_service_pages() -> list[Path]:
    template_path = ROOT / "templates" / "service.html"
    if not template_path.exists() or not SERVICES["services"]:
        return []
    template = template_path.read_text(encoding="utf-8")
    written = []
    for service in SERVICES["services"]:
        others = "\n".join(service_card(s) for s in SERVICES["services"] if s["slug"] != service["slug"])
        values = {
            "title": esc(service["title"]),
            "description": esc(service["description"], quote=True),
            "service_schema": service_schemas(service),
            "hero_picture": hero_picture(service),
            "h1": esc(service["h1"]),
            "lead": md_inline(service["cardText"]),
            "breadcrumb": esc(service["cardTitle"]),
            "content": service_content(service),
            "cta": service_cta(service),
            "other_cards": others,
            "estimate_href": ESTIMATE_PATH if HAS_ESTIMATE_FORM else "#ektimisi",
        }
        page = template
        for key, value in values.items():
            page = page.replace("{{" + key + "}}", value)
        out = ROOT / service["slug"] / "index.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(page, encoding="utf-8", newline="\n")
        written.append(out)
    return written


def block_map_info() -> str:
    hours = "<br>".join(f"{esc(l['days'])}: {esc(l['time'])}" for l in DATA["hours"]["lines"])
    return f"""<dl class="map-info">
  <dt>Διεύθυνση</dt>
  <dd><address class="footer-address">{esc(VALUES['address'])}</address></dd>
  <dt>Ωράριο</dt>
  <dd>{hours}</dd>
  <dt>Τηλέφωνο</dt>
  <dd><a href="{esc(VALUES['tel'])}">{esc(VALUES['phone'])}</a></dd>
</dl>"""


# ---------------------------------------------------------------- page processing
BLOCK_RE = re.compile(r"(?P<indent>[ \t]*)<!-- biz:(?P<name>[\w-]+) -->.*?<!-- /biz:(?P=name) -->", re.S)
TEXT_RE = re.compile(r'(<(?P<tag>\w+)\b[^>]*\bdata-biz="(?P<key>\w+)"[^>]*>)(?P<inner>.*?)(</(?P=tag)>)', re.S)
ATTRS_RE = re.compile(r'<\w+\b[^>]*\bdata-biz-attrs="(?P<spec>[^"]+)"[^>]*>', re.S)


def set_attr(tag: str, name: str, value: str) -> str:
    value = esc(value, quote=True)
    pattern = re.compile(rf'(\s{re.escape(name)}=")[^"]*(")')
    if pattern.search(tag):
        return pattern.sub(lambda m: m.group(1) + value + m.group(2), tag, count=1)
    end = -2 if tag.endswith("/>") else -1
    return f'{tag[:end]} {name}="{value}"{tag[end:]}'


def page_url_path(file: Path) -> str:
    rel = file.relative_to(ROOT).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def process(file: Path) -> list[str]:
    text = file.read_text(encoding="utf-8")
    warnings = []
    is_404 = file.name == "404.html"
    title_m = re.search(r"<title>(.*?)</title>", text, re.S)
    desc_m = re.search(r'<meta name="description" content="([^"]*)"', text)
    title = html.unescape(title_m.group(1).strip()) if title_m else ""
    desc = html.unescape(desc_m.group(1)) if desc_m else ""

    renderers = {
        "head": lambda: block_head(page_url_path(file), title, desc, is_404),
        "schema": lambda: json_ld(business_schema()),
        "footer-contact": block_footer_contact,
        "footer-hours": block_footer_hours,
        "footer-copy": block_footer_copy,
        "map-info": block_map_info,
        "reviews-static": block_reviews_static,
        "header": lambda: block_header(page_url_path(file)),
        "footer": block_footer,
        "chat": block_chat,
        "services": block_services,
        "privacy": block_privacy,
        "estimate": block_estimate,
    }

    def render_block(m: re.Match) -> str:
        name, indent = m.group("name"), m.group("indent")
        if name not in renderers:
            warnings.append(f"unknown block biz:{name}")
            return m.group(0)
        body = "\n".join(indent + line if line else line for line in renderers[name]().split("\n"))
        return f"{indent}<!-- biz:{name} -->\n{body}\n{indent}<!-- /biz:{name} -->"

    text = BLOCK_RE.sub(render_block, text)

    def render_text(m: re.Match) -> str:
        key = m.group("key")
        if key not in VALUES:
            warnings.append(f'unknown data-biz="{key}"')
            return m.group(0)
        return m.group(1) + esc(VALUES[key], quote=False) + m.group(5)

    text = TEXT_RE.sub(render_text, text)

    def render_attrs(m: re.Match) -> str:
        tag = m.group(0)
        for pair in m.group("spec").split(";"):
            attr, _, key = pair.partition(":")
            if key not in VALUES:
                warnings.append(f"unknown data-biz-attrs key {key}")
                continue
            tag = set_attr(tag, attr.strip(), VALUES[key])
        return tag

    text = ATTRS_RE.sub(render_attrs, text)
    file.write_text(text, encoding="utf-8", newline="\n")

    # ---- checks
    h1 = len(re.findall(r"<h1\b", text))
    if h1 != 1:
        warnings.append(f"{h1} <h1> elements (should be 1)")
    if not is_404 and not 50 <= len(title) <= 60:
        warnings.append(f"title is {len(title)} characters (50-60): {title}")
    if not is_404 and not 140 <= len(desc) <= 160:
        warnings.append(f"description is {len(desc)} characters (140-160)")
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        try:
            json.loads(block)
        except json.JSONDecodeError as err:
            warnings.append(f"invalid JSON-LD: {err}")
    return warnings


def pages() -> list[Path]:
    found = []
    for file in sorted(ROOT.rglob("*.html")):
        if SKIP_DIRS & set(file.relative_to(ROOT).parts[:-1]):
            continue
        found.append(file)
    return found


def write_sitemap(files: list[Path]) -> None:
    entries = []
    for file in files:
        if file.name in NOT_IN_SITEMAP:
            continue
        lastmod = dt.date.fromtimestamp(file.stat().st_mtime).isoformat()
        entries.append(f"  <url>\n    <loc>{esc(site_url(page_url_path(file)))}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(entries) + "\n</urlset>\n"
    )
    (ROOT / "sitemap.xml").write_text(xml, encoding="utf-8", newline="\n")


def write_robots() -> None:
    bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
            "PerplexityBot", "Perplexity-User", "Google-Extended"]
    groups = "\n\n".join(f"User-agent: {bot}\nAllow: /" for bot in bots)
    robots = (
        "# Everything may be crawled: search engines and AI assistants alike.\n"
        "# Generated by scripts/build.py from data/business.json\n\n"
        "User-agent: *\nAllow: /\n\n"
        f"{groups}\n\n"
        f"Sitemap: {site_url('/sitemap.xml')}\n"
    )
    (ROOT / "robots.txt").write_text(robots, encoding="utf-8", newline="\n")


def main() -> int:
    generated = generate_service_pages()
    if generated:
        print("service pages: " + ", ".join(p.relative_to(ROOT).parent.as_posix() + "/" for p in generated))
    files = pages()
    problems = 0
    for file in files:
        warnings = process(file)
        rel = file.relative_to(ROOT).as_posix()
        print(f"{'OK  ' if not warnings else 'WARN'} {rel}")
        for w in warnings:
            print(f"     - {w}")
        problems += len(warnings)
    write_sitemap(files)
    write_robots()
    print(f"sitemap.xml: {sum(f.name not in NOT_IN_SITEMAP for f in files)} pages; robots.txt written")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
