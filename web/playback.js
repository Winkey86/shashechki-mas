// Воспроизведение присваиваний: решения, тарифы и репутация здесь не рассчитываются.
export class Playback{
 constructor(data,trace,onChange){
  if(data.schema_version!=='1.0')throw new Error('Версия просмотра не поддерживается');
  this.data=data;this.trace=trace;this.onChange=onChange;this.index=0;this.changeIndex=0;this.state=structuredClone(data.initial_snapshot);this.time=0;this.speed=60;this.playing=false;this.lastFrame=null;this.frame=null;
  this.messageById=new Map();this.prefixMessages=[0];this.previousMessage=[null];
  for(const event of trace){const message=event.details?.message;if(message)this.messageById.set(message.id,message);this.prefixMessages.push(this.prefixMessages.at(-1)+(event.kind==='message_sent'?1:0));this.previousMessage.push(message||this.previousMessage.at(-1));}
  this.lastSeq=0;
 }
 apply(change){for(const [key,items]of Object.entries(change.assignments)){if(['drivers','passengers','orders','dispatcher_telemetry'].includes(key))Object.assign(this.state[key],structuredClone(items));else this.state[key]=structuredClone(items);}}
 seekIndex(index,notify=true){
  index=Math.max(0,Math.min(this.trace.length,Math.round(index)));const seq=index?this.trace[index-1].seq:0;
  if(seq<this.lastSeq||index===0){
   const checkpoint=this.data.checkpoints.filter(item=>item.seq<=seq).at(-1);
   this.state=structuredClone(checkpoint?.state||this.data.initial_snapshot);this.changeIndex=checkpoint?.change_index||0;
  }
  while(this.changeIndex<this.data.changes.length&&this.data.changes[this.changeIndex].seq<=seq)this.apply(this.data.changes[this.changeIndex++]);
  this.index=index;this.lastSeq=seq;this.time=index?this.trace[index-1].time_ms:0;
  if(notify)this.onChange(this);
 }
 seekTime(time){let lo=0,hi=this.trace.length;while(lo<hi){const mid=(lo+hi)>>1;if(this.trace[mid].time_ms<=time)lo=mid+1;else hi=mid;}this.seekIndex(lo,false);this.time=time;this.onChange(this);}
 pause(){this.playing=false;this.lastFrame=null;if(this.frame!==null)cancelAnimationFrame(this.frame);this.frame=null;this.onChange(this);}
 play(){if(this.index>=this.trace.length)this.seekIndex(0,false);this.playing=true;this.lastFrame=null;this.frame=requestAnimationFrame(t=>this.tick(t));this.onChange(this);}
 tick(stamp){if(!this.playing)return;const delta=this.lastFrame===null?0:Math.min(100,stamp-this.lastFrame);this.lastFrame=stamp;
  const end=this.trace.at(-1)?.time_ms||0;const next=Math.min(end,this.time+delta*this.speed);this.seekTime(next);
  if(next>=end){this.pause();return;}this.frame=requestAnimationFrame(t=>this.tick(t));
 }
 message(){const event=this.trace[this.index-1];return event?.details?.message||(event?.details?.message_id?this.messageById.get(event.details.message_id):this.previousMessage[this.index]);}
 destroy(){this.playing=false;if(this.frame!==null)cancelAnimationFrame(this.frame);}
}
export function clock(ms){const total=Math.max(0,Math.floor(ms));return `${String(Math.floor(total/60000)).padStart(2,'0')}:${String(Math.floor(total/1000)%60).padStart(2,'0')}.${String(total%1000).padStart(3,'0')}`;}
