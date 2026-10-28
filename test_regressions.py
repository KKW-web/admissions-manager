"""Synthetic fixtures only. Safe to run in CI without student records."""
import unittest,tempfile,threading,json,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
import import_data,server
from maintenance import enrich

def seed(c):
 import_data.schema(c)
 for sid,status,year,cl,name in [(1,'재학생','2026','1','예시학생가'),(2,'재학생','2026','2','예시학생나'),(3,'졸업생','2025','1','예시졸업생'),(4,'재학생','2026','1','지원없는예시학생')]:
  c.execute('INSERT INTO students VALUES(?,?,?,?,?,?,?,?)',(sid,str(sid),status,year,cl,'1',name,'3.2'))
 for aid,sid,exam in [(1,1,''),(2,1,'00123456'),(3,2,'00876543'),(4,3,'00999999')]:
  c.execute('INSERT INTO applications(id,student_id,university,track,department,exam,grade) VALUES(?,?,?,?,?,?,?)',(aid,sid,'예시대학(본교)' if aid==1 else '예시대학','예시전형','예시학과',exam,'자료 없음' if sid==3 else '3.2'))
 r=[None]*82;r[6]='예시대학(본교)';r[17]='3.8';r[18]='2.7';r[19]='823';r[20]='2.2';r[28]='2026-11-01';r[32]='2026-12-01';r[38]=3.2
 c.execute('INSERT INTO sources(application_id,file,sheet,rownum,raw) VALUES(?,?,?,?,?)',(1,'example-management.xlsx','empty',3,json.dumps(r)))
 r=[None]*82;r[:10]=['재학생',2026,1,1,'예시학생가',3.2,'예시대학','예시전형-예시학과','00123456','080101'];r[20:22]=['예시전형','예시학과']
 c.execute('INSERT INTO sources(application_id,file,sheet,rownum,raw) VALUES(?,?,?,?,?)',(2,'example-search.xlsx','지원내역',2,json.dumps(r)))
 c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(2,'지원 건 대조 필요',json.dumps({'candidate_ids':[1]})));c.commit();enrich(c)

class Regression(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root=Path(__file__).parent/'private'/'test-runs';root.mkdir(parents=True,exist_ok=True);cls.tmp=tempfile.TemporaryDirectory(dir=root);cls.old=import_data.DB;import_data.DB=Path(cls.tmp.name)/'test.sqlite3';c=import_data.connect();seed(c);c.close()
  cls.p='Synthetic-test-password-2027';server.adduser('qa-admin','admin','',cls.p);server.adduser('qa-teacher','teacher','1',cls.p);server.SESSIONS.clear();server.FAILURES.clear();cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.url='http://127.0.0.1:'+str(cls.http.server_port);threading.Thread(target=cls.http.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();server.SESSIONS.clear();import_data.DB=cls.old;cls.tmp.cleanup()
 def req(self,op,path,b=None,csrf=''):
  req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(b).encode() if b is not None else None,headers={'Content-Type':'application/json','X-CSRF':csrf})
  try:
   with op.open(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def client(self,role):
  op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.assertEqual(self.req(op,'login',{'username':'qa-'+role,'password':self.p})[0],200);return op,self.req(op,'me')[1]['csrf']
 def test_1_teacher_scope_and_privacy(self):
  op,token=self.client('teacher');d=self.req(op,'data')[1];self.assertEqual({r['student_id'] for r in d['rows']},{1});self.assertEqual({s['id'] for s in d['students']},{1,4});self.assertTrue(all('birthdate' not in r for r in d['rows']));self.assertNotIn('080101',json.dumps(d));self.assertEqual(self.req(op,'source?id=1')[0],403);self.assertEqual(self.req(op,'audit')[0],403);self.assertEqual(self.req(op,'student',{},token)[0],403)
 def test_2_metadata_migration_and_zero(self):
  op,token=self.client('admin');d=self.req(op,'data')[1];r=next(r for r in d['rows'] if r['id']==1);self.assertEqual(r['details']['interview'],'2026-11-01');self.assertEqual(r['details']['grade9'],'3.8');self.assertEqual(r['details']['grade5'],'2.7');self.assertEqual(r['birthdate'],'080101');self.assertEqual(r['first_stage'],'');self.assertEqual(r['final_stage'],'')
  self.assertEqual(self.req(op,'application',dict(r,exam='00001234'),token)[0],200);new=next(x for x in self.req(op,'data')[1]['rows'] if x['id']==1);self.assertEqual(new['exam'],'00001234');self.assertEqual(new['details'],r['details']);self.assertEqual(self.req(op,'application',r,token)[0],409)
  self.assertEqual(self.req(op,'application',dict(new,interview='changed',result_url='https://example.edu/results',checked_at='2026-10-28T19:00+09:00'),token)[0],200)
  saved=next(x for x in self.req(op,'data')[1]['rows'] if x['id']==1);self.assertEqual(saved['details']['interview'],'changed');self.assertEqual(saved['details']['grade5'],'2.7');self.assertEqual(self.req(op,'application',dict(saved,result_url='javascript:alert(1)'),token)[0],400);after=next(x for x in self.req(op,'data')[1]['rows'] if x['id']==1);self.assertEqual(after['version'],saved['version'])
 def test_3_merge_guard_and_preservation(self):
  op,token=self.client('admin');d=self.req(op,'data')[1];a,b=(next(x for x in d['rows'] if x['id']==i) for i in (1,2));self.assertEqual(self.req(op,'merge',{'keep':1,'drop':2,'resolution':'원본 확인 완료','keep_version':0,'drop_version':1},token)[0],409)
  # Restore the test fixture's exam conflict with a version-aware normal edit.
  a['exam']='';self.assertEqual(self.req(op,'application',a,token)[0],200);a=next(x for x in self.req(op,'data')[1]['rows'] if x['id']==1)
  self.assertEqual(self.req(op,'merge',{'keep':1,'drop':2,'resolution':'원본 확인 완료','keep_version':a['version'],'drop_version':b['version']},token)[0],200);d=self.req(op,'data')[1];r=next(x for x in d['rows'] if x['id']==1);self.assertEqual(r['exam'],'00123456');self.assertTrue(r['details']['interview']);c=import_data.connect();self.assertEqual(c.execute('SELECT count(*) FROM sources WHERE application_id=1').fetchone()[0],2);self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall());c.close()
 def test_4_anonymous_csrf_and_invalid_grade(self):
  op=urllib.request.build_opener();self.assertEqual(self.req(op,'data')[0],401);op,t=self.client('admin');self.assertEqual(self.req(op,'student',{},'')[0],403);self.assertEqual(self.req(op,'student',{'status':'재학생','year':'2026','classroom':'1','number':'5','name':'예시학생','grade':'10'},t)[0],400)
 def test_5_missing_alumni_grade_can_be_saved(self):
  op,t=self.client('admin');r=next(x for x in self.req(op,'data')[1]['rows'] if x['id']==4);self.assertEqual(r['grade'],'');self.assertEqual(r['details']['grade_note'],'자료 없음');self.assertEqual(self.req(op,'application',dict(r,final_stage='합격'),t)[0],200)
if __name__=='__main__':unittest.main()
