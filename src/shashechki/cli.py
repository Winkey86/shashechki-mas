"""Командный адаптер к тому же ядру, которое использует веб-интерфейс."""
import argparse,json,sys
from pathlib import Path
from .domain import InputError
from .validation import load,config
from .artifacts import execute,replay_inputs,compare,export_result,canonical
from .experiments import load_experiment,run_series

def output(value):print(canonical(value).decode())
def main(argv=None):
    p=argparse.ArgumentParser(prog='shashechki',description='Локальная многоагентная система такси')
    sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate');g=v.add_mutually_exclusive_group(required=True);g.add_argument('--scenario');g.add_argument('--experiment')
    r=sub.add_parser('run');g=r.add_mutually_exclusive_group(required=True);g.add_argument('--scenario');g.add_argument('--replay-inputs');r.add_argument('--output-root',default='results');r.add_argument('--allocation',choices=['central','auction']);r.add_argument('--protection',choices=['baseline','protected'])
    s=sub.add_parser('series');s.add_argument('--experiment',required=True);s.add_argument('--output-root',default='results')
    s=sub.add_parser('serve');s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8765);s.add_argument('--output-root',default='results')
    e=sub.add_parser('export');e.add_argument('--result',required=True);e.add_argument('--destination',required=True)
    c=sub.add_parser('compare');c.add_argument('--left',required=True);c.add_argument('--right',required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='validate':
            data=load(a.scenario) if a.scenario else load_experiment(a.experiment);output({'valid':True,'schema_version':data['schema_version']})
        elif a.command=='run':
            inputs=replay_inputs(a.replay_inputs) if a.replay_inputs else load(a.scenario)
            if a.allocation:inputs['config']['allocation']=a.allocation
            if a.protection:inputs['config']['protection_profile']=a.protection
            m,path=execute(inputs,a.output_root);output({'result_id':m['result_id'],'path':str(path),'status':m['termination_reason'],'case_id':m['case_id']})
        elif a.command=='series':
            def progress(done,total,ident):print(f'Прогоны: {done}/{total}',file=sys.stderr)
            m,path=run_series(load_experiment(a.experiment),a.output_root,progress=progress);output({'result_id':m['result_id'],'path':str(path),'completed_runs':m['completed_runs'],'complete_pairs':m['complete_pairs']})
        elif a.command=='export':output(export_result(a.result,a.destination))
        elif a.command=='compare':
            result=compare(a.left,a.right);output(result)
            if not result['equal']:return 4
        elif a.command=='serve':
            from .server import LocalServer
            with LocalServer(a.host,a.port,a.output_root) as server:
                output({'url':f'http://127.0.0.1:{server.server_port}','status':'listening'});sys.stdout.flush()
                try:server.serve_forever()
                except KeyboardInterrupt:pass
        return 0
    except InputError as exc:
        print(json.dumps({'code':exc.code,'message':str(exc),'path':exc.path},ensure_ascii=False),file=sys.stderr);return 2
    except (OSError,ValueError) as exc:print('Операция не завершена: '+str(exc),file=sys.stderr);return 3
    except KeyboardInterrupt:return 130
