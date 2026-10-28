"""Local launcher; no Excel dependencies required to run the app."""
import getpass
import socket
import threading
import webbrowser
from pathlib import Path
import server

def main():
 print('이음 · 통합 수시진학관리\n이 창을 닫으면 프로그램이 종료됩니다.\n',flush=True)
 with socket.socket() as sock:
  if sock.connect_ex(('127.0.0.1',8765))==0:
   print('8765 포트가 이미 사용 중입니다. 기존 이음 실행 창이 있으면 해당 창을 이용하세요.')
   input('Enter 키를 눌러 종료합니다.');return
 c=server.connect();server.schema(c)
 from maintenance import enrich
 enrich(c)
 has_admin=c.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone();c.close()
 if not has_admin:
  print('첫 실행입니다. 관리자 계정은 admin 입니다.\n비밀번호는 입력해도 화면에 표시되지 않습니다.\n')
  while True:
   p=getpass.getpass('관리자 비밀번호 (12자 이상): ')
   q=getpass.getpass('비밀번호 다시 입력: ')
   if len(p)<12:print('12자 이상으로 입력하세요.');continue
   if p!=q:print('두 비밀번호가 다릅니다. 다시 입력하세요.');continue
   server.adduser('admin','admin','',p);del p,q;break
  print('\n관리자 계정 설정 완료. 로그인 계정: admin\n')
 url='http://127.0.0.1:8765'
 http=server.ThreadingHTTPServer(('127.0.0.1',8765),server.Handler)
 print('접속 주소: '+url+'\n종료하려면 Ctrl+C 또는 이 창을 닫으세요.',flush=True)
 threading.Timer(1,lambda:webbrowser.open(url)).start()
 try:http.serve_forever()
 except KeyboardInterrupt:pass
 finally:http.server_close()
if __name__=='__main__':
 try:main()
 except Exception as e:
  print('\n실행 오류: '+str(e));input('이 오류 메시지를 알려주세요. Enter 키를 눌러 종료합니다.')
