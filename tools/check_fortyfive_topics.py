"""Check the 45 requested queries without treating implementation as search exposure."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
KMC = (ROOT / 'src/content/clinical-catalog.json').is_file()
CONTENT = ROOT / ('src/content' if KMC else 'content')
CATALOG = ROOT / ('src/content/clinical-catalog.json' if KMC else 'app/clinical-catalog.json')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest = read(CONTENT / 'series-revisions-fortyfive-20261025.json')
    current = read(CATALOG)
    baseline = json.loads(subprocess.check_output(['git', 'show', manifest['baseline_commit'] + ':' + CATALOG.relative_to(ROOT).as_posix()], cwd=ROOT, text=True))
    before = {p['id']: p for p in baseline['profiles']}
    profiles = {p['id']: p for p in current['profiles']}
    ids = manifest['profile_ids']
    assert len(ids) == len(set(ids)) == 29
    assert len(manifest['queries']) == 45 and [x['order'] for x in manifest['queries']] == list(range(1, 46))
    assert {x['profile_id'] for x in manifest['queries']} == set(ids)
    assert all(x['query'].startswith('오창 ') for x in manifest['queries'])
    extension_file = CONTENT / 'series-revisions-women-urology-20261026.json'
    extension = read(extension_file) if extension_file.exists() else {'profile_ids': [], 'new_profile_ids': []}
    assert set(profiles) == set(before) | set(extension['new_profile_ids'])
    later_ids = set(extension['profile_ids'])
    newest_file = CONTENT / 'series-revisions-women-sleep-20261027.json'
    if newest_file.exists():
        later_ids.update(read(newest_file)['profile_ids'])
    for pid, profile in profiles.items():
        if pid not in set(ids) | later_ids:
            assert profile == before[pid], pid + ': unrelated profile changed'
    priority = read(CONTENT / 'priority80.json')
    assessment = {p['id']: p for p in priority['profiles']}
    assert priority['updated_at'] >= manifest['updated_at']
    revised_images = {(x['profile_id'], x['topic']) for x in manifest['image_revisions']}
    bodies, metadata_titles, descriptions = set(), set(), set()
    image_count = 0
    for pid in ids:
        p, old = profiles[pid], before[pid]
        assert p['status'] == 'published' and p['updated_at'] == manifest['updated_at']
        assert p['published_at'] == old['published_at'] and p['hub_path'] == old['hub_path']
        assert p['medical_review_status'] == 'pending' and p.get('reviewed_by') is None and p.get('reviewed_at') is None
        assert len(p['topics']) == 6 and [t['path'] for t in p['topics']] == [t['path'] for t in old['topics']]
        assert len({t['question'] for t in p['topics']}) == 6
        assert len(assessment[pid]['checks']) == 3 and len(assessment[pid]['branches']) == 2
        assert len(set(assessment[pid]['checks'])) == 3
        assert all(b['related_id'] in profiles for b in assessment[pid]['branches'])
        assert priority['profile_updated_at'][pid] == manifest['updated_at']
        declared = {s['url'] for s in p['sources']} | {s['url'] for s in assessment[pid]['evidence']}
        assert len(p['reading_sections']) >= 2 and len(p['faq']) >= 3
        for owner in [p] + p['topics']:
            assert owner['reading_sections'] and len(owner['faq']) >= 2
            assert len({f['question'] for f in owner['faq']}) == len(owner['faq'])
            for block in owner['reading_sections']:
                assert block['heading'].strip() and block['text'].strip() and block['source_urls']
                assert set(block['source_urls']) <= declared
            for faq in owner['faq']:
                assert faq['question'].strip() and faq['answer'].strip() and faq['source_urls']
                assert set(faq['source_urls']) <= declared
            meta = owner['page_metadata']
            assert meta['title'] not in metadata_titles and meta['description'] not in descriptions
            metadata_titles.add(meta['title']); descriptions.add(meta['description'])
        for t, previous in zip(p['topics'], old['topics']):
            assert t['image'] == previous['image'] and t['image_small'] == previous['image_small']
            body = '\n'.join(s['text'] for s in t['reading_sections'])
            assert body not in bodies, pid + '/' + t['id'] + ': repeated explanation'
            bodies.add(body)
            changed = (pid, t['id']) in revised_images
            if not changed:
                assert t['question'] == previous['question'] and t['diagram'] == previous['diagram']
            else:
                assert t.get('image_updated_at') == manifest['updated_at']
                assert t['question'] != previous['question']
            for image in [t['image'], t['image_small']]:
                rel = ('docs/' + image.lstrip('/')) if KMC else ('public/images/' + image.removeprefix('/media/'))
                path = ROOT / rel
                old_bytes = subprocess.check_output(['git', 'show', manifest['baseline_commit'] + ':' + rel], cwd=ROOT)
                assert (digest(path.read_bytes()) != digest(old_bytes)) == changed, rel
                image_count += 1
    assert len(bodies) == 174
    rendered = None
    if KMC:
        sys.path.insert(0, str(ROOT / 'src'))
        from clinical_guides import load_catalog
        from check_clinical_guides import Page, resolve_path
        catalog = load_catalog(); origin = catalog['config']['target_origin']
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'i': 'http://www.google.com/schemas/sitemap-image/1.1'}
        tree = ET.parse(ROOT / 'docs/sitemap.xml')
        sitemap = {n.find('s:loc', ns).text: n for n in tree.findall('s:url', ns)}
        titles, descriptions = set(), set()
        rendered = 0
        for pid in ids:
            p = catalog['profiles_by_id'][pid]
            for topic in [None] + p['topics']:
                owner = topic or p; path = topic['path'] if topic else p['hub_path']
                html = resolve_path(path).read_text(); page = Page(html)
                assert len(page.h1) == 1 and page.canonical == origin + '/' + path
                assert len(page.cards) == 6 and [c['url'] for c in page.cards] == ['/' + t['path'] for t in p['topics']]
                items = [n for n in page.schemas if n.get('@type') == 'ItemList']
                assert len(items) == 1
                assert [x['url'] for x in items[0]['itemListElement']] == [origin + '/' + t['path'] for t in p['topics']]
                assert html.count('type="checkbox"') == 3 and {'symptom-check', 'symptom-patterns'} <= page.ids
                assert 'class="clinical-alert"' not in html and 'FAQPage' not in html
                assert ''.join(page.titles) not in titles and page.meta['description'] not in descriptions
                titles.add(''.join(page.titles)); descriptions.add(page.meta['description'])
                for block in owner['reading_sections']:
                    assert block['heading'] in html and block['text'] in html
                for faq in owner['faq']:
                    assert faq['question'] in html and faq['answer'] in html
                node = sitemap[origin + '/' + path]
                assert node.find('s:lastmod', ns).text == p['updated_at']
                assert [x.text for x in node.findall('i:image/i:loc', ns)] == [origin + '/' + t['image'] for t in p['topics']]
                rendered += 1
        assert rendered == 203
        tennis_path = profiles['msk-tennis-elbow']['hub_path']
        assert next(c['title'] for c in current['conditions'] if c['path'] == tennis_path) == next(c['title'] for c in baseline['conditions'] if c['path'] == tennis_path)
    report = ROOT / 'verification/fortyfive-topics-20261025.json'
    result = read(report) if report.exists() else {}
    result.update({'updated_at': manifest['updated_at'], 'queries': 45, 'profiles': 29, 'core_pages': 203,
                   'source_checks': 'passed', 'rendered_html_pages_checked': rendered,
                   'distinct_detail_bodies': 174, 'image_files_checked': image_count,
                   'changed_diagrams': len(revised_images), 'other_profiles_unchanged': not bool(later_ids),
                   'later_authorized_profile_revisions': sorted(later_ids),
                   'medical_review_status': 'pending',
                   'search_exposure': manifest['search_exposure']})
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
