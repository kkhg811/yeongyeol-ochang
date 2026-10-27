"""Verify 21 requested expressions in 18 complete, independently editable series."""
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


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    m = read(CONTENT / 'series-revisions-women-sleep-20261027.json')
    cat = read(CATALOG)
    by_id = {p['id']: p for p in cat['profiles']}
    ids = set(m['profile_ids'])
    assert len(ids) == 18 and len(m['queries']) == 21 and m['core_pages'] == 126
    assert [q['order'] for q in m['queries']] == list(range(1, 22))
    assert {q['profile_id'] for q in m['queries']} == ids
    assert len(by_id) == (189 if KMC else 191)
    assert m['new_profile_ids'] == m['image_revisions'] == [] and m['new_core_pages'] == 0
    assert set(by_id) == ids | set(m['preserved_profile_sha256'])
    for pid, expected in m['preserved_profile_sha256'].items():
        assert digest(by_id[pid]) == expected, pid + ': unrelated profile changed'
    priority = read(CONTENT / 'priority80.json')
    assert digest(priority) == m['priority80_sha256']
    assert len(priority['profiles']) == 80 and [p['order'] for p in priority['profiles']] == list(range(1, 81))
    extra = read(CONTENT / 'additional-clinical-assessments.json')
    extra_by = {p['id']: p for p in extra['profiles']}
    assert extra['status'] == 'published' and len(extra['profiles']) == len(extra_by) == 20
    assert set(extra_by) == ids | {'urology-benign-prostate', 'urology-urinary-incontinence'}
    assert not set(extra_by) & {p['id'] for p in priority['profiles']}
    for pid, expected in m['preserved_additional_assessment_sha256'].items():
        assert digest(extra_by[pid]) == expected, pid + ': prior assessment changed'
    bodies, titles, descriptions = set(), set(), set()
    image_files = 0
    for pid in ids:
        p, old, a = by_id[pid], m['target_baselines'][pid], extra_by[pid]
        assert p['status'] == 'published' and p['updated_at'] == m['updated_at']
        assert p['created_at'] == old['created_at'] and p['published_at'] == old['published_at']
        assert p['hub_path'] == old['hub_path'] and len(p['topics']) == 6
        assert p['medical_review_status'] == 'pending' and p['reviewed_by'] is None and p['reviewed_at'] is None
        assert extra['profile_updated_at'][pid] == m['updated_at']
        assert len(a['checks']) == len(set(a['checks'])) == 3 and len(a['branches']) == len(a['faq']) == 2
        assert a['evidence'] and all(b['related_id'] in by_id and b['observation'] and b['possibility'] and b['distinction'] for b in a['branches'])
        known = {s['url'] for s in p['sources']} | {s['url'] for s in a['evidence']}
        assert len(p['reading_sections']) >= 2 and len(p['faq']) >= 3
        for i, owner in enumerate([p] + p['topics']):
            assert owner['reading_sections'] and len(owner['faq']) >= 2
            for block in owner['reading_sections']:
                assert block['heading'].strip() and block['text'].strip() and block['source_urls'] and set(block['source_urls']) <= known
            for faq in owner['faq']:
                assert faq['question'].strip() and faq['answer'].strip() and faq['source_urls'] and set(faq['source_urls']) <= known
            meta = owner['page_metadata']
            assert meta['title'] and meta['title'] not in titles and meta['description'] and meta['description'] not in descriptions
            titles.add(meta['title']); descriptions.add(meta['description'])
            if old['prior_copy_prefix']:
                prior = old['prior_copy_prefix'][i]
                for key in ['reading_sections', 'faq']:
                    assert owner[key][:len(prior[key])] == prior[key], pid + ': prior useful copy removed'
        for t, t_old in zip(p['topics'], old['topics']):
            assert {k: t[k] for k in t_old} == t_old, pid + '/' + t['id'] + ': card data or public paths changed'
            body = '\n'.join(s['text'] for s in t['reading_sections'])
            assert body not in bodies
            bodies.add(body)
            for key, size in [('image', 1080), ('image_small', 480)]:
                rel = 'docs/' + t[key].lstrip('/') if KMC else 'public/images/' + t[key].removeprefix('/media/')
                file = ROOT / rel
                with Image.open(file) as im:
                    assert im.format == 'WEBP' and im.size == (size, size)
                assert file.read_bytes() == subprocess.check_output(['git', 'show', m['baseline_commit'] + ':' + rel], cwd=ROOT), rel
                image_files += 1
    assert len(bodies) == 108 and image_files == 216
    rendered = None
    if KMC:
        prior = json.loads(subprocess.check_output(['git', 'show', m['baseline_commit'] + ':src/content/clinical-catalog.json'], cwd=ROOT, text=True))
        for kind in ['conditions', 'columns']:
            fields = ['path', 'profile_id', 'canonical_path']
            assert [tuple(e[k] for k in fields) for e in cat[kind]] == [tuple(e[k] for k in fields) for e in prior[kind]]
        insomnia_path = by_id['mind-insomnia']['hub_path']
        assert next(c['title'] for c in cat['conditions'] if c['path'] == insomnia_path) == next(c['title'] for c in prior['conditions'] if c['path'] == insomnia_path)
        sys.path.insert(0, str(ROOT / 'src'))
        from check_clinical_guides import Page, resolve_path
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'i': 'http://www.google.com/schemas/sitemap-image/1.1'}
        origin = cat['config']['target_origin']
        sitemap = {n.find('s:loc', ns).text: n for n in ET.parse(ROOT / 'docs/sitemap.xml').findall('s:url', ns)}
        rendered = 0
        for pid in ids:
            p = by_id[pid]
            for t in [None] + p['topics']:
                owner, path = t or p, t['path'] if t else p['hub_path']
                html = resolve_path(path).read_text(); page = Page(html)
                assert len(page.h1) == 1 and page.canonical == origin + '/' + path
                assert [c['url'] for c in page.cards] == ['/' + x['path'] for x in p['topics']]
                assert [c['url'] for c in page.cards if c.get('current') == 'page'] == (['/' + path] if t else [])
                lists = [n for n in page.schemas if n.get('@type') == 'ItemList']
                assert len(lists) == 1 and [x['url'] for x in lists[0]['itemListElement']] == [origin + '/' + x['path'] for x in p['topics']]
                assert html.count('type="checkbox"') == 3 and {'symptom-check', 'symptom-patterns'} <= page.ids
                assert 'class="clinical-alert"' not in html and 'FAQPage' not in html
                assert page.meta['og:image'] == origin + '/' + (t or p['topics'][0])['image']
                for block in owner['reading_sections']:
                    assert block['heading'] in html and block['text'] in html
                for faq in owner['faq']:
                    assert faq['question'] in html and faq['answer'] in html
                node = sitemap[origin + '/' + path]
                assert node.find('s:lastmod', ns).text == p['updated_at']
                assert [n.text for n in node.findall('i:image/i:loc', ns)] == [origin + '/' + x['image'] for x in p['topics']]
                rendered += 1
        assert rendered == 126
    report = ROOT / 'verification/women-sleep-20261027.json'
    result = read(report) if report.exists() else {}
    result.update({'updated_at': m['updated_at'], 'queries': 21, 'profiles': 18, 'core_pages': 126,
        'new_core_pages': 0, 'source_checks': 'passed', 'rendered_html_pages_checked': rendered,
        'distinct_detail_bodies': 108, 'preserved_image_files': image_files,
        'other_profiles_unchanged': True, 'priority80_unchanged': True,
        'previous_urology_assessments_preserved': True, 'previous_miscarriage_copy_preserved': True,
        'medical_review_status': 'pending', 'search_exposure': m['search_exposure']})
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
