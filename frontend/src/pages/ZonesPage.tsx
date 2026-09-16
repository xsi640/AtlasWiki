import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ZoneInfo } from "../api/types";

export function ZonesPage() {
  const [zones, setZones] = useState<ZoneInfo[] | null>(null);

  useEffect(() => {
    api
      .get<ZoneInfo[]>("/zones")
      .then(setZones)
      .catch(() => setZones([]));
  }, []);

  if (!zones) return <div className="page"><p className="empty-state">加载中…</p></div>;
  if (zones.length === 0)
    return <div className="page"><p className="empty-state">暂无分区，先导入素材并编译。</p></div>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>分区浏览</h1>
        <p className="page-subtitle">{zones.length} 个主题分区</p>
      </header>
      <ul className="card-list">
        {zones.map((z) => (
          <li key={z.name} className="card-item">
            <Link to={`/zones/${encodeURIComponent(z.name)}`} className="card-link">
              <strong className="card-title">{z.name}</strong>
              <span className="meta-item">{z.page_count} 页</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
