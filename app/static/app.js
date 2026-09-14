/* ===== LLM Wiki 前端 ===== */
(() => {
'use strict';

/* ------------------------------------------------------------------ */
/* 基础工具                                                             */
/* ------------------------------------------------------------------ */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// 只放行 http(s)。markdown 渲染器里的链接已经这么限制了，
// 这里补上是为了让所有 href 走同一套规则 —— escapeHtml 挡得住属性注入，
// 但挡不住 `javascript:` 这类危险协议。
function safeUrl(u) {
  const s = String(u == null ? '' : u).trim();
  return /^https?:\/\//i.test(s) ? s : '';
}

let toastTimer = null;
function toast(msg, kind = '') {
  const node = $('#toast');
  node.textContent = msg;
  node.className = 'toast ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.add('hidden'), 3600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail || j.message || detail; } catch (_) {}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

function fmtSize(chars) {
  if (chars == null) return '';
  if (chars < 1000) return chars + ' 字';
  return (chars / 1000).toFixed(1) + 'k 字';
}

function fmtTime(s) { return (s || '').replace('T', ' ').slice(0, 16); }

/* ------------------------------------------------------------------ */
/* Markdown 渲染                                                        */
/* ------------------------------------------------------------------ */
const KIND_DIRS = ['sources', 'entities', 'concepts', 'analyses'];

function inlineMd(text, placeholders) {
  let s = text;
  // 行内代码先挖出来，避免被后续规则破坏
  s = s.replace(/`([^`]+)`/g, (_, code) => {
    placeholders.push(`<code>${escapeHtml(code)}</code>`);
    return `\u0000${placeholders.length - 1}\u0000`;
  });
  s = escapeHtml(s);

  // [[双链]]
  s = s.replace(/\[\[([^\[\]]+?)\]\]/g, (_, raw) => {
    const [target, display] = raw.split('|');
    return wikilinkHtml(target.trim(), (display || target).trim());
  });
  // 图片
  s = s.replace(/!\[([^\]]*)\]\((https?:[^)\s]+)\)/g,
    (_, alt, src) => `<img src="${src}" alt="${alt}" loading="lazy">`);
  // 链接
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
    if (href.startsWith('http')) return `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>`;
    return `<a href="#" data-wiki="${href}">${label}</a>`;
  });
  // 强调
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*\w])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  // 还原行内代码
  s = s.replace(/\u0000(\d+)\u0000/g, (_, i) => placeholders[Number(i)]);
  return s;
}

function mdToHtml(src) {
  const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  const placeholders = [];
  const para = [];
  let i = 0;

  const flush = () => {
    if (!para.length) return;
    out.push(`<p>${inlineMd(para.join(' '), placeholders)}</p>`);
    para.length = 0;
  };

  while (i < lines.length) {
    const line = lines[i];

    // 代码块
    const fence = line.match(/^\s*```\s*([\w+-]*)\s*$/);
    if (fence) {
      flush();
      const lang = fence[1] || '';
      const body = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { body.push(lines[i]); i++; }
      i++;
      out.push(`<pre><code data-lang="${escapeHtml(lang)}">${escapeHtml(body.join('\n'))}</code></pre>`);
      continue;
    }

    if (!line.trim()) { flush(); i++; continue; }

    // 标题
    const head = line.match(/^(#{1,6})\s+(.*)$/);
    if (head) {
      flush();
      const lv = head[1].length;
      out.push(`<h${lv}>${inlineMd(head[2].trim(), placeholders)}</h${lv}>`);
      i++; continue;
    }

    // 分隔线
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) { flush(); out.push('<hr>'); i++; continue; }

    // 引用
    if (/^\s*>/.test(line)) {
      flush();
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, '')); i++;
      }
      out.push(`<blockquote>${mdToHtml(buf.join('\n'))}</blockquote>`);
      continue;
    }

    // 表格
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      flush();
      const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      const header = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
      let html = '<table><thead><tr>' + header.map((c) => `<th>${inlineMd(c, placeholders)}</th>`).join('') + '</tr></thead><tbody>';
      for (const row of rows) {
        html += '<tr>' + row.map((c) => `<td>${inlineMd(c, placeholders)}</td>`).join('') + '</tr>';
      }
      out.push(html + '</tbody></table>');
      continue;
    }

    // 列表
    const isUl = /^\s*[-*+]\s+/.test(line);
    const isOl = /^\s*\d+[.)]\s+/.test(line);
    if (isUl || isOl) {
      flush();
      const tag = isOl ? 'ol' : 'ul';
      const items = [];
      while (i < lines.length) {
        const m = lines[i].match(isOl ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/);
        if (!m) break;
        const sub = [];
        i++;
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*[-*+\d]/.test(lines[i])) {
          sub.push(lines[i].trim()); i++;
        }
        items.push(inlineMd(m[1].trim() + (sub.length ? ' ' + sub.join(' ') : ''), placeholders));
      }
      out.push(`<${tag}>` + items.map((t) => `<li>${t}</li>`).join('') + `</${tag}>`);
      continue;
    }

    para.push(line.trim());
    i++;
  }
  flush();
  return out.join('\n');
}

/* ------------------------------------------------------------------ */
/* 状态                                                                 */
/* ------------------------------------------------------------------ */
const state = {
  pages: [],
  linkMap: new Map(),
  rawItems: [],
  stats: null,
  config: null,
  health: null,
  currentPath: null,
  chat: [],
  busy: false,
};

function buildLinkMap(pages) {
  const map = new Map();
  for (const p of pages) {
    const keys = [p.title, p.slug, p.path, p.path.replace(/\.md$/, '')];
    for (const k of keys) {
      if (!k) continue;
      const low = k.toLowerCase();
      if (!map.has(low)) map.set(low, p);
    }
  }
  state.linkMap = map;
}

function resolveWiki(target) {
  const raw = String(target || '').trim().replace(/^\//, '');
  const low = raw.toLowerCase();
  if (state.linkMap.has(low)) return state.linkMap.get(low);
  if (low.endsWith('.md') && state.linkMap.has(low.slice(0, -3))) return state.linkMap.get(low.slice(0, -3));
  if (!low.endsWith('.md') && state.linkMap.has(low + '.md')) return state.linkMap.get(low + '.md');
  const stem = low.split('/').pop();
  if (state.linkMap.has(stem)) return state.linkMap.get(stem);
  return null;
}

function wikilinkHtml(target, display) {
  const resolved = resolveWiki(target);
  if (!resolved) {
    return `<a class="wikilink missing" title="页面还不存在：${escapeHtml(target)}">${escapeHtml(display)}</a>`;
  }
  const src = resolved.kind === 'sources' ? ' source-link' : '';
  return `<a class="wikilink${src}" data-wiki="${escapeHtml(resolved.path)}" title="${escapeHtml(resolved.path)}">${escapeHtml(display)}</a>`;
}

function kindLabel(kind) {
  return { sources: '素材', entities: '实体', concepts: '概念', analyses: '分析', root: '总览' }[kind] || kind;
}

/* ------------------------------------------------------------------ */
/* 数据加载                                                             */
/* ------------------------------------------------------------------ */
async function refreshAll() {
  const [pagesRes, rawRes, statsRes, healthRes] = await Promise.all([
    api('/api/pages'),
    api('/api/raw'),
    api('/api/stats'),
    api('/api/health'),
  ]);
  state.pages = pagesRes.items || [];
  state.rawItems = rawRes.items || [];
  state.stats = statsRes;
  state.health = healthRes;
  buildLinkMap(state.pages);
  renderSidebar();
  renderLlmBadge();
  $('#vault-path').textContent = healthRes.paths?.vault || '';
  $('#vault-path').title = healthRes.paths?.vault || '';
}

function renderLlmBadge() {
  const badge = $('#llm-badge');
  if (state.health?.llm_ready) {
    badge.className = 'badge badge-ok';
    badge.textContent = '● ' + (state.health.llm_model || 'LLM 已就绪');
    badge.title = state.health.llm_base_url;
  } else {
    badge.className = 'badge badge-warn';
    badge.textContent = '● 未配置大模型';
    badge.title = '在「设置」里填写 API Key 后，wiki 将由 LLM 编译维护';
  }
}

function renderSidebar() {
  const tree = $('#page-tree');
  const groups = { root: [], concepts: [], entities: [], sources: [], analyses: [] };
  for (const p of state.pages) (groups[p.kind] || (groups[p.kind] = [])).push(p);

  const order = ['concepts', 'entities', 'sources', 'analyses', 'root'];
  let html = '';
  for (const kind of order) {
    const items = groups[kind] || [];
    if (!items.length) continue;
    items.sort((a, b) => a.title.localeCompare(b.title, 'zh'));
    html += `<div class="tree-group-title"><span class="dot" style="background:${kindColor(kind)}"></span>${kindLabel(kind)}<span class="muted">${items.length}</span></div>`;
    html += items.map((p) =>
      `<a class="tree-item" data-nav="page" data-path="${escapeHtml(p.path)}" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</a>`
    ).join('');
  }
  tree.innerHTML = html || '<div class="muted" style="padding:6px 9px">还没有页面</div>';
  $('#page-total').textContent = state.pages.length;

  const pendingSet = new Set(state.rawItems.filter((r) => r.pending).map((r) => r.path));
  $('#raw-list').innerHTML = state.rawItems.length
    ? state.rawItems.map((r) =>
        `<div class="raw-item${pendingSet.has(r.path) ? ' pending' : ''}" data-nav="raw" data-path="${escapeHtml(r.path)}" title="${escapeHtml(r.title)} · ${r.chars} 字">${escapeHtml(r.title)}</div>`
      ).join('')
    : '<div class="muted" style="padding:6px 9px">还没有素材</div>';
  $('#raw-total').textContent = state.rawItems.length;

  markActive();
}

function kindColor(kind) {
  return { concepts: '#4f46e5', entities: '#059669', sources: '#d97706', analyses: '#7c3aed', root: '#475569' }[kind] || '#94a3b8';
}

function markActive() {
  const hash = location.hash || '#/home';
  $$('.nav-item').forEach((n) => n.classList.toggle('active', hash.startsWith('#/' + n.dataset.nav) && !hash.startsWith('#/page')));
  $$('.tree-item').forEach((n) => n.classList.toggle('active', state.currentPath === n.dataset.path));
}

/* ------------------------------------------------------------------ */
/* 路由                                                                 */
/* ------------------------------------------------------------------ */
async function route() {
  const hash = location.hash || '#/home';
  const parts = hash.slice(2).split('/');
  const view = parts[0] || 'home';
  state.currentPath = null;
  markActive();

  if (view === 'page') {
    const path = decodeURIComponent(parts.slice(1).join('/'));
    state.currentPath = path;
    markActive();
    await viewPage(path);
  } else if (view === 'ingest') viewIngest();
  else if (view === 'ask') viewAsk();
  else if (view === 'graph') await viewGraph();
  else if (view === 'lint') await viewLint();
  else if (view === 'settings') await viewSettings();
  else if (view === 'raw') await viewRaw(decodeURIComponent(parts.slice(1).join('/')));
  else await viewHome();
  $('#main').scrollTop = 0;
}

function go(hash) { location.hash = hash; }

/* ------------------------------------------------------------------ */
/* 视图：总览                                                           */
/* ------------------------------------------------------------------ */
async function viewHome() {
  const main = $('#main');
  const s = state.stats || {};
  const index = await api('/api/index');
  const log = await api('/api/log?limit=12');

  const byKind = s.by_kind || {};
  const cards = [
    { label: 'wiki 页面', value: s.pages ?? 0, hint: Object.entries(byKind).map(([k, v]) => `${kindLabel(k)} ${v}`).join(' · ') },
    { label: '原始素材', value: s.raw_sources ?? 0, hint: s.pending_raw ? `${s.pending_raw} 篇待编译` : '全部已编译' },
    { label: '双链数量', value: s.links ?? 0, hint: '页面之间的引用关系' },
    { label: '总字数', value: fmtSize(s.chars), hint: 'wiki 正文合计' },
  ];

  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">总览</h1>
        <div class="page-meta">
          <span>${escapeHtml(s.vault || '')}</span>
          ${s.pending_raw ? `<span class="badge badge-warn">${s.pending_raw} 篇素材待编译</span>` : ''}
        </div>
      </div>

      <div class="row" style="gap:12px;margin-bottom:20px">
        ${cards.map((c) => `
          <div class="card" style="flex:1;min-width:150px;margin:0">
            <div class="card-title" style="color:var(--muted);font-weight:600">${c.label}</div>
            <div style="font-size:26px;font-weight:700;line-height:1.3">${c.value}</div>
            <div class="card-sub" style="margin:0">${escapeHtml(c.hint)}</div>
          </div>`).join('')}
      </div>

      ${s.pending_raw ? `
      <div class="card" style="border-color:#f0dcb8;background:var(--warn-soft)">
        <div class="row">
          <div style="flex:1">
            <div class="card-title">有 ${s.pending_raw} 篇素材还没有编译进 wiki</div>
            <div class="card-sub" style="margin:0">编译会读取原始素材，生成素材页并更新相关的概念页、实体页与索引。</div>
          </div>
          <button class="btn btn-primary" id="compile-pending">开始编译</button>
        </div>
        <div id="compile-log"></div>
      </div>` : ''}

      <div class="card">
        <div class="card-title">索引 index.md</div>
        <div class="card-sub">这是 LLM 维护的目录。回答问题时它也会先读这里。</div>
        <div class="md" id="index-body">${mdToHtml(index.content || '（索引为空）')}</div>
      </div>

      <div class="card">
        <div class="card-title">操作日志 log.md</div>
        <div class="card-sub">append-only，记录每一次收录、查询与体检。</div>
        <div id="log-body">
          ${(log.entries || []).length ? log.entries.map((e) => `
            <div class="lint-item" style="display:flex;gap:10px">
              <span class="muted" style="flex:0 0 118px">${escapeHtml(e.time)}</span>
              <span class="badge badge-accent" style="flex:0 0 auto">${escapeHtml(e.kind)}</span>
              <span style="flex:1">${escapeHtml(e.title)}</span>
            </div>`).join('') : '<div class="muted">还没有记录</div>'}
        </div>
      </div>
    </div>`;

  const btn = $('#compile-pending');
  if (btn) btn.onclick = () => runCompile({ paths: null }, $('#compile-log'), btn);
}

/* ------------------------------------------------------------------ */
/* 视图：页面                                                           */
/* ------------------------------------------------------------------ */
async function viewPage(path) {
  const main = $('#main');
  main.innerHTML = '<div class="wrap"><div class="empty"><span class="spinner"></span> 载入中…</div></div>';
  let page;
  try {
    page = await api('/api/page?path=' + encodeURIComponent(path));
  } catch (e) {
    main.innerHTML = `<div class="wrap"><div class="empty"><h3>页面不存在</h3><div class="hint">${escapeHtml(path)}</div></div></div>`;
    return;
  }

  const fm = page;
  const srcList = (page.sources || []).map((s) =>
    `<span class="wikilink source-link" data-nav="raw" data-path="${escapeHtml(s)}">${escapeHtml(s.replace(/^raw\//, ''))}</span>`
  ).join(' ') || '<span class="muted">—</span>';

  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">${escapeHtml(page.title)}</h1>
        <div class="page-meta">
          <span class="kind-chip kind-${escapeHtml(page.kind)}">${escapeHtml(page.kind_label)}</span>
          <span>${escapeHtml(page.path)}</span>
          <span>·</span>
          <span>更新于 ${escapeHtml(fm.updated_at || '')}</span>
          <span>·</span>
          <span>${fmtSize(page.size)}</span>
          <span class="spacer"></span>
          <button class="btn btn-sm" id="edit-page">编辑</button>
          <a class="btn btn-sm" href="/api/page/raw?path=${encodeURIComponent(page.path)}" download>下载</a>
          <button class="btn btn-sm btn-danger" id="delete-page">删除</button>
        </div>
      </div>

      ${page.summary ? `<div class="card" style="background:var(--accent-soft);border-color:#dfe3fd"><strong>摘要</strong>　${escapeHtml(page.summary)}</div>` : ''}

      <div class="card">
        <div class="md" id="page-body">${mdToHtml(page.body)}</div>
      </div>

      ${(page.tags || []).length ? `<div class="row" style="margin-bottom:14px">${page.tags.map((t) => `<span class="tag" data-search="${escapeHtml(t)}">#${escapeHtml(t)}</span>`).join('')}</div>` : ''}

      <div class="card">
        <div class="card-title">关联</div>
        <div class="card-sub">文件是唯一真相来源，这些链接都是页面里真实写下的 [[双链]]。</div>
        <div class="row" style="align-items:flex-start;gap:24px">
          <div style="flex:1;min-width:200px">
            <div class="muted" style="margin-bottom:6px">出链 ${page.resolved_links.length}</div>
            ${page.resolved_links.length ? page.resolved_links.map((l) => l.exists
              ? `<a class="backlink-item" data-nav="page" data-path="${escapeHtml(l.path)}">→ ${escapeHtml(l.raw)}</a>`
              : `<div class="backlink-item" style="color:var(--danger)">→ ${escapeHtml(l.raw)} <span class="muted">（未创建）</span></div>`
            ).join('') : '<div class="muted">无</div>'}
          </div>
          <div style="flex:1;min-width:200px">
            <div class="muted" style="margin-bottom:6px">反向链接 ${page.backlink_pages.length}</div>
            ${page.backlink_pages.length ? page.backlink_pages.map((b) =>
              `<a class="backlink-item" data-nav="page" data-path="${escapeHtml(b.path)}">← ${escapeHtml(b.title)}</a>`).join('')
              : '<div class="muted">还没有页面链接到这里</div>'}
          </div>
        </div>
        <div style="margin-top:14px">
          <div class="muted" style="margin-bottom:6px">原始素材</div>
          ${srcList}
        </div>
      </div>
    </div>`;

  $('#edit-page').onclick = () => editPage(page);
  $('#delete-page').onclick = async () => {
    if (!confirm(`删除「${page.title}」？文件会移入 vault/.trash 而不是彻底删除。`)) return;
    await api('/api/page?path=' + encodeURIComponent(page.path), { method: 'DELETE' });
    toast('已删除', 'ok');
    await refreshAll();
    go('#/home');
  };
}

function editPage(page) {
  const main = $('#main');
  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">编辑：${escapeHtml(page.title)}</h1>
        <div class="page-meta"><span>${escapeHtml(page.path)}</span><span class="spacer"></span>
          <button class="btn btn-sm" id="cancel-edit">取消</button>
          <button class="btn btn-sm btn-primary" id="save-edit">保存</button>
        </div>
      </div>
      <div class="card">
        <textarea id="edit-area" style="min-height:60vh;font-family:var(--mono);font-size:13px">${escapeHtml(page.body)}</textarea>
      </div>
    </div>`;
  $('#cancel-edit').onclick = () => route();
  $('#save-edit').onclick = async () => {
    await api('/api/page?path=' + encodeURIComponent(page.path), {
      method: 'PUT',
      body: JSON.stringify({ content: $('#edit-area').value, title: page.title }),
    });
    toast('已保存', 'ok');
    await refreshAll();
    route();
  };
}

/* ------------------------------------------------------------------ */
/* 视图：收录                                                           */
/* ------------------------------------------------------------------ */
function viewIngest() {
  const main = $('#main');
  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">收录素材</h1>
        <div class="page-meta">支持抖音分享链接、B 站分享链接、任意网页 URL、doc/docx/pdf/md/txt 文档，也可以直接粘贴文本。</div>
      </div>

      <div class="card ingest-box">
        <div class="card-title">粘贴链接或文本</div>
        <div class="card-sub">每行一条。抖音那种「文案 + 短链」的整段分享文本可以直接粘。</div>
        <textarea id="ingest-input" placeholder="https://v.douyin.com/xxxxxxx/
https://www.bilibili.com/video/BV1xx411c7mD
https://example.com/some-article

或者直接粘贴一段 Markdown / 纯文本笔记"></textarea>
        <div class="row" style="margin-top:10px">
          <input type="text" id="ingest-tags" placeholder="标签，逗号分隔（可选）" style="flex:1">
          <button class="btn btn-primary" id="ingest-btn">收录到 raw/</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">上传文件</div>
        <div class="card-sub">支持 .docx / .doc / .rtf / .pdf / .md / .txt / .html</div>
        <div class="dropzone" id="dropzone">
          点击选择文件，或把文件拖到这里
          <input type="file" id="file-input" multiple hidden
                 accept=".docx,.doc,.dot,.rtf,.pdf,.md,.markdown,.txt,.html,.htm">
        </div>
      </div>

      <div id="ingest-results"></div>
      <div id="compile-area"></div>
    </div>`;

  const input = $('#ingest-input');
  const btn = $('#ingest-btn');
  btn.onclick = async () => {
    const value = input.value.trim();
    if (!value) { toast('请输入内容', 'err'); return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> 采集中…';
    try {
      const tags = $('#ingest-tags').value.split(',').map((t) => t.trim()).filter(Boolean);
      const res = await api('/api/ingest', { method: 'POST', body: JSON.stringify({ input: value, tags }) });
      renderIngestResults(res);
      input.value = '';
      await refreshAll();
      if (res.auto_compile !== false && res.raw_paths?.length) startCompile(res.raw_paths);
    } catch (e) {
      toast(e.message, 'err');
    } finally {
      btn.disabled = false;
      btn.textContent = '收录到 raw/';
    }
  };

  const drop = $('#dropzone');
  const fileInput = $('#file-input');
  drop.onclick = () => fileInput.click();
  fileInput.onchange = () => uploadFiles(fileInput.files);
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => {
    e.preventDefault(); drop.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => {
    e.preventDefault(); drop.classList.remove('over');
  }));
  drop.addEventListener('drop', (e) => uploadFiles(e.dataTransfer.files));
}

function renderIngestResults(res) {
  const box = $('#ingest-results');
  if (!box) return;
  box.innerHTML = `
    <div class="card">
      <div class="card-title">收录结果</div>
      <div class="card-sub">成功 ${res.ok_count} 条，失败 ${res.fail_count} 条</div>
      <div class="result-list">
        ${res.results.map((r) => r.ok ? `
          <div class="result-item ok">
            <span>✓</span>
            <div class="r-main">
              <div class="r-title">${escapeHtml(r.title)}</div>
              <div class="r-sub">${escapeHtml(r.source_type_label || '')} · ${fmtSize(r.chars)} · ${escapeHtml(r.raw_path)}
                ${r.author ? ' · ' + escapeHtml(r.author) : ''}</div>
              ${(r.warnings || []).length ? `<div class="r-sub" style="color:var(--warn)">⚠ ${r.warnings.map(escapeHtml).join('；')}</div>` : ''}
            </div>
            <button class="btn btn-sm" data-open-raw="${escapeHtml(r.raw_path)}">查看原文</button>
          </div>` : `
          <div class="result-item fail">
            <span>✕</span>
            <div class="r-main">
              <div class="r-title">${escapeHtml(r.input)}</div>
              <div class="r-sub">${escapeHtml(r.error)}</div>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
}

async function uploadFiles(files) {
  if (!files || !files.length) return;
  const form = new FormData();
  Array.from(files).forEach((f) => form.append('files', f));
  const tags = ($('#ingest-tags')?.value || '').split(',').map((t) => t.trim()).filter(Boolean).join(',');
  toast('正在解析文件…');
  try {
    const res = await api('/api/ingest/upload?tags=' + encodeURIComponent(tags), { method: 'POST', body: form });
    renderIngestResults(res);
    await refreshAll();
    if (res.auto_compile !== false && res.raw_paths?.length) startCompile(res.raw_paths);
  } catch (e) {
    toast(e.message, 'err');
  }
}

function startCompile(paths) {
  const area = $('#compile-area');
  if (!area) return;
  area.innerHTML = `
    <div class="card">
      <div class="card-title">编译进 wiki</div>
      <div class="card-sub">读取原始素材 → 生成素材页 → 更新概念页 / 实体页 → 重建索引</div>
      <div id="compile-log" class="stream-log"><div class="line dim">准备中…</div></div>
    </div>`;
  runCompile({ paths }, $('#compile-log'), null);
}

async function runCompile(payload, logEl, btn) {
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 编译中…'; }
  if (logEl) logEl.innerHTML = '';
  const append = (text, cls = '') => {
    if (!logEl) return;
    const div = document.createElement('div');
    div.className = 'line ' + cls;
    div.textContent = text;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
  };

  try {
    const res = await fetch('/api/compile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: payload.paths || null, all: !!payload.all }),
    });
    await consumeSSE(res, (ev) => {
      if (ev.type === 'batch_start') append(`开始编译 ${ev.count} 篇素材（${ev.llm ? 'LLM 模式' : '确定性编译器'}）`, 'dim');
      else if (ev.type === 'batch_progress') append(`\n[${ev.index}/${ev.total}] 《${ev.title}》`, 'tool');
      else if (ev.type === 'compile_start') append(`  → ${ev.raw_path}`, 'dim');
      else if (ev.type === 'step') append(`  · ${ev.description}`, 'tool');
      else if (ev.type === 'compile_done') append(`  ✓ 生成 ${ev.created.length} 个页面：${ev.created.slice(0, 8).join(', ')}${ev.created.length > 8 ? ' …' : ''}`);
      else if (ev.type === 'batch_done') append(`\n全部完成，共 ${ev.count} 篇`, 'dim');
      else if (ev.type === 'error') append('  ✕ ' + ev.message, 'err');
      else if (ev.type === 'notice') append('  ' + ev.message, 'dim');
    });
    toast('编译完成', 'ok');
    await refreshAll();
  } catch (e) {
    append('✕ ' + e.message, 'err');
    toast(e.message, 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '开始编译'; }
  }
}

async function consumeSSE(response, onEvent) {
  if (!response.ok) throw new Error('请求失败：' + response.status);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop();
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data:')) continue;
      const data = line.slice(5).trim();
      if (data === '[DONE]') return;
      try { onEvent(JSON.parse(data)); } catch (_) {}
    }
  }
}

/* ------------------------------------------------------------------ */
/* 视图：提问                                                           */
/* ------------------------------------------------------------------ */
function viewAsk() {
  const main = $('#main');
  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">提问</h1>
        <div class="page-meta">模型会先读 index.md 定位相关页面，再逐个读取页面内容综合作答 —— 这是 LLM Wiki 的查询方式，不做向量检索。</div>
      </div>
      <div class="chat" id="chat"></div>
      <div class="card">
        <div class="ask-bar">
          <textarea id="ask-input" placeholder="例如：RAG 和 LLM Wiki 的核心区别是什么？"></textarea>
          <button class="btn btn-primary" id="ask-btn">提问</button>
        </div>
        <div class="row" style="margin-top:10px">
          <label style="display:flex;gap:6px;align-items:center;font-size:12.5px;color:var(--text-2)">
            <input type="checkbox" id="file-answer" style="width:auto"> 把回答归档成 wiki 页面（analyses/）
          </label>
        </div>
        <div id="ask-log"></div>
      </div>
    </div>`;
  renderChat();

  const input = $('#ask-input');
  const btn = $('#ask-btn');
  const submit = () => askQuestion(input.value.trim(), btn);
  btn.onclick = submit;
  input.onkeydown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit();
  };
}

function renderChat() {
  const chat = $('#chat');
  if (!chat) return;
  if (!state.chat.length) {
    chat.innerHTML = `<div class="empty"><h3>还没有对话</h3><div class="hint">知识库里已有 ${state.pages.length} 个页面可供检索。</div></div>`;
    return;
  }
  chat.innerHTML = state.chat.map((m) => `
    <div class="msg ${m.role}">
      <div class="avatar">${m.role === 'user' ? '你' : 'AI'}</div>
      <div class="bubble">
        ${m.steps?.length ? `<details class="raw-view"><summary>查看检索过程（${m.steps.length} 步）</summary>
          <div class="stream-log">${m.steps.map((s) => `<div class="line tool">· ${escapeHtml(s.description)}</div>`).join('')}</div>
        </details>` : ''}
        <div class="md">${mdToHtml(m.content || '')}</div>
        ${m.filed ? `<div class="badge badge-ok" style="margin-top:8px">已归档到 ${escapeHtml(m.filed)}</div>` : ''}
      </div>
    </div>`).join('');
}

async function askQuestion(question, btn) {
  if (!question) { toast('请输入问题', 'err'); return; }
  if (state.busy) return;
  state.busy = true;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 思考中…';

  state.chat.push({ role: 'user', content: question });
  const answer = { role: 'assistant', content: '', steps: [], filed: '' };
  state.chat.push(answer);
  renderChat();

  const logEl = $('#ask-log');
  if (logEl) logEl.innerHTML = '<div class="stream-log" id="ask-stream"><div class="line dim">正在读取索引…</div></div>';
  const stream = $('#ask-stream');
  const appendStep = (text, cls = 'tool') => {
    if (!stream) return;
    const div = document.createElement('div');
    div.className = 'line ' + cls;
    div.textContent = text;
    stream.appendChild(div);
    stream.scrollTop = stream.scrollHeight;
  };

  const history = state.chat.slice(0, -1).map((m) => ({ role: m.role, content: m.content })).filter((m) => m.content);

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        history,
        file_answer: $('#file-answer')?.checked || false,
      }),
    });
    await consumeSSE(res, (ev) => {
      if (ev.type === 'token') {
        answer.content += ev.text;
        const bubble = $$('#chat .msg.assistant .bubble').pop();
        const md = bubble?.querySelector('.md');
        if (md) md.innerHTML = mdToHtml(answer.content);
      } else if (ev.type === 'retract') {
        answer.content = answer.content.slice(0, Math.max(0, answer.content.length - (ev.chars || 0)));
      } else if (ev.type === 'step') {
        answer.steps.push(ev);
        appendStep('· ' + ev.description);
      } else if (ev.type === 'filed') {
        answer.filed = ev.path;
        appendStep('✓ 已归档到 ' + ev.path, 'dim');
      } else if (ev.type === 'notice') {
        appendStep(ev.message, 'dim');
      } else if (ev.type === 'error') {
        appendStep('✕ ' + ev.message, 'err');
        if (!answer.content) answer.content = '⚠️ ' + ev.message;
      }
    });
    renderChat();
    if (answer.filed) await refreshAll();
  } catch (e) {
    toast(e.message, 'err');
    answer.content = answer.content || ('⚠️ ' + e.message);
    renderChat();
  } finally {
    state.busy = false;
    btn.disabled = false;
    btn.textContent = '提问';
    if ($('#ask-input')) $('#ask-input').value = '';
  }
}

/* ------------------------------------------------------------------ */
/* 视图：图谱                                                           */
/* ------------------------------------------------------------------ */
async function viewGraph() {
  const main = $('#main');
  main.innerHTML = `
    <div class="wrap wide">
      <div class="page-head">
        <h1 class="page-title">链接图谱</h1>
        <div class="page-meta">节点是 wiki 页面，连线是 [[双链]]。孤立节点说明还没有被任何页面引用。</div>
      </div>
      <div class="graph-wrap"><svg id="graph-svg"></svg>
        <div class="graph-legend">
          ${['concepts', 'entities', 'sources', 'analyses', 'root'].map((k) =>
            `<div><span class="dot" style="background:${kindColor(k)}"></span>${kindLabel(k)}</div>`).join('')}
        </div>
      </div>
    </div>`;

  const data = await api('/api/graph');
  drawGraph(data);
}

function drawGraph(data) {
  const svg = $('#graph-svg');
  if (!svg) return;
  const W = svg.clientWidth || 900;
  const H = svg.clientHeight || 600;
  const nodes = data.nodes.map((n, i) => ({
    ...n,
    x: W / 2 + Math.cos(i * 2.4) * Math.min(W, H) * 0.32 + (Math.random() - .5) * 40,
    y: H / 2 + Math.sin(i * 2.4) * Math.min(W, H) * 0.32 + (Math.random() - .5) * 40,
    vx: 0, vy: 0,
  }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = data.edges.map((e) => ({ ...e, s: byId.get(e.source), t: byId.get(e.target) })).filter((l) => l.s && l.t);

  // 力导向布局
  const iterations = 420;
  for (let step = 0; step < iterations; step++) {
    const alpha = 1 - step / iterations;
    for (const n of nodes) { n.vx = 0; n.vy = 0; }
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy || 0.01;
        const rep = 5200 / d2;
        const d = Math.sqrt(d2);
        dx /= d; dy /= d;
        a.vx -= dx * rep; a.vy -= dy * rep;
        b.vx += dx * rep; b.vy += dy * rep;
      }
    }
    for (const l of links) {
      const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (d - 110) * 0.012;
      l.s.vx += (dx / d) * force; l.s.vy += (dy / d) * force;
      l.t.vx -= (dx / d) * force; l.t.vy -= (dy / d) * force;
    }
    for (const n of nodes) {
      n.vx += (W / 2 - n.x) * 0.0016;
      n.vy += (H / 2 - n.y) * 0.0016;
      n.x += n.vx * alpha * 1.4;
      n.y += n.vy * alpha * 1.4;
      n.x = Math.max(40, Math.min(W - 40, n.x));
      n.y = Math.max(30, Math.min(H - 30, n.y));
    }
  }

  const radius = (n) => Math.max(6, Math.min(22, 6 + Math.sqrt(n.degree) * 3.2));
  const parts = [];
  for (const l of links) {
    parts.push(`<line x1="${l.s.x.toFixed(1)}" y1="${l.s.y.toFixed(1)}" x2="${l.t.x.toFixed(1)}" y2="${l.t.y.toFixed(1)}"
      stroke="#d3d8e2" stroke-width="1.1" />`);
  }
  for (const n of nodes) {
    const r = radius(n);
    const short = n.title.length > 14 ? n.title.slice(0, 13) + '…' : n.title;
    parts.push(`<g class="node" data-path="${escapeHtml(n.id)}" style="cursor:pointer">
      <circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r.toFixed(1)}"
        fill="${kindColor(n.kind)}" fill-opacity="0.88" stroke="#fff" stroke-width="1.6">
        <title>${escapeHtml(n.title)} · ${escapeHtml(n.kind_label)} · 连接 ${n.degree}</title>
      </circle>
      <text x="${n.x.toFixed(1)}" y="${(n.y + r + 12).toFixed(1)}" text-anchor="middle"
        font-size="10.5" fill="#5b6472">${escapeHtml(short)}</text>
    </g>`);
  }
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = parts.join('');

  svg.querySelectorAll('.node').forEach((g) => {
    g.addEventListener('click', () => go('#/page/' + encodeURIComponent(g.dataset.path)));
  });
}

/* ------------------------------------------------------------------ */
/* 视图：体检                                                           */
/* ------------------------------------------------------------------ */
async function viewLint() {
  const main = $('#main');
  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">健康体检</h1>
        <div class="page-meta">结构性问题由规则检查（快、零成本）；矛盾、陈旧说法、数据缺口交给 LLM。</div>
      </div>
      <div class="row" style="margin-bottom:16px">
        <button class="btn btn-primary" id="lint-struct">运行结构体检</button>
        <button class="btn" id="lint-save">保存报告到 wiki</button>
        <button class="btn" id="lint-llm">LLM 语义体检</button>
      </div>
      <div id="lint-body"></div>
      <div id="lint-llm-body"></div>
    </div>`;

  $('#lint-struct').onclick = () => runStructLint();
  $('#lint-save').onclick = async () => {
    const res = await api('/api/lint/save', { method: 'POST' });
    toast(`报告已保存到 ${res.path}`, 'ok');
    await refreshAll();
  };
  $('#lint-llm').onclick = () => runLlmLint();
  await runStructLint();
}

async function runStructLint() {
  const body = $('#lint-body');
  body.innerHTML = '<div class="card"><span class="spinner"></span> 检查中…</div>';
  const r = await api('/api/lint');
  const section = (title, items, render) => {
    if (!items.length) return '';
    return `<div class="lint-section card">
      <h3>${title}<span class="lint-count">${items.length}</span></h3>
      ${items.slice(0, 30).map(render).join('')}
    </div>`;
  };
  const link = (path, label) => `<code data-nav="page" data-path="${escapeHtml(path)}">${escapeHtml(label || path)}</code>`;

  body.innerHTML = `
    <div class="card" style="background:${r.issues ? 'var(--warn-soft)' : 'var(--ok-soft)'};border-color:transparent">
      <div class="card-title">共 ${r.pages} 个页面，发现 ${r.issues} 处待处理项</div>
      <div class="card-sub" style="margin:0">${r.issues ? '下面按类别列出，点击路径可直接跳转。' : '结构很干净，没有发现问题。'}</div>
    </div>
    ${section('孤儿页（没有任何入链）', r.orphans, (i) => `<div class="lint-item">${link(i.path)}　${escapeHtml(i.title)}</div>`)}
    ${section('失效链接', r.broken_links, (i) => `<div class="lint-item">${link(i.path)} 中的 <strong>[[${escapeHtml(i.link)}]]</strong> 指向不存在的页面</div>`)}
    ${section('被反复提及但没有独立页面', r.missing_concepts, (i) => `<div class="lint-item">「${escapeHtml(i.term)}」出现 ${i.mentions} 次</div>`)}
    ${section('陈旧页面', r.stale, (i) => `<div class="lint-item">${link(i.path)}　最后更新 ${escapeHtml(i.updated)}</div>`)}
    ${section('缺少摘要', r.missing_meta, (i) => `<div class="lint-item">${link(i.path)}　${escapeHtml(i.title)}</div>`)}
    ${section('内容过短', r.thin_pages, (i) => `<div class="lint-item">${link(i.path)}　${escapeHtml(i.title)}（${i.chars} 字符）</div>`)}
    ${section('未进入索引', r.unindexed, (i) => `<div class="lint-item">${link(i.path)}　${escapeHtml(i.title)}</div>`)}
  `;
}

async function runLlmLint() {
  const box = $('#lint-llm-body');
  box.innerHTML = `<div class="card"><div class="card-title">LLM 语义体检</div>
    <div class="stream-log" id="lint-stream"><div class="line dim">开始…</div></div>
    <div class="md" id="lint-answer" style="margin-top:14px"></div></div>`;
  const stream = $('#lint-stream');
  let answer = '';
  const append = (t, cls = 'tool') => {
    const d = document.createElement('div');
    d.className = 'line ' + cls; d.textContent = t;
    stream.appendChild(d); stream.scrollTop = stream.scrollHeight;
  };
  try {
    const res = await fetch('/api/lint/llm', { method: 'POST' });
    await consumeSSE(res, (ev) => {
      if (ev.type === 'token') { answer += ev.text; $('#lint-answer').innerHTML = mdToHtml(answer); }
      else if (ev.type === 'retract') answer = answer.slice(0, Math.max(0, answer.length - (ev.chars || 0)));
      else if (ev.type === 'step') append('· ' + ev.description);
      else if (ev.type === 'error') append('✕ ' + ev.message, 'err');
    });
    await refreshAll();
  } catch (e) {
    append('✕ ' + e.message, 'err');
  }
}

/* ------------------------------------------------------------------ */
/* 视图：设置                                                           */
/* ------------------------------------------------------------------ */
async function viewSettings() {
  const main = $('#main');
  const cfg = await api('/api/config');
  state.config = cfg;
  const llm = cfg.llm || {};

  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">设置</h1>
        <div class="page-meta">配置文件位于 <code>${escapeHtml(cfg.paths?.config || 'config.yaml')}</code>，改动会直接写回该文件。</div>
      </div>

      <div class="card">
        <div class="card-title">大模型（LLM）</div>
        <div class="card-sub">填上 API Key 后，wiki 就由模型编译维护。留空则使用内置的确定性编译器。</div>
        <label class="field"><span>API Base URL</span>
          <input type="text" id="cfg-base" value="${escapeHtml(llm.base_url || '')}" placeholder="https://api.openai.com/v1">
          <small>任何 OpenAI 兼容接口都行：DeepSeek、通义、Kimi、Ollama、vLLM…</small></label>
        <label class="field"><span>API Key</span>
          <input type="password" id="cfg-key" placeholder="${llm.api_key_set ? '已设置（' + escapeHtml(llm.api_key_masked || '') + '），留空则保持不变' : '未设置'}"></label>
        <div class="settings-grid">
          <label class="field"><span>模型名</span>
            <input type="text" id="cfg-model" value="${escapeHtml(llm.model || '')}"></label>
          <label class="field"><span>温度</span>
            <input type="text" id="cfg-temp" value="${escapeHtml(String(llm.temperature ?? 0.2))}"></label>
          <label class="field"><span>单次回答上限 tokens</span>
            <input type="text" id="cfg-maxtok" value="${escapeHtml(String(llm.max_tokens ?? 4096))}"></label>
          <label class="field"><span>工具调用轮数上限</span>
            <input type="text" id="cfg-rounds" value="${escapeHtml(String(llm.max_tool_rounds ?? 24))}"></label>
        </div>
        <label class="field"><span>额外写作要求（追加到 SCHEMA 之后）</span>
          <textarea id="cfg-extra" style="min-height:70px">${escapeHtml(llm.extra_instructions || '')}</textarea></label>
        <button class="btn btn-primary" id="save-llm">保存</button>
      </div>

      <div class="card">
        <div class="card-title">抓取</div>
        <div class="card-sub">B 站字幕接口需要登录态；填了 Cookie 后就能抓到视频文稿。</div>
        <label class="field"><span>B 站 Cookie</span>
          <input type="text" id="cfg-cookie" value="${escapeHtml(cfg.fetch?.bilibili_cookie || '')}"
                 placeholder="SESSDATA=xxx; bili_jct=xxx">
          <small>浏览器登录 B 站后，从开发者工具里复制 Cookie 里的 SESSDATA 即可。</small></label>
        <button class="btn btn-primary" id="save-fetch">保存</button>
      </div>

      <div class="card">
        <div class="card-title">维护操作</div>
        <div class="card-sub">这些都是幂等的，可以随时执行。</div>
        <div class="row">
          <button class="btn" id="op-reindex">重建索引 index.md</button>
          <button class="btn" id="op-recompile">全量重新编译 wiki</button>
        </div>
        <div id="op-log" class="stream-log hidden"></div>
      </div>

      <div class="card">
        <div class="card-title">路径</div>
        <dl class="meta-grid">
          <dt>知识库</dt><dd>${escapeHtml(cfg.paths?.vault || '')}</dd>
          <dt>原始素材</dt><dd>${escapeHtml(cfg.paths?.raw || '')}</dd>
          <dt>wiki</dt><dd>${escapeHtml(cfg.paths?.wiki || '')}</dd>
          <dt>配置文件</dt><dd>${escapeHtml(cfg.paths?.config || '')}</dd>
        </dl>
      </div>
    </div>`;

  $('#save-llm').onclick = async () => {
    const payload = {
      llm: {
        base_url: $('#cfg-base').value.trim(),
        model: $('#cfg-model').value.trim(),
        temperature: parseFloat($('#cfg-temp').value) || 0.2,
        max_tokens: parseInt($('#cfg-maxtok').value, 10) || 4096,
        max_tool_rounds: parseInt($('#cfg-rounds').value, 10) || 24,
        extra_instructions: $('#cfg-extra').value,
      },
    };
    const key = $('#cfg-key').value.trim();
    if (key) payload.llm.api_key = key;
    await api('/api/config', { method: 'PUT', body: JSON.stringify(payload) });
    toast('已保存', 'ok');
    await refreshAll();
    $('#cfg-key').value = '';
  };

  $('#save-fetch').onclick = async () => {
    await api('/api/config', {
      method: 'PUT',
      body: JSON.stringify({ fetch: { bilibili_cookie: $('#cfg-cookie').value.trim() } }),
    });
    toast('已保存', 'ok');
  };

  $('#op-reindex').onclick = async () => {
    await api('/api/index/rebuild', { method: 'POST' });
    toast('索引已重建', 'ok');
    await refreshAll();
  };

  $('#op-recompile').onclick = async () => {
    if (!confirm('全量重新编译会重新生成所有素材页与概念页，耗时较长。继续？')) return;
    const log = $('#op-log');
    log.classList.remove('hidden');
    log.innerHTML = '';
    const append = (t, cls = '') => {
      const d = document.createElement('div'); d.className = 'line ' + cls; d.textContent = t;
      log.appendChild(d); log.scrollTop = log.scrollHeight;
    };
    try {
      const res = await fetch('/api/compile', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all: true }),
      });
      await consumeSSE(res, (ev) => {
        if (ev.type === 'batch_progress') append(`\n[${ev.index}/${ev.total}] 《${ev.title}》`, 'tool');
        else if (ev.type === 'step') append('  · ' + ev.description, 'tool');
        else if (ev.type === 'compile_done') append(`  ✓ ${ev.created.length} 个页面`);
        else if (ev.type === 'batch_done') append(`\n完成，共 ${ev.count} 篇`, 'dim');
        else if (ev.type === 'error') append('  ✕ ' + ev.message, 'err');
      });
      toast('重新编译完成', 'ok');
      await refreshAll();
    } catch (e) { append('✕ ' + e.message, 'err'); }
  };
}

/* ------------------------------------------------------------------ */
/* 视图：原始素材                                                       */
/* ------------------------------------------------------------------ */
async function viewRaw(path) {
  const main = $('#main');
  main.innerHTML = '<div class="wrap"><div class="empty"><span class="spinner"></span> 载入中…</div></div>';
  const data = await api('/api/raw/content?path=' + encodeURIComponent(path));
  const fm = data.frontmatter || {};
  main.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <h1 class="page-title">${escapeHtml(fm.title || path)}</h1>
        <div class="page-meta">
          <span class="kind-chip">原始素材 · 只读</span>
          <span>${escapeHtml(path)}</span>
          ${safeUrl(fm.source_url) ? `<span>·</span><a href="${escapeHtml(safeUrl(fm.source_url))}" target="_blank" rel="noreferrer">原链接 ↗</a>` : ''}
          <span class="spacer"></span>
          <button class="btn btn-sm" id="raw-compile">编译进 wiki</button>
        </div>
      </div>
      <div class="card" style="background:var(--panel-2)">
        <dl class="meta-grid">
          ${Object.entries(fm).filter(([k]) => !['title'].includes(k)).map(([k, v]) =>
            `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(Array.isArray(v) ? v.join(', ') : String(v))}</dd>`).join('')}
        </dl>
      </div>
      <div class="card"><div class="md">${mdToHtml(data.body)}</div></div>
      <div id="compile-area"></div>
    </div>`;
  $('#raw-compile').onclick = () => startCompile([path]);
}

/* ------------------------------------------------------------------ */
/* 全局搜索                                                             */
/* ------------------------------------------------------------------ */
function setupSearch() {
  const input = $('#global-search');
  const panel = $('#search-panel');
  let timer = null;

  const close = () => panel.classList.add('hidden');
  document.addEventListener('click', (e) => {
    if (!panel.contains(e.target) && e.target !== input) close();
  });

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { close(); return; }
    timer = setTimeout(async () => {
      const res = await api('/api/search?q=' + encodeURIComponent(q) + '&limit=20');
      const hits = res.results || [];
      if (!hits.length) {
        panel.innerHTML = '<div class="search-hit"><div class="hit-snip">没有匹配结果</div></div>';
      } else {
        panel.innerHTML = hits.map((h) => `
          <div class="search-hit" data-nav="page" data-path="${escapeHtml(h.path)}">
            <div class="hit-title">${escapeHtml(h.title)}<span class="hit-kind">${escapeHtml(h.kind_label)}</span></div>
            <div class="hit-snip">${escapeHtml((h.hits[0]?.text || '').replace(/\s+/g, ' ').slice(0, 130))}</div>
          </div>`).join('');
      }
      panel.classList.remove('hidden');
    }, 180);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { close(); input.blur(); }
    if (e.key === 'Enter') {
      const first = panel.querySelector('.search-hit[data-path]');
      if (first) { go('#/page/' + encodeURIComponent(first.dataset.path)); close(); }
    }
  });
}

/* ------------------------------------------------------------------ */
/* 全局事件委托                                                         */
/* ------------------------------------------------------------------ */
document.addEventListener('click', (e) => {
  const nav = e.target.closest('[data-nav]');
  if (nav) {
    e.preventDefault();
    const target = nav.dataset.nav;
    const path = nav.dataset.path || '';
    if (target === 'page') go('#/page/' + encodeURIComponent(path));
    else if (target === 'raw') go('#/raw/' + encodeURIComponent(path));
    else go('#/' + target);
    $('#search-panel')?.classList.add('hidden');
    return;
  }

  const wiki = e.target.closest('[data-wiki]');
  if (wiki) {
    e.preventDefault();
    go('#/page/' + encodeURIComponent(wiki.dataset.wiki));
    return;
  }

  const openRaw = e.target.closest('[data-open-raw]');
  if (openRaw) {
    go('#/raw/' + encodeURIComponent(openRaw.dataset.openRaw));
    return;
  }

  const tag = e.target.closest('.tag[data-search]');
  if (tag) {
    const input = $('#global-search');
    input.value = tag.dataset.search;
    input.dispatchEvent(new Event('input'));
    input.focus();
  }
});

$('#brand').addEventListener('click', () => go('#/home'));

document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    $('#global-search').focus();
    $('#global-search').select();
  }
});

window.addEventListener('hashchange', route);

/* ------------------------------------------------------------------ */
/* 启动                                                                 */
/* ------------------------------------------------------------------ */
(async function init() {
  try {
    await refreshAll();
    await route();
  } catch (e) {
    $('#main').innerHTML = `<div class="wrap"><div class="empty">
      <h3>加载失败</h3><div class="hint">${escapeHtml(e.message)}</div></div></div>`;
  }
})();

})();
