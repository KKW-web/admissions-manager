import json, sqlite3, re, hashlib, sys
from pathlib import Path
ROOT=Path(__file__).parent
DB=ROOT/'private'/'admissions.sqlite3'
def norm(x): return re.sub(r'\s+','',str(x or '')).strip()
def uni(x): return re.sub(r'\([^)]*\)','',norm(x))
def text(x): return '' if x is None else str(x).strip()
MISSING_VALUES={'자료없음','자료미기재','미기재','미확인','없음','-','\'-'}
def grade_value(x):return '' if norm(x) in MISSING_VALUES else text(x)
def connect():
 DB.parent.mkdir(exist_ok=True); c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def schema(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY,identity TEXT UNIQUE,status TEXT,year TEXT,classroom TEXT,number TEXT,name TEXT,grade TEXT);
 CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY,student_id INTEGER REFERENCES students(id),university TEXT,track TEXT,department TEXT,exam TEXT DEFAULT '',grade TEXT DEFAULT '',first_stage TEXT DEFAULT '',final_stage TEXT DEFAULT '',registration TEXT DEFAULT '',version INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,application_id INTEGER REFERENCES applications(id),file TEXT,sheet TEXT,rownum INTEGER,raw TEXT,UNIQUE(file,sheet,rownum));
 CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY,application_id INTEGER REFERENCES applications(id),kind TEXT,detail TEXT,resolved INTEGER DEFAULT 0,resolution TEXT DEFAULT '');
 CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,salt TEXT,password TEXT,role TEXT,classroom TEXT,active INTEGER DEFAULT 1);
 CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT DEFAULT CURRENT_TIMESTAMP,actor TEXT,action TEXT,target TEXT,detail TEXT);
 CREATE TABLE IF NOT EXISTS imports(hash TEXT PRIMARY KEY,file TEXT,rows INTEGER);
 CREATE TABLE IF NOT EXISTS application_details(application_id INTEGER PRIMARY KEY REFERENCES applications(id),data TEXT NOT NULL DEFAULT '{}');
 CREATE TABLE IF NOT EXISTS student_private(student_id INTEGER PRIMARY KEY REFERENCES students(id),birthdate TEXT NOT NULL DEFAULT '');
 ''')
def load(path,sheet):
 import openpyxl
 w=openpyxl.load_workbook(path,read_only=True,data_only=True); s=w[sheet] if sheet else w.active; s.reset_dimensions(); rows=list(s.values); w.close(); return rows
def ingest(paths):
 c=connect();schema(c); counts={}
 for kind,path in paths:
  digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
  if c.execute('SELECT 1 FROM imports WHERE hash=?',(digest,)).fetchone(): continue
  rows=load(path,'지원내역' if kind=='search' else None); count=0
  for rn,r in enumerate(rows,1):
   r=list(r)+[None]*82
   if kind=='search':
    if rn<2 or r[0] not in ('재학생','졸업생') or not r[4]: continue
    status,year,cl,num,name,grade,u,rawtrack,exam=r[:9]; track,dept=r[20:22]
    if not track or not dept: track,dept='',text(rawtrack)
    first=final=reg=''
   else:
    if rn<3 or not r[3] or not r[6]:continue
    status,year='재학생',2026; cl,num,name=r[1:4];u=r[6];track=r[10];dept=r[12];exam='';grade=r[38];first,final=r[21:23];reg=r[26]
   vals=list(map(text,[status,year,cl,num,name,grade_value(grade),u,track,dept,exam,first,final,reg]));status,year,cl,num,name,grade,u,track,dept,exam,first,final,reg=vals
   identity='|'.join([status,year,cl,num,norm(name)])
   c.execute('INSERT OR IGNORE INTO students(identity,status,year,classroom,number,name,grade) VALUES(?,?,?,?,?,?,?)',(identity,status,year,cl,num,name,grade))
   s=c.execute('SELECT * FROM students WHERE identity=?',(identity,)).fetchone(); sid=s['id']
   candidates=c.execute('SELECT * FROM applications WHERE student_id=?',(sid,)).fetchall()
   exact=[a for a in candidates if norm(a['university'])==norm(u) and norm(a['department'])==norm(dept) and norm(a['track'])==norm(track)]
   if len(exact)==1 and (not exam or not exact[0]['exam'] or exam==exact[0]['exam']):
    a=exact[0];aid=a['id']
    c.execute("UPDATE applications SET exam=CASE WHEN exam='' THEN ? ELSE exam END WHERE id=?",(exam,aid))
   else:
    aid=c.execute('INSERT INTO applications(student_id,university,track,department,exam,grade,first_stage,final_stage,registration) VALUES(?,?,?,?,?,?,?,?,?)',(sid,u,track,dept,exam,grade,first,final,reg)).lastrowid
    near=[a['id'] for a in candidates if uni(a['university'])==uni(u)]
    if near:c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(aid,'지원 건 대조 필요',json.dumps({'candidate_ids':near,'reason':'동일 학생·대학, 전형/학과 또는 수험번호 불일치. 자동 병합 안 함'},ensure_ascii=False)))
   if grade and s['grade'] and norm(grade)!=norm(s['grade']): c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(aid,'내신 불일치',json.dumps({'master':s['grade'],'source':grade},ensure_ascii=False)))
   if not track or not dept:c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(aid,'전형/학과 확인','원본 분리 필드가 비어 있음. 임의 하이픈 분할 안 함'))
   c.execute('INSERT INTO sources(application_id,file,sheet,rownum,raw) VALUES(?,?,?,?,?)',(aid,Path(path).name,'지원내역' if kind=='search' else 'empty',rn,json.dumps(r[:82],ensure_ascii=False,default=str)))
   count+=1
  c.execute('INSERT INTO imports VALUES(?,?,?)',(digest,Path(path).name,count));counts[kind]=count
 # Same historical class/number with different names is never silently joined.
 for row in c.execute('SELECT status,year,classroom,number,COUNT(*) n FROM students GROUP BY status,year,classroom,number HAVING n>1').fetchall():
  for s in c.execute('SELECT id FROM students WHERE status=? AND year=? AND classroom=? AND number=?',tuple(row)[:4]):
   a=c.execute('SELECT id FROM applications WHERE student_id=? LIMIT 1',(s[0],)).fetchone()
   c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(a[0],'학생 식별 충돌','동일 재학구분·자료학년도·반·번호에 서로 다른 이름. 별도 학생으로 보존'))
 c.commit()
 report={'imported_rows':counts,'students':dict(c.execute('SELECT status,count(*) FROM students GROUP BY status').fetchall()),'applications':c.execute('SELECT count(*) FROM applications').fetchone()[0],'source_rows':c.execute('SELECT count(*) FROM sources').fetchone()[0],'issues':dict(c.execute('SELECT kind,count(*) FROM issues GROUP BY kind').fetchall()),'exam_missing':c.execute("SELECT count(*) FROM applications WHERE exam='' ").fetchone()[0]}
 (ROOT/'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));c.close()
if __name__=='__main__': ingest([('management',sys.argv[1]),('search',sys.argv[2])])
