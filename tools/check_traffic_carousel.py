"""Audit rendered traffic galleries against their source and original URL pairs."""
import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
KMC = (ROOT / "src/content/clinical-catalog.json").exists()
CONTENT = ROOT / ("src/content" if KMC else "content")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.schemas, self.meta, self.ids, self.cards = [], [], [], []
        self.raw, self.in_schema, self.in_cards = "", False, False
        self.current = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "meta":
            self.meta.append(a)
        if tag == "script" and a.get("type") == "application/ld+json":
            self.in_schema, self.raw = True, ""
        if tag == "ol" and a.get("class") == "clinical-cards":
            self.in_cards = True
        if self.in_cards and tag == "a" and a.get("class") == "clinical-card":
            self.current = {"href": a["href"], "images": [], "text": ""}
            self.cards.append(self.current)
        if self.in_cards and tag == "img" and self.current is not None:
            self.current["images"].append(a)

    def handle_data(self, text):
        if self.in_schema:
            self.raw += text
        if self.in_cards and self.current is not None:
            self.current["text"] += text

    def handle_endtag(self, tag):
        if tag == "script" and self.in_schema:
            self.schemas.append(json.loads(self.raw))
            self.in_schema = False
        if tag == "a":
            self.current = None
        if tag == "ol":
            self.in_cards = False


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html-root", type=Path, required=True)
    args = parser.parse_args()
    cat = json.loads((ROOT / ("src/content/clinical-catalog.json" if KMC else "app/clinical-catalog.json")).read_text())
    manifest = json.loads((CONTENT / "traffic-accident-carousel-20261103.json").read_text())
    profiles = {p["id"]: p for p in cat["profiles"]}
    profile = profiles["other-accident-care"]
    before, after = dict(manifest["baseline"]), dict(profile)
    before.pop("updated_at")
    after.pop("updated_at")
    assert after == before, "Only the actual revision date may change in the source profile"
    for pid, sha in manifest["preserved_other_profiles"].items():
        assert digest(profiles[pid]) == sha, pid
    if KMC:
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        from site_info import SITE
        origin = SITE["url"].rstrip("/")
    else:
        origin = cat["config"]["origin"].rstrip("/")
    paths = [profile["hub_path"], *[t["path"] for t in profile["topics"]]]
    if KMC:
        paths.insert(0, "services/accident")
    expected = [(urljoin(origin + "/", t["path"]), urljoin(origin + "/", t["image"])) for t in profile["topics"]]
    results = []
    for path in paths:
        page = Page()
        page.feed((args.html_root / (path.lstrip("/") + ".html")).read_text())
        nodes = [node for schema in page.schemas for node in (schema if isinstance(schema, list) else schema.get("@graph", [schema]))]
        lists = [n for n in nodes if n.get("@type") == "ItemList"]
        assert len(lists) == 1, (path, "Expected one gallery ItemList")
        listing = lists[0]
        assert listing["numberOfItems"] == len(page.cards) == 6, path
        assert [n["position"] for n in listing["itemListElement"]] == list(range(1, 7)), path
        assert [(n["url"], n["image"]) for n in listing["itemListElement"]] == expected, path
        assert listing["@id"].split("#")[-1] in page.ids, path
        for topic, card, (url, image) in zip(profile["topics"], page.cards, expected):
            assert urljoin(origin + "/", card["href"]) == url, path
            assert len(card["images"]) == 1 and topic["question"] in card["text"], path
            picture = card["images"][0]
            assert picture.get("alt") == topic["image_alt"], path
            assert topic["image"].lstrip("/") in picture.get("srcset", ""), path
        target = next((t for t in profile["topics"] if t["path"] == path), None)
        expected_images = [urljoin(origin + "/", target["image"])] if target else [i for _, i in expected]
        assert [m["content"] for m in page.meta if m.get("property") == "og:image"] == expected_images, path
        page_node = next(n for n in nodes if n.get("@type") in ["Article", "CollectionPage"] or "MedicalWebPage" in n.get("@type", []))
        node_images = page_node["image"]
        assert (node_images if isinstance(node_images, list) else [node_images]) == expected_images, path
        if not target:
            assert page_node["mainEntity"]["@id"] == listing["@id"], path
        if target and not KMC:
            assert page_node["isPartOf"]["@id"] == origin + profile["hub_path"] + "#page", path
        robots = next(m["content"] for m in page.meta if m.get("name") == "robots")
        assert "noindex" not in robots and "max-image-preview:large" in robots.replace(" ", ""), path
        results.append({"path": path, "cards": 6, "og_images": len(expected_images), "ordered_original_pairs": True})
    result = {"status": "passed", "core_pages": len(results), "other_profiles_preserved": len(profiles) - 1,
              "body_titles_images_urls_preserved": True, "pages": results, "search_exposure": "Observed separately; not inferred from markup"}
    (ROOT / "verification/traffic-carousel-20261103.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "pages"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
