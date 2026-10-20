import type { components } from './api-types';
export type CaseCard=components['schemas']['CaseCard'];
export type CasePage=components['schemas']['CasePage'];
export type Run=components['schemas']['RunResult'];
export async function api<T>(path:string,body?:unknown,version?:number,key?:string):Promise<T>{
  const response=await fetch('/api/v1'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(body===undefined?{}:{'Idempotency-Key':key??crypto.randomUUID()}),...(version?{'If-Match':String(version)}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw new Error(`${data.error?.code??response.status}: ${data.error?.message??'Request failed'}`);
  return data as T;
}
