"""Fail CI if a record/secret/archive is tracked. No file contents are printed."""
import subprocess,sys
from pathlib import PurePosixPath
def forbidden(path):
 p=PurePosixPath(path);lower=path.lower()
 return any(x in ('private','backups','__pycache__') for x in p.parts) or p.suffix.lower() in {'.xlsx','.xls','.csv','.zip','.sqlite3','.db','.log','.png'} or '.sqlite3' in lower or p.name=='.env' or p.name.startswith('.env.') or p.name in {'analysis.json','audit-details.json','test_app.py'}
if __name__=='__main__':
 r=subprocess.run(['git','ls-files','-z'],check=True,capture_output=True);bad=[p for p in r.stdout.decode().split('\0') if p and forbidden(p)]
 if bad:print('개인정보·비밀정보가 포함될 수 있는 파일 형식 또는 폴더가 추적되고 있습니다. 업로드를 중지하세요.');sys.exit(1)
 print('추적 파일의 개인정보 폴더·데이터 파일 제외 검사 통과. 내용 검토를 대신하지는 않습니다.')
