"""Maintainer tool. Frozen fixtures are committed; never regenerate during a suite."""
import copy
import json
import hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
T=datetime(2026,10,19,12,0,tzinfo=timezone.utc)
def stamp(hours): return (T+timedelta(hours=hours)).isoformat()
def bundle(cid,i):
    common={'schema_version':'1.0','record_version':1,'event_time':stamp(-1),'ingest_time':stamp(-0.5),'evidence_class':'SYNTHETIC','trusted':True,'quality':'GOOD'}
    rs=[{**common,'domain':'health','asset_id':f'AP-{100+i%12}','component_id':'ENG-A','parameter':'temperature','value':78+i%16,'unit':'C','urgency':i%6,'consequence':1+i%5,'warning_lead_hours':8+i%40},
        {**common,'domain':'technical','asset_id':f'AP-{100+i%12}','component_id':'ENG-A','configuration_id':'CFG-01','alias':'ENGINE-PRIMARY','approved':True,'valid_from':stamp(-240),'valid_to':stamp(240)},
        {**common,'domain':'spares','part_number':'PN-TURB-100','compatible_components':['ENG-A'],'quantity':2,'serviceable':True,'lead_hours':4},
        {**common,'domain':'agency','agency_id':'MRO-CHN','capability':True,'bay_capacity':2,'window_start':stamp(6),'window_end':stamp(30),'approval':True}]
    for n,r in enumerate(rs): r['source_record_key']=f'{cid}-{n}'
    return {'case_id':cid,'title':f'Engine inspection · {rs[0]["asset_id"]}','policy':{'version':'gate-a-v1','rul_required':False,'max_age_hours':24},'records':rs}

def make(name,valid_count,family_count):
    bundles=[]; expected={}
    for i in range(valid_count):
        b=bundle(f'{name[:3].upper()}-VALID-{i+1:03}',i)
        bundles.append(b);expected[b['case_id']]='READY_FOR_HUMAN_REVIEW'
    for family in range(6):
        for i in range(family_count):
            b=bundle(f'{name[:3].upper()}-F{family+1}-{i+1:03}',i+family*20)
            if family==0:
                b['records'][1]['approved']=False
            elif family==1:
                b['records'][2]['event_time']=stamp(-72)
            elif family==2:
                b['records'][0]['schema_version']='unsupported'
            elif family==3:
                b['records'][0]['unit']='UNKNOWN_UNIT'
            elif family==4:
                b['records'].append(copy.deepcopy(b['records'][0]))
            elif family==5:
                b['records'][2]['quantity']=0
            bundles.append(b);expected[b['case_id']]='BLOCK' if family==5 else 'HOLD'
    if name=='development-v1':
        for i,mode in enumerate(('missing_policy','required_rul','unknown_approval','alias_conflict')):
            b=bundle(f'DEV-EDGE-{i+1:03}',i)
            if i==0:b['policy']=None
            if i==1:b['policy']['rul_required']=True
            if i==2:b['records'][3]['approval']=None
            if i==3:
                other=copy.deepcopy(b['records'][1]);other['source_record_key']+='-overlap';b['records'].append(other)
            bundles.append(b);expected[b['case_id']]='HOLD'
    pack={'version':name,'anchor_time':T.isoformat(),'bundles':bundles,'expected':expected}
    path=ROOT/'fixtures'/f'{name}.json'
    path.write_text(json.dumps(pack,indent=2))
    return {'filename':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cases':len(bundles)}
if __name__=='__main__':
    manifest=[make('development-v1',18,3),make('holdout-v1',120,20)]
    (ROOT/'fixtures'/'manifest.json').write_text(json.dumps(manifest,indent=2))
