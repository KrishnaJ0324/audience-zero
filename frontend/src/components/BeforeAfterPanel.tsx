import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BeforeAfter } from "../types";

export function BeforeAfterPanel({ cmp }: { cmp: BeforeAfter }) {
  const n = Math.max(cmp.before_curve.length, cmp.after_curve.length);
  const data = Array.from({ length: n }, (_, i) => ({
    beat: `B${i + 1}`,
    before: cmp.before_curve[i] != null ? Math.round(cmp.before_curve[i]) : null,
    after: cmp.after_curve[i] != null ? Math.round(cmp.after_curve[i]) : null,
  }));

  return (
    <div className="card fade-in" style={{ borderColor: "var(--border-glow)" }}>
      <h2 data-idx="06">Before / After</h2>
      {cmp.target === "ending" ? (
        <div className="lift-banner" style={{ color: cmp.binge_lift_pct >= 0 ? "var(--ok)" : "var(--danger)" }}>
          {cmp.binge_lift_pct >= 0 ? "+" : ""}
          {cmp.binge_lift_pct.toFixed(0)} pts binge probability
          <span className="muted mono" style={{ fontSize: 12, marginLeft: 10 }}>
            ({cmp.before_binge.toFixed(0)}% → {cmp.after_binge.toFixed(0)}% · stronger ending)
          </span>
        </div>
      ) : (
        <div className="lift-banner">
          +{cmp.lift_pct.toFixed(0)} pts retained at beat {cmp.beat_index + 1}
          <span className="muted mono" style={{ fontSize: 12, marginLeft: 10 }}>
            ({cmp.before_drop_pct.toFixed(0)}% → {cmp.after_drop_pct.toFixed(0)}% drop)
          </span>
        </div>
      )}
      <div className="chart-wrap" style={{ height: 300, marginTop: 10 }}>
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
            />
            <Legend wrapperStyle={{ fontSize: 12, fontFamily: "var(--mono)" }} />
            <ReferenceLine
              x={`B${cmp.beat_index + 1}`}
              stroke="var(--warn)"
              strokeDasharray="4 4"
              strokeOpacity={0.6}
            />
            <Line
              type="monotone"
              dataKey="before"
              name="Before"
              stroke="var(--muted)"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="after"
              name="After fix"
              stroke="var(--ok)"
              strokeWidth={3}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
