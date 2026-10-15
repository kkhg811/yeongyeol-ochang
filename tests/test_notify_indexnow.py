from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools import notify_indexnow as notify


def html(url, text="방문 준비와 진료일정", robots="index, follow"):
    return ('<!doctype html><html><head><title>첫 방문 안내</title>'
            f'<link rel="canonical" href="{url}">'
            f'<meta name="robots" content="{robots}"></head>'
            f'<body><main><h1>{text}</h1><a href="/about">의료진</a></main></body></html>')


class IndexNowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.url = notify.ORIGIN + "/guide/ochang-clinic"
        self.page = self.docs / "guide.html"
        self.page.write_text(html(self.url), encoding="utf-8")
        self.set_sitemap(self.url)
        self.patch_docs = patch.object(notify, "DOCS", self.docs)
        self.patch_docs.start()
        self.addCleanup(self.patch_docs.stop)
        self.key = "a" * 32
        self.filename = self.key + ".txt"

    def set_sitemap(self, url):
        (self.docs / "sitemap.xml").write_text(
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'<url><loc>{url}</loc></url></urlset>', encoding="utf-8")

    def live_text(self, url):
        return self.key if url.endswith(".txt") else html(self.url)

    def test_canonical_urls_are_deduplicated(self):
        pages = notify.collect_pages([self.page, self.page])
        self.assertEqual([p.url for p in pages], [self.url])

    def test_files_outside_the_deployment_directory_are_rejected(self):
        outside = self.root / "outside.html"
        outside.write_text(html(self.url))
        with self.assertRaisesRegex(ValueError, "docs/"):
            notify.collect_pages([outside])

    def test_another_domain_cannot_be_submitted(self):
        self.page.write_text(html("https://other.example/guide"))
        self.set_sitemap("https://other.example/guide")
        with self.assertRaisesRegex(ValueError, "운영 도메인"):
            notify.collect_pages([self.page])

    def test_pages_excluded_from_indexing_or_sitemap_are_rejected(self):
        self.page.write_text(html(self.url, robots="noindex, follow"))
        with self.assertRaisesRegex(ValueError, "색인 제외"):
            notify.collect_pages([self.page])
        self.page.write_text(html(self.url))
        self.set_sitemap(notify.ORIGIN + "/")
        with self.assertRaisesRegex(ValueError, "사이트맵"):
            notify.collect_pages([self.page])

    def test_mismatched_ownership_file_prevents_notification(self):
        pages = notify.collect_pages([self.page])
        with patch.object(notify, "get_text", return_value="different"), \
                patch.object(notify, "post_payload") as post:
            with self.assertRaisesRegex(ValueError, "소유 확인"):
                notify.submit_pages(pages, self.filename, self.key)
            post.assert_not_called()

    def test_old_deployed_content_prevents_notification(self):
        pages = notify.collect_pages([self.page])
        def old_live(url):
            return self.key if url.endswith(".txt") else html(self.url, text="이전 본문")
        with patch.object(notify, "get_text", side_effect=old_live), \
                patch.object(notify, "post_payload") as post:
            with self.assertRaisesRegex(ValueError, "배포 후"):
                notify.submit_pages(pages, self.filename, self.key)
            post.assert_not_called()

    def test_live_noindex_prevents_notification(self):
        pages = notify.collect_pages([self.page])
        def noindex_live(url):
            return self.key if url.endswith(".txt") else html(self.url, robots="noindex")
        with patch.object(notify, "get_text", side_effect=noindex_live), \
                patch.object(notify, "post_payload") as post:
            with self.assertRaisesRegex(ValueError, "색인을 제외"):
                notify.submit_pages(pages, self.filename, self.key)
            post.assert_not_called()

    def test_analytics_injection_does_not_change_content_verification(self):
        pages = notify.collect_pages([self.page])
        def live_with_analytics(url):
            return (self.key if url.endswith(".txt") else
                    html(self.url).replace("</body>", '<script src="/analytics.js"></script></body>'))
        with patch.object(notify, "get_text", side_effect=live_with_analytics), \
                patch.object(notify, "post_payload", return_value=200) as post:
            result = notify.submit_pages(pages, self.filename, self.key)
            self.assertEqual(result["state"], "submitted")
            post.assert_called_once()
            self.assertEqual(post.call_args.args[0]["urlList"], [self.url])
            self.assertEqual(post.call_args.args[0]["host"], "www.yeongyeolochangkmc.co.kr")

    def test_202_is_pending_and_rate_limits_are_not_retried(self):
        pages = notify.collect_pages([self.page])
        with patch.object(notify, "get_text", side_effect=self.live_text), \
                patch.object(notify, "post_payload", return_value=202):
            self.assertEqual(notify.submit_pages(pages, self.filename, self.key)["state"],
                             "key_validation_pending")
        with patch.object(notify, "get_text", side_effect=self.live_text), \
                patch.object(notify, "post_payload", side_effect=
                             HTTPError(notify.ENDPOINT, 429, "Too Many Requests", {}, None)) as post:
            with self.assertRaises(HTTPError):
                notify.submit_pages(pages, self.filename, self.key)
            post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
