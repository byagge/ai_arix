'use client';

import { useCallback, useEffect, useState } from 'react';
import { AreaChart } from '@/components/charts';
import { Segmented, TopBar, WidePage } from '@/components/ui/Primitives';
import { Metrics, UsageBucket, fmtCost, fmtNumber, platform } from '@/lib/platform';

const RANGES = [
  { id: '24h', label: '24h', hours: 24, buckets: 24 },
  { id: '7d', label: '7d', hours: 168, buckets: 28 },
  { id: '30d', label: '30d', hours: 720, buckets: 30 },
] as const;

type RangeId = (typeof RANGES)[number]['id'];
type Metric = 'requests' | 'tokens' | 'cost';

export default function UsagePage() {
  const [range, setRange] = useState<RangeId>('7d');
  const [metric, setMetric] = useState<Metric>('requests');
  const [series, setSeries] = useState<UsageBucket[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  const cfg = RANGES.find((r) => r.id === range)!;

  const load = useCallback(async () => {
    const [s, m] = await Promise.all([
      platform.usageSeries(cfg.hours, cfg.buckets).catch(() => null),
      platform.metrics(cfg.hours).catch(() => null),
    ]);
    if (s) setSeries(s.series);
    if (m) setMetrics(m);
  }, [cfg.hours, cfg.buckets]);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const values = series.map((s) =>
    metric === 'requests' ? s.requests : s.input_tokens + s.output_tokens
  );

  const labels = series
    .filter((_, i) => i % Math.max(1, Math.floor(series.length / 6)) === 0)
    .map((s) =>
      new Date(s.t).toLocaleDateString([], { month: 'short', day: 'numeric' })
    );

  return (
    <div>
      <TopBar title="Usage">
        <Segmented
          value={range}
          onChange={setRange}
          options={RANGES.map((r) => ({ id: r.id, label: r.label }))}
        />
      </TopBar>

      <WidePage>
        <div className="mb-6 grid gap-3 sm:grid-cols-4">
          <Tile label="Requests" value={String(metrics?.runs ?? 0)} />
          <Tile
            label="Tokens"
            value={fmtNumber((metrics?.input_tokens ?? 0) + (metrics?.output_tokens ?? 0))}
          />
          <Tile label="Spend" value={fmtCost(metrics?.cost_usd ?? 0)} />
          <Tile label="Latency p50" value={`${metrics?.latency_p50_ms ?? 0} ms`} />
        </div>

        <div className="oai-card mb-6 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[14px] font-medium">
              {metric === 'requests' ? 'Requests over time' : 'Tokens over time'}
            </h2>
            <Segmented
              value={metric}
              onChange={setMetric}
              options={[
                { id: 'requests', label: 'Requests' },
                { id: 'tokens', label: 'Tokens' },
              ]}
            />
          </div>
          <AreaChart data={values} labels={labels} />
        </div>

        <div className="overflow-hidden rounded-xl border border-border">
          <div className="border-b border-border px-4 py-3 text-[14px] font-medium">
            Usage by model
          </div>
          {!metrics?.by_model.length ? (
            <p className="px-4 py-8 text-center text-[13px] text-fg-secondary">
              No usage recorded in this window.
            </p>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-tertiary">
                  <th className="px-4 py-2 text-left font-medium">Model</th>
                  <th className="px-4 py-2 text-right font-medium">Requests</th>
                  <th className="px-4 py-2 text-right font-medium">Tokens</th>
                  <th className="px-4 py-2 text-right font-medium">Avg latency</th>
                  <th className="px-4 py-2 text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {metrics.by_model.map((m) => (
                  <tr
                    key={`${m.provider}/${m.model_id}`}
                    className="border-b border-border last:border-0"
                  >
                    <td className="px-4 py-2.5">
                      {m.model_id}
                      <span className="ml-2 font-mono text-[11px] text-fg-tertiary">
                        {m.provider}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">{m.runs}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">
                      {fmtNumber(m.tokens)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">
                      {m.avg_latency_ms} ms
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">
                      {fmtCost(m.cost_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </WidePage>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="oai-card p-4">
      <div className="text-[13px] text-fg-secondary">{label}</div>
      <div className="mt-1.5 text-[22px] font-medium tracking-tight">{value}</div>
    </div>
  );
}
