import {handleMCP} from './worker/academyinfo/academyinfo-mcp.mjs';
import {downloadJob} from './worker/academyinfo/academyinfo-port.mjs';
export default {async fetch(request,env){
 const path=new URL(request.url).pathname;
 if(path.startsWith('/api/academyinfo/results/'))return downloadJob(request,env.BUCKET);
 if(path==='/api/academyinfo/mcp')return handleMCP(request,{jobStore:env.BUCKET});
 return new Response('Not found',{status:404});
}};
