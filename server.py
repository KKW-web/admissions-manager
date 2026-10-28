import json,secrets,hashlib,hmac,time,sqlite3,os,sys,getpass
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path
from import_data import connect,schema
from maintenance import LABELS
ROOT=Path(__file__).parent
SESSIONS={};FAILURES={}
STAGES=['','미발표','합격','불합격','예비','충원합격','해당없음']
DETAIL_FIELDS=['field','track_type','broad_track','region','round','school_type','capacity','selection','minimum_requirement','general_score','grade9','grade5','converted_score','converted_grade','waitlist','rejection_reason','note','interview','practical','essay','aptitude','announcement','result_url','checked_at','checked_by','result_note']
def password(p,s):return hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),600000).hex()
def adduser(username,role,cl,p):
 if role not in ('admin','teacher') or (role=='teacher' and not cl):raise ValueError('담임은 담당 반 필수')
 if len(p)<12:raise ValueError('비밀번호 12자 이상 필요')
 c=connect();schema(c);s=secrets.token_hex(16);c.execute('INSERT OR REPLACE INTO users VALUES(?,?,?,?,?,1)',(username,s,password(p,s),role,cl));c.commit();c.close()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,obj,code=200):
  data=json.dumps(obj,ensure_ascii=False).encode();self.send_response(code);self.headers_out('application/json; charset=utf-8');self.end_headers();self.wfile.write(data)
 def headers_out(self,typ):
  self.send_header('Content-Type',typ);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>32768:raise ValueError('요청이 너무 큽니다')
  if n<0:raise ValueError()
  value=json.loads(self.rfile.read(n) or '{}')
  if not isinstance(value,dict):raise ValueError()
  return value
 def session(self):
  cookie=self.headers.get('Cookie',''); token=next((x.strip()[4:] for x in cookie.split(';') if x.strip().startswith('sid=')),'');s=SESSIONS.get(token)
  if not s or s['expires']<time.time():return None
  c=connect();u=c.execute('SELECT username,role,classroom FROM users WHERE username=? AND active=1',(s['username'],)).fetchone();c.close()
  return {**dict(u),'csrf':s['csrf']} if u else None
 def do_GET(self):
  path=urlparse(self.path).path
  if path in ('/','/app.js','/style.css'):
   f=ROOT/'static'/({'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]);self.send_response(200);self.headers_out({'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css'}[f.suffix]);self.end_headers();self.wfile.write(f.read_bytes());return
  u=self.session()
  if not u:return self.send({'error':'로그인이 필요합니다'},401)
  c=connect()
  try:
   if path=='/api/me':return self.send(u)
   if path=='/api/data':
    where='' if u['role']=='admin' else " WHERE s.status='재학생' AND s.year='2026' AND s.classroom=?"
    args=() if u['role']=='admin' else (u['classroom'],)
    rows=[dict(r) for r in c.execute('SELECT a.*,s.name,s.status,s.year,s.classroom,s.number,s.grade master_grade FROM applications a JOIN students s ON s.id=a.student_id'+where+' ORDER BY CAST(s.classroom AS INTEGER),CAST(s.number AS INTEGER),a.id',args)]
    details={r[0]:json.loads(r[1]) for r in c.execute('SELECT application_id,data FROM application_details')}
    private={r[0]:r[1] for r in c.execute('SELECT student_id,birthdate FROM student_private')} if u['role']=='admin' else {}
    for r in rows:
     r['details']=details.get(r['id'],{})
     if u['role']=='admin':r['birthdate']=private.get(r['student_id'],'')
    students=[dict(r) for r in c.execute('SELECT id,name,status,year,classroom,number,grade FROM students'+('' if u['role']=='admin' else " WHERE status='재학생' AND year='2026' AND classroom=?"),args)]
    issues=[dict(r) for r in c.execute('SELECT * FROM issues WHERE resolved=0')] if u['role']=='admin' else []
    return self.send({'rows':rows,'issues':issues,'students':students,'detail_labels':LABELS})
   if path=='/api/source' and u['role']=='admin':
    aid=parse_qs(urlparse(self.path).query).get('id',['0'])[0];return self.send([dict(r) for r in c.execute('SELECT file,sheet,rownum,raw FROM sources WHERE application_id=?',(aid,))])
   if path=='/api/audit' and u['role']=='admin':
    return self.send([dict(r) for r in c.execute('SELECT id,at,actor,action,target FROM audit ORDER BY id DESC LIMIT 200')])
   return self.send({'error':'접근할 수 없습니다'},403)
  finally:c.close()
 def do_POST(self):
  try:self.post()
  except (ValueError,KeyError,TypeError):self.send({'error':'입력값을 확인하세요'},400)
  except sqlite3.Error:self.send({'error':'저장 실패. 다시 확인하세요'},409)
 def post(self):
  if self.headers.get('Origin') and self.headers['Origin']!='http://'+self.headers.get('Host',''):return self.send({'error':'허용되지 않은 요청'},403)
  b=self.body();path=urlparse(self.path).path;c=connect()
  try:
   if path=='/api/login':
    ip=self.client_address[0]; failures=FAILURES.get(ip,[]);failures=[t for t in failures if t>time.time()-900]
    if len(failures)>=10:return self.send({'error':'잠시 후 다시 시도하세요'},429)
    u=c.execute('SELECT * FROM users WHERE username=? AND active=1',(b.get('username',''),)).fetchone()
    if not u or not hmac.compare_digest(password(b.get('password',''),u['salt']),u['password']):FAILURES[ip]=failures+[time.time()];return self.send({'error':'계정 또는 비밀번호를 확인하세요'},401)
    token=secrets.token_urlsafe(32);SESSIONS[token]={'username':u['username'],'csrf':secrets.token_urlsafe(32),'expires':time.time()+3600}
    self.send_response(200);self.headers_out('application/json');self.send_header('Set-Cookie',f'sid={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600');self.end_headers();self.wfile.write(b'{}');return
   u=self.session()
   if not u:return self.send({'error':'로그인 필요'},401)
   if not hmac.compare_digest(self.headers.get('X-CSRF',''),u['csrf']):return self.send({'error':'요청 검증 실패'},403)
   if path=='/api/logout':
    for k in list(SESSIONS):
     if SESSIONS[k]['csrf']==u['csrf']:del SESSIONS[k]
    return self.send({})
   if u['role']!='admin':return self.send({'error':'관리자만 수정할 수 있습니다'},403)
   c.execute('BEGIN IMMEDIATE')
   if path=='/api/student':
    v=[str(b.get(k,'')).strip() for k in ['status','year','classroom','number','name','grade']]
    if v[0] not in ('재학생','졸업생') or not all(v[:5]) or not all(x.isdigit() for x in v[1:4]) or any(len(x)>100 for x in v):raise ValueError()
    if v[5] and not 1<=float(v[5])<=9:raise ValueError()
    identity='|'.join(v[:4]+[''.join(v[4].split())]);sid=c.execute('INSERT INTO students(identity,status,year,classroom,number,name,grade) VALUES(?,?,?,?,?,?,?)',(identity,*v)).lastrowid
    c.execute('INSERT INTO audit(actor,action,target,detail) VALUES(?,?,?,?)',(u['username'],'student.create',str(sid),'관리자 입력'));c.commit();return self.send({'id':sid})
   if path=='/api/merge':
    keep,drop=int(b['keep']),int(b['drop']);note=str(b.get('resolution','')).strip()
    if keep==drop or len(note)<5:raise ValueError()
    a=c.execute('SELECT * FROM applications WHERE id=?',(keep,)).fetchone();d=c.execute('SELECT * FROM applications WHERE id=?',(drop,)).fetchone()
    if not a or not d or a['student_id']!=d['student_id']:raise ValueError()
    if b.get('keep_version')!=a['version'] or b.get('drop_version')!=d['version']:return self.send({'error':'지원 정보가 변경되었습니다. 새로 확인한 뒤 병합하세요'},409)
    if a['exam'] and d['exam'] and a['exam']!=d['exam']:return self.send({'error':'수험번호 충돌: 병합할 수 없습니다'},409)
    for k in ['first_stage','final_stage','registration']:
     if a[k] and d[k] and a[k]!=d[k]:return self.send({'error':'합격/등록 상태 충돌: 먼저 수정하세요'},409)
    for k in ['exam','grade','first_stage','final_stage','registration']:
     if not a[k] and d[k]:c.execute('UPDATE applications SET '+k+'=? WHERE id=?',(d[k],keep))
    da=c.execute('SELECT data FROM application_details WHERE application_id=?',(keep,)).fetchone();dd=c.execute('SELECT data FROM application_details WHERE application_id=?',(drop,)).fetchone();merged=json.loads(da[0]) if da else {};other=json.loads(dd[0]) if dd else {}
    for k,v in other.items():
     if merged.get(k) in ('',None):merged[k]=v
     elif v not in ('',None) and merged[k]!=v:
      c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(keep,'병합 후 값 확인',json.dumps({'field':k,'kept':merged[k],'other':v},ensure_ascii=False)))
    c.execute('DELETE FROM application_details WHERE application_id=?',(drop,));c.execute('INSERT INTO application_details VALUES(?,?) ON CONFLICT(application_id) DO UPDATE SET data=excluded.data',(keep,json.dumps(merged,ensure_ascii=False)))
    c.execute('UPDATE sources SET application_id=? WHERE application_id=?',(keep,drop));c.execute('UPDATE issues SET application_id=? WHERE application_id=?',(keep,drop));c.execute('DELETE FROM applications WHERE id=?',(drop,));c.execute('UPDATE applications SET version=version+1 WHERE id=?',(keep,));c.execute('INSERT INTO audit(actor,action,target,detail) VALUES(?,?,?,?)',(u['username'],'application.merge',str(keep),json.dumps({'removed':dict(d),'kept_before':dict(a),'removed_details':other,'kept_details_before':json.loads(da[0]) if da else {},'note':note},ensure_ascii=False)));c.commit();return self.send({})
   if path=='/api/application':
    fields=['university','track','department','exam','grade','first_stage','final_stage','registration'];v=[str(b.get(k,'')).strip() for k in fields]
    if any(len(x)>200 for x in v) or not all(v[:3]) or v[5] not in STAGES or v[6] not in STAGES or v[7] not in ('','미등록','등록','등록포기'):raise ValueError()
    if v[4] and not 1<=float(v[4])<=9:raise ValueError()
    if b.get('id'):
     old=c.execute('SELECT * FROM applications WHERE id=?',(b['id'],)).fetchone()
     if not old:return self.send({'error':'지원 건 없음'},404)
     result=c.execute('UPDATE applications SET '+','.join(k+'=?' for k in fields)+',version=version+1 WHERE id=? AND version=?',(*v,b['id'],b['version']))
     if result.rowcount!=1:return self.send({'error':'다른 관리자가 수정했습니다. 새로고침 후 다시 확인하세요'},409)
     aid=b['id']
    else:
     sid=int(b['student_id'])
     if not c.execute('SELECT 1 FROM students WHERE id=?',(sid,)).fetchone():raise ValueError()
     aid=c.execute('INSERT INTO applications(student_id,'+','.join(fields)+') VALUES('+','.join('?' for _ in range(9))+')',(sid,*v)).lastrowid;old={}
    prev=c.execute('SELECT data FROM application_details WHERE application_id=?',(aid,)).fetchone();extra=json.loads(prev[0]) if prev else {};before_extra=dict(extra)
    for k in DETAIL_FIELDS:
     if k not in b:continue
     value=str(b[k]).strip()
     if len(value)>2000:raise ValueError()
     if k=='result_url' and value and not value.startswith('https://'):raise ValueError()
     extra[k]=value
    c.execute('INSERT INTO application_details VALUES(?,?) ON CONFLICT(application_id) DO UPDATE SET data=excluded.data',(aid,json.dumps(extra,ensure_ascii=False)))
    c.execute('INSERT INTO audit(actor,action,target,detail) VALUES(?,?,?,?)',(u['username'],'application.save',str(aid),json.dumps({'before':dict(old),'after':dict(zip(fields,v)),'details_before':before_extra,'details_after':extra},ensure_ascii=False)));c.commit();return self.send({'id':aid})
   if path=='/api/resolve':
    note=str(b.get('resolution','')).strip()
    if len(note)<5 or len(note)>1000:raise ValueError()
    c.execute('UPDATE issues SET resolved=1,resolution=? WHERE id=?',(note,int(b['id'])));c.execute('INSERT INTO audit(actor,action,target,detail) VALUES(?,?,?,?)',(u['username'],'issue.resolve',str(b['id']),note));c.commit();return self.send({})
   return self.send({'error':'없는 기능'},404)
  finally:c.close()
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='user':adduser(sys.argv[2],sys.argv[3],sys.argv[4] if len(sys.argv)>4 else '',getpass.getpass('Password (12+): '));print('계정 저장 완료')
 else:
  from maintenance import enrich
  c=connect();schema(c);enrich(c);c.close();print('Local: http://127.0.0.1:8765',flush=True);ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
