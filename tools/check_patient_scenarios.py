"""Validate the new injury guides and their existing-series connections."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from clinical_guides import load_catalog
from patient_scenarios import load_scenarios, validate_scenarios
from check_clinical_guides import Page, resolve_path


def main():
    catalog=load_catalog(); entries=load_scenarios(catalog)
    assert [s['path'] for s in entries]==['/guide/ochang-ankle-twist','/conditions/%ED%97%88%EB%A6%AC-%EC%82%90%EB%81%97']
    origin=catalog['config']['target_origin']; titles=set(); descriptions=set()
    sitemap=ET.parse(ROOT/'docs/sitemap.xml'); ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','i':'http://www.google.com/schemas/sitemap-image/1.1'}
    sitemap_nodes={n.find('s:loc',ns).text:n for n in sitemap.findall('s:url',ns)}
    index=resolve_path(catalog['config']['index_path']).read_text()
    for s in entries:
        p=catalog['profiles_by_id'][s['profile_id']]
        html=resolve_path(s['path']).read_text();page=Page(html)
        assert page.h1==[s['h1']]
        assert page.canonical==origin+s['path']
        assert page.meta['description']==s['description'] and 'noindex' not in page.meta.get('robots','')
        title=''.join(page.titles);assert title not in titles and s['description'] not in descriptions
        titles.add(title);descriptions.add(s['description'])
        assert len(page.cards)==6 and [c['url'] for c in page.cards]==['/'+t['path'] for t in p['topics']]
        lists=[n for n in page.schemas if n.get('@type')=='ItemList'];assert len(lists)==1
        assert [i['url'] for i in lists[0]['itemListElement']]==[origin+c['url'] for c in page.cards]
        assert [i['image'] for i in lists[0]['itemListElement']]==[origin+'/'+t['image'] for t in p['topics']]
        assert {'symptom-check','symptom-patterns','questions','sources'}<=page.ids
        assert html.count('type="checkbox"')==3 and html.count('<details>')==3
        assert 'FAQPage' not in html and 'class="clinical-alert"' not in html
        assert all(section['id'] in page.ids for section in s['sections'])
        assert all(faq['answer'] in html for faq in s['faq'])
        assert s['path'] in index and s['path'] in resolve_path(p['hub_path']).read_text()
        assert origin+s['path'] in sitemap_nodes
        assert sitemap_nodes[origin+s['path']].find('s:lastmod',ns).text==s['updated_at']
        assert [n.text for n in sitemap_nodes[origin+s['path']].findall('i:image/i:loc',ns)]==[origin+'/'+t['image'] for t in p['topics']]
        for link in page.links:
            u=urlsplit(link)
            if link.startswith('#'):assert u.fragment in page.ids
            elif link.startswith('/') and not u.netloc:assert resolve_path(link),link
    data=json.loads((ROOT/'src/content/patient-scenarios.json').read_text())
    draft=deepcopy(data);draft['status']='draft';assert validate_scenarios(catalog,draft)==[]
    bad=deepcopy(data);bad['entries'][0]['faq'][0]['answer']=''
    try:validate_scenarios(catalog,bad)
    except ValueError:pass
    else:raise AssertionError('Empty answer accepted')
    search=json.loads((ROOT/'docs/search-index.json').read_text())
    for s in entries:
        assert sum(item['url'].removesuffix('.html')==s['path'] for item in search)==1
    result={'target_pages':len(entries),'new_pages':1,'existing_pages_updated':1,'initial_html_cards':6,'self_canonical_and_sitemap':True,'reciprocal_links':True,'checks_and_faq':True,'draft_not_public':True,'medical_review':'pending','search_exposure':'unverified'}
    (ROOT/'verification/patient-scenarios-20261023.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
