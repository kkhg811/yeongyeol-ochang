# -*- coding: utf-8 -*-
"""
연결한의원 청주오창 홈페이지 정적 빌드 스크립트

  python build.py                    → docs/ 폴더에 HTML 생성
  python tools/build_images.py       → assets/ 원본을 docs/images/ 로 최적화 (사진 바뀔 때만)
  python tools/scrape_network.py all → 연결한의원 네트워크 질환·건강정보 수집 (src/generated/*.json)

콘텐츠 수정은 src/*.py, 레이아웃 수정은 templates/*.html, 스타일은 docs/css/style.css
"""
import json
import os
import sys
import urllib.parse
from html import unescape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from site_info import SITE, NAV, DIRECTORS, FEATURED, TICKER_ROW1, TICKER_ROW2, STATS, CORE, WHO, WHY, HOME_FAQ, RECORD
from services import SERVICES
from columns import PRINCIPLES, PATIENT_QUESTIONS, FAQ_GROUPS
from pain_series import load_series, schemas as pain_schemas
from clinical_guides import load_catalog, page_nodes as clinical_nodes, clean_column_blocks, column_focus
from patient_scenarios import load_scenarios, scenario_profile

REVIEW_MODE = os.environ.get("SITE_STAGE", "production") == "review"
SOURCE_SITE_URL = SITE["url"]
SITE = dict(SITE)
SITE["url"] = os.environ.get("SITE_ORIGIN", SITE["url"]).rstrip("/")
PAIN_SERIES = load_series(review=REVIEW_MODE)
PAIN_TOPICS = {t["slug"]: t for t in PAIN_SERIES["topics"]} if PAIN_SERIES else {}
CLINICAL = load_catalog(review=REVIEW_MODE)
PATIENT_SCENARIOS = load_scenarios(CLINICAL, review=REVIEW_MODE)
if CLINICAL:
    CLINICAL["patient_scenarios"] = PATIENT_SCENARIOS
    for profile in CLINICAL["profiles"]:
        profile["patient_scenarios"] = [s for s in PATIENT_SCENARIOS if s["profile_id"] == profile["id"]]

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("SITE_OUTPUT", os.path.join(ROOT, "docs"))
GEN = os.path.join(ROOT, "src", "generated")

env = Environment(
    loader=FileSystemLoader(os.path.join(ROOT, "templates")),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters["urlencode"] = lambda s: urllib.parse.quote(str(s), safe="")
env.filters["urldecode"] = urllib.parse.unquote

# ── 수집 데이터 (연결한의원 네트워크 공개 콘텐츠를 청주오창 버전으로 변환) ──────
CONDITIONS = json.load(open(os.path.join(GEN, "conditions.json"), encoding="utf-8"))
COLUMNS = json.load(open(os.path.join(GEN, "columns.json"), encoding="utf-8"))
COND = {c["slug"]: c for c in CONDITIONS}

# 보유한 실사 이미지가 있는 질환에만 대표 이미지 연결
COND_IMAGE = {
    "허리디스크": "images/ai/lumbar-disc.webp", "목디스크": "images/ai/cervical-disc.webp",
    "오십견": "images/ai/frozen-shoulder.webp", "척추관협착증": "images/ai/spinal-stenosis.webp",
    "척추협착증": "images/ai/spinal-stenosis.webp", "테니스엘보": "images/ai/tennis-elbow.webp",
    "손목터널증후군": "images/ai/carpal-tunnel.webp", "수근관증후군": "images/ai/carpal-tunnel.webp",
    "족저근막염": "images/ai/plantar-fasciitis.webp", "발바닥근막염": "images/ai/plantar-fasciitis.webp",
    "좌골신경통": "images/ai/sciatica.webp", "교통사고-병원": "images/ai/traffic-accident.webp", "교통사고-한방-재활": "images/ai/traffic-accident.webp",
    "교통사고-한의원": "images/ai/traffic-accident.webp", "만성-두통": "images/ai/chronic-headache.webp",
    "두통-클리닉": "images/ai/chronic-headache.webp", "역류성식도염": "images/ai/reflux.webp",
    "소화불량": "images/ai/indigestion.webp", "기능성-소화불량": "images/ai/indigestion.webp",
    "갱년기증후군": "images/ai/menopause.webp", "갱년기": "images/ai/menopause.webp",
    "불면증": "images/ai/insomnia.webp", "만성피로": "images/ai/insomnia.webp",
    "알레르기비염": "images/ai/allergic-rhinitis.webp", "만성-비염": "images/ai/allergic-rhinitis.webp",
}
for _c in CONDITIONS:
    _c["image"] = COND_IMAGE.get(_c["slug"])
    if _c["slug"] in PAIN_TOPICS:
        _c["image"] = PAIN_TOPICS[_c["slug"]]["image"]
        _c["summary"] = PAIN_TOPICS[_c["slug"]]["summary"]
    if CLINICAL:
        _entry = CLINICAL["conditions_by_slug"][_c["slug"]]
        _profile = CLINICAL["profiles_by_id"][_entry["profile_id"]]
        _c["image"] = _profile["topics"][0]["image"]
        _c["summary"] = _profile["overview"]

CAT_ORDER = ["근골격·통증", "교통사고", "안면·두통", "신경정신·수면", "소화기", "산부인과·여성",
             "호흡기·알레르기", "피부", "턱관절", "소아·성장", "다이어트", "보약·공진단"]


def categories():
    out, seen = [], set()
    names = CAT_ORDER + sorted({c["category"] for c in CONDITIONS} - set(CAT_ORDER))
    for i, name in enumerate(names):
        items = sorted([c for c in CONDITIONS if c["category"] == name], key=lambda c: c["name"])
        if items and name not in seen:
            seen.add(name)
            out.append({"name": name, "id": "cat-%d" % i, "rows": items})
    return out


# ── 건강정보 분류 ───────────────────────────────────────────────────────────
COL_GROUPS = [
    ("근골격·통증", ["디스크", "허리", "어깨", "오십견", "무릎", "족저", "손목", "엘보", "추나", "저림", "관절", "협착", "골반", "거북목", "염좌", "통증"]),
    ("교통사고", ["교통사고", "자동차보험"]),
    ("두통·어지럼", ["두통", "어지럼", "편두통", "이명", "안면"]),
    ("수면·신경정신", ["불면", "수면", "불안", "우울", "화병", "공황", "스트레스", "피로", "번아웃", "집중", "틱", "강박"]),
    ("소화기", ["소화", "역류", "속쓰림", "변비", "설사", "담적", "복통", "식욕", "위염", "장염"]),
    ("여성·산후", ["생리", "월경", "갱년기", "산후", "임신", "난임", "자궁", "질염", "방광", "유산", "출산", "부종"]),
    ("소아·성장", ["소아", "성장", "어린이", "수험생", "학습", "아이"]),
    ("보약·공진단", ["공진단", "보약", "녹용", "면역", "기력", "원기", "체력"]),
    ("다이어트", ["다이어트", "감비", "체중", "비만", "위고비", "마운자로"]),
    ("피부·알레르기", ["비염", "알레르기", "아토피", "두드러기", "피부", "습진", "건선", "탈모"]),
]


def prepare_columns():
    for c in COLUMNS:
        hay = c["title"] + " " + " ".join(b["text"] for b in c["blocks"][:4])
        best, hits_best = "기타 건강정보", 0
        for name, kws in COL_GROUPS:
            hits = sum(hay.count(k) for k in kws)
            if hits > hits_best:
                best, hits_best = name, hits
        c["group"] = best
        body = [b for b in c["blocks"] if b["tag"] == "p"]
        c["summary"] = (body[0]["text"] if body else c["title"])[:170]
        c["reviewer"] = "김현교 대표원장"
        c["blocks"] = [b for b in c["blocks"] if b["text"].strip() != c["title"].strip()]
        if CLINICAL:
            entry = CLINICAL["columns_by_slug"][c["slug"]]
            c["title"] = entry["title"]
            c["summary"] = entry["description"]
    groups = []
    for i, name in enumerate([g[0] for g in COL_GROUPS] + ["기타 건강정보"]):
        items = sorted([c for c in COLUMNS if c["group"] == name], key=lambda c: (c["date"] or ""), reverse=True)
        if items:
            groups.append({"name": name, "id": "col-%d" % i, "rows": items})
    return groups


def search_index():
    idx = [{"title": s["name"], "url": "services/%s.html" % s["slug"], "type": "진료 안내",
            "keywords": s["short"] + " " + " ".join(s["who"])} for s in SERVICES]
    idx.append({"title": "오창 안면마비 한의원 | 구안와사 맞춤한약 진료",
                "url": "treatment/facial-palsy/herbal-care.html",
                "type": "안면마비 진료",
                "keywords": "오창한의원 오창 안면마비 한의원 오창 구안와사 안면신경마비 한약 상담"})
    for c in CONDITIONS:
        idx.append({"title": "오창 %s 한의원" % c["name"],
                    "url": "conditions/%s.html" % urllib.parse.quote(c["slug"], safe=""),
                    "type": c["category"],
                    "keywords": " ".join([c["name"], c.get("medicalName") or "", c.get("summary") or ""] +
                                         list((c.get("symptoms") or {}).get("items") or [])[:4])})
    for c in COLUMNS:
        idx.append({"title": c["title"], "url": "column/%s.html" % urllib.parse.quote(c["slug"], safe=""),
                    "type": "건강정보", "keywords": c["group"] + " " + c["summary"]})
    idx += [
        {"title": "오시는 길 · 주차 안내", "url": "location.html", "type": "안내",
         "keywords": "주차 위치 주소 지도 길찾기 주성리 617 부영 부민빌딩 오창 2산단로 진료시간 야간 주말 공휴일"},
        {"title": "원장 소개", "url": "about.html", "type": "안내", "keywords": "원장 김현교 신재형 이상현 이력 진료요일"},
        {"title": "진료철학", "url": "philosophy.html", "type": "안내", "keywords": "진료 원칙 철학 치료 강도 반응 보정"},
        {"title": "자주 묻는 질문", "url": "faq.html", "type": "안내", "keywords": "FAQ 예약 보험 실비 비용 한약 침 주차 진료시간"},
    ]
    if PAIN_SERIES:
        idx.append({"title": PAIN_SERIES["h1"], "url": PAIN_SERIES["path"], "type": "통증 가이드", "keywords": PAIN_SERIES["description"]})
    if CLINICAL:
        for profile in CLINICAL["profiles"]:
            if profile.get("standalone_hub"):
                idx.append({"title": profile["page_metadata"]["title"], "url": profile["hub_path"],
                            "type": "질환별 가이드", "keywords": profile["overview"] + " " + " ".join(profile.get("keywords", []))})
            for topic in profile["topics"]:
                idx.append({"title": topic["h1"], "url": topic["path"], "type": "질환별 가이드", "keywords": topic["description"]})
    scenario_paths = {s["path"].lstrip("/") for s in PATIENT_SCENARIOS}
    idx = [item for item in idx if item["url"].removesuffix(".html") not in scenario_paths]
    idx.extend({"title": s["title"], "url": s["path"].lstrip("/"), "type": "다친 뒤 증상 안내", "keywords": s["summary"]} for s in PATIENT_SCENARIOS)
    # 검색창은 메인·하위 디렉터리 어디에서 사용하더라도 같은 페이지로 연결한다.
    for item in idx:
        item["url"] = "/" + item["url"]
    return idx


def jsonld(page_path, extra=None):
    data = {
        "@context": "https://schema.org", "@type": "MedicalClinic",
        "@id": SITE["url"] + "/#clinic", "name": SITE["name"],
        "url": SITE["url"] + "/", "telephone": "+82-" + SITE["phone"][1:],
        "image": SITE["url"] + "/images/hero/directors-team.webp",
        "logo": SITE["url"] + "/images/logo/symbol-green-512.png",
        "address": {"@type": "PostalAddress", "streetAddress": "오창읍 2산단로 132, 부민빌딩 3층",
                    "addressLocality": "청주시 청원구", "addressRegion": "충청북도",
                    "postalCode": "28116", "addressCountry": "KR"},
        "geo": {"@type": "GeoCoordinates", "latitude": SITE["coords"]["lat"], "longitude": SITE["coords"]["lng"]},
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "opens": "09:30", "closes": "13:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "opens": "14:00", "closes": "20:00"},
            {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Saturday", "Sunday", "PublicHolidays"], "opens": "09:30", "closes": "15:00"},
        ],
        "medicalSpecialty": "한의학",
        "sameAs": [SITE["naver_place_full"], SITE["blog"]],
    }
    return json.dumps([data, extra] if extra else data, ensure_ascii=False, indent=1)


def canon(path):
    """Cloudflare Workers는 .html 없이 서빙하므로 정식 주소(canonical/sitemap)도 맞춘다."""
    if path == "index.html":
        return SITE["url"] + "/"
    if path.endswith("/index.html"):
        return SITE["url"] + "/" + path[: -len("/index.html")] + "/"
    if path.endswith(".html"):
        return SITE["url"] + "/" + path[: -len(".html")]
    return SITE["url"] + "/" + path


PAGES = []
PAGE_META = {}


def render(template, out_path, **ctx):
    root = "../" * out_path.count("/")
    base = dict(site=SITE, nav=NAV, services=SERVICES, conditions=CONDITIONS, columns=COLUMNS,
                directors=DIRECTORS, directors_by_name={d["name"]: d for d in DIRECTORS},
                root=root, page_path=out_path, canonical=canon(out_path), pain_series=PAIN_SERIES, clinical_catalog=CLINICAL, review_mode=REVIEW_MODE, jsonld=ctx.pop("jsonld", None) or jsonld(out_path))
    base.update(ctx)
    page_template = env.get_template(template)
    metadata_ctx = page_template.new_context(base)
    title = ("".join(page_template.blocks["title"](metadata_ctx)).strip()
             if "title" in page_template.blocks else SITE["title"])
    description = ("".join(page_template.blocks["description"](metadata_ctx)).strip()
                   if "description" in page_template.blocks else SITE["description"])
    title, description = unescape(title), unescape(description)
    schemas = json.loads(base["jsonld"])
    if not isinstance(schemas, list):
        schemas = [schemas]
    page_schema = next((node for node in schemas if node.get("@type") == "WebPage"), None)
    if page_schema is None:
        page_schema = {}
        schemas.append(page_schema)
    page_schema.update({
        "@context": "https://schema.org", "@type": "WebPage",
        "@id": base["canonical"] + "#webpage", "url": base["canonical"],
        "name": title, "description": description, "inLanguage": "ko-KR",
        "isPartOf": {"@id": SITE["url"] + "/#website"},
        "publisher": {"@id": SITE["url"] + "/#clinic"},
    })
    if out_path == "index.html":
        page_schema["mainEntity"] = {"@id": SITE["url"] + "/#clinic"}
    base["jsonld"] = json.dumps(schemas, ensure_ascii=False, indent=1)
    html = page_template.render(**base)
    full = os.path.join(OUT, urllib.parse.unquote(out_path).replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(html)
    PAGES.append(out_path)
    PAGE_META[out_path] = {"canonical": base["canonical"], "images": ctx.get("sitemap_images", []), "updated_at": ctx.get("last_modified")}


def render_clinical(profile, entry=None, topic=None, column=None):
    path = topic["path"] if topic else entry["path"]
    canonical_path = path if topic else entry["canonical_path"]
    all_topics = profile["topics"]
    i = topic["position"] - 1 if topic else 0
    related = [e for e in CLINICAL["columns"] if e["profile_id"] == profile["id"] and e["path"] != path][:4]
    blocks, withheld = clean_column_blocks(column["blocks"]) if column else ([], [])
    focus, companion = column_focus(profile, entry["title"]) if column else (None, None)
    first = profile["overview"]
    context = profile.get("member_contexts", {}).get(entry["slug"], []) if entry else []
    render("clinical_guide.html", path + ".html", profile=profile, entry=entry, topic=topic,
           is_column=bool(column), article_blocks=blocks, article_lead=first,
           is_profile_hub=path == profile["hub_path"],
           article_focus=focus, article_companion=companion,
           related_articles=related, entry_context=context,
           previous_topic=all_topics[i-1] if topic and i else None,
           next_topic=all_topics[i+1] if topic and i+1 < 6 else None,
           canonical=SITE["url"] + "/" + canonical_path,
           last_modified=profile["updated_at"],
           sitemap_images=[t["image"] for t in all_topics],
           jsonld=json.dumps([json.loads(jsonld(path))] + clinical_nodes(CLINICAL, profile, SITE["url"], canonical_path, entry=entry, topic=topic, is_column=bool(column)), ensure_ascii=False))
    return withheld


def build_favicons():
    """기존 로고의 투명 여백을 정리해 정사각형 파비콘을 만든다."""
    with Image.open(os.path.join(OUT, "images", "logo", "symbol-green-512.png")) as source:
        mark = source.convert("RGBA")
    mark = mark.crop(mark.getchannel("A").getbbox())
    scale = 448 / max(mark.size)
    mark = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.Resampling.LANCZOS)
    icon = Image.new("RGBA", (512, 512), (255, 255, 255, 0))
    icon.alpha_composite(mark, ((512 - mark.width) // 2, (512 - mark.height) // 2))
    icon.save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    for size, filename in [(32, "favicon-32.png"), (180, "apple-touch-icon.png")]:
        icon.resize((size, size), Image.Resampling.LANCZOS).save(os.path.join(OUT, filename))


def render_patient_scenario(scenario):
    profile = scenario_profile(CLINICAL, scenario)
    path = scenario["path"].lstrip("/")
    entry = {"name": scenario["keyword"], "title": scenario["title"], "description": scenario["description"], "published_at": scenario["published_at"]}
    render("clinical_scenario.html", path + ".html", scenario=scenario, profile=profile,
           topic=None, is_column=False, is_profile_hub=False,
           canonical=SITE["url"] + scenario["path"], last_modified=scenario["updated_at"],
           sitemap_images=[t["image"] for t in profile["topics"]],
           jsonld=json.dumps([json.loads(jsonld(path))] + clinical_nodes(CLINICAL, profile, SITE["url"], path, entry=entry), ensure_ascii=False))


def main():
    os.makedirs(OUT, exist_ok=True)
    build_favicons()
    col_groups = prepare_columns()
    with open(os.path.join(OUT, "search-index.json"), "w", encoding="utf-8") as f:
        json.dump(search_index(), f, ensure_ascii=False, separators=(",", ":"))
    cats = categories()
    if PAIN_SERIES:
        page = PAIN_SERIES["path"] + ".html"
        render("pain_series.html", page, topic=None, previous_topic=None, next_topic=None,
               jsonld=json.dumps([json.loads(jsonld(page))] + pain_schemas(PAIN_SERIES, None, SITE["url"]), ensure_ascii=False))
    if CLINICAL:
        render("clinical_index.html", CLINICAL["config"]["index_path"] + ".html", last_modified=max([CLINICAL["config"]["updated_at"]] + [p["updated_at"] for p in CLINICAL["profiles"]] + [s["updated_at"] for s in PATIENT_SCENARIOS]))
        if REVIEW_MODE:
            render("clinical_coverage.html", CLINICAL["config"]["coverage_path"] + ".html")
        for profile in CLINICAL["profiles"]:
            if profile.get("standalone_hub"):
                # Dedicated series need a real hub even without a legacy condition entry.
                entry = {"slug": profile["canonical_slug"], "name": profile["name"], "display_name": profile["name"],
                         "path": profile["hub_path"], "canonical_path": profile["hub_path"],
                         "published_at": profile["published_at"], **profile["page_metadata"]}
                render_clinical(profile, entry=entry)
            for topic in profile["topics"]:
                render_clinical(profile, topic=topic)
        for scenario in PATIENT_SCENARIOS:
            if scenario.get("route_policy") != "preserve-existing":
                render_patient_scenario(scenario)

    ticker_links = {}
    for t in TICKER_ROW1 + TICKER_ROW2:
        key = t.replace(" ", "")
        target = next((c["slug"] for c in CONDITIONS if c["name"].replace(" ", "") == key), None)
        ticker_links[t] = ("conditions/%s.html" % urllib.parse.quote(target, safe="")) if target else "conditions/index.html"

    website_ld = {"@context": "https://schema.org", "@type": "WebSite",
                  "@id": SITE["url"] + "/#website",
                  "name": SITE["seo_site_name"], "alternateName": SITE["short"],
                  "url": SITE["url"] + "/", "inLanguage": "ko-KR",
                  "publisher": {"@id": SITE["url"] + "/#clinic"}}
    render("index.html", "index.html", featured=FEATURED, ticker1=TICKER_ROW1, ticker2=TICKER_ROW2,
           ticker_links=ticker_links, stats=STATS, record=RECORD, core=CORE, who=WHO, why=WHY,
           home_faq=HOME_FAQ, jsonld=jsonld("index.html", website_ld))

    render("facial_palsy_herbal.html", "treatment/facial-palsy/herbal-care.html")
    render("guide_ochang_weekend.html", "guide/ochang-weekend-clinic.html")
    render("guide_ochang_saturday.html", "guide/ochang-saturday.html")
    render("guide_ochang_sunday.html", "guide/ochang-sunday.html")
    guide_ld = {"@context": "https://schema.org", "@type": "WebPage",
                "name": "오창한의원 선택 가이드 | 연결한의원 청주오창",
                "url": SITE["url"] + "/guide/ochang-clinic",
                "description": "오창한의원 선택 전 확인할 의료진, 진료 분야, 방문 조건 안내"}
    render("guide_ochang.html", "guide/ochang-clinic.html",
           jsonld=jsonld("guide/ochang-clinic.html", guide_ld))
    render("services_index.html", "services/index.html")
    for s in SERVICES:
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in s["faq"]]}
        rel = [COND[x] for x in s.get("related", []) if x in COND]
        render("service.html", "services/%s.html" % s["slug"], s=s, related_conditions=rel,
               jsonld=jsonld("services/%s.html" % s["slug"], faq_ld))

    render("conditions_index.html", "conditions/index.html", categories=cats)
    for c in CONDITIONS:
        if CLINICAL:
            entry = CLINICAL["conditions_by_slug"][c["slug"]]
            scenario = next((s for s in PATIENT_SCENARIOS if s["path"] == "/" + entry["path"]), None)
            if scenario:
                render_patient_scenario(scenario)
            else:
                render_clinical(CLINICAL["profiles_by_id"][entry["profile_id"]], entry=entry)
            continue
        if c["slug"] in PAIN_TOPICS:
            topic = PAIN_TOPICS[c["slug"]]
            i = topic["position"] - 1
            topics = PAIN_SERIES["topics"]
            page = topic["path"] + ".html"
            render("pain_series.html", page, topic=topic,
                   previous_topic=topics[i-1] if i else None,
                   next_topic=topics[i+1] if i+1 < len(topics) else None,
                   jsonld=json.dumps([json.loads(jsonld(page))] + pain_schemas(PAIN_SERIES, topic, SITE["url"]), ensure_ascii=False))
            continue
        sib = [o for o in CONDITIONS if o["category"] == c["category"] and o["slug"] != c["slug"]][:10]
        rel = [COND[r] for r in c.get("related", []) if r in COND][:8]
        cols = [k for k in COLUMNS if c["name"] in k["title"]][:5]
        ld = None
        if c.get("faqs"):
            ld = {"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q["question"],
                                  "acceptedAnswer": {"@type": "Answer", "text": q["answer"]}} for q in c["faqs"]]}
        p = "conditions/%s.html" % urllib.parse.quote(c["slug"], safe="")
        render("condition.html", p, c=c, siblings=sib, related=rel, columns_rel=cols, jsonld=jsonld(p, ld))

    render("column_index.html", "column/index.html", groups=col_groups)
    withheld_audit = {}
    for c in COLUMNS:
        if CLINICAL:
            entry = CLINICAL["columns_by_slug"][c["slug"]]
            withheld_audit[c["slug"]] = render_clinical(CLINICAL["profiles_by_id"][entry["profile_id"]], entry=entry, column=c)
            continue
        sib = [o for o in COLUMNS if o["group"] == c["group"] and o["slug"] != c["slug"]][:8]
        rel = [x for x in CONDITIONS if x["name"] in c["title"]][:6]
        render("column.html", "column/%s.html" % urllib.parse.quote(c["slug"], safe=""),
               c=c, siblings=sib, related_conditions=rel)

    render("about.html", "about.html", days=["월", "화", "수", "목", "금", "토", "일"])
    render("philosophy.html", "philosophy.html", principles=PRINCIPLES, patient_questions=PATIENT_QUESTIONS)
    render("location.html", "location.html")
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                             for g in FAQ_GROUPS for q, a in g["items"]] +
                            [{"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in HOME_FAQ]}
    render("faq.html", "faq.html", faq_groups=FAQ_GROUPS, home_faq=HOME_FAQ, jsonld=jsonld("faq.html", faq_ld))
    render("privacy.html", "privacy-policy.html")
    render("404.html", "404.html")

    # A private review must not advertise candidate URLs to search engines.
    from xml.etree import ElementTree as ET
    sm = "http://www.sitemaps.org/schemas/sitemap/0.9"
    im = "http://www.google.com/schemas/sitemap-image/1.1"
    ET.register_namespace("", sm)
    ET.register_namespace("image", im)
    urlset = ET.Element("{" + sm + "}urlset")
    series_images = {}
    if PAIN_SERIES:
        series_images[PAIN_SERIES["path"] + ".html"] = [t["image"] for t in PAIN_SERIES["topics"]]
        series_images.update({t["path"] + ".html": [t["image"]] for t in PAIN_SERIES["topics"]})
    if not REVIEW_MODE:
        seen = set()
        for page in PAGES:
            url = PAGE_META[page]["canonical"]
            if page == "404.html" or url != canon(page) or url in seen or page.startswith("review/"):
                continue
            seen.add(url)
            node = ET.SubElement(urlset, "{" + sm + "}url")
            ET.SubElement(node, "{" + sm + "}loc").text = url
            images = PAGE_META[page]["images"] or series_images.get(page, [])
            if images:
                ET.SubElement(node, "{" + sm + "}lastmod").text = PAGE_META[page].get("updated_at") or (CLINICAL["config"]["updated_at"] if CLINICAL else PAIN_SERIES["updated_at"])
                for image in images:
                    ino = ET.SubElement(node, "{" + im + "}image")
                    ET.SubElement(ino, "{" + im + "}loc").text = SITE["url"] + "/" + image
    ET.ElementTree(urlset).write(os.path.join(OUT, "sitemap.xml"), encoding="utf-8", xml_declaration=True)
    open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\n" + ("# Private review; HTML and X-Robots-Tag use noindex.\n" if REVIEW_MODE else "Sitemap: %s/sitemap.xml\n" % SITE["url"]))
    routes_file = os.path.join(OUT, "review-routes.json")
    headers_file = os.path.join(OUT, "_headers")
    if REVIEW_MODE:
        open(headers_file, "w", encoding="utf-8").write("/*\n  X-Robots-Tag: noindex, nofollow, noarchive\n")
        routes = [PAIN_SERIES["path"]] + [t["path"] for t in PAIN_SERIES["topics"]] if PAIN_SERIES else []
        if CLINICAL:
            routes += [e["path"] for e in CLINICAL["conditions"] + CLINICAL["columns"]]
            routes += [t["path"] for p in CLINICAL["profiles"] for t in p["topics"]]
            routes += [CLINICAL["config"]["index_path"], CLINICAL["config"]["coverage_path"]]
            routes = list(dict.fromkeys(routes))
            review_dir = os.path.join(OUT, "review")
            os.makedirs(review_dir, exist_ok=True)
            import hashlib
            assets = []
            for profile in CLINICAL["profiles"]:
                for topic in profile["topics"]:
                    for key in ("image", "image_small"):
                        path = os.path.join(OUT, topic[key])
                        if not os.path.isfile(path):
                            raise ValueError("Render clinical card assets before build: " + path)
                        raw = open(path, "rb").read()
                        assets.append({"path": "/" + topic[key], "kind": "image", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            with open(os.path.join(review_dir, "asset-routes.json"), "w", encoding="utf-8") as f:
                json.dump(assets, f, ensure_ascii=False, separators=(",", ":"))
            samples = [{"path": "/" + CLINICAL["config"]["index_path"], "name": "전체 목록", "cards": False}]
            for group in CLINICAL["groups"]:
                profile = group["profiles"][0]
                samples.append({"path": "/" + profile["hub_path"], "name": group["name"] + " / " + profile["name"], "cards": True})
            for slug in ("목디스크", "발목염좌"):
                entry = CLINICAL["conditions_by_slug"].get(slug)
                if not entry:
                    entry = next((e for e in CLINICAL["conditions"] if e["slug"].replace("-", "") == slug), None)
                if entry:
                    samples.append({"path": "/" + entry["path"], "name": entry["name"], "cards": True})
                    profile = CLINICAL["profiles_by_id"][entry["profile_id"]]
                    samples.append({"path": "/" + profile["topics"][0]["path"], "name": profile["name"] + " 상세", "cards": True})
            longest = max(CLINICAL["profiles"], key=lambda p: len(p["name"]))
            samples.append({"path": "/" + longest["topics"][3]["path"], "name": "긴 제목 / " + longest["name"], "cards": True})
            for e in CLINICAL["columns"][:2]:
                samples.append({"path": "/" + e["path"], "name": e["title"], "cards": True})
            with open(os.path.join(review_dir, "qa-samples.json"), "w", encoding="utf-8") as f:
                json.dump(samples, f, ensure_ascii=False, indent=2)
            with open(os.path.join(review_dir, "clinical-coverage.json"), "w", encoding="utf-8") as f:
                json.dump({k: CLINICAL[k] for k in ("config", "counts", "conditions", "columns", "search_exposure")}, f, ensure_ascii=False, indent=2)
            import csv
            with open(os.path.join(review_dir, "clinical-coverage.csv"), "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["type", "topic", "keyword", "review_url", "target_url", "series_id", "canonical", "relationship", "medical_review", "search_exposure"])
                for kind, entries in (("condition", CLINICAL["conditions"]), ("column", CLINICAL["columns"])):
                    for e in entries:
                        w.writerow([kind, e["name"], "청주 오창 " + e["name"], SITE["url"]+"/"+e["path"], SOURCE_SITE_URL+"/"+e["path"], e["profile_id"], SITE["url"]+"/"+e["canonical_path"], e["relationship"], "pending", "unconfirmed"])
            with open(os.path.join(ROOT, "src/content/legacy-column-withheld.json"), "w", encoding="utf-8") as f:
                json.dump(withheld_audit, f, ensure_ascii=False, indent=2)
        with open(routes_file, "w", encoding="utf-8") as f:
            json.dump({"stage": "review", "origin": SITE["url"], "target_origin": SOURCE_SITE_URL,
                       "series_routes": routes, "search_submission": "not submitted", "index_policy": "noindex"}, f, ensure_ascii=False, indent=2)
    else:
        for path in (routes_file, headers_file, os.path.join(OUT, "qa", "routes.html"), os.path.join(OUT, "qa", "responsive.html")):
            if os.path.exists(path):
                os.remove(path)
        if not PAIN_SERIES:
            # Remove a review-only hub left over by an earlier preview build.
            stale = os.path.join(OUT, "guide", "ochang-pain.html")
            if os.path.exists(stale):
                os.remove(stale)
        if not CLINICAL:
            import shutil
            config = json.load(open(os.path.join(ROOT, "src/content/clinical-guides-config.json"), encoding="utf-8"))
            for path in (os.path.join(OUT, config["index_path"] + ".html"), os.path.join(OUT, "review")):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.exists(path):
                    os.remove(path)
            for filename in ("clinical.html", "clinical-responsive.html"):
                path = os.path.join(OUT, "qa", filename)
                if os.path.exists(path):
                    os.remove(path)
            catalog_path = os.path.join(ROOT, "src/content/clinical-catalog.json")
            if os.path.exists(catalog_path):
                cat = json.load(open(catalog_path, encoding="utf-8"))
                for profile in cat["profiles"]:
                    for topic in profile["topics"]:
                        path = os.path.join(OUT, topic["path"] + ".html")
                        if os.path.exists(path):
                            os.remove(path)

    print("built %d pages → %s" % (len(PAGES), OUT))


if __name__ == "__main__":
    main()
