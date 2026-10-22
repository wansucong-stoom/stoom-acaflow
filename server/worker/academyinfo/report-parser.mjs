/** Bounded, fail-closed port of the public UbiReport rectangular table parser.
 * No eval, DOM dependency, DTD, arbitrary entity, SQL execution or external I/O.
 * Column identity is established by metadata AND all rendered header rectangles.
 * This prototype intentionally rejects template-specific exceptions not ported.
 */
export class PortError extends Error {
  constructor(code, stage = 'source_validation') { super(code); this.name = 'PortError'; this.code = code; this.stage = stage; }
}
const fail = code => { throw new PortError(code, 'table_parse'); };
const dict = () => Object.create(null);
const int = (v, min = 0) => {
  if (!/^(0|[1-9]\d*)$/.test(String(v)) || !Number.isSafeInteger(Number(v)) || Number(v) < min) fail('invalid_metadata_integer');
  return Number(v);
};
const entity = s => String(s).replace(/&([^;]+);/g, (_, v) => {
  const standard = {amp:'&',lt:'<',gt:'>',quot:'"',apos:"'"};
  if (Object.hasOwn(standard, v)) return standard[v];
  if (/^#(?:x[0-9a-fA-F]+|[0-9]+)$/.test(v)) {
    const n = v[1] === 'x' ? parseInt(v.slice(2), 16) : Number(v.slice(1));
    if (n > 0 && n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff)) return String.fromCodePoint(n);
  }
  fail('unsupported_xml_entity');
});

export function parseXML(text, {maxChars = 2 * 1024 * 1024, maxNodes = 25000, maxDepth = 64} = {}) {
  if (typeof text !== 'string' || !text.length || text.length > maxChars || /<!\s*(DOCTYPE|ENTITY)\b/i.test(text)) fail('xml_size_or_dtd_rejected');
  const container = {tag:'#root',attrs:dict(),children:[],parts:[],text:''}, stack = [container];
  let at = 0, nodes = 0;
  while (at < text.length) {
    if (text[at] !== '<') {
      const end = text.indexOf('<', at), stop = end < 0 ? text.length : end;
      const value=entity(text.slice(at, stop));stack.at(-1).text += value;stack.at(-1).parts.push(value); at = stop; continue;
    }
    if (text.startsWith('<!--', at)) { const end = text.indexOf('-->', at + 4); if (end < 0) fail('malformed_xml_comment'); at = end + 3; continue; }
    if (text.startsWith('<![CDATA[', at)) { const end = text.indexOf(']]>', at + 9); if (end < 0) fail('malformed_xml_cdata'); const value=text.slice(at+9,end);stack.at(-1).text+=value;stack.at(-1).parts.push(value); at = end + 3; continue; }
    if (text.startsWith('<?', at)) { const end = text.indexOf('?>', at + 2); if (end < 0) fail('malformed_xml_instruction'); at = end + 2; continue; }
    let end = at + 1, quote = '';
    for (; end < text.length; end++) {
      const c = text[end]; if (quote) { if (c === quote) quote = ''; }
      else if (c === '"' || c === "'") quote = c;
      else if (c === '>') break;
    }
    if (end >= text.length || quote) fail('truncated_xml_tag');
    const body = text.slice(at + 1, end); at = end + 1;
    if (body.startsWith('/')) {
      const name = body.slice(1).trim(); if (stack.length < 2 || stack.at(-1).tag !== name) fail('xml_tag_mismatch');
      stack.pop(); continue;
    }
    const match = /^([A-Za-z_][\w:.-]*)([\s\S]*)$/.exec(body); if (!match) fail('unsupported_xml_tag');
    const self = /\/\s*$/.test(match[2]), rest = self ? match[2].replace(/\/\s*$/, '') : match[2];
    const attrs = dict(); let pos = 0;
    while (pos < rest.length) {
      const ws = /^\s+/.exec(rest.slice(pos)); if (ws) pos += ws[0].length;
      if (pos === rest.length) break;
      const a = /^([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/.exec(rest.slice(pos));
      if (!a || Object.hasOwn(attrs, a[1])) fail('xml_attribute_ambiguous');
      attrs[a[1]] = entity(a[2] ?? a[3]); pos += a[0].length;
    }
    const node = {tag:match[1],attrs,children:[],parts:[],text:''}; stack.at(-1).children.push(node);stack.at(-1).parts.push(node);
    if (++nodes > maxNodes) fail('xml_node_limit');
    if (!self) { stack.push(node); if (stack.length > maxDepth) fail('xml_depth_limit'); }
  }
  if (stack.length !== 1 || container.children.length !== 1 || container.text.trim()) fail('xml_document_not_closed');
  return container.children[0];
}
const child = (n, tag) => n.children.find(c => c.tag === tag);
const textOf = n => n ? n.parts.map(p=>typeof p==='string'?p:textOf(p)).join('') : null;

export function parseJavaMapList(text) {
  if (typeof text !== 'string' || text.length > 8 * 1024 * 1024) fail('metadata_size_limit');
  if (text === '[]') return [];
  if (!text.startsWith('[{') || !text.endsWith('}]')) fail('unsupported_java_map_list');
  return text.slice(2, -2).split(/\}, \{(?=item_mstr_id=)/).map(record => {
    const fields = [...record.matchAll(/(?:^|, )([A-Za-z_][A-Za-z0-9_]*)=/g)];
    if (!fields.length || fields[0].index !== 0 || fields[0][1] !== 'item_mstr_id') fail('metadata_record_boundary');
    const values = dict();
    for (let i = 0; i < fields.length; i++) {
      const f = fields[i], key = f[1];
      if (Object.hasOwn(values,key) || !/^(item_mstr_id|form_clft_cd|row_num|col_num|form_ty_cd|col_no|[hbs]_.*)$/.test(key)) fail('metadata_key_unsupported');
      values[key] = record.slice(f.index + f[0].length, i + 1 < fields.length ? fields[i+1].index : record.length);
    }
    return values;
  });
}
// Exact micro-coordinate arithmetic avoids JS binary floating-point guesses.
// Greater than six fractional digits are explicitly unsupported, never rounded.
const dec = v => {
  const m = /^(-?)(\d+)(?:\.(\d{1,6}))?$/.exec(String(v)); if (!m) fail('unsupported_coordinate_precision');
  const n = BigInt(m[2]) * 1000000n + BigInt((m[3] ?? '').padEnd(6,'0'));
  return m[1] ? -n : n;
};
const decString = n => { const sign = n < 0n ? '-' : ''; if (n < 0n) n = -n; return sign + String(n / 1000000n) + ((n % 1000000n) ? '.' + String(n % 1000000n).padStart(6,'0').replace(/0+$/,'') : ''); };
const rect = c => c._rect;
const bound = (x,w) => `${x}:${w}`;
const headerLabel = v => String(v ?? '').replace(/\\\\n/g,'\n').replace(/\\n/g,'\n').trim();
const labelMatches = (h,c) => headerLabel(h.h_col_hdr_krn_nm) === String(c.text ?? '').trim();

export function validateTemplateMetadata(metadata,expectedForm=null){
  const {master,body,header}=metadata;
  if(!Array.isArray(master)||master.length!==1||!Array.isArray(body)||!Array.isArray(header))fail('metadata_master_header_body_required');
  const id=master[0]?.item_mstr_id;
  if(typeof id!=='string'||!id||['null','undefined'].includes(id))fail('metadata_template_id_missing');
  const rows=[...master,...body,...header];
  if(rows.some(r=>!r||typeof r!=='object'||r.item_mstr_id!==id))fail('metadata_template_id_mismatch');
  const forms=rows.filter(r=>Object.hasOwn(r,'form_clft_cd')).map(r=>r.form_clft_cd);
  if(forms.some(f=>typeof f!=='string'||!f)||new Set(forms).size>1||expectedForm&&forms.some(f=>f!==expectedForm))fail('metadata_form_id_mismatch');
  return id;
}
function columnsFrom(metadata,selectors) {
  validateTemplateMetadata(metadata,selectors?.formClassification??(selectors?.level==='school'?'30':selectors?.level==='department'?'36':null));
  const {master,body,header} = metadata;
  if (!Array.isArray(master) || master.length !== 1 || !Array.isArray(body) || !Array.isArray(header)) fail('metadata_master_header_body_required');
  const declared = int(master[0].col_num,1), count = body.length, headerRows = int(master[0].row_num) + 1;
  if (!count || count > 256 || declared > 1000 || headerRows > 100) fail('metadata_column_limit');
  const byBody = new Map(), byHeader = new Map();
  for (const b of body) { const no = int(b.col_no); if (byBody.has(no)) fail('duplicate_body_column'); byBody.set(no,b); }
  for (const h of header) { const no = int(h.col_no); if (byHeader.has(no)) fail('duplicate_header_column'); byHeader.set(no,h); }
  if (byBody.size !== count || body.some((_,i)=>!byBody.has(i)) || byHeader.size !== count * headerRows || header.some((_,i)=>!byHeader.has(i))) fail('metadata_column_gap');
  const columns = [], keys = new Set();
  for (let no = 0; no < count; no++) {
    const b = byBody.get(no); if (!['Y','N'].includes(b.b_col_hid_yn)) fail('column_visibility_unverified');
    if (b.b_col_hid_yn === 'Y') continue;
    const key = b.b_col_id || b.b_col_cd || `column_${String(no).padStart(4,'0')}`;
    if (key.length>200 || keys.has(key) || /token|password|cookie|session|secret|pkey|parg|ubikey|ubiargs/i.test(key)) fail('column_key_ambiguous_or_private');
    keys.add(key); columns.push({key,source_col_no:no,source_field_id:b.b_col_id ?? '',source_semantic_code:b.b_col_cd ?? ''});
  }
  if (!columns.length) fail('no_public_columns');
  return {columns,byHeader,count,headerRows};
}

function expandLeaves(leaves, columns, byHeader, count, headerRows, bordered, headerEnd) {
  const groups = [];
  for (const [no,h] of byHeader) {
    if (h.h_celmrg_yn !== 'Y') continue;
    const row = Math.floor(no/count), col = no%count, rs = int(h.h_row_mrg_cnt,1), cs = int(h.h_col_mrg_cnt,1);
    if (row + rs !== headerRows) continue;
    const covered = columns.filter(c=>c.source_col_no>=col && c.source_col_no<col+cs);
    if (covered.length) groups.push({col,h,covered});
  }
  groups.sort((a,b)=>a.col-b.col);
  if (groups.length !== leaves.length || groups.flatMap(g=>g.covered).map(c=>c.key).join('|') !== columns.map(c=>c.key).join('|')) fail('bottom_header_column_mapping');
  const out = [];
  for (let i=0;i<leaves.length;i++) {
    const leaf = leaves[i], g = groups[i];
    if (!g.h.h_col_hdr_ofcfmla && !labelMatches(g.h,leaf)) fail('bottom_header_label_mismatch');
    if (g.covered.length === 1) { out.push(leaf); continue; }
    if (g.covered.length > 64) fail('bottom_header_partition_limit');
    const [x,,w] = rect(leaf), end = x+w, rectangles = new Map(), starts = new Map();
    for (const c of bordered) { const [xx,yy,ww] = rect(c); if (yy>=headerEnd && xx>=x && xx+ww<=end) rectangles.set(bound(xx,ww),c); }
    for (const c of rectangles.values()) { const [xx,,ww] = rect(c); if (!starts.has(xx)) starts.set(xx,[]); if (!starts.get(xx).includes(ww)) starts.get(xx).push(ww); }
    const memo = new Map();
    const partitions = (pos,remaining) => {
      const key = `${pos}:${remaining}`; if (memo.has(key)) return memo.get(key);
      if (!remaining) return pos===end ? [[]] : [];
      const choices = [];
      for (const ww of starts.get(pos) ?? []) for (const tail of partitions(pos+ww,remaining-1)) { choices.push([[pos,ww],...tail]); if (choices.length>=2) { memo.set(key,choices); return choices; } }
      memo.set(key,choices); return choices;
    };
    const choices = partitions(x,g.covered.length); if (choices.length!==1) fail('body_partition_not_unique');
    for (const [xx,ww] of choices[0]) { const c=rectangles.get(bound(xx,ww)); out.push({...leaf,geometry:{...leaf.geometry,x:c.geometry.x,width:c.geometry.width},_rect:[xx,leaf._rect[1],ww,leaf._rect[3]]}); }
  }
  return out;
}

function parseTable(cells, metadata, pageIndex, selectors) {
  const {columns,byHeader,count,headerRows} = columnsFrom(metadata,selectors);
  const first = headerLabel(byHeader.get(columns[0].source_col_no).h_col_hdr_krn_nm);
  const bordered = cells.filter(c=>c._rect && ![undefined,null,'','0'].includes(c.text_attrs?.border));
  const anchors = bordered.filter(c=>String(c.text??'').trim()===first); if (anchors.length!==1) fail('first_header_not_unique');
  const [ax,ay,,ah]=rect(anchors[0]), headerEnd=ay+ah;
  const headers=bordered.filter(c=>{const [,y,,h]=rect(c);return y>=ay && y<headerEnd && y+h<=headerEnd;});
  let leaves=headers.filter(c=>rect(c)[1]+rect(c)[3]===headerEnd).sort((a,b)=>rect(a)[0]<rect(b)[0]?-1:rect(a)[0]>rect(b)[0]?1:0);
  if (leaves.length<columns.length) leaves=expandLeaves(leaves,columns,byHeader,count,headerRows,bordered,headerEnd);
  if (leaves.length!==columns.length || rect(leaves[0])[0]!==ax) fail('rendered_header_column_count');
  for (let i=1;i<leaves.length;i++) if (rect(leaves[i-1])[0]+rect(leaves[i-1])[2]!==rect(leaves[i])[0]) fail('header_geometry_overlap_or_gap');
  for (let i=0;i<columns.length;i++) {
    const col=columns[i], leaf=leaves[i], [x,,w]=rect(leaf);
    const parents=headers.filter(c=>rect(c)[0]<=x && rect(c)[0]+rect(c)[2]>=x+w).sort((a,b)=>rect(a)[1]<rect(b)[1]?-1:rect(a)[1]>rect(b)[1]?1:rect(a)[3]>rect(b)[3]?-1:1);
    Object.assign(col,{x:leaf.geometry.x,width:leaf.geometry.width,header_path:parents.map(c=>c.text),header_item_indices:parents.map(c=>c.item_index)});
  }
  const byNo=new Map(columns.map(c=>[c.source_col_no,c])), rowEdges=new Map(columns.map(c=>[c.key,new Map([[0,ay],[headerRows,headerEnd]])])), required=new Map(columns.map(c=>[c.key,new Set([0,headerRows])])), assigned=new Set();
  let pending=[];
  for (const [no,h] of byHeader) {
    if (!['Y','N'].includes(h.h_celmrg_yn)) fail('header_merge_flag_unverified');
    if (h.h_celmrg_yn==='N') continue;
    const r=Math.floor(no/count), start=no%count, rs=int(h.h_row_mrg_cnt,1), cs=int(h.h_col_mrg_cnt,1);
    if (r+rs>headerRows || start+cs>count) fail('header_merge_out_of_range');
    const covered=[]; for(let j=start;j<start+cs;j++)if(byNo.has(j))covered.push(byNo.get(j));
    if (!covered.length) continue;
    const keys=covered.map(c=>c.key); for(const key of keys){required.get(key).add(r);required.get(key).add(r+rs);}
    pending.push({h,r,end:r+rs,keys,x:dec(covered[0].x),w:covered.reduce((sum,c)=>sum+dec(c.width),0n)});
  }
  while(pending.length) {
    let progressed=false;const rest=[];
    for(const p of pending) {
      const matches=headers.filter(c=>{
        const [x,y,w,h]=rect(c);
        return !assigned.has(c.item_index) && x===p.x && w===p.w && p.keys.every(k=>(!rowEdges.get(k).has(p.r)||rowEdges.get(k).get(p.r)===y)&&(!rowEdges.get(k).has(p.end)||rowEdges.get(k).get(p.end)===y+h)) && (p.h.h_col_hdr_ofcfmla || labelMatches(p.h,c));
      });
      if(!matches.length) fail('metadata_rendered_header_mismatch');
      if(matches.length!==1){rest.push(p);continue;}
      const c=matches[0],[,y,,h]=rect(c); for(const k of p.keys){rowEdges.get(k).set(p.r,y);rowEdges.get(k).set(p.end,y+h);}
      assigned.add(c.item_index);progressed=true;
    }
    if(!progressed)fail('header_band_boundaries_not_unique');pending=rest;
  }
  for(const [key,edges] of rowEdges){const ns=[...edges.keys()].sort((a,b)=>a-b);if(edges.size!==required.get(key).size||ns.some(n=>!required.get(key).has(n))||ns.some((n,i)=>i && edges.get(ns[i-1])>=edges.get(n)))fail('header_band_gap_or_reversal');}
  if(assigned.size!==headers.length)fail('unmapped_rendered_header');
  const bounds=new Map(columns.map(c=>[bound(dec(c.x),dec(c.width)),c]));
  const bodyBound=c=>{const [x,,w]=rect(c),exact=bound(x,w);if(bounds.has(exact))return exact;const near=columns.filter(col=>{const left=dec(col.x),right=left+dec(col.width),abs=n=>n<0n?-n:n;return abs(x-left)<=1000000n&&abs(x+w-right)<=1000000n;});return near.length===1?bound(dec(near[0].x),dec(near[0].width)):exact;};
  const body=bordered.filter(c=>rect(c)[1]>=headerEnd && bounds.has(bodyBound(c)));if(!body.length)fail('no_mapped_body_cells');
  const boundaries=[...new Set(body.flatMap(c=>[rect(c)[1],rect(c)[1]+rect(c)[3]]))].sort((a,b)=>a<b?-1:a>b?1:0);
  if(boundaries.length>20001)fail('body_band_limit');
  if(boundaries[0]!==headerEnd)fail('header_body_boundary_gap');
  const starts=new Map(),ends=new Map(),active=new Map([...bounds.keys()].map(k=>[k,new Map()]));
  body.forEach((c,i)=>{const[x,y,w,h]=rect(c),b=bodyBound(c);if(!starts.has(y))starts.set(y,[]);if(!ends.has(y+h))ends.set(y+h,[]);starts.get(y).push([i,b,c]);ends.get(y+h).push([i,b,c]);});
  const rows=[],warnings=[],aggregateItems=new Set();let activeCount=0;
  for(let i=0;i<boundaries.length-1;i++){
    const y=boundaries[i],next=boundaries[i+1];for(const[id,b]of ends.get(y)??[]){active.get(b).delete(id);activeCount--;}for(const[id,b,c]of starts.get(y)??[]){active.get(b).set(id,c);activeCount++;}if(!activeCount)continue;
    const values=dict(),dimensions={...selectors},cellSources=dict(),missing=[],ambiguous=[];
    for(const col of columns){const matches=active.get(bound(dec(col.x),dec(col.width)));if(matches.size!==1){(matches.size?ambiguous:missing).push(col.key);values[col.key]=null;}else{const c=[...matches.values()][0];values[col.key]=c.text;cellSources[col.key]={item_index:c.item_index,geometry:c.geometry,expanded_rowspan:rect(c)[1]!==y||rect(c)[3]!==next-y};}
      const name={APY_YR:'refYear',SCHL_NM:'schoolName',MJR_KRN_NM:'deptName'}[col.source_semantic_code]??{APY_YR:'refYear',SCHL_NM:'schoolName',MJR_KRN_NM:'deptName'}[col.source_field_id];if(name)dimensions[name]=values[col.key];}
    let aggregate=null;
    if(selectors?.formClassification==='60'&&columns.length>missing.length&&missing.length>=4&&!ambiguous.length&&JSON.stringify(missing)===JSON.stringify(columns.slice(0,missing.length).map(c=>c.key))){
      const left=dec(columns[0].x),right=dec(columns[missing.length].x),labels=bordered.filter(c=>{const[x,yy,w,h]=rect(c);return x===left&&yy===y&&w===right-left&&h===next-y&&/^(합계(?:\(신입생포함\))?|신입생)$/.test(String(c.text??'').replace(/\s/g,''));});
      if(labels.length===1){aggregate={...labels[0],covered:columns.slice(0,missing.length).map(c=>c.key)};aggregateItems.add(aggregate.item_index);missing.length=0;}
    }
    rows.push({row_number:rows.length+1,source_page_index:pageIndex,source_request_page:pageIndex+1,y:decString(y),height:decString(next-y),values,dimensions,cell_sources:cellSources,status:missing.length||ambiguous.length?'ambiguous':'complete',missing_columns:missing,ambiguous_columns:ambiguous,...(aggregate?{row_kind:'aggregate',merged_identity_label:{text:aggregate.text,geometry:aggregate.geometry,item_index:aggregate.item_index,covered_columns:aggregate.covered}}:{})});
    if(missing.length||ambiguous.length)warnings.push('body_cell_missing_or_ambiguous');
  }
  if(bordered.some(c=>rect(c)[1]>=headerEnd&&rect(c)[1]<boundaries.at(-1)&&!bounds.has(bodyBound(c))&&!aggregateItems.has(c.item_index)))warnings.push('unmapped_body_rectangle');
  return {columns,rows,warnings};
}

export function validateDoc(text,{page}={}) {
  const root=parseXML(text);if(root.tag!=='Doc')fail('not_ubireport_doc');const pages=root.children.filter(c=>c.tag==='Page');if(!pages.length)fail('no_report_page');
  // Match the observed public Python transport: a blank/absent pagenum is not
  // a global index. Only a nonempty source attribute can be cross-checked.
  if(page!==undefined && (pages.length!==1 || pages[0].attrs.pagenum && pages[0].attrs.pagenum!==String(page)))fail('response_page_number_mismatch');
  return {root,pages};
}
export async function parseReportPage(bytes,{pageIndex,metadata,selectors}={}) {
  const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes),{pages}=validateDoc(text,{page:pageIndex+1});
  const cells=[];for(const [i,n]of pages[0].children.entries())if(n.tag==='Item'){
    const t=child(n,'Text'),c={item_index:i,text:textOf(t),text_attrs:t?.attrs,geometry:null};
    if(c.text!==null&&c.text.length>64*1024)fail('display_cell_text_limit');
    if(['x','y','width','height'].every(k=>Object.hasOwn(n.attrs,k))){c.geometry=Object.fromEntries(['x','y','width','height'].map(k=>[k,n.attrs[k]]));c._rect=['x','y','width','height'].map(k=>dec(n.attrs[k]));const line=!t&&n.attrs.classname==='UbiLineItem'&&n.children.length===1&&n.children[0].tag==='Shape';if(c._rect[2]<=0n||c._rect[3]<=0n){if(!line||c._rect[2]<0n||c._rect[3]<0n||c._rect[2]+c._rect[3]<=0n)fail('invalid_cell_dimensions');}}
    cells.push(c);
  }
  let table;try{table=parseTable(cells,metadata,pageIndex,selectors);}catch(e){if(!(e instanceof PortError))throw e;table={columns:[],rows:[],warnings:[e.code]};}
  return {...table,page:{source_page_index:pageIndex,source_request_page:pageIndex+1,source_sha256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join(''),source_byte_length:bytes.byteLength,page_number_verified:Boolean(pages[0].attrs.pagenum),page_number_basis:pages[0].attrs.pagenum?'source_attribute_and_request_selector':'request_selector_with_source_attribute_blank_or_absent'},status:table.rows.length&&!table.warnings.length&&table.rows.every(r=>r.status==='complete')?'complete':table.rows.length?'partial':'raw_only'};
}
export function combinePages(reports,expectedPages) {
  if(!reports.length)fail('no_pages_to_combine');const signature=p=>JSON.stringify(p.columns.map(c=>[c.key,c.source_col_no,c.source_field_id,c.source_semantic_code,c.header_path,c.x,c.width]));
  const byteHashes=new Set(),bodySignatures=new Set();
  for(const p of reports){
    const hash=p.page.source_sha256;
    if(hash&&byteHashes.has(hash))throw new PortError('report_page_payload_repeated','page_combine');
    if(hash)byteHashes.add(hash);
    if(p.rows.length){const body=JSON.stringify({columns:signature(p),rows:p.rows.map(r=>({values:r.values,dimensions:r.dimensions}))});if(bodySignatures.has(body))throw new PortError('report_page_body_repeated','page_combine');bodySignatures.add(body);}
  }
  const baseline=signature(reports[0]),warnings=reports.flatMap(p=>p.warnings),pages=reports.map(p=>p.page),rows=reports.flatMap(p=>p.rows);
  if(reports.some(p=>signature(p)!==baseline))warnings.push('column_schema_changed_between_pages');
  const ids=pages.map(p=>p.source_page_index),received=[...new Set(ids)].sort((a,b)=>a-b),missing=Array.from({length:expectedPages},(_,i)=>i).filter(i=>!received.includes(i)),duplicates=[...new Set(ids.filter((n,i)=>ids.indexOf(n)!==i))],unexpected=received.filter(i=>i>=expectedPages);
  const complete=!missing.length&&!duplicates.length&&!unexpected.length;
  rows.forEach((r,i)=>{r.source_page_row_number=r.row_number;r.row_number=i+1;});
  return {columns:reports[0].columns,rows,pages,warnings,coverage:{expected_pages:expectedPages,received_pages:received,missing_pages:missing,duplicate_pages:duplicates,unexpected_pages:unexpected,complete},status:rows.length&&complete&&!warnings.length&&rows.every(r=>r.status==='complete')?'complete':rows.length?'partial':'raw_only'};
}
