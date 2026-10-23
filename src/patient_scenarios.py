"""Curated guides for an injury described before a diagnosis is established."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

CONTENT = Path(__file__).parent / "content/patient-scenarios.json"


def validate_scenarios(catalog, data, review=False):
    allowed = {"published", "review"} if review else {"published"}
    if not catalog or data.get("status") not in allowed:
        return []
    if not review and not data.get("publication_authorization", {}).get("authorized_at"):
        raise ValueError("Patient guides need site-owner publication authorization")
    entries, seen = [], set()
    for entry in data.get("entries", []):
        if entry.get("status") not in allowed:
            continue
        existing = next((e for e in catalog["conditions"] if "/" + e["path"] == entry.get("path") and e["profile_id"] == entry.get("profile_id")), None)
        valid_path = entry.get("path") == "/guide/" + entry.get("slug", "") or (entry.get("route_policy") == "preserve-existing" and existing)
        if (entry.get("profile_id") not in catalog["profiles_by_id"] or
                not re.fullmatch(r"ochang-[a-z0-9-]+", entry.get("slug", "")) or
                not valid_path or entry["path"] in seen):
            raise ValueError("Invalid or duplicate patient guide")
        for key in ("title", "description", "h1", "summary", "sections", "checks", "branches", "faq", "sources"):
            if not entry.get(key):
                raise ValueError("Incomplete patient guide: " + key)
        date.fromisoformat(entry["published_at"])
        date.fromisoformat(entry["updated_at"])
        if bool(entry.get("reviewed_by")) != bool(entry.get("reviewed_at")):
            raise ValueError("A real reviewer and actual review date are required together")
        sources = {source["url"] for source in entry["sources"]}
        for source in entry["sources"]:
            url = urlsplit(source["url"])
            if url.scheme != "https" or not url.netloc or not source.get("title") or not source.get("scope"):
                raise ValueError("Invalid clinical source")
        blocks = entry["sections"] + entry["branches"] + entry["faq"] + [{"source_urls": entry["checks_source_urls"]}]
        for block in blocks:
            if not block.get("source_urls") or not set(block["source_urls"]) <= sources:
                raise ValueError("Undeclared clinical evidence")
        for section in entry["sections"]:
            if not section.get("heading") or not section.get("paragraphs") or not all(section["paragraphs"]):
                raise ValueError("Empty patient explanation")
        for faq in entry["faq"]:
            if not faq.get("question") or not faq.get("answer"):
                raise ValueError("Empty patient answer")
        for branch in entry["branches"]:
            if not all(branch.get(key) for key in ("observation", "possibility", "distinction")) or branch.get("related_id") not in catalog["profiles_by_id"]:
                raise ValueError("Incomplete symptom distinction")
        entries.append(entry)
        seen.add(entry["path"])
    return entries


def load_scenarios(catalog, review=False):
    if not CONTENT.exists():
        return []
    return validate_scenarios(catalog, json.loads(CONTENT.read_text()), review)


def scenario_profile(catalog, scenario):
    profile = deepcopy(catalog["profiles_by_id"][scenario["profile_id"]])
    profile.update(overview=scenario["summary"], sources=scenario["sources"], updated_at=scenario["updated_at"],
                   published_at=scenario["published_at"], reviewed_by=scenario["reviewed_by"], reviewed_at=scenario["reviewed_at"])
    profile["comparison_caption"] = scenario["keyword"] + " 뒤 증상에 따라 구분할 점"
    profile["priority"] = {"id": profile["id"], "keyword": scenario["keyword"], "checks": scenario["checks"],
                           "branches": scenario["branches"], "faq": scenario["faq"], "evidence": scenario["sources"]}
    related = dict.fromkeys(b["related_id"] for b in scenario["branches"])
    profile["priority_related"] = [catalog["profiles_by_id"][pid] for pid in related if pid != profile["id"]]
    return profile
