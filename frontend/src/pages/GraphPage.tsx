/** PAGE-006：全局知识图谱。 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { select, type Selection } from "d3-selection";
import { zoom, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import { api } from "../api/client";
import type { GraphEdge, GraphNode, GraphResponse, ZoneInfo } from "../api/types";

type Depth = 1 | 2;

type GraphSimulationNode = GraphNode & SimulationNodeDatum;
type GraphSimulationLink = SimulationLinkDatum<GraphSimulationNode>;
type GraphSvgSelection = Selection<SVGSVGElement, unknown, null, undefined>;

interface CanvasSize {
  width: number;
  height: number;
}

interface HoverState {
  node: GraphNode;
  x: number;
  y: number;
}

const NODE_COLORS: Record<GraphNode["type"], string> = {
  source: "var(--primary)",
  concept: "var(--accent)",
  entity: "var(--primary-border)",
  analysis: "var(--warning)",
};

const NODE_TYPE_LABELS: Record<GraphNode["type"], string> = {
  source: "来源",
  concept: "概念",
  entity: "实体",
  analysis: "分析",
};

const DEPTH_OPTIONS: { value: Depth; label: string }[] = [
  { value: 1, label: "1 层" },
  { value: 2, label: "2 层" },
];

function nodeRadius(node: GraphSimulationNode, maxDegree: number): number {
  const normalized = maxDegree === 0 ? 0 : Math.sqrt(node.degree / maxDegree);
  return 7 + normalized * 17;
}

export function GraphPage() {
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const [depth, setDepth] = useState<Depth>(1);
  const [zone, setZone] = useState("");
  const [zones, setZones] = useState<ZoneInfo[]>([]);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState<CanvasSize>({ width: 0, height: 0 });
  const [hover, setHover] = useState<HoverState | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const openNode = useCallback((nodeId: string) => {
    navigateRef.current(`/page/${encodeURIComponent(nodeId)}`);
  }, []);
  const openNodeRef = useRef(openNode);
  openNodeRef.current = openNode;

  const goToIngest = useCallback(() => {
    navigateRef.current("/ingest");
  }, []);

  useEffect(() => {
    let cancelled = false;

    api
      .get<ZoneInfo[]>("/zones")
      .then((items) => {
        if (!cancelled) setZones(items);
      })
      .catch(() => {
        /* 分区接口失败不应阻塞整张图；图数据接口会单独提示错误。 */
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({ depth: String(depth) });
    if (zone) params.set("zone", zone);

    api
      .get<GraphResponse>(`/graph?${params.toString()}`)
      .then((data) => {
        if (!cancelled) setGraph(data);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "图谱加载失败，请稍后重试");
        setGraph(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [depth, zone, reloadToken]);

  useEffect(() => {
    const element = canvasRef.current;
    if (!element) return;

    const updateSize = () => {
      const rect = element.getBoundingClientRect();
      setSize({ width: rect.width, height: rect.height });
    };

    const observer = new ResizeObserver(updateSize);
    observer.observe(element);
    updateSize();

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const svgElement = svgRef.current;
    if (!graph || size.width <= 0 || size.height <= 0 || !svgElement) return;

    const svg = select(svgElement);
    svg.selectAll("*").remove();

    const nodes: GraphSimulationNode[] = graph.nodes.map((node) => ({ ...node }));
    const links: GraphSimulationLink[] = graph.edges.map((edge: GraphEdge) => ({ ...edge }));
    const maxDegree = nodes.reduce((max, node) => Math.max(max, node.degree), 0);
    const centerX = size.width / 2;
    const centerY = size.height / 2;

    const root = svg.append("g").attr("class", "graph-root");
    const edgeSelection = root
      .append("g")
      .attr("class", "graph-edges")
      .selectAll<SVGLineElement, GraphSimulationLink>("line")
      .data(links)
      .join("line")
      .attr("class", "graph-edge");

    const nodeSelection = root
      .append("g")
      .attr("class", "graph-nodes")
      .selectAll<SVGGElement, GraphSimulationNode>("g")
      .data(nodes)
      .join((enter) => {
        const group = enter.append("g").attr("class", "graph-node").attr("tabindex", 0);
        group.append("circle").attr("class", "graph-node-circle");
        group.append("text").attr("class", "graph-node-label").attr("text-anchor", "middle");
        return group;
      });

    nodeSelection
      .each(function setNodeVisual(node) {
        const current = select(this);
        const radius = nodeRadius(node, maxDegree);

        current
          .select<SVGCircleElement>("circle")
          .attr("r", radius)
          .attr("fill", NODE_COLORS[node.type] ?? NODE_COLORS.entity)
          .append("title")
          .text(node.title);

        current
          .select<SVGTextElement>("text")
          .attr("dy", radius + 15)
          .text(node.title);
      })
      .on("click", (_event: unknown, node: GraphSimulationNode) => openNodeRef.current(node.id))
      .on("keydown", (event: KeyboardEvent, node: GraphSimulationNode) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        openNodeRef.current(node.id);
      })
      .on("pointerenter", (event: PointerEvent, node: GraphSimulationNode) => {
        const bounds = svgElement.getBoundingClientRect();
        setHover({
          node: {
            id: node.id,
            title: node.title,
            type: node.type,
            zone: node.zone,
            degree: node.degree,
            status: node.status,
          },
          x: event.clientX - bounds.left,
          y: event.clientY - bounds.top,
        });
      })
      .on("pointerleave", () => setHover(null));

    const zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event: { transform: ZoomTransform }) => {
        root.attr("transform", event.transform.toString());
      });

    svg.call(zoomBehavior).on("dblclick.zoom", null);

    const simulation: Simulation<GraphSimulationNode, GraphSimulationLink> = forceSimulation(nodes)
      .force(
        "link",
        forceLink<GraphSimulationNode, GraphSimulationLink>(links)
          .id((node) => node.id)
          .distance(72)
          .strength(0.55),
      )
      .force("charge", forceManyBody().strength(nodes.length > 180 ? -180 : -280))
      .force("center", forceCenter(centerX, centerY))
      .force(
        "collide",
        forceCollide<GraphSimulationNode>().radius((node) => nodeRadius(node, maxDegree) + 11),
      )
      .on("tick", () => {
        edgeSelection
          .attr("x1", (link) => (link.source as GraphSimulationNode).x ?? centerX)
          .attr("y1", (link) => (link.source as GraphSimulationNode).y ?? centerY)
          .attr("x2", (link) => (link.target as GraphSimulationNode).x ?? centerX)
          .attr("y2", (link) => (link.target as GraphSimulationNode).y ?? centerY);

        nodeSelection.attr("transform", (node) => `translate(${node.x ?? centerX}, ${node.y ?? centerY})`);
      });

    return () => {
      simulation.stop();
      svg.on(".zoom", null);
      svg.selectAll("*").remove();
    };
  }, [graph, size]);

  const zoneOptions = useMemo(
    () => [{ name: "", page_count: graph?.node_count ?? 0 }, ...zones],
    [graph?.node_count, zones],
  );
  const empty = !loading && !error && graph !== null && graph.nodes.length === 0;

  return (
    <div className="page">
      <style>{`
        .graph-canvas { position: relative; height: calc(100vh - var(--topbar-h) - 188px); min-height: 430px; overflow: hidden; }
        .graph-svg { display: block; width: 100%; height: 100%; cursor: grab; background:
          radial-gradient(circle at 1px 1px, var(--grid-line) 1px, transparent 0) 0 0 / 28px 28px,
          var(--surface-2); }
        .graph-svg:active { cursor: grabbing; }
        .graph-edge { stroke: var(--border); stroke-width: 1; opacity: .86; }
        .graph-node { cursor: pointer; outline: none; }
        .graph-node-circle { stroke: var(--surface); stroke-width: 2; transition: stroke .16s ease, stroke-width .16s ease; }
        .graph-node:hover .graph-node-circle,
        .graph-node:focus-visible .graph-node-circle { stroke: var(--primary); stroke-width: 3; }
        .graph-node:hover .graph-node-label { font-weight: 600; fill: var(--primary); }
        .graph-node-label { font-size: var(--fs-caption); fill: var(--text); paint-order: stroke; stroke: var(--surface-2); stroke-width: 3px; stroke-linejoin: round; pointer-events: none; user-select: none; }
        .graph-tooltip { position: absolute; z-index: 2; pointer-events: none; transform: translate(-50%, calc(-100% - 12px)); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-md); box-shadow: var(--shadow-card); padding: var(--sp-2) var(--sp-3); min-width: 148px; max-width: 240px; }
      `}</style>

      <h1 className="page-title">知识图谱</h1>
      <p className="page-sub">
        {graph ? `${graph.node_count} 个页面 · ${graph.edge_count} 条链接` : "浏览页面之间的链接关系与知识结构。"}
      </p>

      {graph?.truncated && (
        <div className="callout callout-warning" role="status" style={{ marginBottom: "var(--sp-4)" }}>
          节点过多，已截断显示
        </div>
      )}

      <div className="toolbar" style={{ marginBottom: "var(--sp-4)", flexWrap: "wrap" }}>
        <label className="tiny" htmlFor="graph-zone">分区</label>
        <select
          id="graph-zone"
          className="input"
          value={zone}
          onChange={(event) => setZone(event.target.value)}
          style={{ width: 190, height: 30, padding: "0 var(--sp-3)" }}
        >
          {zoneOptions.map((item) => (
            <option key={item.name || "__all__"} value={item.name}>
              {item.name ? item.name : "全部分区"}
            </option>
          ))}
        </select>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
          <span className="tiny">深度</span>
          <nav className="seg" aria-label="图谱深度">
            {DEPTH_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setDepth(option.value)}
                aria-pressed={depth === option.value}
                style={{
                  padding: "5px 12px",
                  border: 0,
                  borderRight: option.value === 1 ? "1px solid var(--border)" : 0,
                  background: depth === option.value ? "var(--primary-soft)" : "transparent",
                  color: depth === option.value ? "var(--primary)" : "var(--text-2)",
                  font: "inherit",
                  fontSize: "var(--fs-meta)",
                  cursor: "pointer",
                }}
              >
                {option.label}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {error && (
        <div className="callout callout-danger" role="alert" style={{ marginBottom: "var(--sp-4)" }}>
          {error}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setReloadToken((token) => token + 1)}>
            重试
          </button>
        </div>
      )}

      {empty ? (
        <div className="card card-pad" style={{ textAlign: "center", padding: "var(--sp-10)" }}>
          <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>还没有可展示的页面</div>
          <p className="muted" style={{ margin: "var(--sp-2) 0 0" }}>
            投放素材并完成编译后，这里会自动生成知识图谱。
          </p>
          <button type="button" className="btn btn-sm" style={{ marginTop: "var(--sp-4)" }} onClick={goToIngest}>
            去投放素材
          </button>
        </div>
      ) : (
        <div
          ref={canvasRef}
          className="graph-canvas card"
          aria-busy={loading}
          aria-label="全局知识图谱画布"
        >
          <svg ref={svgRef} className="graph-svg" role="img" aria-label="可缩放知识图谱" />

          {loading && (
            <div className="tiny" style={{ position: "absolute", left: "var(--sp-4)", top: "var(--sp-3)" }}>
              正在加载图谱…
            </div>
          )}

          {hover && (
            <div className="graph-tooltip" style={{ left: hover.x, top: hover.y }}>
              <div style={{ fontWeight: 500, overflowWrap: "anywhere" }}>{hover.node.title}</div>
              <div className="tiny" style={{ marginTop: 2 }}>
                {`${NODE_TYPE_LABELS[hover.node.type] ?? hover.node.type} · 关联 ${hover.node.degree}`}
              </div>
              <div className="tiny">{hover.node.zone || "未分区"}</div>
            </div>
          )}
        </div>
      )}

      <div className="tiny" style={{ marginTop: "var(--sp-3)" }}>
        滚轮缩放 · 拖拽平移 · 点击节点打开页面
      </div>
    </div>
  );
}
