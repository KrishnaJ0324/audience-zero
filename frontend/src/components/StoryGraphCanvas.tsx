import { useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type WheelEvent as ReactWheelEvent } from "react";
import type { StoryNode } from "../types";

const ROW_H = 74;
const COL_W = 96;
const R = 9;

/** Hand-rolled SVG tree — no graph library. Layout: leaves get sequential
 * x-slots in DFS order, internal nodes sit at the mean x of their children;
 * y is beat_index * ROW_H (already a depth counter by construction, since
 * every parent->child edge increments beat_index by exactly one). */
export function StoryGraphCanvas({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: StoryNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 48, y: 40 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const { positions, edges } = useMemo(() => layout(nodes), [nodes]);

  const onPath = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const path = new Set<string>();
    let cur = selectedId ? byId.get(selectedId) : undefined;
    while (cur) {
      path.add(cur.id);
      cur = cur.parent_node_id ? byId.get(cur.parent_node_id) : undefined;
    }
    return path;
  }, [nodes, selectedId]);

  const onWheel = (e: ReactWheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    setZoom((z) => Math.min(2.5, Math.max(0.4, z - e.deltaY * 0.001)));
  };
  const onMouseDown = (e: ReactMouseEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
  };
  const onMouseMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    setPan({ x: drag.current.panX + (e.clientX - drag.current.x), y: drag.current.panY + (e.clientY - drag.current.y) });
  };
  const endDrag = () => { drag.current = null; };

  if (nodes.length === 0) return <div className="empty">No nodes yet.</div>;

  return (
    <svg
      className="story-graph"
      onWheel={onWheel}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={endDrag}
      onMouseLeave={endDrag}
    >
      <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
        {edges.map(([a, b]) => {
          const pa = positions.get(a), pb = positions.get(b);
          if (!pa || !pb) return null;
          const active = onPath.has(a) && onPath.has(b);
          return (
            <line key={`${a}-${b}`} className={`story-edge${active ? " on-path" : ""}`}
              x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} />
          );
        })}
        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const cls = ["story-node", n.id === selectedId && "sel", onPath.has(n.id) && "on-path"]
            .filter(Boolean).join(" ");
          return (
            <g key={n.id} className={cls} transform={`translate(${p.x},${p.y})`}
              onClick={() => onSelect(n.id)}>
              <circle r={R} />
              {n.consistency_issues.length > 0 && (
                <circle className="story-node-warn" r={3.5} cx={R - 1} cy={-R + 1} />
              )}
              <text y={R + 14}>{n.prompt ? truncate(n.prompt, 16) : n.label || "root"}</text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function layout(nodes: StoryNode[]) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map<string, StoryNode[]>();
  const roots: StoryNode[] = [];
  for (const n of nodes) {
    if (n.parent_node_id && byId.has(n.parent_node_id)) {
      const arr = children.get(n.parent_node_id) ?? [];
      arr.push(n);
      children.set(n.parent_node_id, arr);
    } else {
      roots.push(n);
    }
  }

  const positions = new Map<string, { x: number; y: number }>();
  const edges: [string, string][] = [];
  let nextLeafX = 0;

  function place(node: StoryNode): number {
    const kids = children.get(node.id) ?? [];
    let x: number;
    if (kids.length === 0) {
      x = nextLeafX * COL_W;
      nextLeafX += 1;
    } else {
      const xs = kids.map(place);
      x = xs.reduce((a, b) => a + b, 0) / xs.length;
    }
    positions.set(node.id, { x, y: node.beat_index * ROW_H });
    for (const k of kids) edges.push([node.id, k.id]);
    return x;
  }
  for (const r of roots) place(r);

  return { positions, edges };
}
