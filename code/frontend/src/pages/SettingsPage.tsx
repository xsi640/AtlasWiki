import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SettingsResponse, CostsResponse } from "../api/types";

export function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [costs, setCosts] = useState<CostsResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // 表单状态
  const [vaultPath, setVaultPath] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");

  const load = () => {
    api.get<SettingsResponse>("/settings").then((s) => {
      setSettings(s);
      setVaultPath(s.vault_path);
      setBaseUrl(s.llm.base_url);
      setModel(s.llm.model);
    }).catch(() => {});
    api.get<CostsResponse>("/settings/costs").then(setCosts).catch(() => {});
  };
  useEffect(load, []);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.put("/settings", {
        vault_path: vaultPath || undefined,
        llm_base_url: baseUrl || undefined,
        llm_model: model || undefined,
        llm_api_key: apiKey || undefined,
      });
      setMessage("已保存");
      setApiKey("");
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    setMessage(null);
    try {
      const res = await api.post<{ ok: boolean; message: string }>("/settings/test-connection");
      setMessage(res.message);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "连接失败");
    }
  };

  const gitSync = async () => {
    setMessage(null);
    try {
      await api.post("/settings/git/sync");
      setMessage("推送成功");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "推送失败");
    }
  };

  const openFolder = async () => {
    try {
      await api.post("/system/open-folder");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "打开失败");
    }
  };

  if (!settings)
    return <div className="page"><p className="empty-state">加载中…</p></div>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>设置</h1>
      </header>

      <section>
        <h2>知识库</h2>
        <div className="form-row">
          <label>Vault 路径</label>
          <input type="text" value={vaultPath} onChange={(e) => setVaultPath(e.target.value)} />
        </div>
        <button className="btn-secondary" onClick={openFolder}>打开数据文件夹</button>
      </section>

      <section>
        <h2>LLM 模型</h2>
        <div className="form-row">
          <label>Base URL</label>
          <input type="text" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
        </div>
        <div className="form-row">
          <label>模型</label>
          <input type="text" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div className="form-row">
          <label>API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings.llm.has_key ? "••••（已配置，输入新值可覆盖）" : "未配置"}
          />
        </div>
        <button className="btn-secondary" onClick={testConnection}>测试连接</button>
      </section>

      <section>
        <h2>Git 同步</h2>
        <p className="meta-item">
          远端：{settings.git.has_remote ? settings.git.remote_name : "未配置"}
        </p>
        <button className="btn-secondary" onClick={gitSync} disabled={!settings.git.has_remote}>
          立即同步
        </button>
      </section>

      <section>
        <h2>成本看板</h2>
        {costs ? (
          <>
            <p>累计花费：${costs.total_usd.toFixed(4)} USD</p>
            {costs.entries.length > 0 && (
              <ul className="card-list">
                {costs.entries.slice(-10).reverse().map((c, i) => (
                  <li key={i} className="card-item meta-item">
                    {c.source} · {c.model} · ${c.cost_usd.toFixed(6)}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="empty-state">暂无成本数据。</p>
        )}
      </section>

      {message && <p className="save-message">{message}</p>}
      <button className="btn-primary" onClick={save} disabled={saving}>
        {saving ? "保存中…" : "保存设置"}
      </button>
    </div>
  );
}
