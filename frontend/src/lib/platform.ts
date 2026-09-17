const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    cache: 'no-store',
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json();
}

export interface Provider {
  id: string;
  configured: boolean;
  models: number;
  endpoint?: string;
  key_hint?: string;
}

export interface PromptTurn {
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
}

export interface ModelRecord {
  id: number;
  provider: string;
  model_id: string;
  display_name: string;
  context_window: number | null;
  input_cost_per_mtok: number;
  output_cost_per_mtok: number;
  enabled: boolean;
  is_default: boolean;
  last_status: string;
  last_latency_ms: number | null;
  last_checked_at: string | null;
}

export interface Thread {
  id: string;
  title: string;
  source: string;
  provider: string | null;
  model_id: string | null;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  use_retrieval: boolean;
  total_runs: number;
  total_tokens: number;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface Turn {
  id: number;
  role: string;
  content: string;
  created_at: string;
}

export interface ThreadDetail extends Thread {
  turns: Turn[];
}

export interface Span {
  name: string;
  kind: string;
  status: string;
  duration_ms: number;
  attributes: Record<string, unknown>;
}

export interface Run {
  id: string;
  thread_id: string;
  provider: string;
  model_id: string;
  status: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  ttft_ms: number | null;
  error: string | null;
  prompt_preview: string;
  output_preview: string;
  created_at: string;
}

export interface RunDetail extends Run {
  spans: Span[];
}

export interface Metrics {
  window_hours: number;
  runs: number;
  failed: number;
  success_rate: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  threads: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
  by_model: {
    provider: string;
    model_id: string;
    runs: number;
    tokens: number;
    cost_usd: number;
    avg_latency_ms: number;
  }[];
}

export interface UsageBucket {
  t: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  failed: number;
}

export interface UsageSeries {
  window_hours: number;
  buckets: number;
  series: UsageBucket[];
}

export interface ActivityPoint {
  run_id: string;
  provider: string;
  model_id: string;
  status: string;
  latency_ms: number;
  tokens: number;
  created_at: string;
  thread_id: string;
  thread_title: string;
  source: string;
}

export const platform = {
  providers: () => call<Provider[]>('/providers'),
  models: (enabledOnly = false) =>
    call<ModelRecord[]>(`/models${enabledOnly ? '?enabled_only=true' : ''}`),
  syncModels: () => call<{ results: unknown[] }>('/models/sync', { method: 'POST' }),
  patchModel: (id: number, body: { enabled?: boolean }) =>
    call<ModelRecord>(`/models/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  makeDefault: (id: number) => call<ModelRecord>(`/models/${id}/default`, { method: 'POST' }),
  checkModel: (id: number) => call<ModelRecord>(`/models/${id}/check`, { method: 'POST' }),

  threads: (limit = 50) => call<Thread[]>(`/threads?limit=${limit}`),
  thread: (id: string) => call<ThreadDetail>(`/threads/${id}`),
  createThread: (
    body: Partial<Thread> & { initial_turns?: PromptTurn[] }
  ) => call<Thread>('/threads', { method: 'POST', body: JSON.stringify(body) }),
  seedTurns: (id: string, turns: PromptTurn[]) =>
    call<Turn[]>(`/threads/${id}/turns`, { method: 'POST', body: JSON.stringify(turns) }),
  patchThread: (id: string, body: Partial<Thread>) =>
    call<Thread>(`/threads/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteThread: (id: string) => call<{ deleted: string }>(`/threads/${id}`, { method: 'DELETE' }),

  runs: (limit = 100) => call<Run[]>(`/runs?limit=${limit}`),
  run: (id: string) => call<RunDetail>(`/runs/${id}`),
  metrics: (hours = 24) => call<Metrics>(`/metrics?hours=${hours}`),
  usageSeries: (hours = 168, buckets = 24) =>
    call<UsageSeries>(`/usage/series?hours=${hours}&buckets=${buckets}`),
  activity: (limit = 120) => call<ActivityPoint[]>(`/activity?limit=${limit}`),
};

export interface StreamHandlers {
  onStart?: (d: { run_id: string; provider: string; model: string }) => void;
  onDelta?: (text: string) => void;
  onTtft?: (ms: number) => void;
  onDone?: (d: {
    run_id: string;
    status: string;
    latency_ms: number;
    ttft_ms: number | null;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    spans: { name: string; kind: string; duration_ms: number }[];
  }) => void;
  onError?: (message: string) => void;
}

/** Opens a real SSE stream against the provider through the backend. */
export async function streamRun(
  threadId: string,
  content: string,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/v1/threads/${threadId}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  });

  if (!res.ok || !res.body) {
    handlers.onError?.(`Request failed: ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (payload === '[DONE]') return;

      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(payload);
      } catch {
        continue;
      }

      switch (msg.event) {
        case 'run.started':
          handlers.onStart?.(msg as never);
          break;
        case 'ttft':
          handlers.onTtft?.(msg.ms as number);
          break;
        case 'delta':
          handlers.onDelta?.(msg.text as string);
          break;
        case 'run.completed':
          handlers.onDone?.(msg as never);
          break;
        case 'error':
          handlers.onError?.(msg.message as string);
          break;
      }
    }
  }
}

export function fmtNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

export function fmtCost(usd: number): string {
  if (usd === 0) return '$0';
  if (usd < 0.01) return `$${usd.toFixed(5)}`;
  return `$${usd.toFixed(3)}`;
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
