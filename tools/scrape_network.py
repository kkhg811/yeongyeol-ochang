# -*- coding: utf-8 -*-
"""
연결한의원 네트워크(파주운정·아산탕정) 공개 콘텐츠를 수집해 청주오창 버전으로 변환합니다.

  python tools/scrape_network.py conditions   # 질환 299종 (파주 공개 API)
  python tools/scrape_network.py columns      # 건강정보 칼럼 (파주 HTML)
  python tools/scrape_network.py all

원본은 assets/scraped/ 에, 변환 결과는 src/generated/*.json 에 저장됩니다.
지역·전화·원장·자격 문구는 청주오창 기준으로 자동 치환되며, 청주오창에 해당하지 않는
문구(RMSK 초음파 자격 등)는 제거됩니다.
"""
import concurrent.futures as cf
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from clinic_details import normalize_clinic_details

RAW = os.path.join(ROOT, "assets", "scraped")
GEN = os.path.join(ROOT, "src", "generated")
BASE = "https://yghani.kr"
UA = {"User-Agent": "Mozilla/5.0 (compatible; yeongyeol-ochang-site-builder)"}

# ── 치환 규칙 (순서 중요) ───────────────────────────────────────────────────
SUBS = [
    ("연결한의원 파주운정", "연결한의원 청주오창"),
    ("파주운정점", "청주오창점"), ("파주운정", "청주오창"),
    ("파주 운정신도시", "청주 오창읍"), ("운정신도시", "오창읍"),
    ("파주 운정", "청주 오창"), ("파주·운정", "청주·오창"), ("운정·파주", "오창·청주"),
    ("경기도 파주시 청석로 115, 5층 507호 (동패동)", "충북 청주시 청원구 오창읍 2산단로 132, 301·302호"),
    ("파주시 청석로 115", "청주시 청원구 오창읍 2산단로 132"),
    ("청석로 115, 5층 507호", "2산단로 132, 301·302호"),
    ("청석로", "2산단로"), ("동패동", "주성리"),
    ("031-942-1335", "043-715-3688"), ("031-942-1336", "043-715-3688"),
    ("홍성우", "김현교"),
    ("파주시", "청주시 청원구"), ("파주", "청주"), ("운정", "오창"),
    ("야당동", "각리"), ("교하", "오창"), ("금촌", "오창"), ("문산", "오창"), ("일산", "청주"),
    ("평일 10:00 - 20:00", "평일 09:30 - 20:00"), ("10:00 - 20:00", "09:30 - 20:00"),
    ("점심시간 13:00 - 14:30", "점심시간 13:00 - 14:00"),
    ("주말·공휴일 09:30 - 15:00", "토·일·공휴일 09:30 - 15:00"),
    ("yghani.kr", "www.yeongyeolochangkmc.co.kr"),
    ("오창오창", "오창"), ("청주 청주", "청주"), ("청주시 청원구시", "청주시 청원구"),
]

# 청주오창에 해당하지 않는 문구가 들어간 문장은 통째로 삭제
DROP_SENTENCE = ["RMSK", "근골격계 초음파", "초음파 진단 자격", "국제 초음파", "초음파 유도"]


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def clean_text(t):
    if not isinstance(t, str):
        return t
    # Complete addresses must be recognized before partial city/street rules.
    t = normalize_clinic_details(t)
    for a, b in SUBS:
        t = t.replace(a, b)
    if any(k in t for k in DROP_SENTENCE):
        parts = re.split(r"(?<=[.!?다요])\s+", t)
        parts = [p for p in parts if not any(k in p for k in DROP_SENTENCE)]
        t = " ".join(parts).strip()
    return normalize_clinic_details(re.sub(r"\s{2,}", " ", t))


def clean_deep(o):
    if isinstance(o, str):
        return clean_text(o)
    if isinstance(o, list):
        out = [clean_deep(v) for v in o]
        return [v for v in out if not (isinstance(v, str) and not v.strip())]
    if isinstance(o, dict):
        return {k: clean_deep(v) for k, v in o.items()}
    return o


# ── 질환 ────────────────────────────────────────────────────────────────────
def scrape_conditions():
    slugs, total, off = [], None, 0
    while True:
        d = json.loads(fetch(f"{BASE}/api/v1/conditions?limit=100&offset={off}"))
        total = d["total"]
        slugs += [r["slug"] for r in d["results"]]
        off += d["count"]
        if off >= total or not d["count"]:
            break
    print("conditions listed:", total, len(slugs))
    os.makedirs(os.path.join(RAW, "conditions"), exist_ok=True)

    def one(slug):
        path = os.path.join(RAW, "conditions", urllib.parse.quote(slug, safe="") + ".json")
        if os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
        try:
            j = json.loads(fetch(f"{BASE}/api/v1/conditions/{urllib.parse.quote(slug, safe='')}"))
        except Exception as e:
            print("  fail", slug, e)
            return None
        json.dump(j, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        return j

    got = []
    with cf.ThreadPoolExecutor(8) as ex:
        for j in ex.map(one, slugs):
            if j:
                got.append(j)
    print("conditions fetched:", len(got))

    out = []
    for j in got:
        c = clean_deep(j)
        out.append({
            "slug": j["slug"],
            "name": c.get("name"),
            "medicalName": c.get("medicalName"),
            "category": c.get("category"),
            "summary": c.get("summary"),
            "heading": c.get("heading"),
            "intro": c.get("intro") or [],
            "symptoms": c.get("symptoms") or {},
            "sections": c.get("sections") or [],
            "treatments": c.get("treatments") or [],
            "faqs": c.get("faqs") or [],
            "related": [r.get("slug") for r in (j.get("related") or [])],
            "updated": j.get("updated"),
        })
    os.makedirs(GEN, exist_ok=True)
    json.dump(out, open(os.path.join(GEN, "conditions.json"), "w", encoding="utf-8"), ensure_ascii=False)
    cats = {}
    for c in out:
        cats[c["category"]] = cats.get(c["category"], 0) + 1
    print("saved conditions:", len(out), cats)


# ── 칼럼 ────────────────────────────────────────────────────────────────────
def column_slugs():
    s = fetch(f"{BASE}/columns")
    hrefs = sorted(set(re.findall(r'href="(/columns/[^"#]+)"', s)))
    return [urllib.parse.unquote(h.split("/columns/")[1]) for h in hrefs]


def parse_column(slug, raw):
    body = raw.split("<body", 1)[-1]
    body = re.sub(r"<(script|style|svg)[^>]*>.*?</\1>", "", body, flags=re.S)
    m = re.search(r"<main[^>]*>(.*?)</main>", body, flags=re.S)
    main = m.group(1) if m else body
    title = re.search(r"<h1[^>]*>(.*?)</h1>", main, flags=re.S)
    title = html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else slug
    date = re.search(r"(20\d\d-\d\d-\d\d)", main)
    paras = []
    for m in re.finditer(r"<(p|li|h2|h3)[^>]*>(.*?)</\1>", main, flags=re.S):
        tag, inner = m.group(1), m.group(2)
        txt = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if not txt or len(txt) < 8:
            continue
        if any(k in txt for k in ("All rights reserved", "개인정보처리방침", "대표전화", "사업자등록번호", "본 사이트의 의학 정보")):
            continue
        paras.append({"tag": tag, "text": txt})
    return {"slug": slug, "title": title, "date": date.group(1) if date else None, "blocks": paras}


def scrape_columns():
    slugs = column_slugs()
    print("columns listed:", len(slugs))
    os.makedirs(os.path.join(RAW, "columns"), exist_ok=True)

    def one(slug):
        p = os.path.join(RAW, "columns", urllib.parse.quote(slug, safe="") + ".html")
        if not os.path.exists(p):
            try:
                raw = fetch(f"{BASE}/columns/{urllib.parse.quote(slug, safe='')}")
            except Exception as e:
                print("  fail", slug, e)
                return None
            open(p, "w", encoding="utf-8").write(raw)
        else:
            raw = open(p, encoding="utf-8").read()
        try:
            return parse_column(slug, raw)
        except Exception as e:
            print("  parse fail", slug, e)
            return None

    got = []
    with cf.ThreadPoolExecutor(8) as ex:
        for j in ex.map(one, slugs):
            if j and len(j["blocks"]) >= 3:
                got.append(j)
    print("columns fetched:", len(got))

    out = []
    for j in got:
        c = clean_deep(j)
        sl = j["slug"]
        for a, b in (("파주", "오창"), ("운정", "오창"), ("교하", "오창"), ("금촌", "오창"),
                     ("문산", "오창"), ("야당", "오창"), ("일산", "청주")):
            sl = sl.replace(a, b)
        c["slug"] = re.sub(r"오창+", "오창", sl)
        c["blocks"] = [b for b in c["blocks"] if b["text"].strip()]
        out.append(c)
    # 슬러그 중복 제거
    seen, uniq = set(), []
    for c in out:
        if c["slug"] in seen:
            continue
        seen.add(c["slug"])
        uniq.append(c)
    os.makedirs(GEN, exist_ok=True)
    json.dump(uniq, open(os.path.join(GEN, "columns.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("saved columns:", len(uniq))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("conditions", "all"):
        scrape_conditions()
    if what in ("columns", "all"):
        scrape_columns()
