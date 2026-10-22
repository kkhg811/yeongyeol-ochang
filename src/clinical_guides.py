"""Read structured clinical content and generate matching page/series schemas."""
import json
import re
from pathlib import Path

CONTENT = Path(__file__).parent / "content"
PHASE_KEYS = ("symptoms", "context", "assessment", "care", "daily", "followup")
KIND_LABELS = {"condition": "질환 안내", "symptom": "증상 상담", "service": "진료 상담", "product": "복용 상담"}


def load_catalog(review=False):
    config = json.loads((CONTENT / "clinical-guides-config.json").read_text())
    if config["status"] == "draft" or (not review and config["status"] != "published"):
        return None
    path = CONTENT / "clinical-catalog.json"
    if not path.exists():
        raise ValueError("Compile complete editorial clinical content before building review pages")
    catalog = json.loads(path.read_text())
    if catalog["config"] != config:
        raise ValueError("Clinical configuration changed; recompile the catalog")
    if not review:
        authorization = config.get("publication_authorization", {})
        if not authorization.get("authorized_at") or not authorization.get("instruction"):
            raise ValueError("Public clinical content requires explicit site-owner publication authorization")
        for item in [catalog["config"]] + catalog["profiles"]:
            if item.get("status") != "published" or not item.get("published_at"):
                raise ValueError("Draft or unpublished clinical content cannot enter a public build")
            if bool(item.get("reviewed_by")) != bool(item.get("reviewed_at")):
                raise ValueError("Medical review attribution needs both a real reviewer and actual review date")
    catalog["profiles_by_id"] = {p["id"]: p for p in catalog["profiles"]}
    catalog["conditions_by_slug"] = {e["slug"]: e for e in catalog["conditions"]}
    catalog["columns_by_slug"] = {e["slug"]: e for e in catalog["columns"]}
    for profile in catalog["profiles"]:
        profile["kind_label"] = KIND_LABELS.get(profile["kind"], "상담 안내")
        if profile.get("priority"):
            related_ids = dict.fromkeys(b["related_id"] for b in profile["priority"]["branches"])
            profile["priority_related"] = [catalog["profiles_by_id"][pid] for pid in related_ids
                                           if pid != profile["id"] and pid in catalog["profiles_by_id"]]
    categories = {}
    for profile in catalog["profiles"]:
        categories.setdefault(profile["category"], []).append(profile)
    catalog["groups"] = [{"name": name, "id": "clinical-group-" + str(i), "profiles": sorted(rows, key=lambda p: p["name"])}
                         for i, (name, rows) in enumerate(categories.items())]
    return catalog


def page_nodes(catalog, profile, origin, path, *, entry=None, topic=None, is_column=False):
    url = origin + "/" + path
    name = topic["h1"] if topic else (entry["title"] if entry else "청주·오창 " + profile["name"])
    description = topic["description"] if topic else (entry["description"] if entry else profile["overview"])
    crumbs = [
        {"@type": "ListItem", "position": 1, "name": "홈", "item": origin + "/"},
        {"@type": "ListItem", "position": 2, "name": "질환별 가이드", "item": origin + "/" + catalog["config"]["index_path"]},
    ]
    if (topic or is_column) and path != profile["hub_path"]:
        crumbs.append({"@type": "ListItem", "position": 3, "name": profile["name"], "item": origin + "/" + profile["hub_path"]})
    crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": topic["label"] if topic else (entry.get("display_name", entry["name"]) if entry else profile["name"]), "item": url})
    nodes = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "@id": url + "#breadcrumb", "itemListElement": crumbs},
        {"@context": "https://schema.org", "@type": "ItemList", "@id": url + "#clinical-topics",
         "name": profile["name"] + " 여섯 가지 상담 주제", "numberOfItems": 6,
         "itemListElement": [{"@type": "ListItem", "position": t["position"], "name": t["question"],
                              "url": origin + "/" + t["path"], "image": origin + "/" + t["image"]} for t in profile["topics"]]},
    ]
    article = topic is not None or is_column
    node = {"@context": "https://schema.org", "@type": "Article" if article else "CollectionPage",
            "@id": url + ("#article" if article else "#collection"), "url": url,
            "headline" if article else "name": name, "description": description,
            "inLanguage": "ko-KR", "image": origin + "/" + (topic or profile["topics"][0])["image"],
            "dateModified": profile["updated_at"], "citation": list(dict.fromkeys([s["url"] for s in profile["sources"]] + [s["url"] for s in profile.get("priority", {}).get("evidence", [])])),
            "publisher": {"@id": origin + "/#clinic"}, "mainEntityOfPage": {"@id": url + "#webpage"}}
    if article:
        node["author"] = {"@type": "Organization", "name": "연결한의원 청주오창"}
        parent_path = catalog["config"]["index_path"] if path == profile["hub_path"] else profile["hub_path"]
        node["isPartOf"] = {"@id": origin + "/" + parent_path + "#webpage"}
        if profile.get("status") == "published" and profile.get("published_at"):
            node["datePublished"] = profile["published_at"]
    else:
        node["mainEntity"] = {"@id": url + "#clinical-topics"}
    nodes.append(node)
    return nodes


def clean_column_blocks(blocks):
    """Preserve reader questions and observation prompts, not unverified advice.

    Every legacy medical assertion remains in the source/audit, but is withheld
    from the review rendering. New explanatory sections use the curated clinical
    profile and its primary sources instead. Quoted questions are examples, not
    patient testimonials. This is editorial preparation, not clinician approval.
    """
    kept, withheld = [], []
    rules = [
        ("unverified-review", re.compile(r"작성\s*[·/및]*\s*검토|최근\s*검토|전문가\s*검수")),
        ("unverified-experience", re.compile(r"대표원장|저는|저희는|오시는\s*분들의|오창처럼|진료실에서|내원하신|환자분")),
        ("unverified-coverage-policy", re.compile(r"건강보험|본인부담|첩약.{0,15}적용|실손|실비")),
        ("keyword-list", re.compile(r"(?:한의원|오창|청주|원인|증상).{0,20}·.{0,30}·.{0,30}·")),
        ("unverified-price", re.compile(r"\d[\d,]*\s*(?:만원|원)(?:\s|[,.·]|$)")),
        ("unverified-frequency", re.compile(r"주\s*\d+\s*[~～-]?\s*\d*\s*회|연(?:간)?\s*\d+\s*회")),
        ("outcome-promise", re.compile(r"완치|100\s*%|부작용.{0,8}없|확실한\s*효과|반드시.{0,12}낫")),
        ("unsupported-effect", re.compile(r"조직\s*재생|혈류.{0,8}개선|염증.{0,10}가라앉|치료.{0,10}기간.{0,8}짧|명현")),
    ]
    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            continue
        reason = next((name for name, pattern in rules if pattern.search(text)), None)
        if reason:
            withheld.append({"reason": reason, "text": text})
        elif ((text.startswith("“") and text.endswith("”") and ("?" in text or any(t in text for t in ("나요", "까요", "됩니다", "아파", "저려", "있어요"))))
              or text.startswith("Q.")):
            kept.append({"tag": "p", "text": text})
        elif block.get("tag") == "li" and re.search(r"기록|적어|이름|목록|메모|알려|가져|날짜", text) and not re.search(r"\d|혈자리|누르|마사지|스트레칭|복용하|섭취하", text):
            kept.append({"tag": "li", "text": text.lstrip("•· ")})
        else:
            withheld.append({"reason": "legacy-not-source-verified", "text": text})
    # Keep the distinct scene/question, avoiding an automatically copied FAQ list.
    questions = [b for b in kept if b["tag"] == "p"][:4]
    observations = [b for b in kept if b["tag"] == "li"][:4]
    return questions + observations, withheld


def column_focus(profile, title):
    """Choose the clinical section that answers the existing article's intent."""
    text = title.split("|", 1)[-1]
    rules = [
        ("assessment", ("검사", "감별", "구분", "확인 순서", "시작 시", "언제부터", "기간")),
        ("care", ("침", "약침", "추나", "한약", "복용", "무엇을 고", "무엇부터")),
        ("daily", ("자가", "집에서", "생활", "운전", "장마", "환절기", "스트레칭", "집안", "독서", "아침", "앉아")),
        ("followup", ("반복", "남는", "남아", "되돌아", "경과", "돌아올", "되풀이")),
        ("symptoms", ("신호", "변화", "가족", "통증", "증상")),
    ]
    key = next((key for key, words in rules if any(word in text for word in words)), "assessment")
    focus = next(t for t in profile["topics"] if t["id"] == key)
    companion_key = {"symptoms": "assessment", "context": "assessment", "assessment": "context", "care": "assessment", "daily": "followup", "followup": "care"}[key]
    companion = next(t for t in profile["topics"] if t["id"] == companion_key)
    return focus, companion
