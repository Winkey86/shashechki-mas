import {request,artifact,newRequestId,waitJob} from './api.js';
import {Playback,clock} from './playback.js';
import {CityMap} from './map.js';
import {esc,stateName,orderAt,renderAgent,renderPrice,renderJournal,renderMetrics,renderSeries} from './panels.js';
const $=id=>document.getElementById(id);let catalog=[],player=null,current=null,selected='dispatcher',view='simulation',activeJob=null,lastAction=null,renderKey='';
const map=new CityMap($('map'),id=>selectAgent(id));
function status(text,progress=''){$('job-status').textContent=text;$('job-progress').textContent=progress;}
function fail(error){$('error').hidden=false;$('error-text').textContent=error.message+(error.fields?.length?' · '+error.fields.map(f=>f.path).filter(Boolean).join(', '):'');}
function clearError(){$('error').hidden=true;}
function switchView(name){
 view=['simulation','experiments','reliability','materials'].includes(name)?name:'simulation';for(const element of document.querySelectorAll('.view'))element.hidden=element.id!==view;
 const names={simulation:['Поездка и решения агентов','Водитель, пассажир и диспетчер согласуют условия поездки.','Запустить опыт'],experiments:['Сравнение механизмов','Парные серии на одинаковых заранее сохранённых входах.','Запустить серию'],reliability:['Устойчивость к отказам','Семь воздействий, защитные ограничения и повторная оценка.','Проверить F1–F7'],materials:['Отчёты и приложения','Исходники, измерения и материалы для четырёх лабораторных.','Обновить материалы']};
 const [title,description,action]=names[view];$('page-title').textContent=title;$('page-description').textContent=description;$('run').textContent=action;
 document.querySelectorAll('.nav-item').forEach(button=>button.classList.toggle('active',button.dataset.view===view));$('navigation').classList.remove('open');$('menu').setAttribute('aria-expanded','false');history.replaceState(null,'','#'+view);
 if(view==='experiments')refreshResults().catch(fail);if(view==='materials')refreshMaterials().catch(fail);
}
function scenarioDefaults(){const item=catalog.find(s=>s.id===$('scenario').value&&s.kind==='run');if(!item)return;const cfg=item.config;$('allocation').value=cfg.allocation;$('conflict-policy').value=cfg.conflict_policy;$('rating-policy').value=cfg.rating_policy;$('protection').value=cfg.protection_profile;$('tariff').value='original';$('history').value='original';$('budget').value='';}
function selectAgent(id){selected=id;$('agent-select').value=id;renderKey='';renderPlayback();}
function rebuildAgentSelect(){
 const state=player.state;const options=[['dispatcher','Диспетчер'],...Object.values(state.drivers).map(d=>[d.id,'Водитель '+d.id]),...Object.values(state.passengers).map(p=>[p.id,'Пассажир '+p.id])];
 $('agent-select').innerHTML=options.map(([id,label])=>`<option value="${esc(id)}">${esc(label)}</option>`).join('');$('agent-select').disabled=false;$('agent-select').value=selected;
 const n=options.length;const noun=n%10===1&&n%100!==11?'агент':n%10>=2&&n%10<=4&&(n%100<12||n%100>14)?'агента':'агентов';$('agent-count').textContent=`${n} ${noun}`;
}
function renderPlayback(){
 if(!player)return;const state=player.state;const order=orderAt(state,selected);const event=player.trace[player.index-1];const key=`${player.index}:${selected}:${$('all-messages').checked}`;
 $('main').dataset.eventSeq=String(player.index);$('main').dataset.modelTime=String(player.time);$('clock').value=clock(player.time);$('clock').textContent=clock(player.time);$('timeline').value=String(player.index);$('event-position').textContent=`${player.index} из ${player.trace.length}`;$('play').textContent=player.playing?'Пауза':'Воспроизвести';
 if(key!==renderKey){renderAgent(state,selected);renderPrice(order);renderJournal(player.trace,player.index,$('all-messages').checked);$('event-caption').textContent=event?`${clock(event.time_ms)} · ${event.reason||event.kind}`:'Исходное состояние: решения ещё не приняты.';
  const ids=[...Object.keys(state.drivers),...Object.keys(state.passengers)].slice(0,8);$('participants').innerHTML=ids.map(id=>`<button class="${selected===id?'selected':''}" data-agent-choice="${esc(id)}">${esc(id)}</button>`).join('');renderKey=key;
 }
 map.render(state,player.time,selected,order,player.message(),$('show-messages').checked);
}
async function loadResult(id){
 clearError();player?.destroy();player=null;status('Загрузка сохранённого опыта');const data=await request('/results/'+id);current=data;$('main').dataset.resultId=id;
 if(data.manifest.kind==='series'){switchView('experiments');renderSeries(data);status('Серия загружена',`${data.manifest.complete_pairs} полных пар`);return;}
 const [playback,text,cfg]=await Promise.all([artifact(id,'playback.json'),artifact(id,'trace.jsonl',false),artifact(id,'config.json')]);
 const trace=text.trim()?text.trim().split('\n').map(line=>JSON.parse(line)):[];
 if(trace.some((e,i)=>e.seq!==i+1||!Number.isFinite(e.time_ms)))throw new Error('Трасса повреждена: нарушен порядок событий');
 selected=Object.keys(playback.initial_snapshot.passengers)[0]||Object.keys(playback.initial_snapshot.drivers)[0]||'dispatcher';
 map.cityId=null;player=new Playback(playback,trace,renderPlayback);player.speed=Number($('speed').value);renderKey='';rebuildAgentSelect();
 for(const id of ['play','step','reset','end','timeline','export'])$(id).disabled=false;$('timeline').max=String(trace.length);
 renderMetrics(data);$('scenario').value=data.manifest.scenario_id;if($('scenario').value==='')$('scenario').value='normal';$('allocation').value=cfg.allocation;$('conflict-policy').value=cfg.conflict_policy;$('rating-policy').value=cfg.rating_policy;$('protection').value=cfg.protection_profile;
 const first=trace.findIndex(e=>e.kind==='request_created');const bookmark=new URLSearchParams(location.search);const start=bookmark.get('result')===id&&bookmark.has('seq')?Number(bookmark.get('seq')):Math.max(0,first+1);player.seekIndex(Number.isFinite(start)?start:0);status('Расчёт завершён. Воспроизведение готово.');localStorage.setItem('shashechki-result',id);switchView('simulation');
}
function lockRun(locked){$('run').disabled=locked;$('export').disabled=locked||!current||current.manifest.kind!=='run';$('cancel-job').hidden=!locked;$('cancel-job').disabled=false;for(const element of document.querySelectorAll('.scenario-row input,.scenario-row select'))element.disabled=locked;}
async function operation(body){
 if(activeJob)return;clearError();lockRun(true);player?.pause();let terminal=false;lastAction=()=>operation(body);
 try{
  let job=await request('/jobs',body);activeJob=job;job=await waitJob(job,update=>{activeJob=update;status(update.phase,`${update.completed_runs} / ${update.total_runs} прогонов`);});terminal=true;
  if(job.state==='failed'){lastAction=()=>operation({...body,request_id:newRequestId()});throw new Error(job.error?.message||'Задание завершено с ошибкой');}
  if(job.state==='cancelled'){status('Расчёт отменён. Частичные данные сохранены.');return;}
  if(job.kind==='export'){
   status('Архив подготовлен');const a=document.createElement('a');a.href='/api/v1/exports/'+encodeURIComponent(job.archive.name);a.textContent='Скачать ZIP';a.setAttribute('download',job.archive.name);$('job-progress').replaceChildren(a);
  }else if(job.result_ids.length)await loadResult(job.result_ids[0]);
  await refreshResults();
 }catch(error){fail(error);if(!terminal)status('Запрос не завершён. Повтор использует тот же идентификатор.');}
 finally{activeJob=null;lockRun(false);}
}
function runCurrent(){
 if(view==='materials'){lastAction=refreshMaterials;refreshMaterials().catch(fail);return;}
 const body={schema_version:'1.0',request_id:newRequestId()};
 if(view==='experiments'||view==='reliability')Object.assign(body,{kind:'series',experiment_id:view==='reliability'?'faults':$('experiment').value});
 else{
  const overrides={allocation:$('allocation').value,conflict_policy:$('conflict-policy').value,rating_policy:$('rating-policy').value,protection_profile:$('protection').value};
  if($('tariff').value!=='original')overrides.tariff_id=$('tariff').value;
  if($('budget').value.trim())overrides.budget=$('budget').value.trim().replace(',','.');
  if($('history').value!=='original')overrides.passenger_history_score=Number($('history').value);
  Object.assign(body,{kind:'run',scenario_id:$('scenario').value,overrides});
 }
 operation(body);
}
function exportResult(id){operation({schema_version:'1.0',request_id:newRequestId(),kind:'export',result_id:id,archive_name:id+'-'+crypto.randomUUID().slice(0,6)+'.zip'});}
async function refreshResults(){
 const {results}=await request('/results');$('results-list').innerHTML=results.length?'<div class="results-scroll">'+results.slice(0,30).map(r=>`<div class="result-row"><div><strong>${esc(r.title||r.result_id)}</strong><p>${esc(r.result_id)} · ${r.complete?(r.kind==='series'?`${r.completed_runs} прогонов · ${r.complete_pairs} пар`:esc(r.termination_reason)):'неполная запись'}</p></div>${r.complete?`<button data-result="${esc(r.result_id)}">Открыть</button>`:'<span class="muted">Неполный</span>'}</div>`).join('')+'</div>':'<p class="empty">Серии ещё не выполнены. Выберите исследование и запустите расчёт.</p>';
 return results;
}
async function refreshMaterials(){
 const {materials}=await request('/materials');$('materials-list').innerHTML=materials.length?materials.map(m=>`<article class="material-row"><div><h2>${esc(m.title)}</h2><p>${m.kind==='report'?'Отчёт PDF':'Отдельное приложение ZIP'} · ${(m.bytes/1024/1024).toLocaleString('ru-RU',{maximumFractionDigits:1})} МБ</p></div><a href="${esc(m.url)}" target="_blank" rel="noopener">Открыть ↗</a></article>`).join(''):'<p class="empty">Отчёты появятся после выполнения исследований и подготовки комплекта.</p>';
}
async function init(){
 try{
  const data=await request('/scenarios');catalog=data.scenarios;$('scenario').innerHTML=catalog.filter(x=>x.kind==='run').map(x=>`<option value="${esc(x.id)}">${esc(x.title)}</option>`).join('');$('scenario').value='normal';scenarioDefaults();
  $('experiment').innerHTML=catalog.filter(x=>x.kind==='series').map(x=>`<option value="${esc(x.id)}">${esc(x.title)}</option>`).join('');$('experiment').value='allocation';experimentDescription();
  const notes=['Тайм-аут и переназначение до посадки.','Проверка структуры цены и доступных наблюдений.','Идентификатор, версия и допустимый переход.','Атомарное обязательство и проверка занятости.','Конечные сроки и ограничения действий.','Безопасная остановка и восстановление обслуживания.','Обновление только из проверенных событий.'];
  $('fault-scenarios').innerHTML=catalog.filter(x=>x.kind==='run'&&x.id.startsWith('fault-')).map((x,i)=>`<article class="fault-item"><h2>${esc(x.title)}</h2><p>${notes[i]}</p><button data-fault="${esc(x.id)}">Открыть сценарий</button></article>`).join('');
  const results=await refreshResults();const previous=new URLSearchParams(location.search).get('result')||localStorage.getItem('shashechki-result');if(previous&&results.some(r=>r.result_id===previous&&r.complete))await loadResult(previous);else map.render(null);
  switchView(location.hash.slice(1)||'simulation');
 }catch(error){fail(error);lastAction=init;status('Не удалось загрузить локальные данные');}
}
function experimentDescription(){const e=catalog.find(x=>x.id===$('experiment').value&&x.kind==='series');$('experiment-description').textContent=e?.description||'';}
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>switchView(button.dataset.view)));
$('menu').addEventListener('click',()=>{const open=$('navigation').classList.toggle('open');$('menu').setAttribute('aria-expanded',String(open));});
$('scenario').addEventListener('change',scenarioDefaults);$('experiment').addEventListener('change',experimentDescription);$('run').addEventListener('click',runCurrent);$('retry').addEventListener('click',()=>{clearError();lastAction?.();});
$('cancel-job').addEventListener('click',async()=>{if(!activeJob)return;try{$('cancel-job').disabled=true;const j=await request('/jobs/'+activeJob.job_id+'/cancel',{});status(j.phase);}catch(error){fail(error);$('cancel-job').disabled=false;}});
$('play').addEventListener('click',()=>{if(player)player.playing?player.pause():player.play();});$('step').addEventListener('click',()=>{if(player){player.pause();player.seekIndex(player.index+1);}});$('reset').addEventListener('click',()=>{if(player){player.pause();player.seekIndex(0);}});$('end').addEventListener('click',()=>{if(player){player.pause();player.seekIndex(player.trace.length);}});$('timeline').addEventListener('input',()=>{if(player){player.pause();player.seekIndex(Number($('timeline').value));}});$('speed').addEventListener('change',()=>{if(player)player.speed=Number($('speed').value);});
$('agent-select').addEventListener('change',()=>selectAgent($('agent-select').value));$('participants').addEventListener('click',event=>{const button=event.target.closest('[data-agent-choice]');if(button)selectAgent(button.dataset.agentChoice);});$('show-messages').addEventListener('change',renderPlayback);$('all-messages').addEventListener('change',()=>{renderKey='';renderPlayback();});
$('export').addEventListener('click',()=>{if(current)exportResult(current.manifest.result_id);});$('refresh-results').addEventListener('click',()=>refreshResults().catch(fail));$('results-list').addEventListener('click',event=>{const button=event.target.closest('[data-result]');if(button){lastAction=()=>loadResult(button.dataset.result);loadResult(button.dataset.result).catch(fail);}});$('series-detail').addEventListener('click',event=>{const button=event.target.closest('[data-export]');if(button)exportResult(button.dataset.export);});
$('fault-scenarios').addEventListener('click',event=>{const button=event.target.closest('[data-fault]');if(button){switchView('simulation');$('scenario').value=button.dataset.fault;scenarioDefaults();$('run').focus();}});
window.addEventListener('resize',()=>{map.cityId=null;renderPlayback();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)player?.pause();});
init();
