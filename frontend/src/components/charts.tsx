'use client';

/** All charts are plotted from recorded runs; an empty array renders a flat baseline. */

export function Sparkline({
  data,
  height = 32,
}: {
  data: number[];
  height?: number;
}) {
  const w = 100;
  const max = Math.max(1, ...data);
  const points = data.length
    ? data.map((v, i) => {
        const x = data.length === 1 ? w : (i / (data.length - 1)) * w;
        const y = height - 2 - (v / max) * (height - 6);
        return [x, y] as const;
      })
    : [
        [0, height - 2],
        [w, height - 2],
      ];

  const last = points[points.length - 1];

  return (
    <svg
      viewBox={`0 0 ${w} ${height}`}
      preserveAspectRatio="none"
      className="h-8 w-full overflow-visible"
    >
      <polyline
        points={points.map(([x, y]) => `${x},${y}`).join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.2}
        vectorEffect="non-scaling-stroke"
        className="text-fg-secondary"
      />
      <circle cx={last[0]} cy={last[1]} r={2.4} className="fill-fg" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function BarSeries({ data, height = 32 }: { data: number[]; height?: number }) {
  const bars = data.length ? data : new Array(8).fill(0);
  const max = Math.max(1, ...bars);

  return (
    <div className="flex h-8 items-end gap-1.5">
      {bars.map((v, i) => (
        <div key={i} className="flex flex-1 items-end" style={{ height }}>
          <div
            className="w-full rounded-sm bg-fg-secondary"
            style={{ height: Math.max(2, (v / max) * (height - 2)) }}
          />
        </div>
      ))}
    </div>
  );
}

export function AreaChart({
  data,
  labels,
  height = 200,
}: {
  data: number[];
  labels?: string[];
  height?: number;
}) {
  const w = 600;
  const max = Math.max(1, ...data);
  const pts = data.map((v, i) => {
    const x = data.length <= 1 ? w : (i / (data.length - 1)) * w;
    const y = height - 24 - (v / max) * (height - 44);
    return [x, y] as const;
  });

  const line = pts.map(([x, y]) => `${x},${y}`).join(' ');
  const area = pts.length
    ? `${pts[0][0]},${height - 24} ${line} ${pts[pts.length - 1][0]},${height - 24}`
    : '';

  const gridLines = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
        {gridLines.map((g) => (
          <line
            key={g}
            x1={0}
            x2={w}
            y1={20 + g * (height - 44)}
            y2={20 + g * (height - 44)}
            className="stroke-border"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {pts.length > 0 && (
          <>
            <polygon points={area} className="fill-fg" opacity={0.08} />
            <polyline
              points={line}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
              className="text-fg"
            />
          </>
        )}
      </svg>
      {labels && (
        <div className="mt-2 flex justify-between text-[11px] text-fg-tertiary">
          {labels.map((l, i) => (
            <span key={i}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function Waterfall({
  spans,
  total,
}: {
  spans: { name: string; kind: string; duration_ms: number }[];
  total: number;
}) {
  return (
    <div className="space-y-2.5">
      {spans.map((s, i) => (
        <div key={i}>
          <div className="mb-1 flex items-baseline justify-between text-[12px]">
            <span className="font-mono text-fg-secondary">
              {s.name}
              <span className="ml-2 text-fg-tertiary">{s.kind}</span>
            </span>
            <span className="font-mono">{s.duration_ms}ms</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-active">
            <div
              className="h-full rounded-full bg-fg-secondary"
              style={{ width: `${Math.max(2, (s.duration_ms / Math.max(1, total)) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
