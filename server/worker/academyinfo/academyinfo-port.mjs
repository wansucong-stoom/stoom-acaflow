/** Fresh read-only Academyinfo transport for a JavaScript Worker.
 * Ordinary queries keep transport state in one invocation. Resumable jobs keep
 * transient state in a private R2 prefix until completion, cancellation or expiry.
 * No archive access, cache binding, signed-in browser, arbitrary URL or SQL input.
 */
import {PortError,parseJavaMapList,parseXML,validateTemplateMetadata,validateDoc,parseReportPage,combinePages} from './report-parser.mjs';
export {PortError};
const HOSTS=new Set(['academyinfo.go.kr','www.academyinfo.go.kr','m.academyinfo.go.kr']);
const DATA_PATHS=new Set(['/NewAcInfo.do','/NewAcInfo2.do','/UbiServer.do']);
const PRIVATE=/token|password|passwd|authorization|cookie|session|secret|pkey|parg|ubikey|ubiargs|strquery|resultmaster|resultheader|resultbody|resultsum|generatedsql/i;
const EXTRA=new Set(['resultMaster','resultHeader','resultBody','resultSum','strQuery','url','strSvyYr','strSchlNm','strPgmNm','strUnt','strRmk','strNowDate','strWrtrNm','strFormClftCd','isMerge','columLaung','strItemId','strItemId2','strSchlDivCd','strMasterId']);
const BASE='https://m.academyinfo.go.kr';
export const PUBLIC_ROUTES=Object.freeze({scope:BASE+'/main/main0780/selectListLink.do',catalog:BASE+'/main/main0780/selectItemList.do',schools:BASE+'/intro/intro0350/selectSchlListAll.do',departments:BASE+'/pubinfo/pubinfo1600/selectMjrList.do',schoolPage:BASE+'/pubinfo/pubinfo0020/list.do',metric:BASE+'/pubinfo/pubinfo0081/selectFreshStudentRate.do',bootstrap:'https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do'});
const INDICATORS=Object.freeze({v1:'신입생 경쟁률',v2:'재학생수',v4:'입학정원',v5:'학생 1인당 연간 장학금',v7:'취업률',v8:'평균 등록금'});
const MAX_REPORT_PAGES=32,DEFAULT_REPORT_PAGES=16,MAX_OUTPUT_BYTES=2*1024*1024;
const encoder=new TextEncoder(),decoder=new TextDecoder('utf-8',{fatal:true});
const error=(code,stage)=>{throw new PortError(code,stage);};
const str=(v,max=200)=>{if(typeof v!=='string'||!v.length||v.length>max)error('invalid_input','input');return v;};
const year=v=>{if(!/^\d{4}$/.test(str(v,4)))error('invalid_year','input');return v;};
const division=v=>{if(!['01','02','03','04'].includes(v))error('invalid_division','input');return v;};
const code=v=>{if(!/^\d{7}$/.test(str(v,7)))error('invalid_official_code','input');return v;};
const item=v=>{if(!/^\d{1,6}$/.test(str(v,6)))error('invalid_item_id','input');return String(Number(v));};
const positive=(v,def,max)=>{v=v??def;if(!Number.isSafeInteger(v)||v<1||v>max)error('invalid_bound','input');return v;};
const offset=v=>{v=v??0;if(!Number.isSafeInteger(v)||v<0||v>100000)error('invalid_offset','input');return v;};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const quoteExact=v=>encodeURIComponent(v).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase());
const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
const noQuery=u=>{const x=new URL(u);x.search='';x.hash='';return x.href;};
export function publicURL(value,{data=false}={}){
  let u;try{u=new URL(value);}catch{error('invalid_source_url','input');}
  if(u.protocol!=='https:'||!HOSTS.has(u.hostname)||u.username||u.password||u.hash||(u.port&&u.port!=='443'))error('non_official_source_url','input');
  for(const key of u.searchParams.keys())if(PRIVATE.test(key))error('private_url_parameter_rejected','input');
  if(data&&!DATA_PATHS.has(u.pathname))error('public_report_route_changed','bootstrap');return u;
}
export function publicProjection(v){
  if(Array.isArray(v))return v.map(publicProjection);
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).filter(([k])=>!PRIVATE.test(k)).map(([k,x])=>[k,publicProjection(x)]));
  if(typeof v==='number'&&!Number.isFinite(v))error('non_finite_public_value','output');
  if(typeof v==='string'&&/<!doctype\b|<html\b|<script\b|<body\b/i.test(v))error('source_html_in_public_data','output');
  return v;
}
const source=(ex,parameters)=>({source_url:noQuery(ex.url),method:'POST',public_parameters:parameters,retrieved_utc:ex.time,raw_sha256:ex.hash,response_status:ex.status,response_content_type:ex.type,response_bytes:ex.bytes.length,upstream_age_seconds:ex.age,body_complete:!ex.truncated});
const listAt=(payload,key)=>{if(!payload||!Array.isArray(payload[key])||payload[key].some(r=>!r||typeof r!=='object'||Array.isArray(r)))error('source_row_schema_changed','json');return payload[key];};
const json=ex=>{let v;try{v=JSON.parse(decoder.decode(ex.bytes));}catch{error('source_not_utf8_json','json');}if(v&&typeof v==='object'&&'M_CODE'in v){if(String(v.M_CODE).trim()===''||!Number.isFinite(Number(v.M_CODE))||Number(v.M_CODE)<0)error('source_json_error','json');}return v;};

class MemoryCookies {
  #cookies=new Map();
  accept(headers,requestURL){
    const u=new URL(requestURL);let lines;
    if(typeof headers.getSetCookie==='function')lines=headers.getSetCookie();
    else if(typeof headers.getAll==='function')lines=headers.getAll('Set-Cookie');
    else{const one=headers.get('set-cookie');if(one&&/,\s*[A-Za-z_][\w-]*=/.test(one))error('cookie_header_unsupported','transport');lines=one?[one]:[];}
    for(const line of lines){const parts=line.split(';').map(x=>x.trim()),match=/^([^=\s]+)=(.*)$/.exec(parts.shift());if(!match)error('cookie_format_changed','transport');const attrs=Object.fromEntries(parts.map(x=>{const n=x.indexOf('=');return n<0?[x.toLowerCase(),true]:[x.slice(0,n).toLowerCase(),x.slice(n+1)];}));
      const domain=String(attrs.domain??u.hostname).replace(/^\./,'').toLowerCase(),hostOnly=!attrs.domain;
      if(!HOSTS.has(domain)||(u.hostname!==domain&&!u.hostname.endsWith('.'+domain)))continue;
      const path=String(attrs.path??u.pathname.slice(0,u.pathname.lastIndexOf('/')+1))||'/',expires=attrs['max-age']!==undefined?Date.now()+Number(attrs['max-age'])*1000:attrs.expires?Date.parse(attrs.expires):Infinity;
      const k=`${domain}|${path}|${match[1]}`;if(expires<=Date.now())this.#cookies.delete(k);else this.#cookies.set(k,{name:match[1],value:match[2],domain,path,hostOnly,expires});
    }
  }
  header(value){const u=new URL(value);return[...this.#cookies.values()].filter(c=>c.expires>Date.now()&&(c.hostOnly?u.hostname===c.domain:u.hostname===c.domain||u.hostname.endsWith('.'+c.domain))&&(u.pathname===c.path||u.pathname.startsWith(c.path.endsWith('/')?c.path:c.path+'/'))).sort((a,b)=>b.path.length-a.path.length).map(c=>`${c.name}=${c.value}`).join('; ');}
  snapshot(){return [...this.#cookies.values()].map(c=>({...c,expires:Number.isFinite(c.expires)?c.expires:null}));}
  restore(rows){for(const c of rows??[])this.#cookies.set(`${c.domain}|${c.path}|${c.name}`,{...c,expires:c.expires??Infinity});}
  clear(){this.#cookies.clear();}
}
async function boundedBytes(stream,max,{prefix=false}={}){
  if(!stream)return{bytes:new Uint8Array(),truncated:false};const reader=stream.getReader(),chunks=[];let size=0,truncated=false;
  try{while(true){const r=await reader.read();if(r.done)break;if(size+r.value.length>max){if(!prefix)error('response_byte_limit','transport');chunks.push(r.value.slice(0,max-size));size=max;truncated=true;await reader.cancel();break;}chunks.push(r.value);size+=r.value.length;if(prefix&&size===max){truncated=true;await reader.cancel();break;}}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
  const bytes=new Uint8Array(size);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length;}return{bytes,truncated};
}

export class FreshClient {
  #fetch;#jar=new MemoryCookies();#started=Date.now();#last=0;#count=0;#total=0;#sources=[];#closed=false;
  constructor({fetchImpl=globalThis.fetch,timeoutMs=12000,initializationTimeoutMs=25000,totalMs=45000,maxRequests=40,maxResponseBytes=2*1024*1024,maxTotalBytes=16*1024*1024,intervalMs=250}={}){
    this.#fetch=typeof fetchImpl==='function'?fetchImpl.bind(globalThis):null;this.bounds={timeoutMs,initializationTimeoutMs,totalMs,maxRequests,maxResponseBytes,maxTotalBytes,intervalMs};
  }
  snapshotCookies(){return this.#jar.snapshot();}
  restoreCookies(rows){this.#jar.restore(rows);}
  close(){this.#closed=true;this.#jar.clear();}
  get sources(){return this.#sources.map(x=>({...x}));}
  get performance(){return{requests:this.#count,received_bytes:this.#total,elapsed_ms:Date.now()-this.#started,source_reused:false};}
  get resourceBounds(){return{request_timeout_ms:this.bounds.timeoutMs,report_initialize_timeout_ms:this.bounds.initializationTimeoutMs,total_timeout_ms:this.bounds.totalMs,max_report_pages:MAX_REPORT_PAGES,default_report_pages:DEFAULT_REPORT_PAGES,max_source_requests:this.bounds.maxRequests,max_source_response_bytes:this.bounds.maxResponseBytes,max_total_source_bytes:this.bounds.maxTotalBytes,min_request_interval_ms:this.bounds.intervalMs,max_output_bytes:MAX_OUTPUT_BYTES};}
  async request(value,parameters,{runtime=false,prefixBytes=null,stage='transport'}={}){
    if(this.#closed)error('closed_request_context',stage);publicURL(value,{data:runtime});
    if(!this.#fetch)error('runtime_fetch_api_unavailable',stage);
    if(!runtime&&Object.keys(parameters).some(k=>PRIVATE.test(k)))error('private_input_parameter_rejected','input');
    const pairs=Object.entries(parameters);if(pairs.some(([k,v])=>typeof k!=='string'||typeof v!=='string'))error('non_string_public_parameters','input');
    if(runtime&&pairs.reduce((n,[k,v])=>n+k.length+v.length,0)>512*1024)error('runtime_parameter_byte_limit',stage);
    const body=runtime?pairs.map(([k,v])=>k+'='+quoteExact(quoteExact(v))).join('&'):new URLSearchParams(parameters).toString();
    let target=value,method='POST',requestBody=body;
    for(let hop=0;hop<=3;hop++){
      if(this.#count>=this.bounds.maxRequests)error('request_budget_exhausted',stage);
      let remaining=this.bounds.totalMs-(Date.now()-this.#started);if(remaining<=0)error('query_deadline_exceeded',stage);
      const intervalWait=Math.max(0,this.bounds.intervalMs-(Date.now()-this.#last));
      if(intervalWait>=remaining){await delay(remaining);error('query_deadline_exceeded',stage);}
      if(intervalWait)await delay(intervalWait);
      // Throttling consumes the same invocation budget as source I/O.
      remaining=this.bounds.totalMs-(Date.now()-this.#started);if(remaining<=0)error('query_deadline_exceeded',stage);
      this.#last=Date.now();this.#count++;
      const requestTimeout=stage==='report_initialize'?this.bounds.initializationTimeoutMs:this.bounds.timeoutMs,deadlineLimited=remaining<=requestTimeout;
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),Math.min(remaining,requestTimeout));
      try{
        const headers={'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','Accept-Language':'ko-KR,ko;q=0.9','User-Agent':'academyinfo-flow-js-prototype/0.1 (public disclosure read-only)','Accept':runtime?'application/xml,text/xml,text/plain,*/*':'application/json,text/html,*/*'};
        if(!runtime)headers['X-Requested-With']='XMLHttpRequest';const cookies=this.#jar.header(target);if(cookies)headers.Cookie=cookies;
        const response=await this.#fetch(target,{method,headers,body:requestBody,redirect:'manual',cache:'no-store',signal:controller.signal});
        this.#jar.accept(response.headers,target);
        if([301,302,303,307,308].includes(response.status)){const loc=response.headers.get('location');await response.body?.cancel();if(!loc||hop===3)error('source_redirect_limit',stage);target=new URL(loc,target).href;publicURL(target,{data:runtime});if([301,302,303].includes(response.status)){method='GET';requestBody=undefined;}continue;}
        if(!response.ok){await response.body?.cancel();const e=new PortError(response.status===401||response.status===403?'source_access_refused':response.status===429?'source_rate_limited':'source_http_error',stage);e.http_status=response.status;throw e;}
        const read=await boundedBytes(response.body,prefixBytes??this.bounds.maxResponseBytes,{prefix:prefixBytes!==null});this.#total+=read.bytes.length;if(this.#total>this.bounds.maxTotalBytes)error('query_byte_budget_exhausted',stage);
        const ex={url:target,bytes:read.bytes,truncated:read.truncated,status:response.status,type:response.headers.get('content-type')??'',time:new Date().toISOString(),hash:await sha(read.bytes),sequence:response.headers.get('exportseq')??'',age:/^\d+$/.test(response.headers.get('age')??'')?Number(response.headers.get('age')):null};
        if(!runtime)this.#sources.push(source(ex,parameters));return ex;
      }catch(e){
        if(e instanceof PortError)throw e;
        // Map a few platform exceptions to fixed diagnostic codes. Raw errors
        // can contain report keys/URLs and must never leave this invocation.
        const message=typeof e?.message==='string'?e.message:'';
        const code=controller.signal.aborted?(deadlineLimited?'query_deadline_exceeded':'source_timeout'):/^Illegal invocation\b/.test(message)?'runtime_fetch_invocation_error':/Unsupported cache mode|cache.{0,80}(?:not implemented|not supported)/i.test(message)?'runtime_request_cache_unsupported':'source_connection_error';
        throw new PortError(code,stage);
      }finally{clearTimeout(timer);}
    }
    error('source_redirect_limit',stage);
  }
  record(ex,selectors,page){const s=source(ex,selectors);if(page!==undefined)s.source_request_page=page;this.#sources.push(s);}
}

export function decodeJSString(literal){
  if(typeof literal!=='string'||literal.length<2||literal[0]!==literal.at(-1)||!['"',"'"].includes(literal[0]))error('bootstrap_literal_changed','bootstrap');
  const chars={n:'\n',r:'\r',t:'\t',b:'\b',f:'\f',v:'\v','0':'\0','\\':'\\',"'":"'",'"':'"'};
  return literal.slice(1,-1).replace(/\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|([\s\S]))/g,(_,u,x,c)=>u||x?String.fromCharCode(parseInt(u||x,16)):chars[c]??c);
}
export async function decodeMetadata(value){
  const chars={n:'\n',r:'\r',t:'\t',b:'\b',f:'\f',e:'\0',' ':' ','\\':'\\',"'":"'",'"':'"'};
  const decoded=String(value).replace(/\\(?:u([0-9a-fA-F]{4})|([\s\S]))/g,(_,u,c)=>{if(u)return String.fromCharCode(parseInt(u,16));if(!Object.hasOwn(chars,c))error('metadata_escape_changed','metadata');return chars[c];});
  if(decoded.length>2*1024*1024)error('metadata_encoding_unsupported','metadata');
  const compressed=new Uint8Array(decoded.length);for(let i=0;i<decoded.length;i++){const value=decoded.charCodeAt(i);if(value>255)error('metadata_encoding_unsupported','metadata');compressed[i]=value;}
  try{const stream=new Response(compressed).body.pipeThrough(new DecompressionStream('deflate'));return decoder.decode((await boundedBytes(stream,1024*1024)).bytes);}catch(e){if(e instanceof PortError)throw e;throw new PortError('metadata_deflate_validation_failed','metadata');}
}
const literalPattern='(?:"(?:\\\\.|[^"\\\\])*"|\'(?:\\\\.|[^\'\\\\])*\')';
export async function parseBootstrap(text,selectors){
  const clean=String(text).replace(/^\s*\/\/.*$/gm,''),variables=Object.create(null),extra=Object.create(null);
  for(const m of clean.matchAll(new RegExp('\\bvar\\s+(pKey|pArg|pServerUrl|pResId|pJrf)\\s*=\\s*('+literalPattern+')','g'))){if(Object.hasOwn(variables,m[1]))error('bootstrap_duplicate_variable','bootstrap');variables[m[1]]=decodeJSString(m[2]);}
  if(['pKey','pArg','pServerUrl','pResId','pJrf'].some(k=>!Object.hasOwn(variables,k)))error('bootstrap_protocol_changed','bootstrap');
  publicURL(variables.pServerUrl,{data:true});
  for(const m of clean.matchAll(new RegExp('htmlViewer\\.params\\.(\\w+)\\s*=\\s*('+literalPattern+')','g')))if(EXTRA.has(m[1])){if(Object.hasOwn(extra,m[1]))error('bootstrap_duplicate_parameter','bootstrap');extra[m[1]]=decodeJSString(m[2]);}
  const form=selectors.formClassification??(selectors.level==='department'?'36':'30');
  if(extra.strSvyYr!==selectors.pubYear||extra.strItemId!==selectors.itemId||extra.strFormClftCd!==form||extra.strSchlDivCd!==selectors.schoolDivision||extra.columLaung!=='KOR')error('bootstrap_scope_or_language_mismatch','bootstrap');
  const metadata={};for(const[k,field]of [['master','resultMaster'],['header','resultHeader'],['body','resultBody'],['sum','resultSum']])if(Object.hasOwn(extra,field))metadata[k]=parseJavaMapList(await decodeMetadata(extra[field]));
  if(!metadata.master||!metadata.header||!metadata.body)error('bootstrap_table_metadata_missing','metadata');
  const templateId=validateTemplateMetadata(metadata,form);
  if(extra.strMasterId!==undefined&&extra.strMasterId!==templateId)error('bootstrap_master_template_mismatch','metadata');
  const runtime={reqtype:'0',cHJvY2lk:'GATEWAY',key:variables.pKey,ubiserverurl:variables.pServerUrl,jrffile:variables.pJrf,resid:variables.pResId,arg:variables.pArg,exportseq:String(Date.now()),isStreaming:'true',issvg:'false',isencrypt:'true',isencrypt64:'false',language:'ko',isredbc:'false',...extra};
  return{server:variables.pServerUrl,runtime,metadata,title:extra.strPgmNm??'',selectors};
}
export function parseStatus(bytes,server){
  let text;try{text=decoder.decode(bytes).trim();}catch{error('status_encoding_changed','generation_status');}
  if(new URL(server).pathname==='/UbiServer.do'&&text.startsWith('\0^'))text=text.slice(1);
  if(text.startsWith('ER0'))error('source_report_generation_error','generation_status');
  const chunks=[...text.matchAll(/(?:^|\^)\s*(\d+)#([01])#([01])(?=\^|\s*$)/g)];if(!chunks.length||/[^0-9#^\s]/.test(text))error('status_protocol_changed','generation_status');
  const m=chunks.at(-1),pages=Number(m[1]);if(!Number.isSafeInteger(pages)||pages<1||pages>100000)error('status_page_count_invalid','generation_status');
  return{expected_pages:pages,complete:m[2]==='0',multiple_paper:m[3]==='1'};
}

export async function fetchScope(client){
  const ex=await client.request(PUBLIC_ROUTES.scope,{}, {stage:'scope'});let html;try{html=decoder.decode(ex.bytes);}catch{error('scope_encoding_changed','scope');}
  const options=id=>{const selects=[...html.matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select\s*>/gi)].filter(m=>new RegExp('\\bid\\s*=\\s*["\']'+id+'["\']','i').test(m[1]));if(selects.length!==1)error('scope_selector_changed','scope');return[...selects[0][2].matchAll(/<option\b[^>]*\bvalue\s*=\s*["']([^"']*)["']/gi)].map(m=>m[1]);};
  const years=options('vn_svy_yr'),divisions=options('vn_schl_div_cd');if(!years.length||years.some(y=>!/^\d{4}$/.test(y))||new Set(divisions).size!==4||divisions.some(d=>!['01','02','03','04'].includes(d)))error('published_scope_changed','scope');
  return{years:[...new Set(years)],school_divisions:[...new Set(divisions)]};
}
export async function fetchCatalog(client,y,d){
  year(y);division(d);const ex=await client.request(PUBLIC_ROUTES.catalog,{svyYr:y,schlDivCd:d,searchGbn:'0',category_cd:'',category_gubun:'category',searchVal:''},{stage:'catalog'}),rows=listAt(json(ex),'detailItemList');
  if(rows.some(r=>!['svy_yr','schl_div_cd','item_id','mjr_use_step_cd','pdf_use_yn'].every(k=>Object.hasOwn(r,k))||String(r.svy_yr)!==y||String(r.schl_div_cd)!==d))error('catalog_schema_or_scope_changed','catalog');return rows;
}
async function knownYear(client,y){const scope=await fetchScope(client);if(!scope.years.includes(year(y)))error('year_not_published','scope');return scope;}
async function fetchAffiliations(client,input){
  const y=year(input.year),school=code(input.school_code);await knownYear(client,y);
  const ex=await client.request(PUBLIC_ROUTES.schoolPage,{schlId:school,svyYr:y,pageIdx:'01'},{stage:'affiliations'}),html=decoder.decode(ex.bytes);
  const selects=[...html.matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select\s*>/gi)].filter(m=>/\b(?:id|name)\s*=\s*["']collegeList["']/i.test(m[1]));if(selects.length!==1)error('affiliation_selector_changed','affiliations');
  const rows=[];
  for(const m of selects[0][2].matchAll(/<option\b[^>]*\bvalue\s*=\s*["']([^"']*)["'][^>]*>([\s\S]*?)<\/option\s*>/gi)){
    if(!m[1])continue;const value=/^(\d{7}),(0[1-4])$/.exec(m[1]);if(!value)error('affiliation_code_changed','affiliations');
    const label=m[2].replace(/<[^>]+>/g,'').replace(/&nbsp;/g,'\u00a0');const text=parseXML('<X>'+label+'</X>').text.trim();rows.push({schoolCode:value[1],schoolDivision:value[2],sourceLabel:text});
  }
  if(!rows.length||new Set(rows.map(r=>r.schoolCode)).size!==rows.length||!rows.some(r=>r.schoolCode===school))error('affiliation_identity_unverified','affiliations');return{rows,source_complete:true};
}
async function fetchSchools(client,input){
  const y=year(input.year),name=input.name??'',max=positive(input.max_pages,4,16);await knownYear(client,y);const found=[];let expected=null;
  for(let page=1;page<=max;page++){const ex=await client.request(PUBLIC_ROUTES.schools,{svy_yr:y,pbnf_area_cd:'',searchVal:String(name),pageindex:String(page)},{stage:'schools'}),payload=json(ex),rows=listAt(payload,'resultList'),p=payload.paginationInfo;
    if(rows.some(r=>typeof r.schl_id!=='string'||typeof r.schl_nm!=='string')||!p||!Number.isSafeInteger(p.totalPageCount)||p.currentPageNo!==page||expected!==null&&expected!==p.totalPageCount)error('school_registry_schema_or_page_changed','schools');expected=p.totalPageCount;found.push(...rows);if(page>=expected)return{rows:found,source_complete:true};}
  return{rows:found,source_complete:false,warning:'school_page_limit'};
}
async function fetchDepartments(client,input,{checkScope=true}={}){
  const y=year(input.year),school=code(input.school_code),max=positive(input.max_pages,4,16);if(checkScope)await knownYear(client,y);const found=[],seen=new Set();let expected=null;
  for(let page=1;page<=max;page++){const ex=await client.request(PUBLIC_ROUTES.departments,{svyYr:y,schlId:school,pulYn:input.include_closed===false?'true':'false',pageindex:String(page)},{stage:'departments'}),payload=json(ex),rows=listAt(payload,'resultList'),total=payload.paginationInfo?.totalRecordCount;
    if(!Number.isSafeInteger(total)||total<0||expected!==null&&total!==expected||rows.some(r=>typeof r.mjr_nm!=='string'||!/^\d{7}$/.test(r.schl_mjr_id)||!/^\d{7}$/.test(r.mjr_id)))error('department_registry_schema_changed','departments');expected=total;
    for(const r of rows){const k=r.schl_mjr_id+':'+r.mjr_id;if(seen.has(k))error('department_duplicate_row_or_page','departments');seen.add(k);found.push(r);}if(seen.size>total)error('department_count_exceeded','departments');if(seen.size===total)return{rows:found,source_complete:true};if(!rows.length)error('department_empty_incomplete_page','departments');
  }return{rows:found,source_complete:false,warning:'department_page_limit'};
}
async function fetchMetric(client,input){
  const y=year(input.year),school=code(input.school_code),dept=code(input.department_code),major=code(input.major_code);if(!Object.hasOwn(INDICATORS,input.flag))error('unsupported_department_metric','input');
  await knownYear(client,y);const registry=await fetchDepartments(client,{year:y,school_code:school,max_pages:4},{checkScope:false});if(!registry.source_complete)error('department_identity_lookup_incomplete','metric');const matches=registry.rows.filter(r=>r.schl_mjr_id===dept&&r.mjr_id===major);if(matches.length!==1)error('department_identity_unverified','metric');
  const ex=await client.request(PUBLIC_ROUTES.metric,{svyYr:y,schlMjrId:dept,schlId:school,mjrId:major,flag:input.flag},{stage:'metric'}),p=json(ex),rows=listAt(p,'resultList');if(rows.some(r=>typeof r.year!=='string'||!/^\d{4}$/.test(r.year)||!Object.hasOwn(r,'val')))error('metric_row_schema_changed','metric');
  return{rows,department_name:matches[0].mjr_nm,source_complete:true,indicator_hint:INDICATORS[input.flag],effective_source_year:p.pramMap?.pbnf_bse_yr??null,year_semantics:'source graph year is preserved separately from request/disclosure/reference years',guideline_verified:false,unit_and_formula:'verify annual official guidance before interpretation or derived arithmetic'};
}
async function report(client,input,result,jobStore=null){
  const y=year(input.year),d=division(input.division),id=item(input.item),level=input.level??'school';if(!['school','department'].includes(level))error('invalid_level','input');const maxPages=positive(input.max_pages,DEFAULT_REPORT_PAGES,MAX_REPORT_PAGES),limit=positive(input.limit,50,1000),start=offset(input.offset);result.resource_bounds.requested_max_pages=maxPages;
  const listNames=v=>{if(v===undefined)return[];if(!Array.isArray(v)||v.length>20||v.some(n=>typeof n!=='string'||!n||n.length>200))error('invalid_exact_name_filter','input');return[...new Set(v)];};const schoolNames=listNames(input.school_names),deptNames=listNames(input.department_names);
  await knownYear(client,y);const catalog=await fetchCatalog(client,y,d),matches=catalog.filter(r=>String(Number(r.item_id))===id);if(matches.length!==1)error('item_not_uniquely_published','catalog');const entry=matches[0];result.catalog_item=publicProjection(entry);
  if(level==='department'&&String(entry.mjr_use_step_cd)==='0')error('department_view_not_available','catalog');if(entry.pdf_use_yn==='Y')error('pdf_attachment_listing_not_ported','catalog');
  let schoolLabels=schoolNames;let schoolCode=input.school_code===undefined?null:code(input.school_code);
  if(schoolCode&&(level!=='department'||schoolNames.length!==1))error('school_detail_requires_one_department_school','input');
  if(level==='department'&&schoolNames.length===1){
    const registry=await fetchSchools(client,{year:y,name:schoolNames[0],max_pages:10});
    if(!registry.source_complete)error('school_identity_lookup_incomplete','school_identity');
    const exact=registry.rows.filter(r=>r.schl_nm===schoolNames[0]&&r.schl_div_cd===d&&(!schoolCode||r.schl_id===schoolCode));
    if(exact.length!==1)error('school_identity_not_unique','school_identity');
    schoolCode=code(exact[0].schl_id);if(typeof exact[0].psbs_div_nm==='string'&&exact[0].psbs_div_nm)schoolLabels=[...schoolNames,schoolNames[0]+'_'+exact[0].psbs_div_nm];
  }
  const form=schoolCode?'60':level==='department'?'36':'30',selectors={pubYear:y,schoolDivision:d,itemId:id,level,language:'ko',...(schoolCode?{formClassification:'60'}:{})};
  result.report_scope={route:schoolCode?'school_detail':'national',form_classification:form,...(schoolCode?{requested_school_code:schoolCode,requested_school_name:schoolNames[0]}:{})};
  const ex=await client.request(PUBLIC_ROUTES.bootstrap,{paramSvyYr:y,paramSchlDivCd:d,paramItemId:id,paramFormClftCd:form,paramMjrItem1:'00',paramMjrItem2:'00',paramMjrItem3:'00',paramSchlKindCd:'99',paramSchlEstabCd:'99',paramDomainDiv:'MOB',...(schoolCode?{paramSchlCd:schoolCode,paramZoneCd:'99'}:{})},{stage:'bootstrap'});
  let session;const reports=[];let first=null,last=null,failure=null;
  try{
    session=await parseBootstrap(decoder.decode(ex.bytes),selectors);
    const init=await client.request(session.server,session.runtime,{runtime:true,stage:'report_initialize'}),doc=validateDoc(decoder.decode(init.bytes));if(!init.sequence)error('report_session_unverified','report_initialize');session.runtime.exportseq=init.sequence;session.service=doc.root.attrs.serviceid??'';
    if(jobStore){
      const id=crypto.randomUUID().replace(/-/g,''),now=Date.now(),state={id,created:now,expires:now+2*60*60*1000,status:'generating',next_page:1,expected_pages:null,row_count:0,session,cookies:client.snapshotCookies(),selectors,report_scope:result.report_scope,catalog_item:result.catalog_item,hashes:[],body_hashes:[],chunks:[],columns:null,sources:client.sources};
      await purgeExpiredJobs(jobStore);await jobStore.put(jobStateKey(id),JSON.stringify(state),{customMetadata:{expires:String(state.expires)}});Object.assign(result,jobSummary(state));return;
    }
    const status=async()=>{const control=await client.request(session.server,{...session.runtime,reqtype:'99'},{runtime:true,prefixBytes:4096,stage:'generation_status'});return parseStatus(control.bytes,session.server);};
    for(let poll=0;poll<5;poll++){first=await status();if(first.complete)break;await delay(500);}if(!first?.complete)error('report_generation_incomplete','generation_status');
    result.generation={expected_pages:first.expected_pages,max_pages:maxPages,complete_before_fetch:true};
    for(let page=1;page<=Math.min(first.expected_pages,maxPages);page++){
      const runtime=Object.fromEntries(['cHJvY2lk','key','ubiserverurl','jrffile','resid','exportseq','issvg'].map(k=>[k,session.runtime[k]]));Object.assign(runtime,{reqtype:`91#${page}`,timeout:String(client.bounds.timeoutMs),userHeader:'',serviceid:session.service});
      const pageEx=await client.request(session.server,runtime,{runtime:true,stage:'report_page'});client.record(pageEx,{...selectors,source_request_page:page},page);reports.push(await parseReportPage(pageEx.bytes,{pageIndex:page-1,metadata:session.metadata,selectors}));
    }
    last=await status();if(!last.complete||last.expected_pages!==first.expected_pages)error('report_generation_changed','generation_status');
  }catch(e){failure=e;}finally{if(session){for(const k of Object.keys(session.runtime))delete session.runtime[k];session.service='';session.server='';}}
  if(first)result.generation={...result.generation,expected_pages:first.expected_pages,fetched_pages:reports.length,final_complete:Boolean(last?.complete),page_count_stable:Boolean(!failure&&last?.complete&&last.expected_pages===first.expected_pages)};
  if(reports.length){const combined=combinePages(reports,first.expected_pages),filters={...(schoolNames.length?{schoolName:schoolLabels}:{}),...(deptNames.length?{deptName:deptNames}:{})};const available=new Set(combined.rows.flatMap(r=>Object.keys(r.dimensions)));const filtersVerified=Object.keys(filters).every(k=>available.has(k)&&combined.rows.every(r=>typeof r.dimensions[k]==='string'||r.row_kind==='aggregate'&&r.dimensions[k]===null));
    const matched=combined.rows.filter(r=>Object.entries(filters).every(([k,ns])=>ns.includes(r.dimensions[k]))),selected=matched.slice(start,start+limit);result.rows=selected.map(({cell_sources,...r})=>r);result.columns=combined.columns;result.page_coverage=combined.coverage;result.pages=combined.pages;result.validation_warnings=[...new Set(combined.warnings)];
    const sourceComplete=!failure&&last?.complete&&first.expected_pages===last.expected_pages&&combined.coverage.complete,tableComplete=combined.status==='complete',returnedComplete=filtersVerified&&start===0&&selected.length===matched.length;
    result.complete=Boolean(sourceComplete&&tableComplete&&returnedComplete);result.status=result.complete?'ok':'partial';result.filters={match:'exact_any',dimensions:filters,verified_on_all_source_rows:filtersVerified};result.completeness={source_complete:Boolean(sourceComplete),table_validation_complete:tableComplete,filter_dimension_verified:filtersVerified,returned_complete:returnedComplete,source_fetched_row_count:combined.rows.length,matched_row_count:matched.length,return_offset:start,return_limit:limit,reasons:[...(!sourceComplete?['page_limit_or_generation_unverified']:[]),...(!tableComplete?['table_layout_unverified']:[]),...(!filtersVerified?['filter_dimension_unverified']:[]),...(!returnedComplete?['return_range']:[])]};
    if(first.expected_pages>maxPages)result.next_action='For the complete nationwide table use academyinfo_report_start and continue the same job until complete; changing offset does not fetch later source pages.';result.guideline_verified=false;result.granularity_note='department is the official report form; actual department/field/aggregate scope must be established from columns and annual guidance';
  }
  if(failure)throw failure;
}


// Only temporary live query state uses this isolated prefix. No archive fallback.
const JOB_PREFIX='academyinfo-live-jobs/';
const jobStateKey=id=>JOB_PREFIX+'state/'+id;
const jobPageKey=(id,page)=>JOB_PREFIX+'pages/'+id+'/'+String(page).padStart(6,'0');
const jobId=v=>{if(typeof v!=='string'||!/^[a-f0-9]{32}$/.test(v))error('invalid_job_id','job');return v;};
async function deleteJob(store,id){
  let cursor;do{const list=await store.list({prefix:JOB_PREFIX+'pages/'+id+'/',limit:1000,...(cursor?{cursor}:{})});if(list.objects.length)await store.delete(list.objects.map(o=>o.key));cursor=list.truncated?list.cursor:null;}while(cursor);
  await store.delete(jobStateKey(id));
}
async function purgeExpiredJobs(store){
  const list=await store.list({prefix:JOB_PREFIX+'state/',limit:100,include:['customMetadata']});
  for(const object of list.objects)if(Number(object.customMetadata?.expires)<Date.now())await deleteJob(store,object.key.slice((JOB_PREFIX+'state/').length));
}
async function loadJob(store,id){
  if(!store)error('resumable_storage_unavailable','job');const object=await store.get(jobStateKey(jobId(id)));
  if(!object)error('job_not_found_or_expired','job');if(object.size>2*1024*1024)error('job_state_size_limit','job');const state=await object.json();
  if(state.expires<Date.now()){await deleteJob(store,id);error('job_not_found_or_expired','job');}return{object,state};
}
function jobSummary(s){
  const done=s.status==='complete';return{status:done?'ok':s.status==='failed'?'error':'partial',complete:done,job_id:s.id,job_status:s.status,expires_utc:new Date(s.expires).toISOString(),next_page:s.next_page,expected_pages:s.expected_pages,fetched_pages:s.next_page-1,source_row_count:s.row_count,report_scope:s.report_scope,catalog_item:s.catalog_item,guideline_verified:false,validation_warnings:s.warnings??[],completeness:{source_complete:done,table_validation_complete:done,returned_complete:false,meaning:'Acquisition progress only. Use report_read or the complete JSON download for rows.'},...(done?{download_path:'/api/academyinfo/results/'+s.id+'.json'}:{}),...(s.last_error?{last_error:s.last_error,...(s.status!=='failed'?{retry_after_seconds:Math.min(8,2**(s.retries??1))}:{})}:{}),next_action:done?'Read saved live-query pages or download the complete JSON; annual guidance remains separate.':s.status==='failed'?'Inspect the error. Do not use partial rows as nationwide totals.':'Call academyinfo_report_continue with this job_id and expected_next_page=next_page. Do not restart the national report.'};
}
async function jobStatus(client,session){for(let attempt=0;attempt<3;attempt++){const ex=await client.request(session.server,{...session.runtime,reqtype:'99'},{runtime:true,prefixBytes:4096,stage:'generation_status'});if(decoder.decode(ex.bytes).trim())return parseStatus(ex.bytes,session.server);if(attempt<2)await delay(1000*2**attempt);}error('source_empty_generation_status','generation_status');}
const columnSignature=columns=>JSON.stringify(columns.map(c=>[c.key,c.source_col_no,c.source_field_id,c.source_semantic_code,c.header_path,c.x,c.width]));
function savedPageReader(store,state){
  let current=null,cached=null;
  return async page=>{const chunk=state.chunks?.find(c=>c.start<=page&&c.end>=page),start=chunk?.start??page;if(current!==start){const obj=await store.get(jobPageKey(state.id,start));if(!obj)error('saved_page_missing','job_read');if(obj.size>4*1024*1024)error('saved_chunk_size_limit','job_read');const value=await obj.json();cached=value.batch??[value];current=start;}const found=cached.find(p=>p.page.source_request_page===page);if(!found)error('saved_page_missing','job_read');return found;};
}
async function reportJob(command,input,client,store){
  const id=jobId(input.job_id),loaded=await loadJob(store,id),s=loaded.state;
  if(command==='report_read'){
    const start=positive(input.start_page,1,10000),count=positive(input.page_count,1,4),pages=[],read=savedPageReader(store,s);let bytes=0;
    for(let page=start;page<Math.min(start+count,s.next_page);page++){const value=await read(page);bytes+=encoder.encode(JSON.stringify(value)).length;if(bytes>1536*1024)break;pages.push(value);}
    const readComplete=start===1&&start+pages.length===s.next_page&&s.status==='complete';return{...jobSummary(s),complete:readComplete,status:readComplete?'ok':'partial',rows:pages.flatMap(p=>p.rows),columns:s.columns,pages:pages.map(({rows,...p})=>p),read_start_page:start,read_next_page:pages.length?start+pages.length:start,read_complete:readComplete};
  }
  if(s.busy_until>Date.now())return{...jobSummary(s),retry_after_seconds:Math.ceil((s.busy_until-Date.now())/1000)};
  if(command==='report_cancel'){const claimed=await store.put(jobStateKey(id),JSON.stringify({...s,busy_until:Date.now()+60000,status:'deleting'}),{onlyIf:{etagMatches:loaded.object.etag},customMetadata:{expires:String(s.expires)}});if(!claimed)return{...jobSummary(s),retry_after_seconds:2};await deleteJob(store,id);return{status:'ok',complete:true,job_id:id,job_status:'deleted',rows:[]};}
  if(['complete','failed'].includes(s.status))return jobSummary(s);
  if(!Number.isSafeInteger(input.expected_next_page)||input.expected_next_page!==s.next_page)return{...jobSummary(s),cursor_changed:true};
  const count=positive(input.max_pages,16,32);s.busy_until=Date.now()+60000;
  let lock=await store.put(jobStateKey(id),JSON.stringify(s),{onlyIf:{etagMatches:loaded.object.etag},customMetadata:{expires:String(s.expires)}});
  if(!lock)return{...jobSummary(s),retry_after_seconds:2};
  const save=async()=>{const saved=await store.put(jobStateKey(id),JSON.stringify(s),{onlyIf:{etagMatches:lock.etag},customMetadata:{expires:String(s.expires)}});if(!saved)error('job_concurrent_update','job');lock=saved;};
  client.restoreCookies(s.cookies);const pending=[],firstPage=s.next_page;let pendingBytes=0;s.chunks??=Array.from({length:s.next_page-1},(_,i)=>({start:i+1,end:i+1}));
  try{
    const status=await jobStatus(client,s.session);
    if(!status.complete){if(s.expected_pages!==null)error('report_generation_changed','generation_status');s.status='generating';return jobSummary(s);}
    if(status.expected_pages>5000)error('job_page_bound_exceeded','generation_status');
    if(s.expected_pages!==null&&s.expected_pages!==status.expected_pages)error('report_generation_changed','generation_status');
    s.expected_pages=status.expected_pages;s.status='fetching';
    const orphan=await store.get(jobPageKey(id,s.next_page));if(orphan){const value=await orphan.json();if(!value.batch||!value.checkpoint)error('saved_page_conflict','job');Object.assign(s,value.checkpoint);s.chunks.push({start:firstPage,end:s.next_page-1});await save();return jobSummary(s);}
    for(let n=0;n<count&&s.next_page<=s.expected_pages;n++){
      // Leave time for a final status check and a durable progress checkpoint.
      if(client.performance.elapsed_ms>22000||client.performance.received_bytes>12*1024*1024||pendingBytes>2*1024*1024)break;
      const page=s.next_page,runtime=Object.fromEntries(['cHJvY2lk','key','ubiserverurl','jrffile','resid','exportseq','issvg'].map(k=>[k,s.session.runtime[k]]));
      Object.assign(runtime,{reqtype:`91#${page}`,timeout:String(client.bounds.timeoutMs),userHeader:'',serviceid:s.session.service});
      const ex=await client.request(s.session.server,runtime,{runtime:true,stage:'report_page'});if(!decoder.decode(ex.bytes).trim())error('source_empty_report_page','report_page');const parsed=await parseReportPage(ex.bytes,{pageIndex:page-1,metadata:s.session.metadata,selectors:s.selectors});
      if(parsed.status!=='complete')error('table_layout_unverified','report_page');
      client.record(ex,{...s.selectors,source_request_page:page},page);const signature=columnSignature(parsed.columns),bodyHash=await sha(encoder.encode(JSON.stringify(parsed.rows.map(r=>({values:r.values,dimensions:r.dimensions})))));
      if(s.signature&&s.signature!==signature)error('column_schema_changed_between_pages','report_page');
      if(s.hashes.includes(parsed.page.source_sha256)||s.body_hashes.includes(bodyHash))error('report_page_repeated','report_page');
      if(!s.signature){s.signature=signature;s.columns=parsed.columns;}
      const rows=parsed.rows.map(({cell_sources,...r},i)=>({...r,row_number:s.row_count+i+1,source_page_row_number:r.row_number}));
      const output=publicProjection({page:parsed.page,rows,sources:client.sources.slice(-1),warnings:parsed.warnings});
      const outputBytes=encoder.encode(JSON.stringify(output)).length;if(pendingBytes+outputBytes>3*1024*1024){if(!pending.length)error('saved_page_size_limit','job');break;}pending.push(output);pendingBytes+=outputBytes;
      s.hashes.push(parsed.page.source_sha256);s.body_hashes.push(bodyHash);s.row_count+=rows.length;s.next_page++;s.retries=0;delete s.last_error;s.cookies=client.snapshotCookies();
    }
    const last=await jobStatus(client,s.session);if(!last.complete||last.expected_pages!==s.expected_pages)error('report_generation_changed','generation_status');
    if(s.next_page>s.expected_pages){s.status='complete';delete s.session;delete s.cookies;}
  }catch(e){
    const code=e instanceof PortError?e.code:'job_execution_error';s.last_error={code,stage:e instanceof PortError?e.stage:'job',failed_page:s.next_page,...(Number.isInteger(e.http_status)?{http_status:e.http_status}:{})};
    const retryable=['source_empty_generation_status','source_timeout','source_empty_report_page','query_deadline_exceeded','request_budget_exhausted','source_connection_error'].includes(code)||[500,502,503,504].includes(e.http_status);
    s.retries=(s.retries??0)+1;if(!retryable||s.retries>=3){s.status='failed';delete s.session;delete s.cookies;}else{s.cookies=client.snapshotCookies();}
  }finally{
    if(pending.length){const checkpoint=Object.fromEntries(['next_page','row_count','hashes','body_hashes','signature','columns'].filter(k=>s[k]!==undefined).map(k=>[k,s[k]]));const stored=await store.put(jobPageKey(id,firstPage),JSON.stringify({batch:pending,checkpoint}),{onlyIf:{etagDoesNotMatch:'*'}});if(!stored)error('saved_page_conflict','job');s.chunks.push({start:firstPage,end:s.next_page-1});}
    s.busy_until=0;await save();
  }
  return jobSummary(s);
}
export async function downloadJob(request,store){
  const match=/\/api\/academyinfo\/results\/([a-f0-9]{32})\.json$/.exec(new URL(request.url).pathname);if(!match||!['GET','HEAD'].includes(request.method))return new Response('Not found',{status:404});
  let state;try{state=(await loadJob(store,match[1])).state;}catch{return new Response('Expired or unavailable',{status:404});}if(state.status!=='complete')return new Response('Report is not complete',{status:409});
  let page=0;const read=savedPageReader(store,state);const stream=new ReadableStream({async pull(controller){try{if(page===0){controller.enqueue(encoder.encode(JSON.stringify({...jobSummary(state),complete:true,completeness:{source_complete:true,table_validation_complete:true,returned_complete:true},columns:state.columns}).slice(0,-1)+',"pages":['));page++;return;}if(page<=state.expected_pages){const value=await read(page);controller.enqueue(encoder.encode((page>1?',':'')+JSON.stringify(value)));page++;return;}controller.enqueue(encoder.encode(']}'));controller.close();}catch{controller.error(new Error('Report download incomplete'));}}});
  return new Response(request.method==='HEAD'?null:stream,{headers:{'Content-Type':'application/json; charset=utf-8','Content-Disposition':'attachment; filename="academyinfo-report.json"','Cache-Control':'private, no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}});
}

export async function runFresh(command,input={},options={}){
  const client=new FreshClient(options),result={schema_version:1,source:'대학알리미',mode:'live',command,status:'error',complete:false,rows:[],sources:[],lookup_started_utc:new Date().toISOString(),runtime_fields_omitted:true,raw_responses_saved:false,value_semantics:'Preserve displayed strings, null, blank and dash; empty or failure is never zero.',resource_bounds:client.resourceBounds,completeness:{source_complete:false,returned_complete:false}};
  try{
    if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).some(k=>PRIVATE.test(k)))error('invalid_or_private_input','input');
    if(command==='scope'){const s=await fetchScope(client);Object.assign(result,s,{rows:s.years.map(y=>({year:y})),status:'ok',complete:true,completeness:{source_complete:true,returned_complete:true}});}
    else if(command==='catalog'){await knownYear(client,input.year);const rows=await fetchCatalog(client,input.year,input.division),keyword=input.keyword??'',matched=rows.filter(r=>!keyword||String(r.pgm_estn_nm??r.item_smry_nm??'').includes(keyword)),start=offset(input.offset),limit=positive(input.limit,1000,1000),selected=matched.slice(start,start+limit);Object.assign(result,{rows:selected,status:start===0&&selected.length===matched.length?'ok':'partial',complete:start===0&&selected.length===matched.length,source_item_rows:rows.length,completeness:{source_complete:true,returned_complete:start===0&&selected.length===matched.length,matched_row_count:matched.length}});}
    else if(['schools','affiliations','departments','metric'].includes(command)){const out=command==='schools'?await fetchSchools(client,input):command==='affiliations'?await fetchAffiliations(client,input):command==='departments'?await fetchDepartments(client,input):await fetchMetric(client,input);Object.assign(result,out,{status:out.source_complete?'ok':'partial',complete:out.source_complete,completeness:{source_complete:out.source_complete,returned_complete:out.source_complete}});}
    else if(command==='report')await report(client,input,result);
    else if(command==='report_start'){if(!options.jobStore)error('resumable_storage_unavailable','job');await report(client,{...input,max_pages:1,limit:1},result,options.jobStore);}
    else if(['report_continue','report_read','report_cancel'].includes(command))Object.assign(result,await reportJob(command,input,client,options.jobStore));
    else error('unsupported_command','input');
  }catch(e){result.status=result.rows.length?'partial':'error';result.complete=false;result.completeness.source_complete=false;result.error={code:e instanceof PortError?e.code:'internal_error',stage:e instanceof PortError?e.stage:'internal',message:'Fresh official source retrieval or validation did not complete. No archive substitution or private transport details are returned.'};if(Number.isInteger(e.http_status))result.error.http_status=e.http_status;}
  finally{result.sources=client.sources;result.performance=client.performance;client.close();}
  result.retrieved_utc=result.sources.at(-1)?.retrieved_utc??null;result.returned_row_count=result.rows.length;result.data_availability=result.status==='error'?'error':result.rows.length?'available':'empty';
  try{const value=publicProjection(result);if(encoder.encode(JSON.stringify(value)).length>MAX_OUTPUT_BYTES)error('output_byte_limit','output');return value;}catch(e){return{schema_version:1,mode:'live',status:'error',complete:false,rows:[],resource_bounds:result.resource_bounds,error:{code:e instanceof PortError&&e.code==='output_byte_limit'?'output_byte_limit':'public_output_validation_failed',message:'Public result validation or output bound failed; runtime details omitted.'},runtime_fields_omitted:true,raw_responses_saved:false};}
}
