import { useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type WheelEvent as ReactWheelEvent } from "react";
import type { EpisodeMeta, Universe, Version } from "../types";

const COL_W = 168;
const ROW_H = 96;
const R = 11;
const LABEL_MAX = 16;

// Cycled per universe (by first-appearance order) — same "distinct lane" idea
// as persona colors elsewhere in the app.
const PALETTE = ["#b23a5b", "#2f6a4b", "#1c6e8c", "#8a5a2b", "#6a4c93", "#a3333d", "#3a7d44", "#4c6ef5"];

export const GHOST_PREFIX = "ghost::";

/** Hand-rolled SVG tree — same algorithm as the story-tree canvas (leaves get
 * sequential x-slots in DFS order, internal nodes sit at the mean x of their
 * children), applied to Versions instead of beats: parent_version_id is the
 * edge, episode.sequence is the row. A version with 3 children fans out into
 * 3 edges; a version with none, followed the normal way, is a single dashed
 * "ghost" node one row down inviting the next continuation. */
export function UniverseGraphCanvas({
  universes, episodes, versions, selectedKey, onSelect,
}: {
  universes: Universe[];
  episodes: EpisodeMeta[];
  versions: Version[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 48, y: 40 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const colorOf = useMemo(() => {
    const m = new Map(universes.map((u, i) => [u.id, PALETTE[i % PALETTE.length]]));
    return (universeId: string) => m.get(universeId) ?? "var(--ink-2)";
  }, [universes]);

  const seqOf = useMemo(() => {
    const m = new Map(episodes.map((e) => [e.id, e.sequence]));
    return (episodeId: string) => m.get(episodeId) ?? 1;
  }, [episodes]);

  const { positions, edges, nodeMeta } = useMemo(
    () => layout(versions, seqOf, colorOf, universes, episodes),
    [versions, seqOf, colorOf, universes, episodes],
  );

  const onPath = useMemo(() => {
    const byId = new Map(versions.map((v) => [v.id, v]));
    const path = new Set<string>();
    let curId = selectedKey?.startsWith(GHOST_PREFIX) ? selectedKey.slice(GHOST_PREFIX.length) : selectedKey;
    if (selectedKey?.startsWith(GHOST_PREFIX)) path.add(selectedKey);
    let cur = curId ? byId.get(curId) : undefined;
    while (cur) {
      path.add(cur.id);
      cur = cur.parent_version_id ? byId.get(cur.parent_version_id) : undefined;
    }
    return path;
  }, [versions, selectedKey]);

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

  if (nodeMeta.size === 0) return <div className="empty">No episodes yet.</div>;

  return (
    <svg className="universe-graph" onWheel={onWheel} onMouseDown={onMouseDown}
      onMouseMove={onMouseMove} onMouseUp={endDrag} onMouseLeave={endDrag}>
      <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
        {edges.map(([a, b]) => {
          const pa = positions.get(a), pb = positions.get(b);
          const meta = nodeMeta.get(b);
          if (!pa || !pb || !meta) return null;
          const active = onPath.has(a) && onPath.has(b);
          return (
            <line key={`${a}-${b}`} className={`universe-edge${active ? " on-path" : ""}`}
              stroke={meta.color} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} />
          );
        })}
        {Array.from(nodeMeta.entries()).map(([key, meta]) => {
          const p = positions.get(key);
          if (!p) return null;
          const sel = key === selectedKey;
          const cls = ["universe-node", meta.ghost && "ghost", sel && "sel", onPath.has(key) && "on-path"]
            .filter(Boolean).join(" ");
          return (
            <g key={key} className={cls} transform={`translate(${p.x},${p.y})`}
              onClick={() => onSelect(key)}>
              <circle r={R} stroke={meta.color} fill={meta.ghost ? "none" : meta.color} />
              <title>{meta.universeName}</title>
              <text y={R + 14} fill={meta.color}>{truncate(meta.universeName, LABEL_MAX)}</text>
              <text y={R + 27} className="universe-node-episode">{meta.episodeLabel}</text>
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

type NodeMeta = { color: string; universeName: string; episodeLabel: string; ghost: boolean };

function layout(
  allVersions: Version[],
  seqOf: (episodeId: string) => number,
  colorOf: (universeId: string) => string,
  universes: Universe[],
  episodes: EpisodeMeta[],
) {
  // Exclude same-episode revision variants (rerun_with_fix / materialized
  // story-tree branches) — those are in-episode script experiments, shown in
  // EpisodeView's own version list, not part of this cross-episode graph.
  const byAnyId = new Map(allVersions.map((v) => [v.id, v]));
  const versions = allVersions.filter((v) => {
    if (!v.parent_version_id) return true;
    const parent = byAnyId.get(v.parent_version_id);
    return !parent || parent.episode_id !== v.episode_id;
  });

  const byId = new Map(versions.map((v) => [v.id, v]));
  const children = new Map<string, Version[]>();
  const roots: Version[] = [];
  for (const v of versions) {
    if (v.parent_version_id && byId.has(v.parent_version_id)) {
      const arr = children.get(v.parent_version_id) ?? [];
      arr.push(v);
      children.set(v.parent_version_id, arr);
    } else {
      roots.push(v);
    }
  }

  const universeName = (id: string) => (id ? universes.find((u) => u.id === id)?.name ?? "universe" : "Main");
  const episodeLabel = (id: string) => {
    const e = episodes.find((ep) => ep.id === id);
    return e ? `E${e.sequence}` : "";
  };

  const positions = new Map<string, { x: number; y: number }>();
  const nodeMeta = new Map<string, NodeMeta>();
  const edges: [string, string][] = [];
  let nextLeafX = 0;

  function place(v: Version): number {
    const kids = children.get(v.id) ?? [];
    let x: number;
    if (kids.length === 0) {
      x = nextLeafX * COL_W;
      nextLeafX += 1;
    } else {
      const xs = kids.map(place);
      x = xs.reduce((a, b) => a + b, 0) / xs.length;
    }
    positions.set(v.id, { x, y: (seqOf(v.episode_id) - 1) * ROW_H });
    nodeMeta.set(v.id, {
      color: colorOf(v.universe_id), universeName: universeName(v.universe_id),
      episodeLabel: episodeLabel(v.episode_id), ghost: false,
    });
    for (const k of kids) edges.push([v.id, k.id]);
    if (kids.length === 0) {
      // leaf — offer the next continuation as a dashed ghost one row down
      const ghostKey = `${GHOST_PREFIX}${v.id}`;
      positions.set(ghostKey, { x, y: (seqOf(v.episode_id)) * ROW_H });
      nodeMeta.set(ghostKey, {
        color: colorOf(v.universe_id), universeName: universeName(v.universe_id),
        episodeLabel: `E${seqOf(v.episode_id) + 1}`, ghost: true,
      });
      edges.push([v.id, ghostKey]);
    }
    return x;
  }
  for (const r of roots) place(r);

  return { positions, edges, nodeMeta };
}
