"""통증 시리즈의 콘텐츠·공개 상태·구조화 데이터. UI는 templates/pain_series.html."""
import json
from pathlib import Path
from urllib.parse import quote

DATA_PATH = Path(__file__).parent / "content" / "pain-series.json"
ALLOWED_STATUSES = {"draft", "review", "published"}


def load_series(review=False):
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    validate_series(data)
    visible = {"published", "review"} if review else {"published"}
    # A partially drafted series must never appear as a complete public series.
    if data["status"] not in visible or any(t["status"] not in visible for t in data["topics"]):
        return None
    for position, topic in enumerate(data["topics"], 1):
        topic["position"] = position
        topic["path"] = "conditions/" + quote(topic["slug"], safe="")
        topic["image_small"] = topic["image"].replace(".webp", "-480.webp")
    return data


def validate_series(data):
    required = ["id", "status", "path", "title", "h1", "description", "summary", "created_at", "updated_at", "faq", "topics"]
    if any(not data.get(k) for k in required):
        raise ValueError("Series is missing required content")
    if len(data["topics"]) != 6:
        raise ValueError("This series must define exactly six distinct topics")
    for entity in [data] + data["topics"]:
        if entity["status"] not in ALLOWED_STATUSES:
            raise ValueError("Unsupported content status")
        if entity["status"] == "published":
            # Explicit editorial gate; never infer a clinician's approval.
            for key in ("published_at", "reviewed_by", "reviewed_at"):
                if not (entity.get(key) or (entity is not data and data.get(key))):
                    raise ValueError("Published medical content needs actual publication and review fields")
    for key in ("slug", "id", "image", "title", "description", "summary"):
        values = [t.get(key) for t in data["topics"]]
        if not all(values) or len(set(values)) != 6:
            raise ValueError("Missing or duplicate topic field: " + key)
    for topic in data["topics"]:
        for key in ("h1", "subtitle", "card_title", "card_description", "image_alt", "sections", "checklist", "red_flag", "faq", "sources"):
            if not topic.get(key):
                raise ValueError("Missing topic content: " + key)
        if len({s["id"] for s in topic["sections"]}) != len(topic["sections"]):
            raise ValueError("Duplicate section anchors")
        for section in topic["sections"]:
            if not section.get("title") or not section.get("paragraphs"):
                raise ValueError("Empty section")
            if any(i < 1 or i > len(topic["sources"]) for i in section["sources"]):
                raise ValueError("Invalid source reference")


def schemas(series, topic, origin):
    hub_url = origin + "/" + series["path"]
    page_url = origin + "/" + (topic["path"] if topic else series["path"])
    crumbs = [
        {"@type": "ListItem", "position": 1, "name": "홈", "item": origin + "/"},
        {"@type": "ListItem", "position": 2, "name": "통증 가이드", "item": hub_url},
    ]
    if topic:
        crumbs.append({"@type": "ListItem", "position": 3, "name": topic["topic"], "item": page_url})
    nodes = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "@id": page_url + "#breadcrumb", "itemListElement": crumbs},
        {"@context": "https://schema.org", "@type": "ItemList", "@id": page_url + "#topics", "name": "여섯 가지 통증 가이드", "numberOfItems": 6,
         "itemListElement": [{"@type": "ListItem", "position": t["position"], "name": t["topic"],
                              "image": origin + "/" + t["image"], "url": origin + "/" + t["path"]} for t in series["topics"]]},
    ]
    if topic:
        node = {"@context": "https://schema.org", "@type": "Article", "@id": page_url + "#article",
                "headline": topic["h1"], "description": topic["description"], "url": page_url,
                "image": origin + "/" + topic["image"], "inLanguage": "ko-KR",
                "mainEntityOfPage": {"@id": page_url + "#webpage"},
                "isPartOf": {"@id": hub_url + "#collection"},
                "author": {"@type": "Organization", "name": "연결한의원 청주오창"},
                "publisher": {"@id": origin + "/#clinic"},
                "dateCreated": topic.get("created_at", series["created_at"]),
                "dateModified": topic.get("updated_at", series["updated_at"]),
                "citation": [s["url"] for s in topic["sources"]]}
        if topic["status"] == "published":
            node["datePublished"] = topic.get("published_at") or series["published_at"]
        nodes.append(node)
    else:
        nodes.append({"@context": "https://schema.org", "@type": "CollectionPage", "@id": hub_url + "#collection",
                      "url": hub_url, "name": series["h1"], "description": series["description"],
                      "image": origin + "/" + series["topics"][0]["image"],
                      "mainEntity": {"@id": hub_url + "#topics"}, "inLanguage": "ko-KR"})
    # Visible FAQs remain plain content; no FAQ rich-result eligibility is implied.
    return nodes
