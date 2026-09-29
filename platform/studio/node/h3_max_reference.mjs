#!/usr/bin/env node
// One resumable H3 Max image-to-video request. Credentials stay in root .env.
// node --env-file=.env platform/studio/node/h3_max_reference.mjs submit|status --out REVISION   (npm install in platform/studio/node first)
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
const {values,positionals}=parseArgs({allowPositionals:true,options:{out:{type:'string'},resolution:{type:'string',default:'480p'}}});
const action=positionals[0];
if(!['submit','status'].includes(action)||!values.out)throw Error('Use submit|status --out REVISION');
if(!['480p','768p'].includes(values.resolution))throw Error('H3 Max resolution must be 480p or 768p');
const out=path.resolve(values.out),priv=path.join(out,'api-private'),ledger=path.join(out,'job.json');
await fs.mkdir(priv,{recursive:true,mode:0o700});await fs.chmod(priv,0o700);
await fs.writeFile(path.join(out,'.gitignore'),'api-private/\n*.part\nanalysis-frames/\n');
const key=process.env.AI_GATEWAY_API_KEY?.trim();if(!key)throw Error('Load AI_GATEWAY_API_KEY from root .env');
const {createGateway}=await import('@ai-sdk/gateway');
const gateway=createGateway({apiKey:key}),modelId='minimax/minimax-h3-max',model=gateway.video(modelId);
const sha=b=>createHash('sha256').update(b).digest('hex');const now=()=>new Date().toISOString();
async function read(p){return JSON.parse(await fs.readFile(p,'utf8'));}
async function save(p,obj,privateFile=false){await fs.writeFile(p+'.tmp',JSON.stringify(obj,null,2)+'\n',{mode:privateFile?0o600:0o644});await fs.rename(p+'.tmp',p);}
async function error(e,stage){await save(path.join(priv,stage+'-error.json'),{name:e.name,message:String(e.message).replaceAll(key,'[redacted]'),statusCode:e.statusCode,responseBody:e.responseBody},true);console.error(`${stage}: HTTP ${e.statusCode||'unknown'}; details retained privately. No automatic resubmission.`);}
async function recordCost(job){
 if(job.settled_cost_usd!==undefined)return;
 try{
  const latest=await read(path.join(priv,'latest.json'));
  const id=latest.providerMetadata?.gateway?.generationId;if(!id)return;
  const info=await gateway.getGenerationInfo({id});
  await save(path.join(priv,'generation-info.json'),info,true);
  if(typeof info.totalCost!=='number'||!Number.isFinite(info.totalCost)||info.totalCost<0)return;
  Object.assign(job,{settled_cost_usd:info.totalCost,cost_source:'Vercel Gateway getGenerationInfo.totalCost',cost_checked_at:now()});
  await save(ledger,job);console.log(`Recorded generation cost: $${info.totalCost.toFixed(2)}.`);
 }catch(e){await error(e,'billing-lookup');}
}
async function main(){
 if(action==='submit'){
  try{await fs.access(ledger);throw Error('Submission already recorded; use status.');}catch(e){if(e.code!=='ENOENT')throw e;}
  const credits=await gateway.getCredits();
  await save(path.join(priv,'credits.json'),{...credits,checked_at:now()},true);
  if(!Number.isFinite(Number(credits.balance))||Number(credits.balance)<10)throw Error('Vercel video jobs require at least $10 of available credit. No submission attempted.');
  const input=await fs.readFile(path.join(out,'inputs/starting-frame.png'));const prompt=await fs.readFile(path.join(out,'prompt.txt'),'utf8');
  // Gateway async jobs have a 300 KB persistence limit: pass a scoped HTTPS URL.
  // Keep its token private and verify the unauthenticated response before billing.
  const reference=await read(path.join(priv,'starting-frame-url.json'));
  const inputUrl=new URL(reference.url);
  if(inputUrl.protocol!=='https:'||inputUrl.username||inputUrl.password)throw Error('Expected a hosted HTTPS input');
  const remote=await fetch(inputUrl,{signal:AbortSignal.timeout(60000)});
  if(!remote.ok||sha(Buffer.from(await remote.arrayBuffer()))!==sha(input))throw Error('Hosted input does not match the approved render');
  const catalog=await(await fetch('https://ai-gateway.vercel.sh/v1/models')).json();
  const listed=catalog.data.find(m=>m.id===modelId);if(!listed)throw Error('H3 Max not in current catalog');
  const rate=Number(listed.pricing.video_duration_pricing.find(p=>p.resolution===values.resolution)?.cost_per_second);
  if(!Number.isFinite(rate)||rate>(values.resolution==='480p'?.05:.08))throw Error('Rate above expected H3 Max list price; review before submitting.');
  const settings={model:modelId,n:1,duration:6,resolution:values.resolution,aspectRatio:'1:1'};
  const job={provider:'vercel-ai-gateway',settings,mode:'image-to-video',reference:{file:'inputs/starting-frame.png',sha256:sha(input)},prompt,created_at:now(),status:'submitting',review_status:'not_ready',price_estimate_usd:6*rate,price_per_output_second_usd:rate,price_checked_at:now(),price_source:'https://ai-gateway.vercel.sh/v1/models'};
  await fs.writeFile(ledger,JSON.stringify(job,null,2)+'\n',{flag:'wx'});
  try{
   const result=await model.doStart({...settings,prompt,image:{type:'url',mediaType:'image/png',url:inputUrl.href},providerOptions:{},abortSignal:AbortSignal.timeout(120000)});
   await save(path.join(priv,'operation.json'),result,true);job.status='queued';job.updated_at=now();job.warning_count=result.warnings?.length||0;await save(ledger,job);
   console.log(`H3 Max accepted; estimated output cost $${job.price_estimate_usd.toFixed(2)}. Resume with status.`);
  }catch(e){job.status=e.statusCode&&e.statusCode<500?'rejected':'submission_uncertain';job.http_status=e.statusCode;job.updated_at=now();await save(ledger,job);await error(e,'submit');process.exitCode=1;return;}
 }
 const job=await read(ledger);if(job.settings.model!==modelId)throw Error('Model mismatch');
 if(job.video&&sha(await fs.readFile(path.join(out,job.video)))===job.video_sha256){console.log('Existing video verified.');await recordCost(job);return;}
 const {operation}=await read(path.join(priv,'operation.json'));
 const result=await model.doStatus({operation,abortSignal:AbortSignal.timeout(60000)});await save(path.join(priv,'latest.json'),result,true);
 job.status=result.status==='pending'?'running':result.status==='completed'?'succeeded':'failed';job.updated_at=now();await save(ledger,job);
 if(result.status==='completed'){
  if(result.videos.length!==1)throw Error('Expected one output video');const v=result.videos[0];let bytes;
  if(v.type==='url'){if(new URL(v.url).protocol!=='https:')throw Error('Unexpected output protocol');const r=await fetch(v.url,{signal:AbortSignal.timeout(120000)});if(!r.ok)throw Error('CDN download failed');bytes=Buffer.from(await r.arrayBuffer());}
  else if(v.type==='base64')bytes=Buffer.from(v.data,'base64');else throw Error('Unsupported video data');
  if(bytes.length<1000||bytes.toString('ascii',4,8)!=='ftyp')throw Error('Not an MP4');
  await fs.writeFile(path.join(out,'reference.mp4.part'),bytes);await fs.rename(path.join(out,'reference.mp4.part'),path.join(out,'reference.mp4'));
  Object.assign(job,{video:'reference.mp4',video_sha256:sha(bytes),video_bytes:bytes.length,review_status:'pending',updated_at:now()});await save(ledger,job);
  console.log(`Saved H3 Max video (${bytes.length} bytes).`);
  await recordCost(job);
 }else console.log(`H3 Max: ${job.status}.`);
}
main().catch(async e=>{await error(e,'local');process.exitCode=1;});
