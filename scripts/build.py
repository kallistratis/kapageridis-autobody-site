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
writeReviewUrl, reviewsApiKey, reviewsMinRating, foundingYear, appointmentUrl.

In data/services.json, {phone} is replaced by the phone number above.

It also checks every page: one <h1>, <title> 50-60 characters,
meta description 140-160 characters, valid JSON-LD.

3. Languages: Greek pages are the main site. English pages live under /en/ and say
   <html lang="en">; every generated block is then written in English (TEXT below,
   data/business.json -> "en", data/services.en.json). When a page exists in both
   languages, both get hreflang links, an EN/ΕΛ switch in the header and sitemap entries.
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


def map_embed_url(lang: str = "el") -> str:
    # Google's keyless embed: the place query is base64url-encoded inside "pb"; !1s<lang> = map labels
    token = base64.urlsafe_b64encode(DATA["address"]["full"].encode()).decode().rstrip("=")
    return f"https://www.google.com/maps/embed?origin=mfe&pb=!1m3!2m1!1z{token}!6i16!3m1!1s{lang}!5m1!1s{lang}"


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
APPOINTMENT_FORM = DATA.get("appointmentForm") or {}
APPOINTMENT_ENDPOINT = APPOINTMENT_FORM.get("endpoint", "").strip()   # our form -> Google Apps Script
APPOINTMENT_PATH = "/rantevou/"

# «Κλείστε ραντεβού» buttons: the appointment page if the form is connected, else the contact details
VALUES["appointmentUrl"] = APPOINTMENT_PATH if APPOINTMENT_ENDPOINT else "#epikoinonia"


def fill_tokens(value, phone: str | None = None):
    """Put the phone number from business.json into texts that say {phone}."""
    phone = phone or VALUES["phone"]
    if isinstance(value, str):
        return value.replace("{phone}", phone)
    if isinstance(value, list):
        return [fill_tokens(v, phone) for v in value]
    if isinstance(value, dict):
        return {k: fill_tokens(v, phone) for k, v in value.items()}
    return value


SERVICES = fill_tokens(SERVICES)

esc = html.escape


# ---------------------------------------------------------------- languages
LANG = "el"  # language of the page being written; set by process()
EN = DATA.get("en") or {}
EN_PHONE = EN.get("phoneDisplay") or DATA["phone"]["display"]
SERVICES_EN = fill_tokens(_load("services.en.json", {"home": {}, "services": []}), EN_PHONE)
# photos and videos of an English service come from its Greek twin; every text must be in services.en.json
MEDIA_KEYS = ("image", "homeImage", "homeFocus", "heroVideo", "heroFocus", "dark", "review")
PAIRS: dict[str, str] = {}  # Greek page path -> English page path, for pages that exist in both (main())


def url_exists(url_path: str) -> bool:
    return (ROOT / url_path.strip("/") / "index.html").exists()


def page_pairs() -> dict[str, str]:
    pairs = {"/": "/en/", APPOINTMENT_PATH: "/en/appointment/", PRIVACY_PATH: "/en/privacy-policy/"}
    pairs.update({f"/{s['greek']}/": f"/en/{s['slug']}/" for s in SERVICES_EN.get("services", [])})
    return {gr: en for gr, en in pairs.items() if url_exists(gr) and url_exists(en)}


def counterpart(page_path: str) -> str | None:
    """The same page in the other language, if it exists."""
    if LANG == "en":
        return next((gr for gr, en in PAIRS.items() if en == page_path), None)
    return PAIRS.get(page_path)


def href(greek_path: str) -> str:
    """Link to a Greek page; on English pages its English version when there is one."""
    return PAIRS.get(greek_path, greek_path) if LANG == "en" else greek_path


VALUES_EN = {
    "name": EN.get("name") or DATA.get("latinName") or DATA["name"],
    "shortName": "Kapageridis",
    "phone": EN_PHONE,
    "address": EN.get("address") or DATA["address"]["full"],
    "mapEmbed": map_embed_url("en"),
    "callLabel": f"Call us on {EN_PHONE}",
    "phoneLabel": f"Phone {EN_PHONE}",
}


class LangValues(dict):
    """VALUES that answer in the language of the page being written."""

    def __getitem__(self, key):
        if LANG == "en":
            if key == "appointmentUrl":
                return href(APPOINTMENT_PATH) if APPOINTMENT_ENDPOINT else "#contact"
            if key in VALUES_EN:
                return VALUES_EN[key]
        return super().__getitem__(key)


VALUES = LangValues(VALUES)

TEXT = {
    "el": {
        "nav": [("Αρχική", "/", "home"), ("Σχετικά", "/#sxetika", None), ("Υπηρεσίες", "/#ypiresies", "services"),
                ("Πριν & Μετά", "/#prin-meta", None), ("Επικοινωνία", "#epikoinonia", None)],
        "home": "/", "contactId": "epikoinonia", "locale": "el_GR",
        "mainMenu": "Κεντρικό μενού", "menu": "Μενού", "contact": "Επικοινωνία", "hours": "Ωράριο",
        "services": "Υπηρεσίες", "footerMenu": "Μενού", "footerMenuLabel": "Μενού στο κάτω μέρος",
        "privacy": "Πολιτική απορρήτου", "cookies": "Ρυθμίσεις cookies",
        "phone": "Τηλέφωνο", "emailNote": "Στείλτε μας μήνυμα", "chatLabel": "Επικοινωνία: τηλέφωνο ή email",
        "consentTitle": "Cookies στατιστικών",
        "consentText": "Με το Google Analytics μετράμε πόσοι επισκέπτονται το site και ποιες σελίδες διαβάζουν, "
                       "για να το κάνουμε καλύτερο. Ενεργοποιείται μόνο αν το επιτρέψετε.",
        "deny": "Απόρριψη", "accept": "Αποδοχή",
        "outOf5": "από 5 αστέρια", "reviewsOnGoogle": "κριτικές στο Google", "fullReview": "Ολόκληρη η κριτική στο Google",
        "reviewsRegion": "Κριτικές πελατών από το Google", "learnMore": "Μάθετε περισσότερα", "also": "ΕΠΙΣΗΣ",
        "address": "Διεύθυνση",
        "switch": ("en", "EN", "English"),
        "font": "greek", "book": "Κλείστε ραντεβού", "call": "Καλέστε", "breadcrumb": "Διαδρομή",
        "homeLabel": "Αρχική", "servicesAnchor": "/#ypiresies", "otherServices": "Άλλες υπηρεσίες",
        "customersSay": "Τι λένε οι πελάτες μας", "faq": "Συχνές ερωτήσεις", "googleReview": "κριτική στο Google",
        "ctaId": "ektimisi",
    },
    "en": {
        "nav": [("Home", "/en/", "home"), ("About", "/en/#about", None), ("Services", "/en/#services", "services"),
                ("Before & After", "/en/#before-after", None), ("Contact", "#contact", None)],
        "home": "/en/", "contactId": "contact", "locale": "en_GB",
        "mainMenu": "Main menu", "menu": "Menu", "contact": "Contact", "hours": "Opening hours",
        "services": "Services", "footerMenu": "Menu", "footerMenuLabel": "Footer menu",
        "privacy": "Privacy policy", "cookies": "Cookie settings",
        "phone": "Phone", "emailNote": "Send us a message", "chatLabel": "Contact: phone or email",
        "consentTitle": "Statistics cookies",
        "consentText": "With Google Analytics we count how many people visit the site and which pages they read, "
                       "so we can make it better. It is switched on only if you allow it.",
        "deny": "Reject", "accept": "Accept",
        "outOf5": "out of 5 stars", "reviewsOnGoogle": "reviews on Google", "fullReview": "Read the full review on Google",
        "reviewsRegion": "Customer reviews from Google", "learnMore": "Learn more", "also": "ALSO",
        "address": "Address",
        "switch": ("el", "ΕΛ", "Ελληνικά"),
        "font": "latin", "book": "Book an appointment", "call": "Call", "breadcrumb": "Breadcrumb",
        "homeLabel": "Home", "servicesAnchor": "/en/#services", "otherServices": "Other services",
        "customersSay": "What our customers say", "faq": "Frequently asked questions",
        "googleReview": "Google review, in Greek", "ctaId": "estimate",
    },
}


def t(key: str):
    return TEXT[LANG][key]


def services_list() -> list[dict]:
    """The services in the page's language (English ones get their photos from the Greek twin)."""
    if LANG != "en":
        return SERVICES["services"]
    greek = {s["slug"]: s for s in SERVICES["services"]}
    return [{**{k: v for k, v in greek[s["greek"]].items() if k in MEDIA_KEYS}, **s} for s in SERVICES_EN["services"]]


def service_href(service: dict) -> str:
    if LANG == "en":
        return f"/en/{service['slug']}/" if service.get("h1") else href(f"/{service['greek']}/")
    return f"/{service['slug']}/"


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


def service_page(service: dict) -> str:
    """URL path of a service page: /fanopoiia/ or /en/car-body-repair/."""
    return f"/en/{service['slug']}/" if "greek" in service else f"/{service['slug']}/"


def service_id(service: dict) -> str:
    return site_url(service_page(service) + "#service")


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
    pair = None if is_404 else counterpart(page_path)
    if pair:
        greek, english = (page_path, pair) if LANG == "el" else (pair, page_path)
        lines += [
            f'<link rel="alternate" hreflang="el" href="{esc(site_url(greek))}">',
            f'<link rel="alternate" hreflang="en" href="{esc(site_url(english))}">',
            f'<link rel="alternate" hreflang="x-default" href="{esc(site_url(greek))}">',
        ]
    lines += [
        '<meta property="og:type" content="website">',
        f'<meta property="og:locale" content="{t("locale")}">',
        *([f'<meta property="og:locale:alternate" content="{TEXT["en" if LANG == "el" else "el"]["locale"]}">'] if pair else []),
        f'<meta property="og:site_name" content="{esc(VALUES["name"])}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
    ]
    if not is_404:
        lines.append(f'<meta property="og:url" content="{esc(site_url(page_path))}">')
    lines += [
        f'<meta property="og:image" content="{esc(site_url(img["og"]))}">',
        f'<meta property="og:image:width" content="{img["ogWidth"]}">',
        f'<meta property="og:image:height" content="{img["ogHeight"]}">',
        f'<meta property="og:image:alt" content="{esc(EN.get("ogAlt", img["ogAlt"]) if LANG == "en" else img["ogAlt"])}">',
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


def hours_lines() -> list[dict]:
    return EN.get("hours") or DATA["hours"]["lines"] if LANG == "en" else DATA["hours"]["lines"]


def block_footer_hours() -> str:
    rows = "\n".join(
        f"  <dt>{esc(upper_no_accents(line['days']))}:</dt><dd>{esc(upper_no_accents(line['time']))}</dd>"
        for line in hours_lines()
    )
    return f'<dl class="footer-hours">\n{rows}\n</dl>'


def block_footer_copy() -> str:
    cookie_btn = (
        f' · <button class="footer-link-btn" type="button" data-consent-open>{t("cookies")}</button>'
        if GA4_ID else ""
    )
    return (
        '<div class="footer-bottom">\n'
        f'  <p class="footer-copy">© {TODAY.year} {esc(VALUES["name"])}. All rights reserved. '
        "Proudly serving Thessaloniki with precision and integrity.</p>\n"
        f'  <p class="footer-legal"><a href="{href(PRIVACY_PATH)}">{t("privacy")}</a>{cookie_btn}</p>\n'
        "</div>"
    )


def short_name(full: str) -> str:
    """'Maria Ntotsika' -> 'Maria N.' (first name + initial). Same rule as js/reviews.js."""
    parts = full.split()
    if len(parts) < 2:
        return full
    return f"{parts[0]} {parts[-1][0].upper()}."


def greek_number(value: float) -> str:
    """4.9 -> "4,9" on Greek pages, "4.9" on English ones."""
    return f"{value:.1f}" if LANG == "en" else f"{value:.1f}".replace(".", ",")


GREEK_MONTHS = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος",
                "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"]
ENGLISH_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                  "August", "September", "October", "November", "December"]


def review_date(text: str) -> str:
    """"Νοέμβριος 2026" -> "November 2026" on English pages."""
    if LANG == "en":
        for greek, english in zip(GREEK_MONTHS, ENGLISH_MONTHS):
            text = text.replace(greek, english)
    return text


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
    <span class="review-stars" role="img" aria-label="{score} {t('outOf5')}">{"★" * full}{"☆" * (5 - full)}</span>
    <a class="reviews-count" href="{esc(VALUES['reviewsUrl'])}" target="_blank" rel="noopener">{int(summary["count"])} {t('reviewsOnGoogle')}</a>
  </p>"""
        )

    cards = []
    review_lang = ' lang="el"' if LANG != "el" else ""  # reviews stay word for word, in Greek
    for item in items:
        rating = max(1, min(5, int(item.get("rating", 5))))
        name = short_name(item["author"]) if use_short else item["author"]
        text = "<br>".join(esc(line) for line in item["text"].split("\n"))
        date = f'\n          <p class="review-time">{esc(review_date(item["date"]))}</p>' if item.get("date") else ""
        more = (
            f'\n      <a class="review-more" href="{esc(VALUES["reviewsUrl"])}" target="_blank" rel="noopener">'
            f"{t('fullReview')}</a>"
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
      <span class="review-stars" role="img" aria-label="{rating} {t('outOf5')}">{"★" * rating}{"☆" * (5 - rating)}</span>
      <p class="review-text"{review_lang}>{text}</p>{more}
    </li>"""
        )
    out.append(
        '  <div class="reviews-carousel" data-reviews-carousel>\n'
        f'    <div class="reviews-viewport" tabindex="0" role="region" aria-label="{t("reviewsRegion")}">\n'
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

# Main menu: TEXT[lang]["nav"] = (label, link, which page it marks as current)


def section_of(page_path: str) -> str | None:
    if page_path == t("home"):
        return "home"
    if any(page_path in (f"/{s['slug']}/", f"/en/{s['slug']}/") for s in services_list()):
        return "services"
    return None


def logo_img(width: int, sizes: str, lazy: bool) -> str:
    height = round(width * 195 / 400)
    extra = ' loading="lazy" decoding="async"' if lazy else ""
    return (
        f'<img src="/images/brand/logo-{width}.webp" srcset="/images/brand/logo-400.webp 400w, '
        f'/images/brand/logo-800.webp 800w" sizes="{sizes}" alt="{esc(VALUES["name"])}" '
        f'width="{width}" height="{height}"{extra}>'
    )


def block_header(page_path: str) -> str:
    current = section_of(page_path)
    links = []
    for label, link, key in t("nav"):
        mark = ""
        if key and key == current:
            mark = ' aria-current="page"' if key == "home" else ' aria-current="true"'
        links.append(f'    <a href="{link}"{mark}>{esc(label)}</a>')
    # EN / ΕΛ: the same page in the other language, only when it exists
    other = counterpart(page_path)
    lang, text, label = t("switch")
    switch = (
        f'\n    <a class="lang-switch" href="{other}" hreflang="{lang}" lang="{lang}" aria-label="{label}">{text}</a>'
        if other else ""
    )
    return f"""<header class="fb-header">
  <nav class="fb-nav" id="main-nav" aria-label="{t('mainMenu')}">
{chr(10).join(links)}
  </nav>
  <a class="fb-logo site-logo" href="{t('home')}">
    {logo_img(400, "170px", lazy=False)}
  </a>
  <div class="fb-social">{switch}
    <a href="{esc(VALUES['instagram'])}" target="_blank" rel="noopener" aria-label="Instagram">{ICON['instagram']}</a>
    <a href="{esc(VALUES['tel'])}" aria-label="{esc(VALUES['phoneLabel'])}">{ICON['phone']}</a>
  </div>
  <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="main-nav" aria-label="{t('menu')}">
    {ICON['menu']}
  </button>
</header>"""


def block_footer() -> str:
    menu = "\n".join(f'      <li><a href="{link}">{esc(upper_no_accents(label))}</a></li>' for label, link, _ in t("nav"))
    services = "\n".join(
        f'      <li><a href="{service_href(s)}">{esc(upper_no_accents(s.get("menuLabel") or s["name"]))}</a></li>'
        for s in services_list()
    )
    indent = lambda text, n: "\n".join(" " * n + line for line in text.split("\n"))  # noqa: E731
    return f"""<footer class="fb-footer" id="{t('contactId')}">
  <div class="footer-col">
    <h2 class="visually-hidden">{t('contact')}</h2>
{indent(block_footer_contact(), 4)}
    <div class="fb-social">
      <a href="{esc(VALUES['instagram'])}" target="_blank" rel="noopener" aria-label="Instagram">{ICON['instagram']}</a>
    </div>
  </div>
  <div class="footer-col">
    <h2 class="footer-title">{upper_no_accents(t('hours'))}</h2>
{indent(block_footer_hours(), 4)}
  </div>
  <nav class="footer-col" aria-label="{t('services')}">
    <h2 class="footer-title">{upper_no_accents(t('services'))}</h2>
    <ul class="footer-menu">
{services}
    </ul>
  </nav>
  <nav class="footer-col" aria-label="{t('footerMenuLabel')}">
    <h2 class="footer-title">{upper_no_accents(t('footerMenu'))}</h2>
    <ul class="footer-menu">
{menu}
    </ul>
  </nav>
  <div class="footer-col footer-col-logo">
    <a class="footer-logo" href="{t('home')}">
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
      <span>{t('phone')}<small>{esc(VALUES['phone'])}</small></span>
    </a>
    <a class="chat-option" href="{esc(VALUES['mailto'])}">
      <span class="chat-option-icon">{ICON['mail']}</span>
      <span>Email<small>{t('emailNote')}</small></span>
    </a>
  </div>
  <button class="fb-chat-btn" type="button" aria-expanded="false" aria-controls="chat-menu" aria-label="{t('chatLabel')}">
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
  <h2 class="consent-title" id="consent-title">{t('consentTitle')}</h2>
  <p class="consent-text">{t('consentText')} <a href="{href(PRIVACY_PATH)}">{t('privacy')}</a></p>
  <div class="consent-actions">
    <button class="fb-btn fb-btn-outline" type="button" data-consent="denied">{t('deny')}</button>
    <button class="fb-btn fb-btn-outline" type="button" data-consent="granted">{t('accept')}</button>
  </div>
</div>"""


# Words of the appointment form. The insurance VALUES stay Greek in both languages:
# the Apps Script and the Make message expect exactly these.
INSURANCE_CHOICES = ("Ναι", "Όχι, ιδιωτικά", "Δεν ξέρω ακόμα")
FORM = {
    "el": {
        "car": "Αυτοκίνητο (μάρκα, μοντέλο, χρονιά)", "carHint": "π.χ. Toyota Yaris 2018",
        "damage": "Τι έπαθε το αυτοκίνητο;", "damageHint": "π.χ. Με χτύπησαν στο πάρκινγκ, βαθούλωμα στην πίσω πόρτα",
        "insurance": "Θα πάει μέσω ασφαλιστικής;", "choices": INSURANCE_CHOICES, "insurer": "Ποια ασφαλιστική;",
        "day": "Ημέρα", "time": "Ώρα", "prev": "Προηγούμενος μήνας", "next": "Επόμενος μήνας",
        "week": ("Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"), "open": "Διαθέσιμες μέρες",
        "notice": "Το ραντεβού κλείνει όταν σας στείλουμε <strong>μήνυμα επιβεβαίωσης</strong> στο κινητό.",
        "name": "Ονοματεπώνυμο", "phone": "Κινητό (εδώ θα έρθει το μήνυμα επιβεβαίωσης)", "phoneHint": "69xx xxx xxx",
        "consent": "Συμφωνώ να χρησιμοποιηθούν τα στοιχεία μου μόνο για το ραντεβού ({link}).",
        "privacyLink": "πολιτική απορρήτου", "honeypot": "Αφήστε το κενό", "submit": "Κλείστε ραντεβού",
        "noscript": "Η φόρμα χρειάζεται JavaScript. Καλέστε μας στο {phone}.",
        "doneTitle": "Ευχαριστούμε! Λάβαμε το αίτημά σας.",
        "done": "Θα σας στείλουμε μήνυμα στο κινητό μόλις επιβεβαιώσουμε τη μέρα και την ώρα. "
                "Αν η ώρα δεν είναι διαθέσιμη, θα σας προτείνουμε άλλη.",
        "steps": ("Πείτε μας για το αυτοκίνητο", "Διαλέξτε μέρα και ώρα", "Σας στέλνουμε μήνυμα επιβεβαίωσης"),
        "noForm": "Καλέστε μας στο {phone} για να κλείσουμε ραντεβού.",
        "callNote": "Προτιμάτε να μιλήσετε; Καλέστε μας στο {phone}.",
    },
    "en": {
        "car": "Car (make, model, year)", "carHint": "e.g. Toyota Yaris 2018",
        "damage": "What happened to the car?", "damageHint": "e.g. Someone hit me in a car park, dent in the rear door",
        "insurance": "Will it go through insurance?", "choices": ("Yes", "No, I will pay myself", "Not sure yet"),
        "insurer": "Which insurance company?",
        "day": "Day", "time": "Time", "prev": "Previous month", "next": "Next month",
        "week": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), "open": "Available days",
        "notice": "Your appointment is booked once we send you a <strong>confirmation text message</strong> on your mobile.",
        "name": "Full name", "phone": "Mobile (the confirmation text comes here)", "phoneHint": "+30 69xx xxx xxx",
        "consent": "I agree that my details are used only for this appointment ({link}).",
        "privacyLink": "privacy policy", "honeypot": "Leave this empty", "submit": "Book an appointment",
        "noscript": "The form needs JavaScript. Call us on {phone}.",
        "doneTitle": "Thank you! We have received your request.",
        "done": "We will text you as soon as we confirm the day and time. "
                "If that time is not available, we will suggest another one.",
        "steps": ("Tell us about the car", "Choose a day and time", "We text you to confirm"),
        "noForm": "Call us on {phone} to book an appointment.",
        "callNote": "Prefer to talk? Call us on {phone}.",
    },
}


def appointment_form_html() -> str:
    """The appointment request form. js/appointment.js draws the month calendar (working
    days of the next 30 days are open), the half-hour slots of the opening hours, checks the
    answers and sends them to the Google Apps Script at appointmentForm.endpoint, which adds
    one row to the requests sheet. Make forwards it to the shop's Telegram and the shop sends
    the customer a confirmation text message."""
    f = FORM[LANG]
    choices = "\n".join(
        f'      <label class="ef-choice"><input type="radio" name="insurance" value="{value}"><span>{esc(label)}</span></label>'
        for value, label in zip(INSURANCE_CHOICES, f["choices"])
    )
    week = "".join(f"<span>{d}</span>" for d in f["week"])
    hours = DATA["hours"]
    privacy = f'<a href="{href(PRIVACY_PATH)}">{f["privacyLink"]}</a>'
    return f"""<form class="ef" id="forma" novalidate data-appointment-form data-endpoint="{esc(APPOINTMENT_ENDPOINT)}" data-phone="{esc(VALUES['phone'])}" data-opens="{esc(hours['opens'])}" data-closes="{esc(hours['closes'])}">
  <div class="ef-field">
    <label class="ef-label" for="ef-car">{f['car']} <span class="ef-req">*</span></label>
    <input class="ef-input" id="ef-car" name="car" type="text" maxlength="200" placeholder="{esc(f['carHint'])}" required>
  </div>
  <div class="ef-field">
    <label class="ef-label" for="ef-damage">{f['damage']} <span class="ef-req">*</span></label>
    <textarea class="ef-input ef-textarea" id="ef-damage" name="damage" rows="3" maxlength="3000" placeholder="{esc(f['damageHint'])}" required></textarea>
  </div>
  <fieldset class="ef-field" data-group="insurance">
    <legend class="ef-label">{f['insurance']} <span class="ef-req">*</span></legend>
    <div class="ef-choices">
{choices}
    </div>
  </fieldset>
  <div class="ef-field" data-insurer hidden>
    <label class="ef-label" for="ef-insurer">{f['insurer']}</label>
    <input class="ef-input" id="ef-insurer" name="insurer" type="text" maxlength="200">
  </div>
  <div class="ef-when">
    <fieldset class="ef-field" data-group="date">
      <legend class="ef-label">{f['day']} <span class="ef-req">*</span></legend>
      <div class="ef-cal" data-calendar>
        <div class="ef-cal-head">
          <p class="ef-cal-title" data-cal-title aria-live="polite"></p>
          <div class="ef-cal-nav">
            <button class="ef-cal-arrow" type="button" data-cal-prev aria-label="{f['prev']}"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
            <button class="ef-cal-arrow" type="button" data-cal-next aria-label="{f['next']}"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button>
          </div>
        </div>
        <div class="ef-cal-week" aria-hidden="true">{week}</div>
        <div class="ef-cal-grid" data-cal-grid></div>
        <p class="ef-cal-legend"><span class="ef-cal-key" aria-hidden="true"></span>{f['open']}</p>
      </div>
      <input type="hidden" name="date" value="">
    </fieldset>
    <fieldset class="ef-field" data-group="time">
      <legend class="ef-label">{f['time']} <span class="ef-req">*</span></legend>
      <div class="ef-choices ef-times" data-times></div>
    </fieldset>
  </div>
  <p class="ef-picked" data-picked aria-live="polite" hidden></p>
  <p class="ef-notice"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span>{f['notice']}</span></p>
  <div class="ef-field">
    <label class="ef-label" for="ef-name">{f['name']} <span class="ef-req">*</span></label>
    <input class="ef-input" id="ef-name" name="name" type="text" autocomplete="name" maxlength="200" required>
  </div>
  <div class="ef-field">
    <label class="ef-label" for="ef-phone">{f['phone']} <span class="ef-req">*</span></label>
    <input class="ef-input" id="ef-phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="{f['phoneHint']}" required>
  </div>
  <div class="ef-field" data-group="consent">
    <label class="ef-check"><input type="checkbox" name="consent" required><span>{f['consent'].format(link=privacy)}</span></label>
  </div>
  <div class="ef-hp" aria-hidden="true"><label>{f['honeypot']} <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
  <p class="ef-error" role="alert" data-error hidden></p>
  <button class="fb-btn fb-btn-primary ef-submit" type="submit">{f['submit']}</button>
  <noscript><p class="ef-error">{f['noscript'].format(phone=esc(VALUES['phone']))}</p></noscript>
</form>
<div class="ef-done" data-done hidden tabindex="-1">
  <h2 class="ef-done-title">{f['doneTitle']}</h2>
  <p>{f['done']}</p>
</div>"""


def block_appointment() -> str:
    """Body of /rantevou/ and /en/appointment/: three steps, the form, the phone as the other way."""
    f = FORM[LANG]
    phone = f'<a href="{esc(VALUES["tel"])}">{esc(VALUES["phone"])}</a>'
    steps = '<ol class="booking-steps">\n' + "\n".join(f"  <li>{step}</li>" for step in f["steps"]) + "\n</ol>"
    if not APPOINTMENT_ENDPOINT:
        return f"{steps}\n<p>{f['noForm'].format(phone=phone)}</p>"
    note = f'<p class="booking-note">{f["callNote"].format(phone=phone)}</p>'
    return f"{steps}\n{appointment_form_html()}\n{note}"


def block_privacy_en() -> str:
    """Body of /en/privacy-policy/: the English text of block_privacy(), same sections."""
    email = DATA["email"]
    contact = f'on <a href="{esc(VALUES["tel"])}">{esc(VALUES["phone"])}</a>' + (
        f' or at <a href="{esc(VALUES["mailto"])}">{esc(email)}</a>' if email else ""
    )
    google_privacy = '<a href="https://policies.google.com/privacy?hl=en" target="_blank" rel="noopener">Google\'s privacy policy</a>'
    parts = [
        "<h2>Who we are</h2>",
        f'<p>The business responsible for your details is <strong lang="el">{esc(DATA["name"])}</strong> '
        f"({esc(VALUES['name'])}), {esc(VALUES['address'])}. For anything about your details, contact us {contact}.</p>",
        "<h2>When you contact us</h2>",
        "<p>When you call or email us, we use what you give us (name, phone number, email, photos of the damage, "
        "details of the car) only to answer you, to give you an estimate and to carry out the repair. We do not sell it "
        "or pass it on to anyone else, unless it is needed for your insurance claim with your agreement or the law "
        "requires it (for example for issuing invoices).</p>",
        "<p>Emails pass through our email provider, under its own terms.</p>",
        "<h2>Google Maps</h2>",
        "<p>The home page shows a map from Google Maps, so you can find the workshop easily. When you scroll near the "
        "map, your browser loads it directly from Google. Google then receives your IP address and may use its own "
        f"cookies; {google_privacy} applies to these. If you do not want the map to load, do not scroll to the end of "
        "the home page.</p>",
    ]
    if APPOINTMENT_ENDPOINT:
        parts += [
            "<h2>Appointment form</h2>",
            f'<p>What you fill in on the <a href="{href(APPOINTMENT_PATH)}">“Book an appointment”</a> page (car, what '
            "happened, insurance, day and time, full name, mobile number) is stored in a Google Sheets spreadsheet in our "
            "Google account and sent to us automatically, through the automation service Make, as a Telegram message, "
            "so that we can confirm the appointment with a text message to your mobile.</p>",
            "<p>We use these details only for the appointment, the estimate and, if you give us the job, the repair, "
            "and we keep them only as long as needed for that. Google and Telegram may process data outside the EU. "
            "You can ask us at any time to delete your request.</p>",
        ]
    if GA4_ID:
        parts += [
            "<h2>Visitor statistics (Google Analytics)</h2>",
            "<p>We use Google Analytics by Google Ireland Limited <strong>only if you press “Accept”</strong> in the "
            "cookie message. It shows us, in total, how many people visit the site, which pages they read, where they "
            "came from (for example a Google search), what device they use and roughly from which area. It does not tell "
            "us who you are and does not store your IP address. We do not use it for advertising.</p>",
            '<ul class="service-list">'
            "<li><strong>Cookies</strong>: <code>_ga</code> and <code>_ga_…</code>, kept for up to 2 years.</li>"
            "<li><strong>How long statistics are kept</strong>: up to 14 months.</li>"
            "<li><strong>Where</strong>: Google may process data outside the EU (for example in the USA), with the "
            "safeguards of the EU-US Data Privacy Framework.</li>"
            "</ul>",
            "<p>You can change your choice at any time: "
            f'<button class="fb-btn fb-btn-primary privacy-consent-btn" type="button" data-consent-open>{t("cookies")}</button></p>',
        ]
    stored = (
        "Your choice about statistics cookies is stored on your device for 12 months, so we do not ask you on every page."
        if GA4_ID else "The site itself sets no cookies."
    )
    parts += [
        "<h2>What is stored on your device</h2>",
        f"<p>{stored} The fonts load from this site itself, not from Google.</p>",
        "<h2>Hosting</h2>",
        "<p>Like every website, the server that hosts these pages records technical details of visits "
        "(IP address, time, page, browser) for security and to keep the site running.</p>",
        "<h2>Your rights</h2>",
        "<p>You can ask to see, correct or delete your details, to restrict or stop their use, and to receive them in "
        f"electronic form. Contact us {contact}. If you believe we have not respected your rights, you can complain to "
        'the <a href="https://www.dpa.gr/en" target="_blank" rel="noopener">Hellenic Data Protection Authority</a>.</p>',
    ]
    return "\n".join(parts)


def block_privacy() -> str:
    """Body of /politiki-aporritou/. Sections for statistics and live Google reviews
    appear only when those features are switched on in data/business.json.
    English pages get block_privacy_en() (keep both in step when a section changes)."""
    if LANG == "en":
        return block_privacy_en()
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
        "<p>Όταν μας καλείτε ή μας στέλνετε email, χρησιμοποιούμε όσα μας δίνετε "
        "(όνομα, τηλέφωνο, email, φωτογραφίες της ζημιάς, στοιχεία του αυτοκινήτου) μόνο για να σας απαντήσουμε, "
        "να κάνουμε την εκτίμηση και την επισκευή. Δεν τα πουλάμε και δεν τα δίνουμε σε άλλους, εκτός αν "
        "χρειάζεται για την ασφαλιστική σας με δική σας συμφωνία ή αν το ζητά ο νόμος (π.χ. για την έκδοση παραστατικών).</p>",
        "<p>Τα email περνούν από τον πάροχο email μας, "
        "σύμφωνα με τους δικούς του όρους.</p>",
        "<h2>Χάρτης Google</h2>",
        "<p>Στην αρχική σελίδα υπάρχει χάρτης από τους Χάρτες Google, για να βρίσκετε εύκολα το συνεργείο. "
        "Όταν φτάνετε κοντά στον χάρτη, ο browser σας τον φορτώνει απευθείας από την Google. Έτσι η Google "
        "λαμβάνει τη διεύθυνση IP σας και μπορεί να χρησιμοποιήσει δικά της cookies. Για αυτά ισχύει η "
        f"{google_privacy}. Αν δεν θέλετε να φορτώσει ο χάρτης, μην κατεβείτε μέχρι το τέλος της αρχικής σελίδας.</p>",
    ]
    if APPOINTMENT_ENDPOINT:
        parts += [
            "<h2>Φόρμα ραντεβού</h2>",
            f'<p>Όσα συμπληρώνετε στη φόρμα της σελίδας <a href="{APPOINTMENT_PATH}">«Κλείστε ραντεβού»</a> (αυτοκίνητο, τι έπαθε, '
            "ασφαλιστική, μέρα και ώρα, ονοματεπώνυμο, κινητό) αποθηκεύονται σε υπολογιστικό φύλλο Google Sheets, στον λογαριασμό "
            "μας στη Google, και μας στέλνονται αυτόματα, μέσω της υπηρεσίας αυτοματισμού Make, ως μήνυμα στο Telegram, "
            "για να σας επιβεβαιώσουμε το ραντεβού με μήνυμα στο κινητό σας.</p>",
            "<p>Χρησιμοποιούμε αυτά τα στοιχεία μόνο για το ραντεβού, την εκτίμηση και, αν μας αναθέσετε τη δουλειά, την επισκευή, "
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
    return f"""<a class="fb-card service-card{dark}" href="{service_href(service)}">
  <span class="fb-thumb service-thumb">{thumb}</span>
  <h3 class="fb-card-title">{esc(service['cardTitle'])}</h3>
  <p class="fb-card-text">{md_inline(service['cardText'])}</p>
  <span class="service-more">{t('learnMore')} <span aria-hidden="true">→</span></span>
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
    return f"""<a class="service-panel" href="{service_href(service)}">
  {img}
  <div class="service-panel-body">
    <h3 class="service-panel-title">{esc(service['cardTitle'])}</h3>
    <p class="service-panel-text">{md_inline(service['cardText'])}</p>
    <span class="service-more">{t('learnMore')} <span aria-hidden="true">→</span></span>
  </div>
</a>"""


def block_services() -> str:
    """Home page «Υπηρεσίες»: title, the full-width band of three photo panels,
    the «Επίσης» strip. (The service pages keep the smaller cards: service_card.)"""
    home = SERVICES_EN["home"] if LANG == "en" else SERVICES["home"]
    panels = "\n".join(service_panel(s) for s in services_list())
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
    <p class="fb-eyebrow">{esc(home.get('extrasTitle', t('also')))}</p>
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
        return "<p>[review]</p>"
    name = short_name(review["author"]) if REVIEWS.get("nameStyle", "short") == "short" else review["author"]
    rating = max(1, min(5, int(review.get("rating", 5))))
    text = "<br>".join(esc(line) for line in review["text"].split("\n"))
    return f"""<figure class="service-review">
  <span class="review-stars" role="img" aria-label="{rating} {t('outOf5')}">{"★" * rating}{"☆" * (5 - rating)}</span>
  <blockquote{' lang="el"' if LANG != "el" else ""}><p>«{text}»</p></blockquote>
  <figcaption>— {esc(name)}, <a href="{esc(VALUES['reviewsUrl'])}" target="_blank" rel="noopener">{t('googleReview')}</a></figcaption>
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
        parts.append(f"<h2>{t('customersSay')}</h2>")
        parts.append(review_html(service["review"]))
    if service.get("faqs"):
        parts.append(f"<h2>{t('faq')}</h2>")
        for faq in service["faqs"]:
            parts.append(f'<h3>{esc(faq["q"])}</h3>\n<p>{md_inline(faq["a"])}</p>')
    return "\n".join(parts)


def service_cta(service: dict) -> str:
    # second button: the appointment form, when the site has one
    appointment_html = (
        f'<a class="fb-btn fb-btn-outline" href="{href(APPOINTMENT_PATH)}">{t("book")}</a>'
        if APPOINTMENT_ENDPOINT else ""
    )
    return f"""<section class="service-cta" id="{t('ctaId')}" aria-labelledby="cta-title">
  <div class="container">
    <div class="service-cta-box">
      <h2 class="service-cta-text" id="cta-title">{md_inline(service['cta'])}</h2>
      <div class="fb-row">
        <a class="fb-btn fb-btn-primary" href="{esc(VALUES['tel'])}">{t('call')} {esc(VALUES['phone'])}</a>
        {appointment_html}
      </div>
    </div>
  </div>
</section>"""


def service_schemas(service: dict) -> str:
    url = site_url(service_page(service))
    graph = [
        {
            "@context": "https://schema.org",
            "@type": "Service",
            "@id": service_id(service),
            "inLanguage": LANG,
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
                {"@type": "ListItem", "position": 1, "name": t("homeLabel"), "item": site_url(t("home"))},
                {"@type": "ListItem", "position": 2, "name": t("services"), "item": site_url(t("servicesAnchor"))},
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
    """Greek pages /<slug>/ from services.json, English pages /en/<slug>/ from services.en.json."""
    global LANG
    template_path = ROOT / "templates" / "service.html"
    if not template_path.exists() or not SERVICES["services"]:
        return []
    template = template_path.read_text(encoding="utf-8")
    written = []
    for LANG in ("el", "en"):
        for page in service_pages(template):
            written.append(page)
    LANG = "el"
    return written


def service_pages(template: str) -> list[Path]:
    written = []
    services = [s for s in services_list() if LANG == "el" or s.get("h1")]  # English: only fully written ones
    for service in services:
        others = "\n".join(service_card(s) for s in services_list() if s["slug"] != service["slug"])
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
            "appointment_href": href(APPOINTMENT_PATH) if APPOINTMENT_ENDPOINT else f"#{t('ctaId')}",
            "lang": LANG,
            "font": t("font"),
            "book": t("book"),
            "breadcrumb_label": t("breadcrumb"),
            "home_href": t("home"),
            "home_label": t("homeLabel"),
            "services_href": t("servicesAnchor"),
            "services_label": t("services"),
            "other_title": t("otherServices"),
        }
        page = template
        for key, value in values.items():
            page = page.replace("{{" + key + "}}", value)
        out = ROOT / service_page(service).strip("/") / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8", newline="\n")
        written.append(out)
    return written


def block_map_info() -> str:
    hours = "<br>".join(f"{esc(l['days'])}: {esc(l['time'])}" for l in hours_lines())
    return f"""<dl class="map-info">
  <dt>{t('address')}</dt>
  <dd><address class="footer-address">{esc(VALUES['address'])}</address></dd>
  <dt>{t('hours')}</dt>
  <dd>{hours}</dd>
  <dt>{t('phone')}</dt>
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
    global LANG
    text = file.read_text(encoding="utf-8")
    warnings = []
    lang_m = re.search(r'<html\b[^>]*\blang="([a-z]{2})', text)
    LANG = lang_m.group(1) if lang_m and lang_m.group(1) in TEXT else "el"
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
        "appointment": block_appointment,
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
    english_to_greek = {en: gr for gr, en in PAIRS.items()}
    for file in files:
        if file.name in NOT_IN_SITEMAP:
            continue
        path = page_url_path(file)
        lastmod = dt.date.fromtimestamp(file.stat().st_mtime).isoformat()
        alternates = ""
        greek = path if path in PAIRS else english_to_greek.get(path)
        if greek:  # the page exists in both languages: tell Google which is which
            alternates = "".join(
                f'\n    <xhtml:link rel="alternate" hreflang="{lang}" href="{esc(site_url(target))}"/>'
                for lang, target in (("el", greek), ("en", PAIRS[greek]), ("x-default", greek))
            )
        entries.append(f"  <url>\n    <loc>{esc(site_url(path))}</loc>\n    <lastmod>{lastmod}</lastmod>{alternates}\n  </url>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(entries) + "\n</urlset>\n"
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
    global PAIRS
    PAIRS = page_pairs()  # pages that already exist (appointment, privacy), for links inside the service pages
    generated = generate_service_pages()
    PAIRS = page_pairs()
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
