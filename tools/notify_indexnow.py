#!/usr/bin/env python3
"""Notify Naver about changed, deployed pages. Defaults to a local dry run."""

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "src"))
from site_info import SITE

ORIGIN = SITE["url"].rstrip("/")
ENDPOINT = "https://searchadvisor.naver.com/indexnow"
USER_AGENT = "Mozilla/5.0 (compatible; YeongyeolOchangSiteUpdate/1.0)"


class PageInfo(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.title = ""
        self.canonical = ""
        self.robots = ""
        self.in_title = False
        self.in_main = False
        self.skip = 0
        self.parts = []
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "main":
            self.in_main = True
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "link" and "canonical" in attrs.get("rel", "").split():
            self.canonical = attrs.get("href", "")
        if tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.robots = attrs.get("content", "")
        if self.in_main and tag == "a":
            self.links.append(attrs.get("href", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "main":
            self.in_main = False
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_main and not self.skip:
            self.parts.append(data)

    def fingerprint(self):
        return (self.title, self.canonical,
                " ".join(" ".join(self.parts).split()), tuple(self.links))


@dataclass
class ChangedPage:
    url: str
    info: PageInfo


def collect_pages(files):
    sitemap = ET.parse(DOCS / "sitemap.xml")
    known_urls = {node.text for node in sitemap.findall(
        "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
        "{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
    pages = {}
    for filename in files:
        path = Path(filename).resolve()
        if not path.is_relative_to(DOCS.resolve()) or path.suffix != ".html":
            raise ValueError("docs/ 내부의 배포용 HTML 파일만 지정할 수 있습니다.")
        info = PageInfo(path.read_text(encoding="utf-8"))
        url = urlsplit(info.canonical)
        if (url.scheme, url.netloc) != ("https", urlsplit(ORIGIN).netloc):
            raise ValueError("운영 도메인의 대표 주소가 아닌 파일입니다.")
        if url.query or url.fragment or info.canonical not in known_urls:
            raise ValueError("사이트맵에 등록된 대표 주소가 아닙니다.")
        if "noindex" in info.robots.lower() or not info.parts:
            raise ValueError("색인 제외 또는 본문이 없는 페이지는 알리지 않습니다.")
        pages[info.canonical] = ChangedPage(info.canonical, info)
    if not pages:
        raise ValueError("실제로 변경된 페이지를 지정해 주세요.")
    return list(pages.values())


def load_key():
    config = json.loads((ROOT / "tools" / "indexnow.json").read_text())
    filename = config["key_file"]
    if not re.fullmatch(r"[A-Fa-f0-9-]{8,128}\.txt", filename):
        raise ValueError("IndexNow 소유 확인 파일 설정이 잘못되었습니다.")
    key = (DOCS / filename).read_text(encoding="utf-8").strip()
    if key != filename[:-4]:
        raise ValueError("소유 확인 파일의 이름과 내용이 다릅니다.")
    return filename, key


def get_text(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("운영 URL이 200으로 직접 응답하지 않습니다.")
        if "noindex" in response.headers.get("X-Robots-Tag", "").lower():
            raise ValueError("운영 응답에 색인 제외 설정이 있습니다.")
        return response.read().decode("utf-8")


def post_payload(payload):
    request = Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json; charset=utf-8",
                               "User-Agent": USER_AGENT}, method="POST")
    with urlopen(request, timeout=20) as response:
        body = response.read()
        if response.geturl() != ENDPOINT or b"<html" in body[:300].lower():
            raise ValueError("예상한 IndexNow API 응답이 아닙니다.")
        return response.status


def submit_pages(pages, filename, key):
    key_url = ORIGIN + "/" + filename
    if get_text(key_url).strip() != key:
        raise ValueError("운영 사이트의 소유 확인 파일이 수정본과 다릅니다.")
    for page in pages:
        live = PageInfo(get_text(page.url))
        if "noindex" in live.robots.lower():
            raise ValueError("운영 페이지의 메타 태그가 색인을 제외하고 있습니다.")
        if live.fingerprint() != page.info.fingerprint():
            raise ValueError("운영 본문이 로컬 수정본과 다릅니다. 배포 후 실행하세요: " + page.url)
    status = post_payload({"host": urlsplit(ORIGIN).netloc, "key": key,
                           "keyLocation": key_url, "urlList": [p.url for p in pages]})
    if status not in (200, 202):
        raise ValueError("IndexNow 알림이 접수되지 않았습니다. HTTP " + str(status))
    return {"mode": "submit", "http_status": status,
            "state": "submitted" if status == 200 else "key_validation_pending",
            "urls": [p.url for p in pages],
            "note": "변경 알림의 접수 상태이며, 수집·색인·검색 순위 완료를 뜻하지 않습니다."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True, type=Path,
                        help="실제로 변경한 docs/ 아래 HTML 파일")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--submit", action="store_true", help="운영 반영을 검증한 뒤 실제 전송")
    mode.add_argument("--dry-run", action="store_true", help="전송 없이 로컬 설정 검사 (기본값)")
    args = parser.parse_args()
    try:
        pages = collect_pages(args.files)
        filename, key = load_key()
        result = (submit_pages(pages, filename, key) if args.submit else
                  {"mode": "dry-run", "endpoint": ENDPOINT,
                   "urls": [p.url for p in pages], "requires_live_verification": True})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, HTTPError, URLError) as error:
        print("전송하지 못했습니다: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
