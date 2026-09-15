import { useParams } from "react-router-dom";
export function ZoneDetailPage() { const { name } = useParams(); return <div className="page"><h1>分区: {name}</h1></div>; }
