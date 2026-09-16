import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiRequestError, api } from "../api/client";
import type { SourceDetail } from "../api/types";

type ImportMode = "url" | "pdf" | "note";

interface FieldError {
  field: string;
  reason: string;
}

interface ImportFormError {
  code: string;
  message: string;
  fields: Record<string, string>;
  existingTitle: string | null;
}

interface CompileResponse {
  job_id: string | null;
}

const MODES: { value: ImportMode; label: string }[] = [
  { value: "url", label: "粘贴 URL" },
  { value: "pdf", label: "上传 PDF" },
  { value: "note", label: "手写笔记" },
];

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function parseTags(value: string): string[] {
  return [...new Set(
    value
      .split(/[,，]/)
      .map((tag) => tag.trim())
      .filter(Boolean),
  )];
}

function normalizeFieldErrors(details: Record<string, unknown>): Record<string, string> {
  const rawFields = details.fields;
  if (!rawFields) return {};

  if (Array.isArray(rawFields)) {
    return rawFields.reduce<Record<string, string>>((result, item) => {
      if (
        item &&
        typeof item === "object" &&
        "field" in item &&
        "reason" in item &&
        typeof item.field === "string" &&
        typeof item.reason === "string"
      ) {
        result[item.field] = item.reason;
      }
      return result;
    }, {});
  }

  if (typeof rawFields === "object") {
    return Object.entries(rawFields).reduce<Record<string, string>>((result, [field, reason]) => {
      if (typeof reason === "string") result[field] = reason;
      return result;
    }, {});
  }

  return {};
}

function normalizeExistingTitle(details: Record<string, unknown>): string | null {
  const existing = details.existing;
  if (existing && typeof existing === "object" && "title" in existing) {
    const title = existing.title;
    if (typeof title === "string" && title.trim()) return title;
  }
  if (typeof existing === "string" && existing.trim()) return existing;
  return null;
}

function toFormError(error: unknown, fallback: string): ImportFormError {
  if (error instanceof ApiRequestError) {
    return {
      code: error.code,
      message:
        error.code === "E_DUPLICATE_SOURCE"
          ? "素材已存在"
          : error.code === "E_PARSE_FAILED"
            ? "解析失败，请检查文件/链接"
            : error.code === "E_VALIDATION"
              ? "请检查输入内容"
              : error.message || fallback,
      fields: normalizeFieldErrors(error.details),
      existingTitle: error.code === "E_DUPLICATE_SOURCE" ? normalizeExistingTitle(error.details) : null,
    };
  }

  return {
    code: "UNKNOWN",
    message: error instanceof Error && error.message ? error.message : fallback,
    fields: {},
    existingTitle: null,
  };
}

async function postFormData<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    const error = (payload as { error?: { code?: string; message?: string; details?: Record<string, unknown> } })
      ?.error;
    throw new ApiRequestError(
      error?.code ?? "UNKNOWN",
      response.status,
      error?.message ?? response.statusText,
      error?.details ?? {},
    );
  }

  return (await response.json()) as T;
}

export function IngestPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<ImportMode>("url");
  const [url, setUrl] = useState("");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [result, setResult] = useState<SourceDetail | null>(null);
  const [formError, setFormError] = useState<ImportFormError | null>(null);
  const [compileError, setCompileError] = useState<string | null>(null);

  const tags = useMemo(() => parseTags(tagInput), [tagInput]);

  const selectFile = useCallback((file: File | null) => {
    setFormError(null);
    if (!file) {
      setPdfFile(null);
      return;
    }

    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setFormError({
        code: "E_VALIDATION",
        message: "请选择 PDF 文件",
        fields: { file: "仅支持 PDF 文件" },
        existingTitle: null,
      });
      return;
    }

    setPdfFile(file);
  }, []);

  const validateBeforeSubmit = useCallback((): boolean => {
    const fields: Record<string, string> = {};

    if (mode === "url") {
      const trimmedUrl = url.trim();
      if (!trimmedUrl) fields.url = "请输入网页链接";
      else if (!/^https?:\/\//i.test(trimmedUrl)) fields.url = "链接必须以 http:// 或 https:// 开头";
    }

    if (mode === "pdf" && !pdfFile) fields.file = "请选择 PDF 文件";

    if (mode === "note") {
      if (!noteTitle.trim()) fields.title = "请输入笔记标题";
      if (!noteContent.trim()) fields.content = "请输入笔记正文";
    }

    if (Object.keys(fields).length > 0) {
      setFormError({
        code: "E_VALIDATION",
        message: "请检查输入内容",
        fields,
        existingTitle: null,
      });
      return false;
    }

    return true;
  }, [mode, noteContent, noteTitle, pdfFile, url]);

  const submit = useCallback(async () => {
    if (!validateBeforeSubmit()) return;

    setSubmitting(true);
    setFormError(null);
    setResult(null);
    setCompileError(null);

    try {
      let imported: SourceDetail;
      if (mode === "url") {
        imported = await api.post<SourceDetail>("/sources/web", {
          url: url.trim(),
          tags,
        });
        setUrl("");
      } else if (mode === "pdf" && pdfFile) {
        const formData = new FormData();
        formData.append("file", pdfFile);
        if (tags.length > 0) formData.append("tags", tags.join(","));
        imported = await postFormData<SourceDetail>("/sources/pdf", formData);
      } else {
        imported = await api.post<SourceDetail>("/sources/note", {
          title: noteTitle.trim(),
          content: noteContent.trim(),
          tags,
        });
        setNoteTitle("");
        setNoteContent("");
      }

      setTagInput("");
      setPdfFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setResult(imported);
    } catch (error) {
      setFormError(toFormError(error, "导入失败，请稍后重试"));
    } finally {
      setSubmitting(false);
    }
  }, [mode, noteContent, noteTitle, pdfFile, tags, url, validateBeforeSubmit]);

  const compileNow = useCallback(async () => {
    setCompiling(true);
    setCompileError(null);
    try {
      await api.post<CompileResponse>("/compile", {});
      navigate("/compile");
    } catch (error) {
      setCompileError(toFormError(error, "编译任务启动失败").message);
    } finally {
      setCompiling(false);
    }
  }, [navigate]);

  const canSubmit = !submitting && !compiling;

  return (
    <div className="ingest-page page">
      <style>{`
        .ingest-tabs { display: flex; gap: var(--sp-2); margin-bottom: var(--sp-5); flex-wrap: wrap; }
        .ingest-tab { border: 1px solid var(--border); background: var(--surface); color: var(--text-2); border-radius: var(--r-full); min-height: 34px; padding: 0 var(--sp-4); font-size: var(--fs-sm); cursor: pointer; }
        .ingest-tab.active { border-color: var(--primary-border); background: var(--primary-soft); color: var(--primary); }
        .ingest-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-lg); box-shadow: var(--shadow-card); }
        .ingest-card-body { padding: var(--sp-5); }
        .ingest-label { display: block; color: var(--text-2); font-size: var(--fs-meta); margin-bottom: 6px; }
        .ingest-field { margin-bottom: var(--sp-4); }
        .ingest-field-error { color: var(--danger); font-size: var(--fs-caption); margin-top: 6px; }
        .ingest-row { display: flex; gap: var(--sp-2); align-items: flex-start; }
        .ingest-row .input { flex: 1; min-width: 0; }
        .ingest-dropzone { border: 1.5px dashed var(--border-strong); background: var(--bg-subtle); border-radius: var(--r-lg); padding: var(--sp-6); text-align: center; cursor: pointer; transition: border-color .15s ease, background .15s ease; }
        .ingest-dropzone.dragging { border-color: var(--primary); background: var(--primary-soft); }
        .ingest-file-input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
        .ingest-spinner { width: 14px; height: 14px; border: 2px solid color-mix(in srgb, currentColor 25%, transparent); border-top-color: currentColor; border-radius: 50%; display: inline-block; animation: ingest-spin .8s linear infinite; }
        @keyframes ingest-spin { to { transform: rotate(360deg); } }
        @media (max-width: 640px) { .ingest-row { flex-direction: column; } .ingest-row button { width: 100%; justify-content: center; } }
      `}</style>

      <header>
        <h1 className="page-title">喂素材</h1>
        <p className="page-sub">粘贴网页、上传 PDF，或直接写一篇笔记。导入后可以立即编译成 Wiki 页面。</p>
      </header>

      <nav className="ingest-tabs" aria-label="素材投放方式">
        {MODES.map((item) => (
          <button
            key={item.value}
            type="button"
            className={item.value === mode ? "ingest-tab active" : "ingest-tab"}
            aria-pressed={item.value === mode}
            onClick={() => {
              setMode(item.value);
              setFormError(null);
              setResult(null);
              setCompileError(null);
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {result && (
        <div className="callout callout-success" role="status" style={{ marginBottom: "var(--sp-4)" }}>
          <div className="btn-row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
            <span>导入成功：{result.title}</span>
            <button type="button" className="btn btn-primary btn-sm" onClick={compileNow} disabled={compiling}>
              {compiling ? <span className="ingest-spinner" aria-hidden="true" /> : null}
              {compiling ? "正在启动编译" : "立即编译"}
            </button>
          </div>
        </div>
      )}

      {compileError && (
        <div className="callout callout-danger" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          {compileError}
        </div>
      )}

      {formError && (
        <div className="callout callout-danger" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          <strong>{formError.message}</strong>
          {formError.existingTitle && <div>已有素材：{formError.existingTitle}</div>}
          {!formError.existingTitle && Object.entries(formError.fields).map(([field, reason]) => (
            <div key={`${field}-${reason}`}>
              {field === "url" ? "链接" : field === "file" ? "文件" : field === "title" ? "标题" : field === "content" ? "正文" : field}
              ：{reason}
            </div>
          ))}
          {!formError.existingTitle && Object.keys(formError.fields).length === 0 && formError.code === "E_PARSE_FAILED" && (
            <div>请确认 PDF 有文本层，或网页链接可以访问。</div>
          )}
        </div>
      )}

      <section className="ingest-card" aria-labelledby="ingest-mode-title">
        <div className="ingest-card-body">
          <h2 id="ingest-mode-title" className="card-title" style={{ marginTop: 0 }}>
            {MODES.find((item) => item.value === mode)?.label}
          </h2>

          {mode === "url" && (
            <div className="ingest-field">
              <label className="ingest-label" htmlFor="ingest-url">网页链接</label>
              <div className="ingest-row">
                <input
                  id="ingest-url"
                  className="input"
                  type="url"
                  inputMode="url"
                  placeholder="https://example.com/article"
                  value={url}
                  aria-invalid={Boolean(formError?.fields.url)}
                  onChange={(event) => setUrl(event.target.value)}
                  disabled={!canSubmit}
                />
              </div>
              {formError?.fields.url && <p className="ingest-field-error">{formError.fields.url}</p>}
            </div>
          )}

          {mode === "pdf" && (
            <div className="ingest-field">
              <span className="ingest-label" id="ingest-pdf-label">PDF 文件</span>
              <div
                className={dragging ? "ingest-dropzone dragging" : "ingest-dropzone"}
                role="button"
                tabIndex={0}
                aria-labelledby="ingest-pdf-label"
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  selectFile(event.dataTransfer.files[0] ?? null);
                }}
              >
                {pdfFile ? (
                  <div className="btn-row" style={{ justifyContent: "center", flexWrap: "wrap" }}>
                    <strong style={{ fontWeight: 500 }}>{pdfFile.name}</strong>
                    <span className="tiny">{formatFileSize(pdfFile.size)}</span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        selectFile(null);
                      }}
                      disabled={!canSubmit}
                    >
                      移除
                    </button>
                  </div>
                ) : (
                  <>
                    <div style={{ fontWeight: 500 }}>拖拽 PDF 到这里，或点击选择文件</div>
                    <div className="tiny" style={{ marginTop: "var(--sp-1)" }}>仅支持 PDF；扫描件可能无法提取文本</div>
                  </>
                )}
              </div>
              <input
                ref={fileInputRef}
                className="ingest-file-input"
                type="file"
                accept=".pdf,application/pdf"
                aria-describedby={formError?.fields.file ? "ingest-pdf-error" : undefined}
                onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
                disabled={!canSubmit}
              />
              {formError?.fields.file && (
                <p id="ingest-pdf-error" className="ingest-field-error">{formError.fields.file}</p>
              )}
            </div>
          )}

          {mode === "note" && (
            <>
              <div className="ingest-field">
                <label className="ingest-label" htmlFor="ingest-note-title">标题</label>
                <input
                  id="ingest-note-title"
                  className="input"
                  value={noteTitle}
                  placeholder="例如：关于检索增强生成的一点理解"
                  aria-invalid={Boolean(formError?.fields.title)}
                  onChange={(event) => setNoteTitle(event.target.value)}
                  disabled={!canSubmit}
                />
                {formError?.fields.title && <p className="ingest-field-error">{formError.fields.title}</p>}
              </div>
              <div className="ingest-field">
                <label className="ingest-label" htmlFor="ingest-note-content">正文</label>
                <textarea
                  id="ingest-note-content"
                  className="input"
                  rows={8}
                  value={noteContent}
                  placeholder="用 Markdown 或纯文本记录内容…"
                  aria-invalid={Boolean(formError?.fields.content)}
                  onChange={(event) => setNoteContent(event.target.value)}
                  disabled={!canSubmit}
                />
                {formError?.fields.content && <p className="ingest-field-error">{formError.fields.content}</p>}
              </div>
            </>
          )}

          <div className="ingest-field">
            <label className="ingest-label" htmlFor="ingest-tags">标签（可选）</label>
            <input
              id="ingest-tags"
              className="input"
              value={tagInput}
              placeholder="LLM, RAG, 产品思考"
              onChange={(event) => setTagInput(event.target.value)}
              disabled={!canSubmit}
            />
            <p className="field-hint">多个标签用英文或中文逗号分隔。</p>
          </div>

          <div className="btn-row">
            <button type="button" className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
              {submitting && <span className="ingest-spinner" aria-hidden="true" />}
              {submitting ? "导入中" : "导入素材"}
            </button>
            <span className="tiny">{submitting ? "正在提交，请稍候…" : "导入成功后可选择立即编译。"}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
