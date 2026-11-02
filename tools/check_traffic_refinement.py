"""Verify distinct traffic landing content, useful detail explanations and preservation."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
KMC=(ROOT/'src/content/clinical-catalog.json').exists()
CONTENT=ROOT/('src/content' if KMC else 'content')
def read(p):return json.loads(p.read_text())
def digest(d):return hashlib.sha256(json.dumps(d,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def main():
    catpath=ROOT/('src/content/clinical-catalog.json'if KMC else'app/clinical-catalog.json')
    cat=read(catpath);profiles={p['id']:p for p in cat['profiles']};p=profiles['other-accident-care']
    m=read(CONTENT/'traffic-accident-refinement-20261102.json');old=m['baseline']
    for pid,h in m['preserved_other_profiles'].items():assert digest(profiles[pid])==h,pid
    for key in ['id','members','hub_path','created_at','published_at','keywords']:assert p[key]==old[key],key
    assert p['medical_review_status']=='pending' and not p['reviewed_by'] and not p['reviewed_at']
    bodies=set()
    for before,t in zip(old['topics'],p['topics']):
        for key in ['id','path','image','image_small','image_alt','visual_asset']:assert t[key]==before[key],key
        for path in [t['image'],t['image_small']]:
            rel='docs/'+path if KMC else'public'+path.replace('/media/','/images/')
            previous=subprocess.check_output(['git','show',m['baseline_commit']+':'+rel],cwd=ROOT)
            assert (ROOT/rel).read_bytes()==previous,path
        assert len(t['reading_sections'])==2
        assert [s['heading']for s in t['reading_sections']]!=[s['heading']for s in before['reading_sections']]
        for section in t['reading_sections']:
            assert section['text']not in bodies; bodies.add(section['text'])
            assert set(section['source_urls'])<={s['url']for s in p['sources']}
    assert len(bodies)==12
    if KMC:
        html=(ROOT/'docs/services/accident.html').read_text()
        assert 'id="traffic-care"'in html and'id="traffic-doctors"'in html
        assert 'id="overview-symptoms"'not in html,'Service landing must have its own body'
        assert '"@type": "Service"'in html
        for q in p['service_page']['faq']:assert q['question']in html
        for t in p['topics']:
            html=(ROOT/'docs'/(t['path']+'.html')).read_text()
            for b in t['reading_sections']:assert b['text']in html,b['heading']
            assert '/services/accident'in html
        hub=(ROOT/'docs'/(p['hub_path']+'.html')).read_text()
        assert 'id="overview-symptoms"'in hub and'"@type": "Service"'not in hub
    result={'status':'passed','profile':'other-accident-care','other_profiles_preserved':len(profiles)-1,'detail_explanations':12,'old_core_urls_preserved':7,'existing_cover_files_preserved':12,'medical_review':'pending','search_rank':'unverified'}
    out=ROOT/'verification/traffic-refinement-20261102.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
