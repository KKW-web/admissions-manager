import {requireChatGPTUser} from './chatgpt-auth';
export const dynamic='force-dynamic';
export default async function Home(){await requireChatGPTUser('/');return <iframe src="/shell.html" title="2027 수시진학관리" allow="clipboard-write" style={{width:'100%',height:'100dvh',border:0,display:'block'}}/>;}
