/** 共享 API 类型定义（契约层冻结，与后端 Pydantic 模型人工对齐）。 */

// --- 系统 ---

export interface HealthResponse {
  version: string;
  vault: { path: string; initialized: boolean; page_count?: number; source_count?: number };
  llm: { configured: boolean; provider: string; model: string };
  jobs: { running: boolean; queued: number; current_job_id: string | null };
}

export interface BootstrapResponse {
  vault_initialized: boolean;
  is_empty: boolean;
  page_count: number;
  pending_lint_count: number;
  failed_source_count: number;
  stale_source_count: number;
}

// --- 通用 ---

export interface ApiError {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface CostInfo {
  currency: string;
  total: number;
}

// --- 页面 ---

export type PageType = "source" | "concept" | "entity" | "analysis";
export type SourceType = "compiled" | "query-generated" | "human";
export type PageStatus = "active" | "invalid";

export interface PageSummary {
  name: string;
  title: string;
  type: PageType;
  zone: string;
  source_type: SourceType;
  human_edited: boolean;
  status: PageStatus;
  link_count: number;
  backlink_count: number;
  updated_at: string;
}

export interface PageDetail extends PageSummary {
  created_at: string;
  origin_source: string | null;
  content: string;
  links: string[];
  backlinks: { name: string; title: string }[];
  sources: { id: string; title: string; kind: string }[];
}

export interface GraphNode {
  id: string;
  title: string;
  type: PageType;
  zone: string;
  degree: number;
  status: PageStatus;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  node_count: number;
  edge_count: number;
}

export interface ZoneInfo {
  name: string;
  page_count: number;
}

export interface SearchResult {
  name: string;
  title: string;
  zone: string;
  type: PageType;
  snippet: string;
}

// --- 素材 ---

export type MaterialKind = "web" | "pdf" | "note";
export type MaterialStatus = "normal" | "failed" | "deleted" | "stale";

export interface SourceSummary {
  id: string;
  title: string;
  kind: MaterialKind;
  source_url: string | null;
  status: MaterialStatus;
  tags: string[];
  author: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  derived_page_count: number;
  failure_reason: string | null;
}

export interface SourceDetail extends SourceSummary {
  note: string;
  content: string;
  content_editable: boolean;
  asset_path: string | null;
  raw_meta: Record<string, unknown>;
  derived_pages: { name: string; title: string; status: PageStatus }[];
}

// --- 编译 ---

export type JobStatus = "idle" | "queued" | "running" | "done" | "failed";

export interface JobStep {
  name: string;
  state: "pending" | "running" | "done" | "failed";
}

export interface JobSnapshot {
  job_id: string | null;
  status: JobStatus;
  kind: string;
  total_sources: number;
  done_sources: number;
  current_source: { id: string; title: string } | null;
  current_page: string | null;
  steps: JobStep[];
  cost: CostInfo;
  started_at: string | null;
  finished_at: string | null;
  failure_reason: string | null;
  can_leave: boolean;
}

export type ChangeType = "created" | "updated" | "zone_changed";

export interface ChangeItem {
  name: string;
  title: string;
  change_type: ChangeType;
  zone: string;
  zone_before: string | null;
  has_diff: boolean;
}

export interface ChangesResponse {
  job_id: string;
  status: JobStatus;
  started_at: string | null;
  finished_at: string | null;
  cost: CostInfo;
  items: ChangeItem[];
  failed_sources: { id: string; title: string; reason: string }[];
}

// --- 问答 ---

export interface Citation {
  page: string;
  title: string;
  anchor_text: string;
}

export interface AskResponse {
  id: string;
  question: string;
  answer: string;
  sufficient: boolean;
  citations: Citation[];
  related_pages: { name: string; title: string }[];
  pages_considered: number;
  cost: CostInfo;
  created_at: string;
  saved_page: { name: string; title: string } | null;
}

// --- 体检 ---

export type LintKind = "contradiction" | "orphan" | "dead_link" | "missing_index" | "zone_mix";

export interface LintIssue {
  id: string;
  kind: LintKind;
  page: string;
  detail: string;
  suggestion: string;
  ignored: boolean;
}

export interface LintReport {
  generated_at: string;
  issues: LintIssue[];
}

// --- 设置 ---

export interface SettingsResponse {
  vault_path: string;
  llm: {
    provider: string;
    base_url: string;
    model: string;
    has_key: boolean;
    timeout_s: number;
    max_cost_per_task_usd: number;
  };
  git: {
    auto_commit: boolean;
    auto_push: boolean;
    remote_name: string;
    has_remote: boolean;
  };
}

export interface CostEntry {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  source: string;
  created_at: string;
}

export interface CostsResponse {
  entries: CostEntry[];
  total_usd: number;
  currency: "USD";
}

// --- SSE 事件 ---

export interface SseEvent {
  event: string;
  job_id?: string;
  [key: string]: unknown;
}
