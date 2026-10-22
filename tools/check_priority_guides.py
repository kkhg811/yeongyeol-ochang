"""Verify the priority guides as generated HTML, without a network dependency."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.checks, self.links, self.for_ids = set(), 0, [], set()
        self.feed(text)

    def handle_starttag(self, tag, pairs):
        a = dict(pairs)
        if a.get('id'):
            assert a['id'] not in self.ids, 'Duplicate HTML id: ' + a['id']
            self.ids.add(a['id'])
        if tag == 'input' and a.get('type') == 'checkbox':
            self.checks += 1
        if tag == 'label' and a.get('for'):
            self.for_ids.add(a['for'])
        if tag == 'a':
            self.links.append(a.get('href', ''))

def main():
    data = json.loads((ROOT/'src/content/priority80.json').read_text())
    catalog = json.loads((ROOT/'src/content/clinical-catalog.json').read_text())
    by_id = {p['id']:p for p in catalog['profiles']}
    assert data['status'] == 'published' and len(data['profiles']) == 80
    assert [p['order'] for p in data['profiles']] == list(range(1,81))
    assert data.get('reviewed_by') is None and data.get('reviewed_at') is None
    count = 0
    for item in data['profiles']:
        p = by_id[item['id']]
        assert len(item['checks']) == 3 and len(set(item['checks'])) == 3
        assert len(item['branches']) == 2 and len(item['faq']) == 2 and item['evidence']
        for path in [p['hub_path']] + [t['path'] for t in p['topics']]:
            html = (ROOT/'docs'/(unquote(path)+'.html')).read_text()
            page = Page(html)
            assert page.checks == 3, path
            assert page.for_ids <= page.ids, path
            assert {'symptom-check', 'symptom-patterns'} <= page.ids, path
            assert 'class="clinical-alert"' not in html, path
            for t in p['topics']:
                assert '/'+t['path'] in page.links, path
            for b in item['branches']:
                assert b['observation'] in html and b['distinction'] in html, path
            assert 'FAQPage' not in html, 'FAQ content is not a promise of a Naver rich result'
            count += 1
    result = {'profiles':80, 'verified_primary_and_detail_pages':count, 'checks_per_page':3,
              'two_observation_branches_and_uncertain_case':True, 'search_exposure':'not_asserted'}
    target = ROOT/'verification/priority80-build.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__':
    main()
