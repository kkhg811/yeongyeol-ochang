"""Compile a complete, auditable mapping from existing URLs to clinical series.

Source facts are editorially prepared in clinical-profiles/*.json. This tool
never manufactures a missing medical profile or publishes incomplete entries.
"""
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "src/content"
PHASES = [
    ("symptoms", "증상·대상 확인"), ("context", "원인·배경 살피기"),
    ("assessment", "진찰·검사 준비"), ("care", "치료·상담 선택"),
    ("daily", "생활에서 관리하기"), ("followup", "변화·재평가 확인"),
]
MANUAL_COLUMNS = {
    "목-어깨-담-반복": "승모근-통증",
    "오창-알레르기비염-가족이-먼저-알아챈다": "rhinitis",
    "오창-비염-자가관리-경계": "rhinitis",
    "오창-시험불안-언제부터": "시험불안",
    "오창-턱관절-검사가-먼저인-신호": "tmj",
    "오창-턱관절-이악물기-하루장면": "tmj",
    "오창-회전근개-가족이-먼저-알아챈-변화": "회전근개-증후군",
}
DISPLAY_NAMES = {
    "습관성유산예방": "반복유산 평가와 다음 임신 상담",
    "부인과-한의원": "여성 증상 상담과 진료 준비",
    "이비인후과-한의원": "코·목·귀 증상 상담과 진료 준비",
    "위고비": "위고비 약물 정보와 병용 상담",
    "마운자로": "마운자로 약물 정보와 병용 상담",
    "공진단-효능": "공진단 효능 설명과 근거 확인",
    "녹용효능": "녹용 효능 정보와 복용 전 확인",
    "사향효능": "사향 효능 정보와 복용 전 확인",
}


def normalized(text):
    return re.sub(r"[\s\-·ㆍ_·]", "", text).lower()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_profile(profile):
    if not re.fullmatch(r"[a-z][a-z0-9-]*", profile["id"]):
        raise ValueError("Non-ASCII or unsafe profile ID: " + profile["id"])
    for key in ("name", "overview", "sections", "red_flags", "sources"):
        if not profile.get(key):
            raise ValueError(f"{profile['id']}: missing {key}")
    if profile.get("kind") not in ("condition", "symptom", "service", "product"):
        raise ValueError("Unknown profile kind: " + profile["id"])
    for member in profile["members"]:
        relation = profile.get("member_relationships", {}).get(member, "canonical" if member == profile["canonical_slug"] else "related-symptom")
        if relation not in ("canonical", "alias", "related-symptom", "service-context"):
            raise ValueError(f"{profile['id']}/{member}: unknown relationship")
        if relation not in ("canonical", "alias") and len(profile.get("member_contexts", {}).get(member, [])) < 2:
            raise ValueError(f"{profile['id']}/{member}: distinct related-topic explanation required")
    for key, _ in PHASES:
        section = profile["sections"].get(key, {})
        if not section.get("question") or len(section.get("points", [])) < 3 or len(section.get("diagram", [])) != 3:
            raise ValueError(f"{profile['id']}/{key}: incomplete independent topic")
        if not all(isinstance(p, str) and p.strip() for p in section["points"] + section["diagram"]):
            raise ValueError("Empty or invalid clinical text")
    if len({profile["sections"][key]["question"] for key, _ in PHASES}) != 6:
        raise ValueError("Six questions must be distinct")
    if len({tuple(profile["sections"][key]["points"]) for key, _ in PHASES}) != 6:
        raise ValueError("Six bodies must be distinct")
    for source in profile["sources"]:
        if not source.get("title") or not source.get("scope") or urlsplit(source.get("url", "")).scheme != "https":
            raise ValueError(f"{profile['id']}: source needs title, https URL and supported scope")
    # Optional revisions are source-backed content, never placeholder text.
    known_sources = {source["url"] for source in profile["sources"]}
    known_sources.update(source["url"] for source in profile.get("priority", {}).get("evidence", []))
    for owner in [profile] + list(profile["sections"].values()):
        for block in owner.get("reading_sections", []):
            if not all(isinstance(block.get(key), str) and block[key].strip() for key in ("heading", "text")):
                raise ValueError(f"{profile['id']}: incomplete explanatory section")
            if not block.get("source_urls") or not set(block["source_urls"]) <= known_sources:
                raise ValueError(f"{profile['id']}: explanatory section needs a declared source")
        for faq in owner.get("faq", []):
            if not all(isinstance(faq.get(key), str) and faq[key].strip() for key in ("question", "answer")):
                raise ValueError(f"{profile['id']}: incomplete patient question")
            if not faq.get("source_urls") or not set(faq["source_urls"]) <= known_sources:
                raise ValueError(f"{profile['id']}: patient answer needs a declared source")
        if owner.get("page_metadata") and not all(owner["page_metadata"].get(key) for key in ("title", "description")):
            raise ValueError(f"{profile['id']}: incomplete page metadata")
    if profile.get("page_metadata") and not all(profile["page_metadata"].get(key) for key in ("title", "description")):
        raise ValueError(f"{profile['id']}: incomplete primary-page metadata")


def column_title(original, subject):
    # The existing source contains a mistaken location substitution in one title.
    if "청주시 청원구험불안" in original:
        original = original.replace("청주시 청원구험불안", "오창시험불안")
    if "|" in original:
        left, right = original.split("|", 1)
        left = re.sub(r"^(?:청주시\s*청원구|청주|오창)\s*", "", left.strip())
        left = re.sub(r"한의원$", "", left).strip()
        right = right.strip()
        for before, after in (
            ("집에서 해보는 감별 확인", "진찰 전 기록할 차이"),
            ("집에서 구분하는 법", "진찰에서 구분할 점"),
            ("집에서 먼저 구분해보기", "진찰 전에 관찰할 변화"),
            ("집에서 먼저 구분하기", "진찰 전에 관찰할 변화"),
            ("집에서 해보는 구분", "진찰 전 구분해 기록할 증상"),
        ):
            right = right.replace(before, after)
        if any(word in right for word in ("장마", "환절기", "비 오기")) and "이유" in right:
            right = "날씨가 바뀔 때 달라지는 불편, 무엇을 기록할까요?"
        return "청주·오창 " + (left or subject) + " | " + right
    return "청주·오창 " + subject + " | " + original


def main():
    config = read(CONTENT / "clinical-guides-config.json")
    priority_file = CONTENT / "priority80.json"
    priority_data = read(priority_file) if priority_file.exists() else {"status": "draft", "profiles": []}
    priority = {p["id"]: p for p in priority_data["profiles"]} if priority_data["status"] == "published" else {}
    assessment_updated_at = dict(priority_data.get("profile_updated_at", {}))
    extra_file = CONTENT / "additional-clinical-assessments.json"
    extra = read(extra_file) if extra_file.exists() else {"status": "draft", "profiles": []}
    if extra["status"] == "published":
        if set(priority) & {p["id"] for p in extra["profiles"]}:
            raise ValueError("Additional assessments must not replace the original priority80 records")
        priority.update({p["id"]: p for p in extra["profiles"]})
        assessment_updated_at.update(extra.get("profile_updated_at", {}))
    conditions = read(ROOT / "src/generated/conditions.json")
    columns = read(ROOT / "src/generated/columns.json")
    condition_by_slug = {c["slug"]: c for c in conditions}
    columns_by_slug = {c["slug"]: c for c in columns}
    profiles = []
    for filename in config["profile_files"]:
        source = CONTENT / "clinical-profiles" / filename
        if not source.exists():
            raise SystemExit("Editorial research incomplete: " + filename)
        for profile in read(source)["profiles"]:
            if profile["id"] in priority:
                profile["priority"] = priority[profile["id"]]
                profile["name"] = priority[profile["id"]]["name"]
            validate_profile(profile)
            profile["editorial_source"] = filename
            profiles.append(profile)
    if len({p["id"] for p in profiles}) != len(profiles):
        raise ValueError("Duplicate profile IDs")
    members = [m for p in profiles for m in p["members"]]
    duplicates = [m for m, n in Counter(members).items() if n != 1]
    missing, unknown = set(condition_by_slug) - set(members), set(members) - set(condition_by_slug)
    if duplicates or missing or unknown:
        raise ValueError(f"Incomplete coverage. Duplicate={duplicates}, missing={sorted(missing)}, unknown={sorted(unknown)}")
    by_member, explicit_columns = {}, {}
    for profile in profiles:
        primary = profile["canonical_slug"]
        if profile.get("canonical_path"):
            profile["hub_path"] = "/".join(quote(part, safe="") for part in profile["canonical_path"].split("/"))
        else:
            if primary not in profile["members"]:
                raise ValueError("Primary slug must be one of the owned members")
            profile["hub_path"] = "conditions/" + quote(primary, safe="")
        profile["category"] = profile.get("category") or (condition_by_slug[primary]["category"] if primary in condition_by_slug else "피부")
        profile.setdefault("status", "review")
        profile.setdefault("created_at", config["created_at"])
        priority_updated = assessment_updated_at.get(profile["id"], priority_data["updated_at"])
        profile["updated_at"] = max(profile.get("updated_at", config["created_at"]), priority_updated) if profile.get("priority") else profile.get("updated_at", config["created_at"])
        profile.setdefault("reviewed_by", None)
        profile.setdefault("reviewed_at", None)
        profile["search_terms"] = " ".join([profile["name"]] + profile.get("keywords", []) +
                                           [condition_by_slug[m]["name"] + " " + m.replace("-", " ") for m in profile["members"]])
        profile["topics"] = []
        for position, (key, label) in enumerate(PHASES, 1):
            section = dict(profile["sections"][key])
            section.update({"id": key, "label": label, "position": position,
                            "path": "guide/ochang-" + profile["id"] + "/" + key,
                            "image": "images/clinical-guides/" + profile["id"] + "/" + key + ".webp",
                            "image_small": "images/clinical-guides/" + profile["id"] + "/" + key + "-480.webp"})
            section["image_alt"] = profile["name"] + " " + label + ": " + ", ".join(section["diagram"]) + " 세 항목을 정리한 설명 도식"
            section["h1"] = "청주·오창 " + profile["name"] + " · " + section["question"]
            section["title"] = section["h1"] + " | 연결한의원 청주오창"
            section["description"] = "청주·오창 " + profile["name"] + " 상담을 준비하며 " + section["question"] + " " + section["points"][0]
            if section.get("page_metadata"):
                section["title"] = section["page_metadata"]["title"]
                section["h1"] = section["title"].split(" | ")[0]
                section["description"] = section["page_metadata"]["description"]
            profile["topics"].append(section)
        for member in profile["members"]:
            by_member[member] = profile
        for column in profile.get("column_slugs", []):
            if column not in columns_by_slug or column in explicit_columns:
                raise ValueError("Unknown or repeated explicit column mapping: " + column)
            explicit_columns[column] = profile
    candidates = []
    for condition in conditions:
        for term in [condition["name"].split(" · ")[0], condition["slug"].replace("-", " ")]:
            term = normalized(term)
            if len(term) >= 2:
                candidates.append((term, by_member[condition["slug"]], condition["slug"]))
    for profile in profiles:
        candidates.extend((normalized(term), profile, profile["canonical_slug"]) for term in profile.get("keywords", []) if len(normalized(term)) >= 2)
    candidates.sort(key=lambda item: len(item[0]), reverse=True)
    condition_entries, column_entries = [], []
    for condition in conditions:
        profile = by_member[condition["slug"]]
        relationship = profile.get("member_relationships", {}).get(condition["slug"], "canonical" if condition["slug"] == profile["canonical_slug"] else "related-symptom")
        path = "conditions/" + quote(condition["slug"], safe="")
        canonical = profile["hub_path"] if relationship == "alias" else path
        display_name = DISPLAY_NAMES.get(condition["slug"], condition["name"])
        condition_entries.append({"slug": condition["slug"], "name": condition["name"], "profile_id": profile["id"],
                                  "display_name": display_name,
                                  "path": path, "canonical_path": canonical, "relationship": relationship,
                                  "category": condition["category"], "title": "청주·오창 " + display_name + " | 증상·검사·관리 가이드",
                                  "description": "청주·오창에서 " + display_name + "에 관해 확인할 증상·배경·진찰·상담 선택·생활 관리·재평가 항목을 여섯 설명 도식과 상세 글로 안내합니다."})
        # Keep already observed leading results and every public URL intact.
        retained = {"msk-cervical-disc", "msk-lumbar-disc", "msk-carpal-tunnel", "msk-tennis-elbow", "women-menopause"}
        if profile.get("priority") and path == profile["hub_path"] and profile["id"] not in retained:
            keyword = profile["priority"]["keyword"]
            condition_entries[-1]["title"] = "청주·오창 " + keyword + " | 증상 구분과 검사 준비"
            condition_entries[-1]["description"] = "오창 " + keyword + ": " + profile["overview"].split(". ")[0] + ". 관찰한 증상과 진찰에서 확인할 차이, 검사·치료 선택 전 질문을 정리했습니다."
        if path == profile["hub_path"] and profile.get("page_metadata"):
            condition_entries[-1].update(profile["page_metadata"])
    unmatched = []
    for column in columns:
        slug = column["slug"]
        profile, matched_slug, method = None, None, None
        if slug in explicit_columns:
            profile, matched_slug, method = explicit_columns[slug], explicit_columns[slug]["canonical_slug"], "editorial-explicit"
        elif slug in MANUAL_COLUMNS:
            matched_slug = MANUAL_COLUMNS[slug]
            profile, method = by_member[matched_slug], "editorial-title-or-context"
        else:
            text = normalized(column["title"])
            match = next(((p, m) for term, p, m in candidates if term in text), None)
            if match:
                profile, matched_slug, method = match[0], match[1], "longest-specific-title-term"
        if profile is None:
            unmatched.append({"slug": slug, "title": column["title"]})
            continue
        name = condition_by_slug[matched_slug]["name"] if matched_slug in condition_by_slug else profile["name"]
        title = column_title(column["title"], name)
        # Retain the article's distinct question/scene, URL and existing body.
        column_entries.append({"slug": slug, "name": name, "profile_id": profile["id"], "path": "column/" + quote(slug, safe=""),
                               "canonical_path": "column/" + quote(slug, safe=""), "relationship": "related-article", "category": profile["category"],
                               "title": title, "original_title": column["title"], "mapping_method": method,
                               "description": title.replace(" | ", ". ") + ". " + profile["sections"]["assessment"]["points"][0]})
    if unmatched:
        raise ValueError("Unmapped articles must be editorially resolved: " + json.dumps(unmatched, ensure_ascii=False))
    condition_count, column_count = len(condition_entries), len(column_entries)
    result = {"config": config, "profiles": profiles, "conditions": condition_entries, "columns": column_entries,
              "counts": {"condition_urls": condition_count, "column_urls": column_count, "covered_existing_urls": condition_count + column_count,
                         "profiles": len(profiles), "detail_pages": len(profiles) * 6, "original_images": len(profiles) * 6,
                         "true_alias_urls": sum(e["relationship"] == "alias" for e in condition_entries)},
              "sources_checked_date": config["updated_at"], "search_exposure": {"submitted": False, "crawled": "unconfirmed", "indexed": "unconfirmed", "carousel": "unconfirmed"}}
    path = CONTENT / "clinical-catalog.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"catalog": str(path), **result["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
