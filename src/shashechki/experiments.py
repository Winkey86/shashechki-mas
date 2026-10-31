"""Материализация общих входов до вариантов и парное сравнение."""
from pathlib import Path
from copy import deepcopy
from random import Random
from statistics import mean,stdev
from fractions import Fraction
from decimal import Decimal,localcontext,ROUND_HALF_UP
from .pricing import rounded,rubles
import hashlib,sys
from .validation import load,validate,fields,require,integer,identifier,config
from .artifacts import read_json,write_json,reserve,execute,digest,file_manifest,write_csv,canonical
from .domain import SCHEMA_VERSION,MODEL_VERSION

ROOT=Path(__file__).resolve().parents[2]
def stream(seed,label):return Random(int.from_bytes(hashlib.sha256(f'{seed}:{label}'.encode()).digest(),'big'))
def load_experiment(path):
    e=read_json(path);fields(e,('schema_version','experiment_id','kind','seeds','conditions','order_count','driver_count','variants'),('title',))
    require(e['schema_version']==SCHEMA_VERSION,'Неподдерживаемая схема','schema_version');identifier(e['experiment_id'],'experiment_id')
    require(e['kind'] in {'allocation','negotiation','rating','faults','dynamic-reputation'},'Неизвестное исследование','kind')
    require(isinstance(e['seeds'],list) and 1<=len(e['seeds'])<=100 and all(type(x) is int for x in e['seeds']) and len(set(e['seeds']))==len(e['seeds']),'Неверные seeds','seeds')
    for seed in e['seeds']:integer(seed,'seed')
    integer(e['order_count'],'order_count',1);integer(e['driver_count'],'driver_count',1)
    require(e['order_count']<=1000 and e['driver_count']<=100,'Превышен объём исследования')
    if e['kind'] not in ('allocation','faults'):require(e['driver_count']>=2 and e['driver_count']%2==0,'Для конфликтов нужно чётное число водителей ≥2','driver_count')
    allowed={'normal','high_load','scarcity','delays'} if e['kind']=='allocation' else ({f'F{i}' for i in range(1,8)} if e['kind']=='faults' else {'controlled'})
    require(bool(e['conditions']) and set(e['conditions'])<=allowed,'Неизвестное условие','conditions')
    require(len(e['variants'])==2,'Для парного сравнения нужны два варианта','variants')
    for v in e['variants']:fields(v,('id','overrides'));identifier(v['id'],'variant.id');config(v['overrides'])
    require(e['variants'][0]['id']!=e['variants'][1]['id'],'Варианты должны различаться')
    expected={'allocation':'allocation','negotiation':'conflict_policy','rating':'rating_policy','faults':'protection_profile','dynamic-reputation':'rating_policy'}[e['kind']]
    a,b=[config(v['overrides']) for v in e['variants']]
    require([k for k in a if a[k]!=b[k]]==[expected],'В паре должен изменяться ровно исследуемый фактор','variants')
    return e

def history(value,who):
    return [{'id':f'H-{who}-{i}','value':value,'cause':'fixture','commitment_id':f'past-{i}','source_event_id':f'past-{i}','origin':'fixture'} for i in range(10)]

def materialize(e,seed,condition):
    ch=stream(seed,'characteristics');orders_rng=stream(seed,'orders');comm=stream(seed,'communication')
    if e['kind']=='faults':
        s=load(ROOT/'scenarios'/f'fault-f{condition[1:]}.json')
        for d in s['drivers']:d['markup']=f'{ch.randrange(0,5)*5}.00'
        s['passengers'][0]['budget']=f'{ch.randrange(350,651)}.00'
        s['channel_profile'][0]['delay_ms']=comm.randrange(10,151)
    else:
        base=load(ROOT/'scenarios'/'playback-10.json');s=deepcopy(base);s['scenario_id']=e['experiment_id']+'-'+condition+'-'+str(seed);s['title']=e.get('title',e['experiment_id'])+' · '+condition
        for edge in s['city']['edges']:edge['travel_ms']=120000
        template_d=base['drivers'][0];template_p=base['passengers'][0];s['drivers']=[];s['passengers']=[];s['orders']=[]
        nodes=[n['id'] for n in s['city']['nodes']]
        conflict=e['kind']!='allocation'
        for i in range(e['driver_count']):
            d=deepcopy(template_d);d.update(id=f'D{i:02}',start_node='N00' if conflict else ch.choice(nodes),vehicle_class='comfort' if conflict or i>=e['driver_count']//2 else 'economy',markup=f'{ch.randrange(0,5)*5 if conflict else (i%3)*10}.00')
            d['rating_history']=history(5,d['id'])
            if condition=='scarcity' and i<8:d['unavailable_until_ms']=1800000
            s['drivers'].append(d)
        time_ms=0
        for i in range(e['order_count']):
            who=f'P{i:03}';p=deepcopy(template_p);p.update(id=who,budget=f'{ch.randrange(300,901)}.00');p['rating_history']=history((3,4,5)[i%3],who)
            if conflict:p['budget']='250.00' if i%3==0 else '500.00'
            origin='N00' if conflict else orders_rng.choice(nodes);destination='N01' if conflict else orders_rng.choice([n for n in nodes if n!=origin])
            o={'id':f'O{i:03}','passenger_id':who,'created_at_ms':time_ms,'origin':origin,'destination':destination,'tariff_id':'economy'}
            if conflict:
                pair=(i%max(1,e['driver_count']//2))*2;o['candidate_ids']=[f'D{pair:02}',f'D{pair+1:02}']
                if e['kind']=='negotiation' and i%5==0:o['tariff_id']='comfort';p['budget']='270.00'
                time_ms+=300000+orders_rng.randrange(-5000,5001)
            else:time_ms+=orders_rng.randrange(5000,15001) if condition=='high_load' else orders_rng.randrange(15000,45001)
            s['passengers'].append(p);s['orders'].append(o)
        s['faults']=[]
        if conflict:s['channel_profile'][0]['delay_ms']=comm.randrange(25,101)
        s['config'].update(conflict_policy='negotiation' if conflict else 'first_acceptable',rating_policy='fixed' if e['kind']=='negotiation' else 'off')
        if condition=='delays':
            s['channel_profile']=[]
            for channel in ('driver:dispatcher','dispatcher:driver','passenger:dispatcher','dispatcher:passenger'):
                for t in range(0,time_ms+1800000,1000):s['channel_profile'].append({'channel':channel,'from_ms':t,'to_ms':t+1000,'delay_ms':comm.randrange(500,2501),'drop':False,'duplicate_count':0,'duplicate_offset_ms':1})
    s['provenance']={'seed':seed,'generator_version':'1.0','python_version':sys.version.split()[0],'condition':condition,'experiment':e['kind']}
    return validate(s)

def pair_summary(pairs):
    groups={}
    for pair in pairs:
        if pair['complete']:groups.setdefault(pair['condition'],[]).append(pair)
    summary={}
    for condition,items in groups.items():
        metrics={}
        keys=items[0]['a_metrics'].keys()
        for key in keys:
            a=[];b=[];delta=[]
            unit=items[0]['a_metrics'][key]['unit'];parse=Fraction if unit=='RUB' else float
            for p in items:
                av,bv=p['a_metrics'][key]['value'],p['b_metrics'][key]['value']
                if av is not None:a.append(parse(av))
                if bv is not None:b.append(parse(bv))
                if av is not None and bv is not None:delta.append(parse(bv)-parse(av))
            def avg(values):
                if not values:return None
                q=sum(values)/len(values)
                return rubles(rounded(q*100)) if unit=='RUB' else q
            if len(delta)>1 and unit=='RUB':
                center=sum(delta)/len(delta);variance=sum((x-center)**2 for x in delta)/(len(delta)-1)
                with localcontext() as context:
                    context.prec=40;sd=str((Decimal(variance.numerator)/Decimal(variance.denominator)).sqrt().quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
            else:sd=stdev(delta) if len(delta)>1 else None
            metrics[key]={'a_mean':avg(a),'b_mean':avg(b),'delta_mean':avg(delta),'delta_sd':sd,'n':len(delta),'n_a':len(a),'n_b':len(b),'unit':unit,'reason':None if delta else 'NO_COMPLETE_OBSERVATIONS'}
        summary[condition]=metrics
    return summary

def run_series(e,root,cancel=None,progress=None):
    ident,path=reserve(root,'series');(path/'input_bundles').mkdir();(path/'runs').mkdir();write_json(path/'experiment.json',e)
    pairs=[];completed=0;total=len(e['conditions'])*len(e['seeds'])*2
    stopped=False
    # Сначала материализуются ВСЕ внешние входы, затем запускаются варианты.
    for condition in e['conditions']:
        for seed in e['seeds']:
            if cancel and cancel():stopped=True;break
            write_json(path/'input_bundles'/f'{condition}-{seed}.json',materialize(e,seed,condition))
        if stopped:break
    if not stopped:
        for condition in e['conditions']:
            for seed in e['seeds']:
                inputs=read_json(path/'input_bundles'/f'{condition}-{seed}.json');results=[]
                for v in e['variants']:
                    if cancel and cancel():stopped=True;break
                    variant=deepcopy(inputs);merged=deepcopy(variant['config'])
                    for k,value in v['overrides'].items():merged[k]=value
                    variant['config']=merged
                    manifest,runpath=execute(variant,path/'runs',cancel)
                    results.append((manifest,read_json(runpath/'metrics.json'),read_json(runpath/'faults.json')))
                    completed+=1
                    if progress:progress(completed,total,manifest['result_id'])
                if len(results)==2:
                    a,b=results;paired=a[0]['input_hash']==b[0]['input_hash'] and a[0]['complete'] and b[0]['complete'] and all(f['status']=='activated' for item in results for f in item[2])
                    pairs.append({'condition':condition,'seed':seed,'input_hash':a[0]['input_hash'],'a_result_id':a[0]['result_id'],'b_result_id':b[0]['result_id'],'a_metrics':a[1],'b_metrics':b[1],'complete':paired,'reason':None if paired else 'INCOMPLETE_OR_NOT_TRIGGERED'})
                if stopped:break
            if stopped:break
    summary=pair_summary(pairs);write_json(path/'pairs.json',pairs);write_json(path/'summary.json',summary)
    write_csv(path/'pairs.csv',[{k:v for k,v in p.items() if k not in {'a_metrics','b_metrics'}} for p in pairs])
    m={'schema_version':SCHEMA_VERSION,'model_version':MODEL_VERSION,'kind':'series','result_id':ident,'experiment_id':e['experiment_id'],'title':e.get('title',e['experiment_id']),'complete':not stopped,'termination_reason':'cancelled' if stopped else 'completed','completed_runs':completed,'total_runs':total,'complete_pairs':sum(p['complete'] for p in pairs),'input_hashes':[p['input_hash'] for p in pairs],'variants':[v['id'] for v in e['variants']],'files':file_manifest(path)}
    write_json(path/'manifest.json',m);return m,path
