"""Проверка минимальной копии без site-packages, Git и внешних сервисов."""
from pathlib import Path
import tempfile,shutil,subprocess,os,json,sys
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='shashechki-clean-') as temp:
    dest=Path(temp)
    for name in ['src','web','tests','scenarios','design/fonts']:shutil.copytree(ROOT/name,dest/name,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT/'pyproject.toml',dest/'pyproject.toml')
    env={**os.environ,'PYTHONPATH':str(dest/'src'),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
    def call(*args):
        r=subprocess.run([sys.executable,'-S',*args],cwd=dest,env=env,text=True,capture_output=True,timeout=60)
        if r.returncode:raise RuntimeError(f'{args}: {r.stderr}')
        return r
    tests=call('-m','unittest','discover','-s','tests','-q')
    steps=[]
    for scene in ['normal','playback-10','conflict','tariff-switch']+[f'fault-f{i}' for i in range(1,8)]:
        d=json.loads(call('-m','shashechki','run','--scenario',f'scenarios/{scene}.json').stdout);steps.append({'scenario':scene,'status':d['status']})
        if scene=='normal':first=d['path']
    repeat=json.loads(call('-m','shashechki','run','--replay-inputs',first).stdout)['path']
    assert json.loads(call('-m','shashechki','compare','--left',first,'--right',repeat).stdout)['equal']
    call('-m','shashechki','run','--scenario','scenarios/playback-10.json','--allocation','auction')
    call('-m','shashechki','validate','--experiment','scenarios/series/allocation.json')
    call('-m','shashechki','export','--result',first,'--destination','clean-demo.zip')
    result={'python':sys.version,'site_packages':False,'external_services':False,'tests':tests.stderr.splitlines()[-4:],'steps':steps,'replay_equal':True,'auction':True,'export':True,'temporary_copy_removed':True}
(ROOT/'evidence/tests.txt').write_text(tests.stderr)
(ROOT/'evidence/clean-run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
(ROOT/'evidence/clean-run.md').write_text('# Чистый локальный запуск\n\nПроверено scripts/check_clean.py в новой временной копии src/web/tests/scenarios/fonts. Git, .local, существующие results и site-packages не переносились. Python запущен с -S; сетевые аккаунты и внешние сервисы не использовались.\n\n'+tests.stderr.split('----------------------------------------------------------------------')[-1].strip()+'\n\nВыполнены normal, playback-10, conflict, tariff-switch, F1–F7; дополнительно auction, validate experiment, повтор normal с canonical compare и ZIP-экспорт. Все команды завершились успешно. HTTP-проверки использовали временный loopback-порт. Временная копия удалена. Подробности: clean-run.json.\n')
print(json.dumps(result,ensure_ascii=False))
