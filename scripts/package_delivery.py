"""Упаковка по разрешённому списку; исходники и демонстрация отделены от PDF."""
from pathlib import Path
import json,zipfile,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from shashechki.artifacts import read_json,write_json,sha,verify
ROOT=Path(__file__).resolve().parents[1]
def zip_files(destination,entries):
    temp=destination.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for arc,p in sorted(entries.items()):z.write(p,arcname=arc)
    temp.replace(destination)
# Только целые прогоны с неизменённым завершающим манифестом.
selected={};book=read_json(ROOT/'evidence/series-index.json')
for name,b in book.items():
 p=ROOT/b['path'];pairs=read_json(p/'pairs.json');conditions=sorted({x['condition'] for x in pairs})
 for condition in conditions:
  pair=next(x for x in pairs if x['condition']==condition)
  for side in ('a','b'):
   q=p/'runs'/pair[side+'_result_id'];verify(q);selected[q.name]=q
for b in read_json(ROOT/'evidence/controls.json').values():
 p=ROOT/b['path'];verify(p);selected[p.name]=p
entries={}
for ident,path in selected.items():
 for p in path.rglob('*'):
  if p.is_file():entries[str(Path('results')/ident/p.relative_to(path))]=p
for name,b in book.items():
 for p in (ROOT/b['path']/'input_bundles').glob('*.json'):entries[str(Path('evidence/input_bundles')/name/p.name)]=p
manifest={'format':'selected-complete-runs-v1','description':'Full selected runs and all external input bundles. All 260 raw runs remain in the original local results directory.','full_run_count':len(selected),'runs':[{'result_id':i,'canonical_sha256':read_json(p/'manifest.json')['canonical_sha256']} for i,p in sorted(selected.items())],'series_index':'evidence/series-index.json','files':{a:{'sha256':sha(p),'bytes':p.stat().st_size} for a,p in entries.items()}}
write_json(ROOT/'evidence/demo-manifest.json',manifest);entries['evidence/demo-manifest.json']=ROOT/'evidence/demo-manifest.json';zip_files(ROOT/'evidence/demo.zip',entries)
files=[]
for name in ['src','web','tests','scenarios','design/fonts','docs','specs','scripts','.specify','reports','evidence']:
 for p in (ROOT/name).rglob('*'):
  if not p.is_file() or '__pycache__' in p.parts or p.suffix in {'.pyc','.zip','.tmp'}:continue
  if p.parent==ROOT/'reports' and p.suffix=='.pdf':continue
  if p.name in {'source-manifest.json','delivery-hashes.json','archive-check.json'}:continue
  files.append(p)
for name in ['README.md','pyproject.toml','.gitignore','.gitattributes']:files.append(ROOT/name)
source={str(p.relative_to(ROOT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(set(files))}
write_json(ROOT/'evidence/source-manifest.json',{'schema':'source-snapshot-v1','model_version':'1.0.0','files':source,'excluded':['.git','.local','runtime results','skills','report PDFs','ZIP archives','secrets']})
sourceentries={str(p.relative_to(ROOT)):p for p in files};sourceentries['evidence/source-manifest.json']=ROOT/'evidence/source-manifest.json';zip_files(ROOT/'evidence/source.zip',sourceentries)
print(json.dumps({'source_MB':round((ROOT/'evidence/source.zip').stat().st_size/1048576,2),'demo_MB':round((ROOT/'evidence/demo.zip').stat().st_size/1048576,2),'full_demo_runs':len(selected)}))
