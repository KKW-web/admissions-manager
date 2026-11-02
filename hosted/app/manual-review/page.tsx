import {requireChatGPTUser} from '../chatgpt-auth';
export const dynamic='force-dynamic';
export default async function ManualReview(){await requireChatGPTUser('/manual-review');return <iframe src="/manual-review.html" title="가천대 수동 조회 도우미" allow="clipboard-write" style={{width:'100%',height:'100dvh',border:0,display:'block'}}/>;}
