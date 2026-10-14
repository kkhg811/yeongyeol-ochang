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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from jinja2 import Environment, FileSystemLoader, select_autoescape

from site_info import SITE, NAV, DIRECTORS, FEATURED, TICKER_ROW1, TICKER_ROW2, STATS, CORE, WHO, WHY, HOME_FAQ, RECORD
from services import SERVICES
from columns import PRINCIPLES, PATIENT_QUESTIONS, FAQ_GROUPS

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs")
GEN = os.path.join(ROOT, "src", "generated")

env = Environment(
    loader=FileSystemLoader(os.path.join(ROOT, "templates")),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters["urlencode"] = lambda s: urllib.parse.quote(str(s), safe="")

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
    return idx


def jsonld(page_path, extra=None):
    data = {
        "@context": "https://schema.org", "@type": "MedicalClinic", "name": SITE["name"],
        "url": canon(page_path), "telephone": "+82-" + SITE["phone"][1:],
        "image": SITE["url"] + "/images/hero/directors-team.webp",
        "logo": SITE["url"] + "/images/logo/symbol-green-512.png",
        "address": {"@type": "PostalAddress", "streetAddress": "오창읍 2산단로 132, 부민빌딩 3층",
                    "addressLocality": "청주시 청원구", "addressRegion": "충청북도",
                    "postalCode": "28116", "addressCountry": "KR"},
        "geo": {"@type": "GeoCoordinates", "latitude": SITE["coords"]["lat"], "longitude": SITE["coords"]["lng"]},
        "openingHoursSpecification": [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "opens": "09:30", "closes": "20:00"},
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


def render(template, out_path, **ctx):
    root = "../" * out_path.count("/")
    base = dict(site=SITE, nav=NAV, services=SERVICES, conditions=CONDITIONS, columns=COLUMNS,
                directors=DIRECTORS, directors_by_name={d["name"]: d for d in DIRECTORS},
                root=root, page_path=out_path, canonical=canon(out_path), jsonld=ctx.pop("jsonld", None) or jsonld(out_path))
    base.update(ctx)
    html = env.get_template(template).render(**base)
    full = os.path.join(OUT, urllib.parse.unquote(out_path).replace("/", os.sep))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8").write(html)
    PAGES.append(out_path)


def main():
    os.makedirs(OUT, exist_ok=True)
    col_groups = prepare_columns()
    idx_json = json.dumps(search_index(), ensure_ascii=False)
    cats = categories()

    ticker_links = {}
    for t in TICKER_ROW1 + TICKER_ROW2:
        key = t.replace(" ", "")
        target = next((c["slug"] for c in CONDITIONS if c["name"].replace(" ", "") == key), None)
        ticker_links[t] = ("conditions/%s.html" % urllib.parse.quote(target, safe="")) if target else "conditions/index.html"

    website_ld = {"@context": "https://schema.org", "@type": "WebSite",
                  "name": SITE["seo_site_name"], "alternateName": SITE["name"],
                  "url": SITE["url"] + "/", "inLanguage": "ko-KR"}
    render("index.html", "index.html", featured=FEATURED, ticker1=TICKER_ROW1, ticker2=TICKER_ROW2,
           ticker_links=ticker_links, stats=STATS, record=RECORD, core=CORE, who=WHO, why=WHY,
           home_faq=HOME_FAQ, search_index=idx_json, jsonld=jsonld("index.html", website_ld))

    render("facial_palsy_herbal.html", "treatment/facial-palsy/herbal-care.html")
    render("services_index.html", "services/index.html")
    for s in SERVICES:
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in s["faq"]]}
        rel = [COND[x] for x in s.get("related", []) if x in COND]
        render("service.html", "services/%s.html" % s["slug"], s=s, related_conditions=rel,
               jsonld=jsonld("services/%s.html" % s["slug"], faq_ld))

    render("conditions_index.html", "conditions/index.html", categories=cats, search_index=idx_json)
    for c in CONDITIONS:
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

    render("column_index.html", "column/index.html", groups=col_groups, search_index=idx_json)
    for c in COLUMNS:
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
    render("404.html", "404.html", search_index=idx_json)

    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in PAGES:
            if p == "404.html":
                continue
            f.write("  <url><loc>%s</loc><changefreq>weekly</changefreq></url>\n" % canon(p))
        f.write("</urlset>\n")
    open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % SITE["url"])

    print("built %d pages → %s" % (len(PAGES), OUT))


if __name__ == "__main__":
    main()
