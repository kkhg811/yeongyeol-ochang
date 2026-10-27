"""Verify the 21 requested intents, two new series, and preserved existing content."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
KMC = (ROOT / 'src/content/clinical-catalog.json').exists()
CONTENT = ROOT / ('src/content' if KMC else 'content')
CATALOG = ROOT / ('src/content/clinical-catalog.json' if KMC else 'app/clinical-catalog.json')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    m = read(CONTENT / 'series-revisions-women-urology-20261026.json')
    current = read(CATALOG)
    baseline = json.loads(subprocess.check_output(['git', 'show', m['baseline_commit'] + ':' + CATALOG.relative_to(ROOT).as_posix()], cwd=ROOT, text=True))
    before = {p['id']: p for p in baseline['profiles']}
    profiles = {p['id']: p for p in current['profiles']}
    ids, new_ids = set(m['profile_ids']), set(m['new_profile_ids'])
    later_file = CONTENT / 'series-revisions-women-sleep-20261027.json'
    later = read(later_file) if later_file.exists() else {'profile_ids': [], 'updated_at': m['updated_at']}
    later_ids = set(later['profile_ids'])
    assert len(ids) == 15 and len(new_ids) == 2
    assert set(profiles) == set(before) | new_ids and not new_ids & set(before)
    assert len(m['queries']) == 21 and [q['order'] for q in m['queries']] == list(range(1, 22))
    assert {q['profile_id'] for q in m['queries']} == ids
    for pid in set(before) - ids - later_ids:
        assert profiles[pid] == before[pid], pid + ': unrelated profile changed'
    # The original 1–80 table retains its ordering; extra series are independent.
    priority = read(CONTENT / 'priority80.json')
    extra = read(CONTENT / 'additional-clinical-assessments.json')
    assert len(priority['profiles']) == 80
    assert [p['order'] for p in priority['profiles']] == list(range(1, 81))
    assert extra['status'] == 'published'
    assert {p['id'] for p in extra['profiles']} == new_ids | {'women-after-miscarriage'} | later_ids
    assessments = {p['id']: p for p in priority['profiles'] + extra['profiles']}
    dates = {**priority['profile_updated_at'], **extra['profile_updated_at']}
    images = {(x['profile_id'], x['topic']): x for x in m['image_revisions']}
    bodies, titles, descriptions = set(), set(), set()
    images_checked = 0
    for pid in ids:
        p = profiles[pid]
        expected_date = later['updated_at'] if pid in later_ids else m['updated_at']
        assert p['status'] == 'published' and p['updated_at'] == expected_date
        assert p['medical_review_status'] == 'pending' and p['reviewed_by'] is None and p['reviewed_at'] is None
        assert len(p['topics']) == 6 and len({t['question'] for t in p['topics']}) == 6
        if pid in new_ids:
            assert p['created_at'] == p['published_at'] == m['updated_at']
            assert p['hub_path'].lstrip('/') == 'guide/ochang-' + pid
        else:
            old = before[pid]
            assert p['published_at'] == old['published_at'] and p['created_at'] == old['created_at']
            assert p['hub_path'] == old['hub_path']
            assert [t['path'] for t in p['topics']] == [t['path'] for t in old['topics']]
        a = assessments[pid]
        assert dates[pid] == expected_date
        assert len(a['checks']) == len(set(a['checks'])) == 3
        assert len(a['branches']) == len(a['faq']) == 2 and a['evidence']
        assert all(b['related_id'] in profiles and b['observation'] and b['possibility'] and b['distinction'] for b in a['branches'])
        declared = {s['url'] for s in p['sources']} | {s['url'] for s in a['evidence']}
        assert len(p['reading_sections']) >= 2 and len(p['faq']) >= 3
        for owner in [p] + p['topics']:
            assert owner['reading_sections'] and len(owner['faq']) >= 2
            for block in owner['reading_sections']:
                assert block['heading'].strip() and block['text'].strip() and block['source_urls']
                assert set(block['source_urls']) <= declared
            for faq in owner['faq']:
                assert faq['question'].strip() and faq['answer'].strip() and faq['source_urls']
                assert set(faq['source_urls']) <= declared
            meta = owner['page_metadata']
            assert meta['title'] and meta['title'] not in titles
            assert meta['description'] and meta['description'] not in descriptions
            titles.add(meta['title']); descriptions.add(meta['description'])
        for t in p['topics']:
            body = '\n'.join(s['text'] for s in t['reading_sections'])
            assert body not in bodies, pid + '/' + t['id']
            bodies.add(body)
            changed = (pid, t['id']) in images
            if pid not in new_ids:
                old = next(x for x in before[pid]['topics'] if x['id'] == t['id'])
                assert t['image'] == old['image'] and t['image_small'] == old['image_small']
                if not changed:
                    assert t['question'] == old['question'] and t['points'] == old['points'] and t['diagram'] == old['diagram']
            for key, size in [('image', 1080), ('image_small', 480)]:
                image = t[key]
                rel = 'docs/' + image.lstrip('/') if KMC else 'public/images/' + image.removeprefix('/media/')
                path = ROOT / rel
                with Image.open(path) as im:
                    assert im.format == 'WEBP' and im.size == (size, size)
                if pid in new_ids:
                    assert changed and t['image_updated_at'] == m['updated_at']
                    assert subprocess.run(['git', 'cat-file', '-e', m['baseline_commit'] + ':' + rel], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
                else:
                    old_bytes = subprocess.check_output(['git', 'show', m['baseline_commit'] + ':' + rel], cwd=ROOT)
                    assert (hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(old_bytes).digest()) == changed, rel
                images_checked += 1
    assert len(bodies) == 90 and images_checked == 180
    rendered = None
    if KMC:
        # All pre-existing condition and column relationships remain exactly as released.
        for kind in ['conditions', 'columns']:
            keys = ['path', 'profile_id', 'canonical_path']
            assert [tuple(e[k] for k in keys) for e in current[kind]] == [tuple(e[k] for k in keys) for e in baseline[kind]]
        sys.path.insert(0, str(ROOT / 'src'))
        from clinical_guides import load_catalog
        from check_clinical_guides import Page, resolve_path
        cat = load_catalog(); origin = cat['config']['target_origin']
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'i': 'http://www.google.com/schemas/sitemap-image/1.1'}
        xml = ET.parse(ROOT / 'docs/sitemap.xml')
        sitemap = {n.find('s:loc', ns).text: n for n in xml.findall('s:url', ns)}
        rendered = 0
        for pid in ids:
            p = cat['profiles_by_id'][pid]
            for topic in [None] + p['topics']:
                owner = topic or p; path = topic['path'] if topic else p['hub_path']
                html = resolve_path(path).read_text(); page = Page(html)
                assert len(page.h1) == 1 and page.canonical == origin + '/' + path
                assert len(page.cards) == 6 and [c['url'] for c in page.cards] == ['/' + t['path'] for t in p['topics']]
                lists = [n for n in page.schemas if n.get('@type') == 'ItemList']
                assert len(lists) == 1 and [x['url'] for x in lists[0]['itemListElement']] == [origin + '/' + t['path'] for t in p['topics']]
                assert html.count('type="checkbox"') == 3 and {'symptom-check', 'symptom-patterns'} <= page.ids
                assert 'class="clinical-alert"' not in html and 'FAQPage' not in html
                assert page.meta['og:image'] == origin + '/' + (topic or p['topics'][0])['image']
                for block in owner['reading_sections']:
                    assert block['heading'] in html and block['text'] in html
                for faq in owner['faq']:
                    assert faq['question'] in html and faq['answer'] in html
                node = sitemap[origin + '/' + path]
                assert node.find('s:lastmod', ns).text == p['updated_at']
                assert [n.text for n in node.findall('i:image/i:loc', ns)] == [origin + '/' + t['image'] for t in p['topics']]
                rendered += 1
        assert rendered == 105
        search = read(ROOT / 'docs/search-index.json')
        assert all(any(e['url'] == '/' + profiles[pid]['hub_path'] for e in search) for pid in new_ids)
    report = ROOT / 'verification/women-urology-20261026.json'
    result = read(report) if report.exists() else {}
    result.update({'updated_at': m['updated_at'], 'queries': 21, 'profiles': 15, 'existing_series_revised': 13,
                   'new_series': 2, 'core_pages': 105, 'new_core_pages': 14, 'source_checks': 'passed',
                   'rendered_html_pages_checked': rendered, 'distinct_detail_bodies': 90, 'image_files_checked': images_checked,
                   'created_diagrams': len([i for i in images.values() if i['action'] == 'created']),
                   'other_profiles_unchanged': not bool(later_ids), 'priority80_order_preserved': True,
                   'later_authorized_profile_revisions': sorted(later_ids),
                   'medical_review_status': 'pending', 'search_exposure': m['search_exposure']})
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
