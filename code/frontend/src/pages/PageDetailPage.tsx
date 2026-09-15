import { useParams } from "react-router-dom";
export function PageDetailPage() { const { name } = useParams(); return <div className="page"><h1>页面</h1><p>正在查看: {name}</p></div>; }
