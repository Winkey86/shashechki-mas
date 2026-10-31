export async function request(path,body){
 const response=await fetch('/api/v1'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json();
 if(!response.ok){const error=new Error(data.error?.message||'Не удалось выполнить запрос');error.code=data.error?.code;error.fields=data.error?.field_errors||[];throw error;}
 return data;
}
export async function artifact(resultId,name,json=true){
 const response=await fetch(`/api/v1/results/${encodeURIComponent(resultId)}/artifacts/${name}`);
 if(!response.ok)throw new Error('Не удалось загрузить артефакт '+name);
 return json?response.json():response.text();
}
export function newRequestId(){return 'ui-'+crypto.randomUUID();}
export async function waitJob(job,onProgress){
 while(true){onProgress(job);if(['succeeded','failed','cancelled'].includes(job.state))return job;
  await new Promise(resolve=>setTimeout(resolve,500));job=await request('/jobs/'+job.job_id);
 }
}
