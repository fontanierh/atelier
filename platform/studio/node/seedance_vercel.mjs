#!/usr/bin/env node
// Resumable Seedance 2.5 generation via the official Vercel Gateway SDK.
// Install once: (cd platform/studio/node && npm install)
// submit --out REVISION (prompt.txt, inputs/, api-private/reference-urls.json)
// status --out REVISION [--watch]. Never automatically resubmits a paid request.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { parseArgs } from 'node:util';

const { values, positionals } = parseArgs({allowPositionals:true, options:{
  out:{type:'string'}, watch:{type:'boolean', default:false},
}});
const action = positionals[0];
if (!['submit','status'].includes(action) || !values.out) {
  throw new Error('Usage: seedance_vercel.mjs submit|status --out REVISION [--watch]');
}
const out = path.resolve(values.out), privateDir = path.join(out,'api-private');
await fs.mkdir(privateDir,{recursive:true,mode:0o700});
await fs.chmod(privateDir,0o700);
await fs.writeFile(path.join(out,'.gitignore'),'api-private/\n*.part\nanalysis-frames/\n');
const ledger = path.join(out,'job.json');
const modelId = 'bytedance/seedance-2.5';
const now = () => new Date().toISOString();
const sha = data => createHash('sha256').update(data).digest('hex');
const read = async file => JSON.parse(await fs.readFile(file,'utf8'));
async function save(file,data,privateFile=false) {
  const temporary=file+'.tmp';
  await fs.writeFile(temporary,JSON.stringify(data,null,2)+'\n',{mode:privateFile?0o600:0o644});
  if(privateFile) await fs.chmod(temporary,0o600);
  await fs.rename(temporary,file);
}
const key = (process.env.AI_GATEWAY_API_KEY || '').trim(); if (!key) throw new Error('Load AI_GATEWAY_API_KEY from the root .env (node --env-file=.env ...)');
const {createGateway} = await import('@ai-sdk/gateway');
const gateway=createGateway({apiKey:key}),model=gateway.video(modelId);
// Error responses may contain signed URLs. Persist details privately only.
async function recordError(error,stage) {
  await save(path.join(privateDir,stage+'-error.json'),{
    name:error.name,message:String(error.message).replaceAll(key,'[redacted]'),
    statusCode:error.statusCode,responseBody:error.responseBody,
  },true);
  console.error(`${stage} failed (HTTP ${error.statusCode || 'unknown'}); details saved privately. No resubmission.`);
}
async function recordCost(job) {
  if(job.settled_cost_usd!==undefined)return;
  try {
    const latest=await read(path.join(privateDir,'latest.json'));
    const id=latest.providerMetadata?.gateway?.generationId;if(!id)return;
    const info=await gateway.getGenerationInfo({id});
    await save(path.join(privateDir,'generation-info.json'),info,true);
    if(typeof info.totalCost!=='number'||!Number.isFinite(info.totalCost)||info.totalCost<0)return;
    Object.assign(job,{settled_cost_usd:info.totalCost,cost_source:'Vercel Gateway getGenerationInfo.totalCost',cost_checked_at:now()});
    await save(ledger,job);console.log(`Recorded generation cost: $${info.totalCost.toFixed(2)}.`);
  } catch(error) {await recordError(error,'billing-lookup');}
}
async function main() {
  if(action==='submit') {
    try {
      await fs.access(ledger);
      console.error('This revision already has a submission ledger. Use status for an accepted job, or a new revision after resolving a rejection.');
      process.exitCode=1;return;
    } catch(error) {if(error.code!=='ENOENT') throw error;}
    const refs=await read(path.join(privateDir,'reference-urls.json'));
    if(!Array.isArray(refs)||refs.length!==2) throw new Error('Provide exactly two approved reference images');
    const references=[];
    for(const ref of refs) {
      if(!['character-three-quarter.png','character-side.png'].includes(ref.name)) throw new Error('Unexpected reference filename');
      const url=new URL(ref.url);
      if(url.protocol!=='https:'||url.username||url.password) throw new Error('References require HTTPS URLs without embedded credentials');
      const local=await fs.readFile(path.join(out,'inputs',ref.name));
      const response=await fetch(url,{signal:AbortSignal.timeout(30000)});
      if(!response.ok) throw new Error('Reference URL is not accessible; refresh it before submitting');
      if(sha(Buffer.from(await response.arrayBuffer()))!==sha(local)) throw new Error('Hosted reference does not match local input');
      references.push({file:'inputs/'+ref.name,sha256:sha(local)});
    }
    const prompt=await fs.readFile(path.join(out,'prompt.txt'),'utf8');
    const settings={model:modelId,n:1,duration:6,resolution:'1280x720',aspectRatio:'4:3',generateAudio:false};
    const job={provider:'vercel-ai-gateway',settings,references,prompt,created_at:now(),status:'submitting',review_status:'not_ready'};
    // Exclusive creation is the paid-submission lock, also after a process crash.
    await fs.writeFile(ledger,JSON.stringify(job,null,2)+'\n',{flag:'wx'});
    let result;
    try {
      result=await model.doStart({...settings,prompt,providerOptions:{},
        inputReferences:refs.map(ref=>({type:'url',url:ref.url,mediaType:'image/png'})),
        abortSignal:AbortSignal.timeout(120000)});
    } catch(error) {
      job.status=error.statusCode && error.statusCode<500?'rejected':'submission_uncertain';
      job.http_status=error.statusCode;job.updated_at=now();
      if(error.statusCode===402 && error.message.includes('minimum balance of $10')) {
        job.error_code='minimum_video_balance';job.minimum_balance_usd=10;
      }
      await save(ledger,job);await recordError(error,'submit');process.exitCode=1;return;
    }
    await save(path.join(privateDir,'operation.json'),result,true);
    job.status='queued';job.updated_at=now();
    await save(ledger,job);
    console.log('Seedance 2.5 job accepted; operation saved for resume.');
  }
  const job=await read(ledger);
  if(job.provider!=='vercel-ai-gateway'||job.settings.model!==modelId) throw new Error('Ledger provider/model mismatch');
  if(job.video && sha(await fs.readFile(path.join(out,job.video)))===job.video_sha256) {
    console.log('Video already downloaded and verified.');await recordCost(job);return;
  }
  const {operation}=await read(path.join(privateDir,'operation.json'));
  const deadline=Date.now()+15*60*1000;
  let previous;
  do {
    let result;
    try {result=await model.doStatus({operation,abortSignal:AbortSignal.timeout(60000)});}
    catch(error){await recordError(error,'status');process.exitCode=1;return;}
    await save(path.join(privateDir,'latest.json'),result,true);
    job.status=result.status==='pending'?'running':result.status==='completed'?'succeeded':'failed';
    job.updated_at=now();await save(ledger,job);
    if(previous!==job.status){console.log('Seedance: '+job.status);previous=job.status;}
    if(result.status==='completed') {
      if(result.videos.length!==1) throw new Error('Expected exactly one generated video');
      const video=result.videos[0];let bytes;
      if(video.type==='url') {
        if(new URL(video.url).protocol!=='https:') throw new Error('Unexpected download protocol');
        // No Gateway auth headers are forwarded to the output CDN.
        const response=await fetch(video.url,{signal:AbortSignal.timeout(180000)});
        if(!response.ok) throw new Error('Video download failed; status can safely resume');
        bytes=Buffer.from(await response.arrayBuffer());
      } else if(video.type==='base64') bytes=Buffer.from(video.data,'base64');
      else throw new Error('Unsupported video response type');
      if(bytes.length<1000||bytes.toString('ascii',4,8)!=='ftyp') throw new Error('Download is not an MP4');
      await fs.writeFile(path.join(out,'reference.mp4.part'),bytes);
      await fs.rename(path.join(out,'reference.mp4.part'),path.join(out,'reference.mp4'));
      Object.assign(job,{video:'reference.mp4',video_sha256:sha(bytes),video_bytes:bytes.length,review_status:'pending',updated_at:now()});
      await save(ledger,job);console.log(`Saved reference.mp4 (${bytes.length.toLocaleString()} bytes).`);await recordCost(job);return;
    }
    if(result.status==='error'){console.error('Generation failed; provider details saved privately.');process.exitCode=1;return;}
    if(!values.watch) return;
    await new Promise(resolve=>setTimeout(resolve,15000));
  } while(Date.now()<deadline);
  console.log('Still processing. Resume with status --watch; do not submit again.');
}
main().catch(async error=>{await recordError(error,'local');process.exitCode=1;});
