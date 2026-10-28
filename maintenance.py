"""Lossless metadata migration. Existing application edits and accounts are preserved."""
import json,datetime,sqlite3
from pathlib import Path
from import_data import connect,schema,norm,MISSING_VALUES

MANAGEMENT_FIELDS={4:'school_type',5:'region',7:'round',8:'track_type',9:'broad_track',11:'field',13:'capacity',14:'selection',15:'minimum_requirement',16:'general_score',17:'grade9',18:'grade5',19:'converted_score',20:'converted_grade',23:'rejection_reason',24:'waitlist',26:'source_registration',27:'note',28:'interview',29:'practical',30:'essay',31:'aptitude',32:'announcement'}
LABELS={'school_type':'학교유형','region':'지역','round':'모집시기','track_type':'전형유형','broad_track':'전형명(대)','field':'계열','capacity':'모집인원','selection':'선발유형','minimum_requirement':'최저학력기준','general_score':'일반점수 (9등급 기준)','grade9':'지원별 일반등급 (9등급)','grade5':'지원별 일반등급 (5등급)','converted_score':'대학 환산점수','converted_grade':'대학 환산등급','rejection_reason':'불합격 사유','waitlist':'최초 후보순위','note':'비고','interview':'면접일','practical':'실기일','essay':'논술일','aptitude':'적성일','announcement':'최종발표일','request_count':'검색기 요청 이력수','evaluation_target':'원본 평가대상명','subject_grades':'교과별 내신 (원본)','result_url':'합불 확인 출처 URL','checked_at':'합불 확인 시각','checked_by':'합불 확인 담당자','result_note':'합불 확인 근거'}
def issue(c,aid,kind,detail):
 if not c.execute('SELECT 1 FROM issues WHERE application_id=? AND kind=? AND detail=?',(aid,kind,detail)).fetchone():c.execute('INSERT INTO issues(application_id,kind,detail) VALUES(?,?,?)',(aid,kind,detail))
def enrich(c):
 schema(c)
 for a in c.execute('SELECT * FROM applications').fetchall():
  existing=c.execute('SELECT data FROM application_details WHERE application_id=?',(a['id'],)).fetchone();d=json.loads(existing[0]) if existing else {};us=[]
  if norm(a['grade']) in MISSING_VALUES:
   d.setdefault('grade_note',a['grade']);c.execute("UPDATE applications SET grade='',version=version+1 WHERE id=?",(a['id'],));c.execute('INSERT INTO audit(actor,action,target,detail) VALUES(?,?,?,?)',('system','migration.grade_missing',str(a['id']),json.dumps({'before':a['grade'],'after':'','reason':'원본 설명문을 숫자 내신과 분리'},ensure_ascii=False)))
  for src in c.execute('SELECT * FROM sources WHERE application_id=? ORDER BY id',(a['id'],)).fetchall():
   r=json.loads(src['raw']);r += [None]*82;us.append(str(r[6] or ''))
   if src['sheet']=='empty':
    for idx,k in MANAGEMENT_FIELDS.items():d.setdefault(k,'' if r[idx] is None else str(r[idx]).strip())
    d.setdefault('subject_grades',{k:r[i] for i,k in enumerate(['국어','영어','수학','사회','과학','전교과'],33)})
   elif src['sheet']=='지원내역':
    d.setdefault('request_count',r[10]);d.setdefault('evaluation_target',r[7]);birth=str(r[9] or '').strip()
    if norm(r[5]) in MISSING_VALUES:d.setdefault('grade_note',str(r[5]))
    if birth:
     old=c.execute('SELECT birthdate FROM student_private WHERE student_id=?',(a['student_id'],)).fetchone()
     if old and old[0]!=birth:issue(c,a['id'],'생년월일 불일치','동일 학생의 검색기 원본 생년월일이 서로 다릅니다. 원본 확인 필요.')
     else:c.execute('INSERT OR IGNORE INTO student_private VALUES(?,?)',(a['student_id'],birth))
  if len({norm(u) for u in us})>1:issue(c,a['id'],'대학명·캠퍼스 확인','기존 자동 통합에서 대학명의 괄호/캠퍼스 표기를 제외했습니다. 대학·전형·학과·수험번호 원본을 교차 확인하세요.')
  for key in ('track','department'):
   if norm(a[key]) in MISSING_VALUES or norm(a[key]).isdigit():issue(c,a['id'],'전형·학과 원자료 미기재',('전형' if key=='track' else '학과')+'의 원본이 미기재 또는 코드입니다. 임의로 이름을 추정하지 않았습니다.')
  c.execute('INSERT INTO application_details VALUES(?,?) ON CONFLICT(application_id) DO UPDATE SET data=excluded.data',(a['id'],json.dumps(d,ensure_ascii=False,default=str)))
 for s in c.execute('SELECT id,grade FROM students').fetchall():
  if norm(s['grade']) in MISSING_VALUES:c.execute("UPDATE students SET grade='' WHERE id=?",(s['id'],))
 # Differences in the two source populations are visible without inventing missing applications.
 for s in c.execute("SELECT id FROM students WHERE status='재학생'").fetchall():
  rows=c.execute('SELECT src.sheet,a.id FROM applications a JOIN sources src ON src.application_id=a.id WHERE a.student_id=?',(s['id'],)).fetchall();sheets={r[0] for r in rows}
  if not rows:continue
  if '지원내역' not in sheets:issue(c,rows[0][1],'검색기에 없는 재학생','진학관리에는 있으나 검색기 지원내역에는 해당 학생이 없습니다. 수험번호·생년월일을 추정 입력하지 않았습니다.')
  if 'empty' not in sheets:issue(c,rows[0][1],'진학관리에 없는 재학생','검색기에는 있으나 진학관리 원본에 해당 학생이 없습니다. 지원별 환산내신·일정 자료를 확인하세요.')
 c.commit()
def backup_and_migrate():
 from import_data import DB
 c=connect();stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');target=DB.parent/'backups'/('before-update-'+stamp+'.sqlite3');target.parent.mkdir(exist_ok=True)
 with sqlite3.connect(target) as out:c.backup(out)
 enrich(c);c.close();return target
if __name__=='__main__':print('백업 및 정보 보완 완료:',backup_and_migrate())
