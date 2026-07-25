import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LiveState } from "../useRun";

interface Props {
  state: LiveState;
  showAggregate?: boolean;
}

/**
 * Six attention curves drawing progressively across the episode timeline, with
 * drop-point markers and the weakest beat highlighted. This is the magic
 * moment: curves dipping in unison at the boring beat.
 */
export function AttentionChart({ state, showAggregate = true }: Props) {
  const { beats, personas, scores, verdict } = state;
  const [hidden, setHidden] = useState<Record<string, boolean>>({});

  const data = useMemo(() => {
    return beats.map((b) => {
      const row: Record<string, number | string> = {
        beat: `B${b.index + 1}`,
        idx: b.index,
      };
      for (const p of personas) {
        const v = scores[p.id]?.[b.index];
        if (v !== undefined) row[p.id] = v;
      }
      if (showAggregate && verdict?.aggregate_curve?.[b.index] !== undefined) {
        row.__aggregate = Math.round(verdict.aggregate_curve[b.index]);
      }
      return row;
    });
  }, [beats, personas, scores, verdict, showAggregate]);

  const weakest = verdict?.weakest_beat;

  const toggle = (id: string) =>
    setHidden((h) => ({ ...h, [id]: !h[id] }));

  return (
    <div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 16, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="beat"
              tick={{ fill: "var(--muted-2)", fontSize: 11, fontFamily: "var(--mono)" }}
              axisLine={{ stroke: "var(--border)" }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: "var(--muted-2)", fontSize: 11, fontFamily: "var(--mono)" }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip
              contentStyle={{
                background: "var(--panel-2)",
                border: "1px solid var(--border-glow)",
                borderRadius: 10,
                fontSize: 12,
                fontFamily: "var(--mono)",
              }}
              labelStyle={{ color: "var(--muted)" }}
            />
            {weakest !== undefined && beats[weakest] && (
              <ReferenceLine
                x={`B${weakest + 1}`}
                stroke="var(--danger)"
                strokeDasharray="4 4"
                strokeOpacity={0.6}
                label={{
                  value: "weakest beat",
                  fill: "var(--danger)",
                  fontSize: 10,
                  fontFamily: "var(--mono)",
                  position: "top",
                }}
              />
            )}
            {personas.map((p) => (
              <Line
                key={p.id}
                type="monotone"
                dataKey={p.id}
                name={p.name}
                stroke={p.color}
                strokeWidth={2}
                dot={false}
                hide={hidden[p.id]}
                isAnimationActive={false}
                connectNulls
                strokeOpacity={0.92}
              />
            ))}
            {showAggregate && verdict && (
              <Line
                type="monotone"
                dataKey="__aggregate"
                name="Panel (weighted)"
                stroke="var(--ink)"
                strokeWidth={3.5}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            )}
            {showAggregate && verdict && weakest !== undefined && (
              <ReferenceDot
                x={`B${weakest + 1}`}
                y={Math.round(verdict.aggregate_curve[weakest])}
                r={5}
                fill="var(--danger)"
                stroke="#fff"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="legend">
        {personas.map((p) => (
          <span
            key={p.id}
            className={`item ${hidden[p.id] ? "off" : ""}`}
            onClick={() => toggle(p.id)}
          >
            <span className="swatch" style={{ background: p.color }} />
            {p.name}
          </span>
        ))}
        {showAggregate && verdict && (
          <span className="item">
            <span className="swatch" style={{ background: "var(--ink)", height: 4 }} />
            Panel (weighted)
          </span>
        )}
      </div>
    </div>
  );
}
