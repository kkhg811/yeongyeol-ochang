"""Verify every reviewed clinical URL, its six cards and rendered assets.

This verifies implementation and coverage, not clinical approval or search
engine crawling/indexing/exposure. It never makes HTTP requests to search engines.
"""
import hashlib
import json
import os
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("SITE_OUTPUT", ROOT / "docs"))
CAT = ROOT / "src/content/clinical-catalog.json"


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.meta, self.ids, self.links, self.images = {}, set(), [], []
        self.cards, self.schemas, self.h1, self.titles = [], [], [], []
        self.guide_terms = []
        self.title_on = self.h1_on = self.script_on = False
        self.card_on = self.card_title_on = False
        self.script = ""
        self.canonical = None
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("data-guide-name"):
            self.guide_terms.append(a["data-guide-name"])
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "meta":
            self.meta[a.get("name", a.get("property", ""))] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if tag in ("a", "link") and a.get("href"):
            self.links.append(a["href"])
        if tag in ("img", "script") and a.get("src"):
            self.links.append(a["src"])
        if tag == "a" and "clinical-card" in a.get("class", "").split():
            self.card_on = True
            self.cards.append({"url": a.get("href"), "current": a.get("aria-current"), "title": ""})
        if tag == "h3" and self.card_on:
            self.card_title_on = True
        if tag == "img":
            self.images.append(a)
            if self.card_on:
                self.cards[-1]["image"] = a
        if tag == "script" and a.get("type") == "application/ld+json":
            self.script_on, self.script = True, ""
        if tag == "title":
            self.title_on = True
        if tag == "h1":
            self.h1_on = True
            self.h1.append("")

    def handle_data(self, data):
        self.text.append(data)
        if self.title_on:
            self.titles.append(data)
        if self.h1_on:
            self.h1[-1] += data
        if self.script_on:
            self.script += data
        if self.card_title_on:
            self.cards[-1]["title"] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self.card_on = False
        if tag == "h3":
            self.card_title_on = False
        if tag == "h1":
            self.h1_on = False
        if tag == "title":
            self.title_on = False
        if tag == "script" and self.script_on:
            self.script_on = False
            parsed = json.loads(self.script)
            self.schemas.extend(parsed if isinstance(parsed, list) else [parsed])


def resolve_path(raw):
    path = unquote(urlsplit(raw).path).lstrip("/")
    path = path or "index.html"
    direct = OUT / path
    for candidate in (direct, direct / "index.html", OUT / (path.rstrip("/") + ".html")):
        if candidate.is_file():
            return candidate
    return None


def main():
    cat = json.loads(CAT.read_text())
    config, counts = cat["config"], cat["counts"]
    reviewing = (OUT / "review-routes.json").exists()
    origin = json.loads((OUT / "review-routes.json").read_text())["origin"] if reviewing else config["target_origin"]
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    check(counts["condition_urls"] == 299 and counts["column_urls"] == 318, "Inventory count differs from public list/source census")
    profiles = {p["id"]: p for p in cat["profiles"]}
    index = Page(resolve_path(config["index_path"]).read_text())
    normalize = lambda value: "".join(c for c in value if c not in " ·-_\t\n").lower()
    for entry in cat["conditions"]:
        check(any(normalize(entry["name"]) in normalize(terms) for terms in index.guide_terms), "Index filter cannot find existing topic: " + entry["name"])
    pages = []
    for entry in cat["conditions"] + cat["columns"]:
        pages.append((entry["path"], entry["canonical_path"], profiles[entry["profile_id"]], None))
    for profile in cat["profiles"]:
        if profile.get("standalone_hub"):
            pages.append((profile["hub_path"], profile["hub_path"], profile, None))
        for topic in profile["topics"]:
            pages.append((topic["path"], topic["path"], profile, topic))
    titles, descriptions = [], []
    checked_links = set()
    for path, canonical, profile, topic in pages:
        file = resolve_path(path)
        if not file:
            errors.append("Missing page: " + path)
            continue
        html = file.read_text()
        try:
            page = Page(html)
        except (ValueError, KeyError) as exc:
            errors.append(f"{path}: invalid HTML/schema {exc}")
            continue
        check(len(page.h1) == 1 and page.h1[0].strip(), path + ": H1")
        title = "".join(page.titles).strip()
        titles.append(title)
        descriptions.append(page.meta.get("description", ""))
        check(bool(title and page.meta.get("description")), path + ": metadata missing")
        check(page.canonical == origin + "/" + canonical, path + ": canonical mismatch")
        check(("noindex" in page.meta.get("robots", "")) == reviewing, path + ": robots policy mismatch")
        if not reviewing:
            check("chatgpt.site" not in html and "검토용 원고" not in html, path + ": review content leaked into production")
        check(page.meta.get("og:url") == page.canonical, path + ": OG URL mismatch")
        expected_image = origin + "/" + (topic or profile["topics"][0])["image"]
        check(page.meta.get("og:image") == expected_image, path + ": OG image mismatch")
        check(page.meta.get("twitter:image") == expected_image, path + ": Twitter image mismatch")
        check(len(page.cards) == 6, path + ": expected six initial HTML cards")
        itemlists = [n for n in page.schemas if n.get("@type") == "ItemList"]
        check(len(itemlists) == 1, path + ": expected one ItemList")
        if len(itemlists) == 1:
            items = itemlists[0]["itemListElement"]
            check(len(items) == 6, path + ": schema count")
            for card, item, expected in zip(page.cards, items, profile["topics"]):
                check(card["url"] == "/" + expected["path"] == urlsplit(item["url"]).path, path + ": card/schema order or URL mismatch")
                check(card["title"].strip() == item["name"] == expected["question"], path + ": card/schema name mismatch")
                check(item["position"] == expected["position"], path + ": position mismatch")
                check(item["image"] == origin + "/" + expected["image"], path + ": schema needs matching original image")
                check(card.get("image", {}).get("alt") == expected["image_alt"], path + ": card alt mismatch")
        current = [c for c in page.cards if c["current"] == "page"]
        check(len(current) == (1 if topic else 0), path + ": current topic state")
        if topic:
            check("/" + profile["hub_path"] in page.links, path + ": hub link missing")
            for adjacent in (topic["position"]-2, topic["position"]):
                if 0 <= adjacent < 6:
                    check("/" + profile["topics"][adjacent]["path"] in page.links, path + ": previous/next missing")
        check(not any(n.get("reviewedBy") for n in page.schemas), path + ": unverified expert review schema")
        check("작성·검토" not in html and "대표원장의 진료 노트" not in html, path + ": inherited unverified review claim")
        for image in page.images:
            check("alt" in image, path + ": image has no alt attribute")
            if image.get("src", "").startswith("/images/clinical-guides/"):
                check(bool(image.get("width") and image.get("height")), path + ": image dimensions missing")
        for raw in page.links:
            url = urlsplit(raw)
            if url.scheme or url.netloc:
                continue
            if raw.startswith("#"):
                check(url.fragment in page.ids, path + ": broken fragment " + raw)
            elif raw.startswith("/") and url.path not in checked_links:
                check(resolve_path(raw) is not None, path + ": broken local link " + raw)
                checked_links.add(url.path)
    for kind, values in (("title", titles), ("description", descriptions)):
        for value, count in Counter(values).items():
            check(count == 1, f"Duplicate {kind} ({count}): {value}")
    hashes, originals, renditions, max_bytes = set(), 0, 0, 0
    media = json.loads((ROOT / "src/content/clinical-card-images.json").read_text())
    check(media["catalog_sha256"] == hashlib.sha256(CAT.read_bytes()).hexdigest(), "Image manifest points to an old catalog")
    media_by_topic = {(a["profile_id"], a["topic"]): a for a in media["assets"]}
    for profile in cat["profiles"]:
        for topic in profile["topics"]:
            for key, size in (("image", 1080), ("image_small", 480)):
                file = OUT / topic[key]
                if not file.is_file():
                    errors.append("Missing image " + str(file))
                    continue
                with Image.open(file) as image:
                    check(image.size == (size, size) and image.format == "WEBP", topic[key] + ": image format/dimensions")
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
                declared = media_by_topic[(profile["id"], topic["id"])]["sha256" if key == "image" else "thumbnail_sha256"]
                check(digest == declared, topic[key] + ": image differs from its recorded SHA-256")
                check(digest not in hashes, topic[key] + ": duplicated image bytes")
                hashes.add(digest)
                max_bytes = max(max_bytes, file.stat().st_size)
                check(file.stat().st_size < 250000, topic[key] + ": excessive image weight")
                originals += key == "image"
                renditions += key == "image_small"
    for profile in cat["profiles"]:
        for member in profile["members"]:
            relationship = profile.get("member_relationships", {}).get(member, "canonical" if member == profile["canonical_slug"] else "related-symptom")
            if relationship not in ("canonical", "alias"):
                check(len(profile.get("member_contexts", {}).get(member, [])) >= 2, profile["id"] + ": distinct member explanation missing " + member)
    sitemap = ET.parse(OUT / "sitemap.xml").getroot()
    if reviewing:
        check(len(sitemap) == 0, "Review sitemap should not submit candidate pages")
    else:
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "i": "http://www.google.com/schemas/sitemap-image/1.1"}
        locations = [n.find("s:loc", ns).text for n in sitemap]
        check(len(locations) == len(set(locations)), "Duplicate sitemap URLs")
        expected = {origin + "/" + canonical for path, canonical, _, _ in pages if path == canonical}
        check(expected <= set(locations), "Published canonical clinical URLs missing from sitemap")
        for path, canonical, _, _ in pages:
            if path != canonical:
                check(origin + "/" + path not in locations, "Alias is incorrectly included in sitemap: " + path)
        for value in locations:
            check(value.startswith(origin + "/") and "/review/" not in value, "Non-public sitemap URL")
        check(not (OUT / "_headers").exists() and not (OUT / "review").exists(), "Review-only files in public distribution")
    report = {"stage": "review" if reviewing else "production", "implementation_checks": "passed" if not errors else "failed", "counts": counts,
              "rendered_clinical_pages_checked": len(pages), "unique_internal_targets_checked": len(checked_links),
              "original_images_checked": originals, "responsive_renditions_checked": renditions, "largest_image_bytes": max_bytes,
              "medical_review": "pending", "browser_http_checks": "see browser-qa.json",
              "search_exposure": cat["search_exposure"], "errors": errors}
    report_path = OUT / "review/validation.json" if reviewing else ROOT / "verification/clinical-production.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
