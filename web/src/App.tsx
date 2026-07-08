import {
  Activity,
  CheckCircle2,
  Clock,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

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

type ExampleDoc = { id: string; name: string; preview: string };

type ReviewReq = {
  step_id: string;
  action: string;
  decision: string;
  policy_flags: string[];
  reasons: string[];
  raw: string;
};

type Session = {
  run_id: string;
  status: string;
  review: ReviewReq | null;
  result: { status: string; note: string; results: { action: string; output: unknown }[] } | null;
  error: string | null;
  path: string | null;
};

const TERMINAL = ["completed", "aborted", "error"];

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

/** Guided run + in-browser human review — the non-technical entry point. */
function RunPanel({ onDone }: { onDone: () => void }) {
  const [examples, setExamples] = useState<ExampleDoc[]>([]);
  const [source, setSource] = useState<string>("");
  const [text, setText] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [reason, setReason] = useState("");
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    fetch("/api/examples")
      .then((r) => r.json())
      .then((d: ExampleDoc[]) => {
        setExamples(d);
        setSource(d[0] ? `example:${d[0].id}` : "text");
      })
      .catch(() => setSource("text"));
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
  }, []);

  const poll = (runId: string) => {
    fetch(`/api/run/${runId}`)
      .then((r) => r.json())
      .then((s: Session) => {
        setSession(s);
        if (TERMINAL.includes(s.status)) {
          onDone();
        } else {
          pollRef.current = window.setTimeout(() => poll(runId), 800);
        }
      })
      .catch((e) => setSession((prev) => (prev ? { ...prev, status: "error", error: String(e) } : prev)));
  };

  const start = async () => {
    setEditing(false);
    setReason("");
    const body = source === "text" ? { text } : { source };
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      setSession({ run_id: "", status: "error", review: null, result: null, error: data.error, path: null });
      return;
    }
    setSession({ run_id: data.run_id, status: "running", review: null, result: null, error: null, path: null });
    poll(data.run_id);
  };

  const decide = async (decision: string, output?: unknown) => {
    if (!session) return;
    await fetch(`/api/run/${session.run_id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reason, output }),
    });
    setEditing(false);
    setSession({ ...session, status: "running", review: null });
    poll(session.run_id);
  };

  const busy = session != null && !TERMINAL.includes(session.status);

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
      <h2 className="text-sm font-semibold text-slate-200">Run a document</h2>
      <p className="mt-0.5 text-xs text-slate-500">
        Pick an example or paste text, then press Run. If the reviewer flags something, you decide
        right here — nothing risky is accepted without you.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          disabled={busy}
          className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-200"
        >
          {examples.map((ex) => (
            <option key={ex.id} value={`example:${ex.id}`}>
              Example: {ex.name}
            </option>
          ))}
          <option value="text">Paste my own text…</option>
        </select>
        <button
          onClick={start}
          disabled={busy || (source === "text" && !text.trim())}
          className="flex items-center gap-2 rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {busy ? "Running…" : "Run pipeline"}
        </button>
      </div>

      {source === "text" && (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
          rows={4}
          placeholder="Paste a document here…"
          className="mt-3 w-full rounded-lg border border-white/10 bg-black/30 p-3 text-sm text-slate-200"
        />
      )}

      {/* Live state */}
      {session?.status === "running" && (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Working — planning, extracting, and reviewing…
        </div>
      )}

      {session?.status === "awaiting_review" && session.review && (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
          <div className="flex items-center gap-2 font-medium text-amber-200">
            <ShieldAlert className="h-4 w-4" /> This needs your review
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {session.review.policy_flags.map((f) => (
              <Chip key={f} text={f} />
            ))}
          </div>
          <ul className="mt-2 list-disc pl-5 text-sm text-slate-300">
            {session.review.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <pre className="mt-3 max-h-40 overflow-auto rounded bg-black/40 p-2 text-xs text-slate-300">
            {session.review.raw}
          </pre>

          {editing && (
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={4}
              className="mt-3 w-full rounded-lg border border-white/10 bg-black/30 p-2 font-mono text-xs text-slate-200"
            />
          )}

          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (recorded in the audit trail)"
            className="mt-3 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-200"
          />

          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => decide("approve")}
              className="rounded-lg bg-emerald-500/90 px-3 py-1.5 text-sm font-medium text-black hover:bg-emerald-400"
            >
              Approve
            </button>
            <button
              onClick={() => decide("reject")}
              className="rounded-lg bg-rose-500/90 px-3 py-1.5 text-sm font-medium text-black hover:bg-rose-400"
            >
              Reject
            </button>
            {!editing ? (
              <button
                onClick={() => {
                  setEditText(session.review?.raw ?? "");
                  setEditing(true);
                }}
                className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-slate-200 hover:bg-white/5"
              >
                Edit…
              </button>
            ) : (
              <button
                onClick={() => {
                  try {
                    decide("edit", JSON.parse(editText));
                  } catch {
                    alert("Edited output must be valid JSON.");
                  }
                }}
                className="rounded-lg bg-amber-500/90 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-400"
              >
                Save edit & approve
              </button>
            )}
          </div>
        </div>
      )}

      {session?.status === "completed" && (
        <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
          <div className="flex items-center gap-2 font-medium text-emerald-200">
            <CheckCircle2 className="h-4 w-4" /> Completed
          </div>
          <div className="mt-2 space-y-1 text-sm text-slate-300">
            {session.result?.results.map((r, i) => (
              <div key={i}>
                <span className="text-cyan-300">{r.action}</span> → {JSON.stringify(r.output)}
              </div>
            ))}
          </div>
        </div>
      )}

      {session?.status === "aborted" && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          <XCircle className="h-4 w-4" /> Stopped: {session.result?.note || "rejected"}
        </div>
      )}

      {session?.status === "error" && (
        <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          Error: {session.error}
        </div>
      )}
    </div>
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
    const escalated = runs.filter((r) => r.events.some((e) => e.decision === "escalate")).length;
    const avgLatency = Math.round(runs.reduce((s, r) => s + runLatency(r), 0) / runs.length);
    return {
      total: runs.length,
      escalationRate: Math.round((100 * escalated) / runs.length),
      avgLatency,
      chainAllOk: runs.every((r) => r.chain_ok),
    };
  }, [runs]);

  return (
    <div className="min-h-screen font-sans">
      <header className="border-b border-white/10 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-100">Audit Console</h1>
            <p className="text-xs text-slate-500">
              local-agent-pipeline — run it, review it, and see every decision proven intact
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

      <div className="px-6 py-5">
        <RunPanel onDone={load} />
      </div>

      {error && (
        <div className="mx-6 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-300">
          Could not reach the audit API: {error}. Start everything with <code>web/start.sh</code>.
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 gap-3 px-6 py-2 md:grid-cols-4">
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
        <div className="space-y-2">
          <h2 className="px-1 text-xs uppercase tracking-wide text-slate-500">Runs</h2>
          {runs?.length === 0 && <p className="px-1 text-sm text-slate-500">No runs yet.</p>}
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
            {new Date(run.started).toLocaleString()} · {run.elapsed_s}s · {run.steps.length} step(s)
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
