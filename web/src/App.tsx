import {
  Activity,
  Clock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";

type AuditEvent = {
  timestamp: string;
  step_id: string | null;
  actor: string;
  action: string;
  model: string | null;
  decision: string | null;
  confidence: number | null;
  latency_ms: number | null;
  policy_flags: string[];
};

type Run = {
  run_id: string;
  started: string;
  elapsed_s: number;
  status: string;
  steps: string[];
  policy_flags: string[];
  chain_ok: boolean;
  chain_reason: string;
  events: AuditEvent[];
};

const ACTOR_COLOR: Record<string, string> = {
  planner: "text-blue-400",
  worker: "text-cyan-400",
  reviewer: "text-fuchsia-400",
  human: "text-amber-400",
  system: "text-slate-400",
};

const DECISION_COLOR: Record<string, string> = {
  pass: "text-emerald-400",
  approve: "text-emerald-400",
  completed: "text-emerald-400",
  escalate: "text-amber-400",
  reject: "text-rose-400",
  rejected: "text-rose-400",
  aborted: "text-rose-400",
};

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  aborted: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  incomplete: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

function runLatency(run: Run): number {
  return run.events.reduce((sum, e) => sum + (e.latency_ms ?? 0), 0);
}

function StatTile({
  label,
  value,
  sub,
  icon,
  tone = "text-slate-100",
}: {
  label: string;
  value: string;
  sub?: string;
  icon: ReactNode;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
        {icon}
        {label}
      </div>
      <div className={`mt-2 text-2xl font-semibold ${tone}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function Chip({ text }: { text: string }) {
  const danger = text.startsWith("pii:") || text.includes("threshold");
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs ring-1 ${
        danger
          ? "bg-rose-500/10 text-rose-300 ring-rose-500/30"
          : "bg-amber-500/10 text-amber-300 ring-amber-500/30"
      }`}
    >
      {text}
    </span>
  );
}

export default function App() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/runs");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Run[] = await res.json();
      setRuns(data);
      setError(null);
      setSelectedId((prev) => prev ?? data[0]?.run_id ?? null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const selected = runs?.find((r) => r.run_id === selectedId) ?? null;

  const stats = useMemo(() => {
    if (!runs || runs.length === 0) return null;
    const escalated = runs.filter((r) =>
      r.events.some((e) => e.decision === "escalate"),
    ).length;
    const avgLatency = Math.round(
      runs.reduce((s, r) => s + runLatency(r), 0) / runs.length,
    );
    const flagFreq: Record<string, number> = {};
    for (const r of runs)
      for (const f of r.policy_flags) flagFreq[f] = (flagFreq[f] ?? 0) + 1;
    const topFlags = Object.entries(flagFreq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
    return {
      total: runs.length,
      escalationRate: Math.round((100 * escalated) / runs.length),
      avgLatency,
      chainAllOk: runs.every((r) => r.chain_ok),
      topFlags,
    };
  }, [runs]);

  return (
    <div className="min-h-screen font-sans">
      <header className="border-b border-white/10 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">Audit Console</h1>
            <p className="text-xs text-slate-500">
              local-agent-pipeline — every run, every decision, provably intact
            </p>
          </div>
          <button
            onClick={load}
            className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-slate-300 hover:bg-white/[0.07]"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="m-6 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-300">
          Could not reach the audit API: {error}. Is <code>web/api_server.py</code> running?
          (Start everything with <code>web/start.sh</code>.)
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 gap-3 px-6 py-5 md:grid-cols-4">
          <StatTile label="Runs" value={String(stats.total)} icon={<Activity className="h-3.5 w-3.5" />} />
          <StatTile
            label="Escalation rate"
            value={`${stats.escalationRate}%`}
            sub="runs that hit the gate"
            tone="text-amber-300"
            icon={<ShieldAlert className="h-3.5 w-3.5" />}
          />
          <StatTile
            label="Avg latency"
            value={`${(stats.avgLatency / 1000).toFixed(1)}s`}
            sub="per run, all stages"
            icon={<Clock className="h-3.5 w-3.5" />}
          />
          <StatTile
            label="Audit chain"
            value={stats.chainAllOk ? "All intact" : "BROKEN"}
            sub={stats.chainAllOk ? "tamper-evident" : "a trail was altered"}
            tone={stats.chainAllOk ? "text-emerald-300" : "text-rose-300"}
            icon={
              stats.chainAllOk ? (
                <ShieldCheck className="h-3.5 w-3.5" />
              ) : (
                <ShieldAlert className="h-3.5 w-3.5" />
              )
            }
          />
        </div>
      )}

      <div className="grid gap-4 px-6 pb-10 lg:grid-cols-[320px_1fr]">
        {/* Runs list */}
        <div className="space-y-2">
          <h2 className="px-1 text-xs uppercase tracking-wide text-slate-500">Runs</h2>
          {runs?.length === 0 && (
            <p className="px-1 text-sm text-slate-500">
              No runs yet. Run <code>agent-pipeline run --input …</code> and refresh.
            </p>
          )}
          {runs?.map((r) => (
            <button
              key={r.run_id}
              onClick={() => setSelectedId(r.run_id)}
              className={`w-full rounded-lg border p-3 text-left transition ${
                r.run_id === selectedId
                  ? "border-white/25 bg-white/[0.07]"
                  : "border-white/10 bg-white/[0.02] hover:bg-white/[0.05]"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs text-slate-300">{r.run_id}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] uppercase ring-1 ${
                    STATUS_STYLE[r.status] ?? STATUS_STYLE.incomplete
                  }`}
                >
                  {r.status}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
                {r.chain_ok ? (
                  <ShieldCheck className="h-3 w-3 text-emerald-500" />
                ) : (
                  <ShieldAlert className="h-3 w-3 text-rose-500" />
                )}
                <span>{r.events.length} events</span>
                <span>·</span>
                <span>{r.policy_flags.length} flags</span>
              </div>
            </button>
          ))}
        </div>

        {/* Selected run */}
        {selected && <RunDetail run={selected} />}
      </div>
    </div>
  );
}

function RunDetail({ run }: { run: Run }) {
  const maxLatency = Math.max(1, ...run.events.map((e) => e.latency_ms ?? 0));
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-mono text-sm text-slate-200">{run.run_id}</div>
          <div className="text-xs text-slate-500">
            {new Date(run.started).toLocaleString()} · {run.elapsed_s}s ·{" "}
            {run.steps.length} step(s)
          </div>
        </div>
        <div
          className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs ring-1 ${
            run.chain_ok
              ? "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30"
              : "bg-rose-500/10 text-rose-300 ring-rose-500/30"
          }`}
          title={run.chain_reason}
        >
          {run.chain_ok ? <ShieldCheck className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
          {run.chain_ok ? "chain intact" : "chain broken"}
        </div>
      </div>

      {run.policy_flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {run.policy_flags.map((f) => (
            <Chip key={f} text={f} />
          ))}
        </div>
      )}

      <div className="mt-5 space-y-1">
        {run.events.map((e, i) => (
          <div
            key={i}
            className="grid grid-cols-[auto_90px_1fr_auto] items-center gap-3 rounded-md px-2 py-1.5 hover:bg-white/[0.03]"
          >
            <span className="w-5 text-right font-mono text-[11px] text-slate-600">{i + 1}</span>
            <span className={`font-mono text-xs ${ACTOR_COLOR[e.actor] ?? "text-slate-300"}`}>
              {e.actor}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-200">{e.action}</span>
                {e.step_id && <span className="text-[11px] text-slate-500">{e.step_id}</span>}
                {e.decision && (
                  <span className={`text-xs ${DECISION_COLOR[e.decision] ?? "text-slate-400"}`}>
                    → {e.decision}
                  </span>
                )}
              </div>
              {e.latency_ms != null && e.latency_ms > 0 && (
                <div className="mt-1 h-1 w-full overflow-hidden rounded bg-white/5">
                  <div
                    className="h-full rounded bg-slate-500/60"
                    style={{ width: `${(100 * e.latency_ms) / maxLatency}%` }}
                  />
                </div>
              )}
            </div>
            <span className="whitespace-nowrap text-right font-mono text-[11px] text-slate-500">
              {e.model ? `${e.model} · ` : ""}
              {e.latency_ms != null && e.latency_ms > 0 ? `${e.latency_ms}ms` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
