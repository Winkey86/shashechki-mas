const NS='http://www.w3.org/2000/svg';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let xStep=170,xOffset=60,dispatchX=646;
const sx=x=>xOffset+x*xStep,sy=y=>45+y*60;
export function position(driver,time,nodes,edges){
 const movement=driver.movement;
 if(!movement)return driver.position||nodes.get(driver.node)||{x:0,y:0};
 let elapsed=Math.max(0,Math.min(time-movement.from_ms,movement.to_ms-movement.from_ms));
 for(const id of movement.route.edge_ids){const edge=edges.get(id);if(!edge)continue;
  if(elapsed<=edge.travel_ms){const a=nodes.get(edge.from),b=nodes.get(edge.to),f=elapsed/edge.travel_ms;return{x:a.x+(b.x-a.x)*f,y:a.y+(b.y-a.y)*f};}elapsed-=edge.travel_ms;
 }
 return nodes.get(movement.route.destination);
}
function routePath(route,nodes,edges){if(!route?.edge_ids?.length)return '';const first=nodes.get(route.origin);return `M${sx(first.x)},${sy(first.y)} `+route.edge_ids.map(id=>{const n=nodes.get(edges.get(id).to);return `L${sx(n.x)},${sy(n.y)}`;}).join(' ');}
export class CityMap{
 constructor(element,onSelect){this.element=element;this.onSelect=onSelect;this.cityId=null;this.nodes=new Map();this.edges=new Map();
  element.addEventListener('click',event=>{const item=event.target.closest('[data-agent]');if(item)onSelect(item.dataset.agent);});
  element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){const item=event.target.closest('[data-agent]');if(item){event.preventDefault();onSelect(item.dataset.agent);}}});
 }
 base(city){
  this.nodes=new Map(city.nodes.map(n=>[n.id,n]));this.edges=new Map(city.edges.map(e=>[e.id,e]));const mobile=innerWidth<=540;xStep=mobile?85:170;xOffset=mobile?40:60;dispatchX=mobile?312:646;this.cityId=city.id+':'+city.edges.length+':'+mobile;
  let blocks='';for(let x=0;x<4;x++)for(let y=0;y<4;y++){
   const px=sx(x)+(mobile?12:20),py=sy(y)+14,park=(x===1&&y===1)||(x===3&&y===2);
   blocks+=`<rect x="${px}" y="${py}" width="${mobile?61:130}" height="32" rx="6" fill="${park?'#e3ebe3':'#e7ebea'}"/>`;
   if(park){for(let i=0;i<(mobile?2:4);i++)blocks+=`<circle cx="${px+15+i*(mobile?29:31)}" cy="${py+16}" r="7" fill="#c1d1c3"/>`;}
   else blocks+=`<rect x="${px+8}" y="${py+7}" width="${mobile?17:43}" height="18" fill="#d7dedd"/><rect x="${px+(mobile?34:72)}" y="${py+7}" width="${mobile?17:43}" height="18" fill="#d7dedd"/>`;
  }
  const unique=new Set();let roads='';for(const edge of city.edges){const key=[edge.from,edge.to].sort().join(':');if(unique.has(key))continue;unique.add(key);const a=this.nodes.get(edge.from),b=this.nodes.get(edge.to);roads+=`<path d="M${sx(a.x)} ${sy(a.y)}L${sx(b.x)} ${sy(b.y)}" fill="none" stroke="#fff" stroke-width="23" stroke-linecap="round"/>`;}
  this.element.innerHTML=`<svg viewBox="0 0 ${mobile?430:800} 330" role="group" aria-label="Условный дорожный граф и участники поездки"><defs><marker id="message-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0L7,3.5L0,7" fill="#2f70bb"/></marker></defs><g>${blocks}${roads}</g><text x="79" y="23" class="road-label">Северная улица</text><text x="79" y="321" class="road-label">Южная улица</text><text x="${sx(1)+26}" y="140" class="road-label">Парк</text><g id="route-layer"></g><g id="message-layer"></g><g id="actor-layer"></g><g data-agent="dispatcher" class="map-pin" tabindex="0" role="button" aria-label="Выбрать диспетчера"><circle class="selection-ring" cx="${dispatchX}" cy="25" r="17"/><rect x="${dispatchX-10}" y="15" width="20" height="20" rx="4" fill="#fff" stroke="#657277"/><path d="M${dispatchX-5} 20h4v4h-4zm5 5h4v4h-4z" fill="#657277"/><text x="${dispatchX+20}" y="30" class="road-label">Диспетчер</text></g></svg>`;
 }
 render(state,time,selected,order,message,showMessages){
  if(!state?.city){this.element.innerHTML='<div class="map-empty">Карта появится после запуска опыта.</div>';return;}
  if(this.cityId!==state.city.id+':'+state.city.edges.length+':'+(innerWidth<=540))this.base(state.city);
  const positions=new Map();let actors='',paths='';const clusters=new Map();
  for(const d of Object.values(state.drivers)){
   const p=position(d,time,this.nodes,this.edges);positions.set(d.id,{x:sx(p.x),y:sy(p.y)});const key=`${Math.round(p.x*100)}:${Math.round(p.y*100)}`;if(!clusters.has(key))clusters.set(key,[]);clusters.get(key).push(d.id);
  }
  for(const d of Object.values(state.drivers)){
   const p=positions.get(d.id);let dx=0;for(const ids of clusters.values())if(ids.includes(d.id)){dx=(ids.indexOf(d.id)-(ids.length-1)/2)*30;break;}
   const color=d.state==='offline'?'#bac3c6':'#eac044';
   if(d.movement){const path=routePath(d.movement.route,this.nodes,this.edges);paths+=`<path d="${path}" fill="none" stroke="${selected===d.id?'#956500':'#8b9b9e'}" stroke-width="${selected===d.id?4:2}" opacity=".85"/>`;}
   actors+=`<g data-agent="${esc(d.id)}" class="map-pin ${selected===d.id?'selected':''}" tabindex="0" role="button" aria-label="Выбрать водителя ${esc(d.id)}" transform="translate(${p.x+dx} ${p.y})"><circle class="selection-ring" r="26"/><rect x="-14" y="-9" width="28" height="18" rx="5" fill="${color}" stroke="#6e5d2c"/><path d="M-7 -6h13l3 4H-10z M-7 6h13l3-4H-10z" fill="#52626b"/><path d="M-5 -2h4v4h-4zm5-0h4v4H0z" fill="#fff"/><path d="M-1 -2h3v4h-3" fill="#243136"/><path d="M-10 -11h6M5 -11h5M-10 11h6M5 11h5" stroke="#243136" stroke-width="3"/><text class="vehicle-label" x="0" y="-19" text-anchor="middle">${esc(d.id)}</text></g>`;
  }
  const relevant=Object.values(state.orders).filter(o=>!['created'].includes(o.state));
  const selectedPerson=selected in state.passengers?selected:null;
  const visible=relevant.filter(o=>o.passenger_id===selectedPerson||o.id===order?.id||!['completed','cancelled','expired','failed'].includes(o.state)).slice(-8);
  for(const o of visible){let node=this.nodes.get(o.state==='completed'?o.destination:o.origin);if(!node)continue;let p={x:sx(node.x),y:sy(node.y)};
   const person=state.passengers[o.passenger_id];if(person?.knowledge?.driver_id&&['in_trip','failed'].includes(o.state)){const vehicle=positions.get(person.knowledge.driver_id);if(vehicle)p={x:vehicle.x+22,y:vehicle.y};}
   positions.set(o.passenger_id,p);actors+=`<g data-agent="${esc(o.passenger_id)}" class="map-pin ${selected===o.passenger_id?'selected':''}" tabindex="0" role="button" aria-label="Выбрать пассажира ${esc(o.passenger_id)}" transform="translate(${p.x+9} ${p.y+14})"><circle class="selection-ring" r="23"/><circle cy="-6" r="5" fill="#273a42"/><path d="M-8 8q0-11 8-11t8 11" fill="#273a42"/><text x="${node.x>=3?-14:14}" y="17" text-anchor="${node.x>=3?'end':'start'}" class="vehicle-label">${esc(o.passenger_id)}</text></g>`;
  }
  positions.set('dispatcher',{x:dispatchX,y:25});let link='';
  if(message&&showMessages){const a=positions.get(message.sender),b=positions.get(message.recipient);if(a&&b){link=`<path d="M${a.x} ${a.y}L${b.x} ${b.y}" fill="none" stroke="#2f70bb" stroke-width="1.6" stroke-dasharray="5 5" marker-end="url(#message-arrow)"/><text x="${(a.x+b.x)/2}" y="${(a.y+b.y)/2-7}" text-anchor="middle" class="road-label" fill="#2f70bb">${esc(message.kind)}</text>`;}}
  this.element.querySelector('#route-layer').innerHTML=paths;this.element.querySelector('#actor-layer').innerHTML=actors;this.element.querySelector('#message-layer').innerHTML=link;
 }
}
