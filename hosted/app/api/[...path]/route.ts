import {env} from 'cloudflare:workers';
import {getChatGPTUser} from '../../chatgpt-auth';
export const dynamic='force-dynamic';
type Obj=Record<string,any>;
const db=()=>{if(!env.DB)throw Error('DB unavailable');return env.DB;};
const stages=['','미발표','합격','불합격','예비','충원합격','해당없음'];
const detailsFields=['field','track_type','broad_track','region','round','school_type','capacity','selection','minimum_requirement','general_score','grade9','grade5','converted_score','converted_grade','waitlist','rejection_reason','note','interview','practical','essay','aptitude','announcement','result_url','checked_at','checked_by','result_note'];
const labels={field:'계열',track_type:'전형유형',broad_track:'전형명(대)',region:'지역',round:'모집시기',school_type:'학교유형',capacity:'모집인원',selection:'선발유형',minimum_requirement:'최저학력기준',general_score:'일반점수 (9등급)',grade9:'지원별 일반등급 (9등급)',grade5:'지원별 일반등급 (5등급)',converted_score:'대학 환산점수',converted_grade:'대학 환산등급',waitlist:'최초 후보순위',rejection_reason:'불합격 사유',note:'비고',interview:'면접일',practical:'실기일',essay:'논술일',aptitude:'적성일',announcement:'최종발표일',result_url:'합불 확인 출처 URL',checked_at:'합불 확인 시각',checked_by:'합불 확인 담당자',result_note:'합불 확인 근거'};
const response=(data:any,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});
async function rows(sql:string,...args:any[]){return (await db().prepare(sql).bind(...args).all()).results as Obj[];}
async function record(kind:string,id:number){const r=await db().prepare('SELECT payload,version FROM admission_records WHERE kind=? AND id=?').bind(kind,id).first<Obj>();return r?{...JSON.parse(r.payload),version:r.version}:null;}
async function token(id:string){const key=String((env as any).CSRF_KEY||'');if(!key)throw Error('CSRF key unavailable');const imported=await crypto.subtle.importKey('raw',new TextEncoder().encode(key),{name:'HMAC',hash:'SHA-256'},false,['sign']);return Array.from(new Uint8Array(await crypto.subtle.sign('HMAC',imported,new TextEncoder().encode(id)))).map(x=>x.toString(16).padStart(2,'0')).join('');}
function equal(a:string,b:string){if(a.length!==b.length)return false;let n=0;for(let i=0;i<a.length;i++)n|=a.charCodeAt(i)^b.charCodeAt(i);return n===0;}
const pinCookie='__Host-admissions_view';
const pinTTL=4*60*60*1000;
async function pinIdentity(request:Request):Promise<Obj|null>{
 const password=String((env as any).VIEW_PASSWORD||'');if(!password)return null;
 const raw=(request.headers.get('Cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith(pinCookie+'='))?.slice(pinCookie.length+1)||'';
 const match=/^(\d{13})\.([a-f0-9-]{36})\.([a-f0-9]{64})$/.exec(raw);if(!match)return null;
 const expires=Number(match[1]),now=Date.now();if(expires<=now||expires>now+pinTTL+60000)return null;
 const payload=match[1]+'.'+match[2];if(!equal(match[3],await token('view:'+password+':'+payload)))return null;
 return {id:'view:'+match[2],username:'공유 조회',role:'viewer',owner:false,classroom:'',academicYear:'2026',csrf:await token('view-csrf:'+match[2]),shared:true};
}
async function pinLogin(request:Request,b:Obj){
 if(request.headers.get('Origin')!==new URL(request.url).origin)return response({error:'허용되지 않은 요청입니다.'},403);
 const password=String((env as any).VIEW_PASSWORD||'');if(!password)return response({error:'접속 비밀번호가 아직 설정되지 않았습니다.'},503);
 const now=Date.now(),until=now+15*60*1000,ip=request.headers.get('CF-Connecting-IP')||'unknown';
 // Reserve attempts atomically so parallel requests cannot bypass the limit.
 for(const [label,limit] of [['ip:'+await token('pin-ip:'+ip),20],['global',200]] as const){
  const result=await db().prepare("INSERT INTO site_settings(key,value) VALUES(?,json_object('n',1,'until',?)) ON CONFLICT(key) DO UPDATE SET value=CASE WHEN json_extract(value,'$.until')<? THEN excluded.value ELSE json_set(value,'$.n',json_extract(value,'$.n')+1) END RETURNING value").bind('pin-rate:'+label,until,now).first<Obj>();
  if(!result||JSON.parse(result.value).n>limit)return response({error:'접속 시도가 많습니다. 15분 후 다시 시도해 주세요.'},429);
 }
 const supplied=String(b.password||'');if(supplied.length>100||!equal(await token('password:'+supplied),await token('password:'+password)))return response({error:'접속 비밀번호가 맞지 않습니다.'},401);
 const payload=String(now+pinTTL)+'.'+crypto.randomUUID(),signature=await token('view:'+password+':'+payload);
 const r=response({saved:true,role:'viewer'});r.headers.set('Set-Cookie',pinCookie+'='+payload+'.'+signature+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=14400');return r;
}
async function identity(request:Request):Promise<Obj|null>{const user=await getChatGPTUser();if(!user)return pinIdentity(request);
 if(user.email.toLowerCase()===String((env as any).OWNER_EMAIL||'').toLowerCase())await db().prepare('INSERT OR IGNORE INTO site_owner(id,user_id,email) VALUES(1,?,?)').bind(user.userId,user.email).run();
 const owner=await db().prepare('SELECT user_id FROM site_owner WHERE id=1').first<Obj>();
 if(owner?.user_id===user.userId)return {id:user.userId,username:user.email,role:'admin',owner:true,classroom:'',academicYear:'2026',csrf:await token(user.userId)};
 let teacher=await db().prepare('SELECT * FROM teacher_members WHERE active=1 AND (user_id=? OR lower(email)=?) ORDER BY CASE WHEN user_id=? THEN 0 ELSE 1 END LIMIT 1').bind(user.userId,user.email.toLowerCase(),user.userId).first<Obj>();
 if(teacher?.user_id?.startsWith('pending:')){await db().prepare("UPDATE teacher_members SET user_id=? WHERE user_id=? AND active=1").bind(user.userId,teacher.user_id).run();teacher={...teacher,user_id:user.userId};}
 if(teacher?.user_id!==user.userId)teacher=null;
 if(!teacher){const viewer=await pinIdentity(request);if(viewer)return viewer;}
 if(!teacher)return {id:user.userId,username:user.email,role:'denied',classroom:'',csrf:''};
 return {id:user.userId,username:user.email,role:teacher.role==='admin'?'admin':'teacher',owner:false,classroom:teacher.classroom,academicYear:teacher.academic_year,csrf:await token(user.userId)};
}
const auditStatement=(u:Obj,action:string,target:any,detail:any)=>db().prepare('INSERT INTO change_audit(at,actor,action,target,detail) VALUES(?,?,?,?,?)').bind(new Date().toISOString(),u.username,action,String(target),JSON.stringify(detail));
export async function GET(request:Request){try{const url=new URL(request.url),path=url.pathname.slice(5);
 if(path==='transfer-status'){const key=String((env as any).IMPORT_KEY||'');if(!key||!equal(request.headers.get('Authorization')||'','Bearer '+key))return response({error:'접근 권한이 없습니다.'},403);return response({counts:await rows('SELECT kind,COUNT(*) count FROM admission_records GROUP BY kind'),sealed:(await db().prepare("SELECT value FROM site_settings WHERE key='import_sealed'").first<Obj>())?.value==='true'});}
 const u=await identity(request);if(!u)return response({error:'ChatGPT 로그인이 필요합니다.'},401);if(u.role==='denied')return response({error:'담당 반 권한이 지정되지 않았습니다.'},403);
 if(path==='me')return response({...u,hosted:true});
 if(path==='data'){
  if((await db().prepare("SELECT value FROM site_settings WHERE key='import_sealed'").first<Obj>())?.value!=='true')return response({error:'초기 자료를 안전하게 반영하고 있습니다. 잠시 후 새로고침해 주세요.'},503);
  const studentRows=['admin','viewer'].includes(u.role)?await rows("SELECT payload FROM admission_records WHERE kind='students'"):await rows("SELECT payload FROM admission_records WHERE kind='students' AND json_extract(payload,'$.status')='재학생' AND json_extract(payload,'$.year')=? AND json_extract(payload,'$.classroom')=?",u.academicYear,u.classroom);const students=studentRows.map(r=>JSON.parse(r.payload));const ids=new Set(students.map(s=>s.id));
  const apps=(await rows("SELECT payload,version FROM admission_records WHERE kind='applications'")).map(r=>({...JSON.parse(r.payload),version:r.version})).filter(a=>ids.has(a.student_id));const map=new Map(students.map(s=>[s.id,s]));
  const data=apps.map(a=>{const s=map.get(a.student_id);const result={...a,name:s.name,status:s.status,year:s.year,classroom:s.classroom,number:s.number,master_grade:s.grade,details:a.details||{}};if(u.role!=='admin')delete result.birthdate;if(u.role==='viewer'){const safe=['field','track_type','broad_track','region','round','school_type','capacity','selection','minimum_requirement','grade9','grade5','converted_score','converted_grade','waitlist','interview','practical','essay','aptitude','announcement'];result.details=Object.fromEntries(Object.entries(result.details).filter(([k])=>safe.includes(k)));}return result;});
  const issues=u.role==='admin'?(await rows("SELECT payload FROM admission_records WHERE kind='issues'")).map(r=>JSON.parse(r.payload)).filter(i=>!i.resolved):[];
  return response({rows:data,students,issues,detail_labels:labels});
 }
 if(path==='source'&&u.role==='admin')return response((await rows("SELECT payload FROM admission_records WHERE kind='sources' AND application_id=?",Number(url.searchParams.get('id')))).map(r=>JSON.parse(r.payload)));
 if(path==='audit'&&u.role==='admin')return response(await rows('SELECT id,at,actor,action,target FROM change_audit ORDER BY id DESC LIMIT 200'));
 if(path==='members'&&u.owner)return response(await rows('SELECT user_id,email,classroom,role,academic_year,active FROM teacher_members ORDER BY email'));
 if(path==='health')return response({ready:true,storage:'persistent',private:true});return response({error:'허용되지 않은 조회입니다.'},403);
 }catch{return response({error:'저장소를 준비하고 있습니다. 잠시 후 다시 확인해 주세요.'},503);}}

async function importRecords(request:Request,b:Obj){
 const secret=String((env as any).IMPORT_KEY||'');if(!secret||!equal(request.headers.get('Authorization')||'','Bearer '+secret))return response({error:'접근 권한이 없습니다.'},403);
 const sealed=await db().prepare("SELECT value FROM site_settings WHERE key='import_sealed'").first<Obj>();if(sealed?.value==='true')return response({error:'초기 자료 반영이 완료되어 가져오기가 잠겨 있습니다.'},409);
 if(b.finish===true){await db().prepare("INSERT INTO site_settings(key,value) VALUES('import_sealed','true') ON CONFLICT(key) DO UPDATE SET value='true'").run();return response({sealed:true});}
 if(!Array.isArray(b.records)||b.records.length>80)return response({error:'자료 범위 오류'},400);
 const allowed=new Set(['students','applications','sources','issues']);const statements=[];
 for(const r of b.records){if(!allowed.has(r.kind)||!Number.isSafeInteger(r.id)||r.id<1||!r.payload||typeof r.payload!=='object')return response({error:'자료 형식 오류'},400);statements.push(db().prepare('INSERT INTO admission_records(kind,id,student_id,application_id,identity,payload,version) VALUES(?,?,?,?,?,?,?) ON CONFLICT(kind,id) DO NOTHING').bind(r.kind,r.id,r.student_id||null,r.application_id||null,r.kind==='students'?r.payload.identity:null,JSON.stringify(r.payload),r.payload.version||1));}
 if(statements.length)await db().batch(statements);return response({received:b.records.length});
}
export async function POST(request:Request){try{const url=new URL(request.url),path=url.pathname.slice(5);if(Number(request.headers.get('Content-Length')||0)>2500000)return response({error:'요청이 너무 큽니다.'},413);const b=await request.json() as Obj;if(!b||Array.isArray(b)||typeof b!=='object')return response({error:'입력값 오류'},400);
 if(path==='pin-login')return pinLogin(request,b);
 if(path==='import')return importRecords(request,b);
 const u=await identity(request);if(!u)return response({error:'로그인이 필요합니다.'},401);if(u.role==='denied')return response({error:'조회 권한이 없습니다.'},403);if(request.headers.get('Origin')&&request.headers.get('Origin')!==url.origin)return response({error:'허용되지 않은 요청'},403);if(!equal(request.headers.get('X-CSRF')||'',u.csrf))return response({error:'요청 검증 실패'},403);
 if(path==='logout'){const r=response({});r.headers.set('Set-Cookie',pinCookie+'=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0');return r;}if(u.role!=='admin')return response({error:'관리자만 수정할 수 있습니다.'},403);
 if(path==='member'){
  if(!u.owner)return response({error:'공유 권한은 소유자만 설정할 수 있습니다.'},403);const email=String(b.email||'').trim().toLowerCase(),role=String(b.role||'teacher'),classroom=String(b.classroom||'').trim(),year=String(b.academic_year||'2026'),active=b.active===false?0:1;
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254||!['teacher','admin'].includes(role)||!/^\d{4}$/.test(year)||role==='teacher'&&(!/^\d{1,2}$/.test(classroom)||Number(classroom)<1)||email===u.username.toLowerCase())return response({error:'이메일·권한·담당 반을 확인하세요.'},400);
  const old=await db().prepare('SELECT * FROM teacher_members WHERE lower(email)=?').bind(email).first<Obj>();const id=old?.user_id||'pending:'+crypto.randomUUID();await db().batch([db().prepare('INSERT INTO teacher_members(user_id,email,classroom,active,role,academic_year) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET email=excluded.email,classroom=excluded.classroom,active=excluded.active,role=excluded.role,academic_year=excluded.academic_year').bind(id,email,classroom,active,role,year),auditStatement(u,'member.save',id,{email,role,classroom,academic_year:year,active})]);return response({saved:true,site_invitation_required:true});
 }
 if(path==='student'){
  const s=Object.fromEntries(['status','year','classroom','number','name','grade'].map(k=>[k,String(b[k]||'').trim()]));if(!['재학생','졸업생'].includes(s.status)||!/^\d{4}$/.test(s.year)||!/^\d+$/.test(s.classroom)||!/^\d+$/.test(s.number)||!s.name||s.name.length>100||s.grade&&!(Number(s.grade)>=1&&Number(s.grade)<=9))return response({error:'학생 정보를 확인하세요.'},400);
  const duplicate=await db().prepare("SELECT id FROM admission_records WHERE kind='students' AND json_extract(payload,'$.status')=? AND json_extract(payload,'$.year')=? AND json_extract(payload,'$.classroom')=? AND json_extract(payload,'$.number')=? AND json_extract(payload,'$.name')=?").bind(s.status,s.year,s.classroom,s.number,s.name).first();if(duplicate)return response({error:'이미 등록된 학생입니다.'},409);
  const identityKey=[s.status,s.year,s.classroom,s.number,s.name.replace(/\s+/g,'')].join('|');const r=await db().prepare("INSERT INTO admission_records(kind,id,identity,payload) SELECT 'students',next_id,?,json_set(?,'$.id',next_id) FROM (SELECT COALESCE(MAX(id),0)+1 next_id FROM admission_records WHERE kind='students') RETURNING id").bind(identityKey,JSON.stringify({...s,identity:identityKey})).first<Obj>();await auditStatement(u,'student.create',r!.id,s).run();return response({id:r!.id});
 }
 if(path==='application'){
  const fields=['university','track','department','exam','grade','first_stage','final_stage','registration'];const v=Object.fromEntries(fields.map(k=>[k,String(b[k]??'').trim()]));if(fields.some(k=>v[k].length>200)||!v.university||!v.track||!v.department||!stages.includes(v.first_stage)||!stages.includes(v.final_stage)||!['','미등록','등록','등록포기'].includes(v.registration)||v.grade&&!(Number(v.grade)>=1&&Number(v.grade)<=9))return response({error:'지원 정보를 확인하세요.'},400);
  const old=b.id?await record('applications',Number(b.id)):null;if(b.id&&!old)return response({error:'지원이 없습니다.'},404);if(old&&old.version!==b.version)return response({error:'다른 변경이 있습니다. 새로고침 후 확인하세요.'},409);const sid=old?.student_id||Number(b.student_id);if(!await record('students',sid))return response({error:'학생을 선택하세요.'},400);
  const extra={...(old?.details||{})};for(const k of detailsFields){if(!(k in b))continue;const value=String(b[k]??'').trim();if(value.length>2000||k==='result_url'&&value&&!value.startsWith('https://'))return response({error:'상세 정보를 확인하세요.'},400);extra[k]=value;}
  const next={...(old||{}),...v,student_id:sid,details:extra,version:old?old.version+1:1};let id;
  if(old){const r=await db().prepare("UPDATE admission_records SET payload=?,version=version+1 WHERE kind='applications' AND id=? AND version=?").bind(JSON.stringify(next),b.id,b.version).run();if(!r.meta.changes)return response({error:'다른 관리자가 변경했습니다.'},409);id=Number(b.id);}
  else{const r=await db().prepare("INSERT INTO admission_records(kind,id,student_id,payload) SELECT 'applications',next_id,?,json_set(?,'$.id',next_id) FROM (SELECT COALESCE(MAX(id),0)+1 next_id FROM admission_records WHERE kind='applications') RETURNING id").bind(sid,JSON.stringify(next)).first<Obj>();id=r!.id;}
  await auditStatement(u,'application.save',id,{before:old,after:next}).run();return response({id});
 }
 if(path==='resolve'){const note=String(b.resolution||'').trim();if(note.length<5||note.length>1000)return response({error:'검토 근거를 입력하세요.'},400);const i=await record('issues',Number(b.id));if(!i)return response({error:'확인 항목이 없습니다.'},404);await db().batch([db().prepare("UPDATE admission_records SET payload=json_set(payload,'$.resolved',1,'$.resolution',?),version=version+1 WHERE kind='issues' AND id=?").bind(note,Number(b.id)),auditStatement(u,'issue.resolve',b.id,note)]);return response({});}
 if(path==='merge'){
  const keep=Number(b.keep),drop=Number(b.drop),a=await record('applications',keep),d=await record('applications',drop),note=String(b.resolution||'').trim();if(!a||!d||keep===drop||a.student_id!==d.student_id||note.length<5)return response({error:'동일 학생의 지원과 검토 근거를 확인하세요.'},400);
  if(a.version!==b.keep_version||d.version!==b.drop_version)return response({error:'지원 정보가 변경됐습니다.'},409);for(const k of ['exam','first_stage','final_stage','registration'])if(a[k]&&d[k]&&a[k]!==d[k])return response({error:'수험번호 또는 합격·등록 상태가 충돌합니다.'},409);
  const extras={...(a.details||{})},conflicts:Obj[]=[];for(const [k,v] of Object.entries(d.details||{})){if(extras[k]===''||extras[k]==null)extras[k]=v;else if(v!==''&&v!=null&&JSON.stringify(extras[k])!==JSON.stringify(v))conflicts.push({field:k,kept:extras[k],other:v});}
  const next={...a,details:extras,version:a.version+1};for(const k of ['exam','grade','first_stage','final_stage','registration'])if(!next[k])next[k]=d[k];
  const guard=crypto.randomUUID();const present='EXISTS(SELECT 1 FROM mutation_guards WHERE token=?)';const result=await db().batch([
   db().prepare("INSERT INTO mutation_guards(token) SELECT ? WHERE (SELECT version FROM admission_records WHERE kind='applications' AND id=?)=? AND (SELECT version FROM admission_records WHERE kind='applications' AND id=?)=?").bind(guard,keep,a.version,drop,d.version),
   db().prepare("UPDATE admission_records SET payload=?,version=version+1 WHERE kind='applications' AND id=? AND "+present).bind(JSON.stringify(next),keep,guard),
   db().prepare("UPDATE admission_records SET application_id=?,payload=json_set(payload,'$.application_id',?) WHERE kind IN ('sources','issues') AND application_id=? AND "+present).bind(keep,keep,drop,guard),
   db().prepare("DELETE FROM admission_records WHERE kind='applications' AND id=? AND "+present).bind(drop,guard),
   db().prepare('INSERT INTO change_audit(at,actor,action,target,detail) SELECT ?,?,?,?,? WHERE '+present).bind(new Date().toISOString(),u.username,'application.merge',String(keep),JSON.stringify({before_keep:a,removed:d,note}),guard),
   ...conflicts.map(detail=>db().prepare("INSERT INTO admission_records(kind,id,application_id,payload) SELECT 'issues',next_id,?,json_object('id',next_id,'application_id',?,'kind','병합 후 값 확인','detail',?,'resolved',0,'resolution','') FROM (SELECT COALESCE(MAX(id),0)+1 next_id FROM admission_records WHERE kind='issues') WHERE "+present).bind(keep,keep,JSON.stringify(detail),guard)),
   db().prepare('DELETE FROM mutation_guards WHERE token=?').bind(guard)
  ]);if(!result[0].meta.changes)return response({error:'다른 변경이 있습니다. 새로고침 후 다시 확인하세요.'},409);return response({});
 }
 return response({error:'지원하지 않는 작업입니다.'},404);
 }catch{return response({error:'처리하지 못했습니다. 입력값을 확인하고 다시 시도하세요.'},400);}}
