import { Link } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ComponentProps, ReactNode } from "react";

const WIKI_LINK_PATTERN = /\[\[([^[\]|]+)(?:\|([^[\]]+))?\]\]/g;
const FENCE_PATTERN = /^\s{0,3}(`{3,}|~{3,})/;

/** 将 [[页面名|显示文本]] 转成应用内 Markdown 链接，交给下方自定义 anchor 渲染。 */
function convertLineWikiLinks(line: string): string {
  return line.replace(WIKI_LINK_PATTERN, (_match, target: string, display?: string) => {
    const label = (display ?? target).trim() || target.trim();
    const name = target.trim();
    if (!name) return _match;
    return `[${label}](/page/${encodeURIComponent(name)})`;
  });
}

/** 避免改动围栏代码块里的 [[示例]] 文本。 */
function withWikiLinks(markdown: string): string {
  const lines = markdown.split(/\r?\n/);
  let fence: string | null = null;
  const converted = lines.map((line) => {
    const opening = line.match(FENCE_PATTERN);
    if (opening) {
      const marker = opening[1];
      if (!fence) {
        fence = marker;
        return line;
      }
      if (marker.startsWith(fence)) {
        fence = null;
        return line;
      }
    }
    return fence ? line : convertLineWikiLinks(line);
  });
  return converted.join("\n");
}

type AnchorProps = ComponentProps<"a"> & { children?: ReactNode };

function MarkdownAnchor({ href, children, ...props }: AnchorProps) {
  const isPageLink = typeof href === "string" && href.startsWith("/page/");
  if (isPageLink) {
    return (
      <Link to={href} className="wikilink" {...props}>
        {children}
      </Link>
    );
  }
  const external = typeof href === "string" && /^https?:\/\//i.test(href);
  return (
    <a
      href={href}
      rel={external ? "noopener noreferrer" : props.rel}
      target={external ? "_blank" : props.target}
      {...props}
    >
      {children}
    </a>
  );
}

const markdownComponents: Components = {
  a: MarkdownAnchor,
  table: ({ children, ...props }) => (
    <div className="table-scroll">
      <table {...props}>{children}</table>
    </div>
  ),
  th: ({ children, ...props }) => (
    <th
      {...props}
      style={{
        textAlign: "left",
        padding: "8px 10px",
        borderBottom: "1px solid var(--border-strong)",
        background: "var(--surface-2)",
        fontSize: "var(--fs-meta)",
      }}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td
      {...props}
      style={{
        padding: "8px 10px",
        borderBottom: "1px solid var(--border)",
        verticalAlign: "top",
        fontSize: "var(--fs-sm)",
      }}
    >
      {children}
    </td>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote className="callout" {...props}>
      {children}
    </blockquote>
  ),
  code: ({ children, className, ...props }) => (
    <code
      className={className}
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: ".92em",
        padding: className ? undefined : "1px 5px",
        borderRadius: "var(--r-sm)",
        background: className ? undefined : "var(--code-bg)",
      }}
      {...props}
    >
      {children}
    </code>
  ),
};

export function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {withWikiLinks(content)}
    </ReactMarkdown>
  );
}
