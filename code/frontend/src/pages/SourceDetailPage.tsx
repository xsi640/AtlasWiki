import { useParams } from "react-router-dom";
export function SourceDetailPage() { const { id } = useParams(); return <div className="page"><h1>素材</h1><p>素材 ID: {id}</p></div>; }
