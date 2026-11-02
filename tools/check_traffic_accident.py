"""Protect existing source/URLs while verifying the focused traffic-accident revision."""
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
KMC=(ROOT/'src/content/clinical-catalog.json').exists()
CONTENT=ROOT/('src/content' if KMC else 'content')
CAT=ROOT/('src/content/clinical-catalog.json' if KMC else 'app/clinical-catalog.json')
PID='other-accident-care'
def read(p):return json.loads(p.read_text())
def digest(o):return hashlib.sha256(json.dumps(o,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def main():
    m=read(CONTENT/'series-revisions-traffic-accident-20261102.json')
    cat=read(CAT);profiles={p['id']:p for p in cat['profiles']};p=profiles[PID];old=m['target_baseline']
    assert m['profile_ids']==[PID]
    assert len(profiles)==(189 if KMC else 191)
    for pid,h in m['preserved_profile_sha256'].items():assert digest(profiles[pid])==h,pid
    assert digest({k:[{f:e[f] for f in ['path','canonical_path','profile_id','relationship','slug'] if f in e} for e in cat.get(k,[])]for k in ['conditions','columns']})==m['mapping_sha256'],'Legacy mappings changed'
    assert digest(read(CONTENT/'priority80.json'))==m['preserved_priority80_sha256']
    extra=read(CONTENT/'additional-clinical-assessments.json');assessments={a['id']:a for a in extra['profiles']}
    assert len(assessments)==len(extra['profiles'])==21
    for pid,h in m['preserved_additional_assessments'].items():assert digest(assessments[pid])==h,pid
    a=assessments[PID]
    assert len(a['checks'])==3 and len(a['branches'])==len(a['faq'])==2
    assert all(b['related_id'] in profiles for b in a['branches'])
    for key in ['hub_path','created_at','published_at','members','keywords']:assert p[key]==old[key],key
    assert p['updated_at']==m['updated_at']=='2026-11-02'
    assert p['medical_review_status']=='pending' and p['reviewed_by'] is None and p['reviewed_at'] is None
    assert len(p['faq'])>=4 and len(p['reading_sections'])>=2
    assert p['image_notice'].startswith('설명용 생성 이미지')
    evidence={s['url'] for s in p['sources']}|{s['url'] for s in a['evidence']}
    images=read(CONTENT/'traffic-accident-image-provenance-20261102.json')
    by_topic={i['id']:i for i in images['assets']}
    assert len(by_topic)==6
    titles=set();descriptions=set();image_shas=set()
    for i,t in enumerate(p['topics']):
        assert t['path']==old['topics'][i]['path'] and t['id']==old['topics'][i]['id']
        assert len(t['reading_sections'])>=1 and len(t['faq'])>=2 and len(t['diagram'])==3
        assert t['page_metadata']['title'] not in titles and t['page_metadata']['description'] not in descriptions
        titles.add(t['page_metadata']['title']);descriptions.add(t['page_metadata']['description'])
        assert t['image_updated_at']==m['updated_at'] and '-cover-20261102' in t['image']
        asset=by_topic[t['id']]
        for pathkey,hashkey,size in [('path','sha256',1080),('thumbnail_path','thumbnail_sha256',480)]:
            f=ROOT/asset[pathkey];body=f.read_bytes()
            assert hashlib.sha256(body).hexdigest()==asset[hashkey] and 0<len(body)<250000
            with Image.open(f) as im:assert im.format=='WEBP' and im.size==(size,size)
        assert asset['sha256'] not in image_shas;image_shas.add(asset['sha256'])
        for key in ['image','image_small']:
            prev=old['topics'][i][key]
            rel='docs/'+prev if KMC else 'public'+prev.replace('/media/','/images/')
            before=subprocess.check_output(['git','show',m['baseline_commit']+':'+rel],cwd=ROOT)
            assert (ROOT/rel).read_bytes()==before,'Old image URL bytes must remain available'
    for owner in [p]+p['topics']:
        for b in owner['reading_sections']+owner['faq']:
            assert set(b['source_urls'])<=evidence and b['source_urls']
    if KMC:
        assert len({t['h1'] for t in p['topics']}) == 6, 'Detail H1s must identify their topic'
        from html.parser import HTMLParser
        paths=[p['hub_path']]+[t['path'] for t in p['topics']]+['services/accident']
        for path in paths:
            html=(ROOT/'docs'/(path+'.html')).read_text()
            assert html.count('<h1>')==1 and '<ol class="clinical-cards">' in html
            assert 'clinical-alert' not in html and 'FAQPage' not in html and '작성·검토' not in html
            assert 'symptom-check' in html and 'symptom-patterns' in html and '설명용 생성 이미지' in html
            assert f'rel="canonical" href="https://www.yeongyeolochangkmc.co.kr/{path}"' in html
            for t in p['topics']:assert f'href="/{t["path"]}"' in html
        service=(ROOT/'docs/services/accident.html').read_text()
        assert '<h1>오창 교통사고 한의원</h1>' in service
        assert '본인부담금 없이' not in service and '부민빌딩 3층' in service
    report={'status':'passed','profile_ids':[PID],'unchanged_other_profiles':len(profiles)-1,
            'old_core_urls_preserved':7,'generated_covers':6,'optimized_renditions':12,'old_image_urls_preserved':12,
            'original_priority80_unchanged':True,'prior_extra_assessments_unchanged':20,'legacy_mappings_unchanged':True,
            'source_status':'Primary sources checked; clinical review pending','search_exposure':m['search_exposure']}
    (ROOT/'verification').mkdir(exist_ok=True)
    (ROOT/'verification/traffic-accident-20261102.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
