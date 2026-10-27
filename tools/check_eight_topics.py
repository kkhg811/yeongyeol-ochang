"""Integration checks for the eight existing series revised on 2026-10-23."""
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from clinical_guides import load_catalog
from check_clinical_guides import Page,resolve_path

IDS=['msk-chuna','msk-knee-osteoarthritis','msk-low-back-pain','msk-lumbar-stenosis','msk-shoulder-impingement','msk-tennis-elbow','msk-hip-pain','msk-pelvic-pain']

def main():
    catalog=load_catalog();origin=catalog['config']['target_origin']
    baseline=json.loads(subprocess.check_output(['git','show','258e2487bd650612626393d516f2a35ef1dfd386:src/content/clinical-catalog.json'],cwd=ROOT,text=True))
    before={p['id']:p for p in baseline['profiles']}
    raw=json.loads((ROOT/'src/content/clinical-catalog.json').read_text())
    later_file=ROOT/'src/content/series-revisions-20261025.json'
    later=set(json.loads(later_file.read_text())['profile_ids']) if later_file.exists() else set()
    newer_file=ROOT/'src/content/series-revisions-fortyfive-20261025.json'
    if newer_file.exists():later.update(json.loads(newer_file.read_text())['profile_ids'])
    extension_file=ROOT/'src/content/series-revisions-women-urology-20261026.json'
    if extension_file.exists():later.update(json.loads(extension_file.read_text())['profile_ids'])
    latest_file=ROOT/'src/content/series-revisions-women-sleep-20261027.json'
    if latest_file.exists():later.update(json.loads(latest_file.read_text())['profile_ids'])
    for p in raw['profiles']:
        if p['id'] not in set(IDS)|later:assert p==before[p['id']],p['id']+' unexpectedly changed'
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','i':'http://www.google.com/schemas/sitemap-image/1.1'}
    tree=ET.parse(ROOT/'docs/sitemap.xml');sitemap={n.find('s:loc',ns).text:n for n in tree.findall('s:url',ns)}
    details=set();titles=set();descriptions=set();count=0
    for pid in IDS:
        p=catalog['profiles_by_id'][pid];old=before[pid]
        assert p['hub_path']==old['hub_path'] and [t['path'] for t in p['topics']]==[t['path'] for t in old['topics']]
        assert p['published_at']==old['published_at'] and p['updated_at']>='2026-10-23'
        assert p['reviewed_by'] is None and p['reviewed_at'] is None
        assert [t['image'] for t in p['topics']]==[t['image'] for t in old['topics']]
        declared={s['url'] for s in p['sources']}
        for topic in [None]+p['topics']:
            owner=topic or p;path=owner['path'] if topic else p['hub_path']
            html=resolve_path(path).read_text();page=Page(html)
            assert len(page.h1)==1 and page.canonical==origin+'/'+path,path
            assert len(page.cards)==6 and [c['url'] for c in page.cards]==['/'+t['path'] for t in p['topics']],path
            lists=[n for n in page.schemas if n.get('@type')=='ItemList'];assert len(lists)==1
            assert [n['url'] for n in lists[0]['itemListElement']]==[origin+'/'+t['path'] for t in p['topics']]
            title=''.join(page.titles);description=page.meta['description']
            assert title not in titles and description not in descriptions,path
            titles.add(title);descriptions.add(description)
            assert html.count('type="checkbox"')==3 and {'symptom-check','symptom-patterns'}<=page.ids
            assert 'class="clinical-alert"' not in html and 'FAQPage' not in html
            for block in owner['reading_sections']:
                assert block['heading'] in html and block['text'] in html,path
                assert set(block['source_urls'])<=declared
            for faq in owner['faq']:
                assert faq['question'] in html and faq['answer'] in html,path
                assert set(faq['source_urls'])<=declared
            if topic:
                body='\n'.join(b['text'] for b in owner['reading_sections'])
                assert body not in details,path
                details.add(body)
            node=sitemap[origin+'/'+path]
            assert node.find('s:lastmod',ns).text==p['updated_at']
            assert [n.text for n in node.findall('i:image/i:loc',ns)]==[origin+'/'+t['image'] for t in p['topics']]
            count+=1
    assert count==56 and len(details)==48
    tennis=next(c for c in raw['conditions'] if c['path']==catalog['profiles_by_id']['msk-tennis-elbow']['hub_path'])
    assert tennis['title']==next(c for c in baseline['conditions'] if c['path']==tennis['path'])['title']
    result=json.loads((ROOT/'verification/eight-topics-20261023.json').read_text())
    result.update({'implementation_checks':'passed','core_pages_checked':count,'distinct_detail_bodies':len(details),'other_profiles_unchanged':not bool(later),'later_authorized_profile_revisions':sorted(later),'preserved_images':48,'source_scopes_checked':'2026-10-23','search_exposure':{'crawled':'unverified','indexed':'unverified','rank_one':'unverified','carousel':'unverified'}})
    (ROOT/'verification/eight-topics-20261023.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
