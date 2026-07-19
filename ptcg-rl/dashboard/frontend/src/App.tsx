import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Beaker,
  BookOpenText,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  ClipboardCheck,
  Clock3,
  FileText,
  FlaskConical,
  GitBranch,
  GraduationCap,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Moon,
  PackageCheck,
  RefreshCw,
  Search,
  ServerCog,
  ShieldAlert,
  Sun,
  X,
} from "lucide-react";
import {
  asArray,
  asNumber,
  asText,
  DashboardState,
  EvidencePayload,
  getJson,
  RecordValue,
  statusClass,
} from "./api";
import { LearningSimulators } from "./LearningSimulators";

type PageName =
  | "command"
  | "roadmap"
  | "work"
  | "hypotheses"
  | "evidence"
  | "learning"
  | "submissions"
  | "review";

const nav = [
  ["command", "Command Center", LayoutDashboard],
  ["roadmap", "Gates & Roadmap", ListChecks],
  ["work", "Runs & Experiments", Beaker],
  ["hypotheses", "Hypotheses", BrainCircuit],
  ["evidence", "Evidence", FileText],
  ["learning", "Learning Lab", GraduationCap],
  ["submissions", "Decks & Submissions", PackageCheck],
  ["review", "Review Inbox", Inbox],
] as const;

const roadmap = ["G0", "G1R", "R1", "G2", "G3a", "G3b", "D1", "G4", "G5", "G6"];
const activeStatuses = new Set(["PLANNED", "QUEUED", "RUNNING", "BLOCKED", "IN_REVIEW"]);

function initialPage(): PageName {
  const raw = location.hash.slice(1);
  if (raw === "gates") return "roadmap";
  if (raw === "timeline" || raw === "reports") return "evidence";
  return nav.some(([id]) => id === raw) ? (raw as PageName) : "command";
}

function Status({ value }: { value: unknown }) {
  const text = asText(value);
  const Icon =
    text === "BLOCKED" || text === "FAILED"
      ? AlertTriangle
      : text === "PASS" || text === "SUCCEEDED" || text === "ACCEPTED" || text === "VERIFIED"
        ? CheckCircle2
        : CircleDot;
  return (
    <span className={statusClass(text)}>
      <Icon size={14} />
      {text}
    </span>
  );
}

function EvidenceButton({ path, onOpen }: { path: unknown; onOpen: (path: string) => void }) {
  const value = asText(path, "");
  if (!value) return null;
  return (
    <button className="evidence-link" onClick={() => onOpen(value)}>
      <BookOpenText size={14} />
      {value}
    </button>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function GateCard({ gate, onEvidence }: { gate: RecordValue; onEvidence: (path: string) => void }) {
  return (
    <article className="panel gate-card">
      <header>
        <div>
          <p className="eyebrow">{asText(gate.gate_id)}</p>
          <h2>{asText(gate.title)}</h2>
        </div>
        <Status value={gate.status} />
      </header>
      <p>{asText(gate.approved_next_action, "No approved action recorded.")}</p>
      <div className="inline-facts">
        <span>Review: {asText(gate.decision)}</span>
        <span>Authorization: {asText(gate.authorization, "N/A")}</span>
      </div>
      <EvidenceButton path={gate.source_path} onOpen={onEvidence} />
    </article>
  );
}

function CommandCenter({ data, onEvidence }: { data: DashboardState; onEvidence: (path: string) => void }) {
  const overview = data.overview;
  const runtime = (overview.runtime.runtime ?? {}) as RecordValue;
  const submission = (overview.runtime.submission ?? {}) as RecordValue;
  const deadline = new Date(asText(overview.runtime.close_instant_utc));
  const days = Number.isNaN(deadline.valueOf())
    ? null
    : Math.max(0, Math.floor((deadline.valueOf() - Date.now()) / 86_400_000));
  const active = overview.active_gates;
  const attention = active.flatMap((gate) => [
    ...asArray<string>(gate.blockers).map((text) => ({ type: "BLOCKER", text })),
    ...asArray<string>(gate.warnings).map((text) => ({ type: "NOTE", text })),
  ]);
  const currentTasks = data.tasks
    .filter((task) => ["RUNNING", "QUEUED", "BLOCKED"].includes(asText(task.status)))
    .sort((a, b) => asNumber(a.priority, 99) - asNumber(b.priority, 99));
  const progress = overview.progress;

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Mission control</p>
          <h1>Active workstreams</h1>
        </div>
        <Status value={overview.data_health.status} />
      </section>
      <section className="metric-strip six" aria-label="mission summary">
        <Metric label="Verified close" value={days === null ? "UNKNOWN" : `${days} days`} note={asText(overview.runtime.close_instant_utc)} />
        <Metric label="Gate progress" value={`${progress.passed}/${progress.total}`} note="strict evidence gates" />
        <Metric label="Active gates" value={String(active.length)} note={active.map((gate) => asText(gate.gate_id)).join(" + ") || "none"} />
        <Metric label="Active jobs" value={String(overview.active_jobs)} note="training remains unauthorized" />
        <Metric label="Verified cost" value={`USD ${asNumber(overview.costs.actual_usd).toFixed(2)}`} note={asText(overview.costs.source)} />
        <Metric label="Package ceiling" value={`${String(submission.hard_package_limit_kb ?? "UNKNOWN")} KB`} note={`target < ${String(submission.internal_package_target_mb ?? "UNKNOWN")} MB`} />
      </section>

      <section className="active-gates">
        {active.map((gate) => (
          <GateCard key={asText(gate.gate_id)} gate={gate} onEvidence={onEvidence} />
        ))}
      </section>

      <div className="content-grid two-one">
        <section className="panel">
          <header>
            <div>
              <p className="eyebrow">Execution order</p>
              <h2>Immediate tasks</h2>
            </div>
            <GitBranch size={20} />
          </header>
          <div className="task-board">
            {currentTasks.slice(0, 8).map((task) => (
              <div className="task-row" key={asText(task.task_id)}>
                <Status value={task.status} />
                <div>
                  <strong>{asText(task.task_id)} · {asText(task.title)}</strong>
                  <p>{asText(task.done_when)}</p>
                </div>
                <span className="task-phase">{asText(task.phase)}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel attention">
          <header>
            <div>
              <p className="eyebrow">Attention queue</p>
              <h2>{attention.length} items</h2>
            </div>
            <ShieldAlert size={20} />
          </header>
          {attention.length ? (
            attention.map((item, index) => (
              <div className={`attention-row ${item.type === "BLOCKER" ? "critical" : "warning"}`} key={`${item.type}-${index}`}>
                {item.type === "BLOCKER" ? <AlertTriangle size={16} /> : <Clock3 size={16} />}
                <div>
                  <strong>{item.type}</strong>
                  <p>{item.text}</p>
                </div>
              </div>
            ))
          ) : (
            <p className="empty-note">No active blocker or warning is recorded.</p>
          )}
        </section>
      </div>

      <div className="content-grid equal">
        <section className="panel">
          <header>
            <div>
              <p className="eyebrow">Latest accepted boundary</p>
              <h2>{asText(overview.latest_completed_gate?.title)}</h2>
            </div>
            <Status value={overview.latest_completed_gate?.decision} />
          </header>
          <EvidenceButton path={overview.latest_completed_gate?.source_path} onOpen={onEvidence} />
        </section>
        <section className="panel">
          <header>
            <div>
              <p className="eyebrow">Runtime profile</p>
              <h2>{asText(runtime.python_family)}</h2>
            </div>
            <ServerCog size={20} />
          </header>
          <dl className="facts">
            <div><dt>Image</dt><dd>{asText(runtime.image)}</dd></div>
            <div><dt>Internet</dt><dd>{String(((runtime.raw_simulation_settings ?? {}) as RecordValue).enableInternet ?? "UNKNOWN")}</dd></div>
            <div><dt>Inference</dt><dd>CPU only</dd></div>
            <div><dt>Main training</dt><dd>Modal approval-gated</dd></div>
          </dl>
        </section>
      </div>
    </>
  );
}

function Roadmap({ data, onEvidence }: { data: DashboardState; onEvidence: (path: string) => void }) {
  const records = new Map(data.gates.map((gate) => [asText(gate.gate_id), gate]));
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">Evidence-gated plan</p><h1>Gates & Roadmap</h1></div></div>
      <div className="roadmap">
        {roadmap.map((gateId, index) => {
          const record = records.get(gateId);
          const passed = ["PASS", "SUCCEEDED"].includes(asText(record?.decision, asText(record?.status)));
          const active = Boolean(record && activeStatuses.has(asText(record.status)));
          return (
            <div className={`roadmap-step ${passed ? "passed" : active ? "current" : "future"}`} key={gateId}>
              <span>{index + 1}</span>
              <div><strong>{gateId}</strong><small>{passed ? "Passed" : active ? asText(record?.status) : "Not started"}</small></div>
            </div>
          );
        })}
      </div>
      <div className="active-gates">
        {data.gates.filter((gate) => activeStatuses.has(asText(gate.status))).map((gate) => (
          <GateCard key={asText(gate.gate_id)} gate={gate} onEvidence={onEvidence} />
        ))}
      </div>
    </section>
  );
}

function Work({ data, query }: { data: DashboardState; query: string }) {
  const experiments = data.experiments.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  const runs = data.runs.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">Execution ledger</p><h1>Runs & Experiments</h1></div><span className="count">{experiments.length} experiments · {runs.length} runs</span></div>
      <div className="content-grid equal">
        <section className="panel">
          <header><div><p className="eyebrow">Registered tests</p><h2>Experiments</h2></div><FlaskConical size={20} /></header>
          {experiments.length ? experiments.map((experiment) => (
            <article className="ledger-item" key={asText(experiment.experiment_id, asText(experiment.record_id))}>
              <div><Status value={experiment.status} /><strong>{asText(experiment.experiment_id)} · {asText(experiment.title)}</strong></div>
              <p>{asText(experiment.hypothesis)}</p>
            </article>
          )) : <div className="empty compact"><Beaker size={24} /><h2>No experiment manifest yet</h2><p>G2 implementation is engineering work until a falsifiable model or training comparison is registered.</p></div>}
        </section>
        <section className="panel">
          <header><div><p className="eyebrow">Immutable executions</p><h2>Runs and jobs</h2></div><Activity size={20} /></header>
          {runs.length ? runs.slice(0, 20).map((run) => (
            <article className="ledger-item" key={asText(run.run_id, asText(run.record_id))}>
              <div><Status value={run.status} /><strong>{asText(run.run_id)}</strong></div>
              <p>{asText(run.experiment_id, asText(run.gate_id))}</p>
            </article>
          )) : <p className="empty-note">No model, PPO, replay or cloud run manifest has started.</p>}
          {data.jobs.map((job) => <article className="ledger-item" key={asText(job.record_id)}><div><Status value={job.status} /><strong>{asText(job.title)}</strong></div></article>)}
        </section>
      </div>
    </section>
  );
}

function Hypotheses({ data, query }: { data: DashboardState; query: string }) {
  const items = data.hypotheses.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">Falsifiable research</p><h1>Hypotheses</h1></div><span className="count">{items.length} registered</span></div>
      <div className="hypothesis-grid">
        {items.map((item) => (
          <article className="panel hypothesis-card" key={asText(item.hypothesis_id)}>
            <header><div><p className="eyebrow">{asText(item.hypothesis_id)} · priority {String(item.priority ?? "UNKNOWN")}</p><h2>{asText(item.title)}</h2></div><Status value={item.status} /></header>
            <p className="hypothesis-statement">{asText(item.statement)}</p>
            <dl className="research-facts">
              <div><dt>Evidence for</dt><dd>{asText(item.evidence_for)}</dd></div>
              <div><dt>Evidence against</dt><dd>{asText(item.evidence_against)}</dd></div>
              <div><dt>Next test</dt><dd>{asText(item.next_test)}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}

function Evidence({ data, query, onEvidence }: { data: DashboardState; query: string; onEvidence: (path: string) => void }) {
  const reports = data.reports.filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">Traceable sources</p><h1>Evidence & Decisions</h1></div><span className="count">{reports.length} reports</span></div>
      <div className="content-grid equal">
        <section className="panel">
          <header><div><p className="eyebrow">Approved rationale</p><h2>Decision log</h2></div><ClipboardCheck size={20} /></header>
          {data.decisions.map((item) => (
            <article className="decision-item" key={asText(item.decision_id)}>
              <div><strong>{asText(item.decision_id)} · {asText(item.title)}</strong><Status value={item.status} /></div>
              <p>{asText(item.decision)}</p>
              <small>{asText(item.rationale)}</small>
              <EvidenceButton path={item.source_path} onOpen={onEvidence} />
            </article>
          ))}
        </section>
        <section className="panel">
          <header><div><p className="eyebrow">Append-only history</p><h2>Timeline</h2></div><Clock3 size={20} /></header>
          <div className="mini-timeline">
            {data.events.slice(0, 20).map((event) => (
              <article key={asText(event.record_id)}>
                <time>{asText(event.created_at_utc)}</time>
                <div><Status value={event.status_after ?? event.status} /><strong>{asText(event.title, asText(event.summary))}</strong><p>{asText(event.summary)}</p></div>
              </article>
            ))}
          </div>
        </section>
      </div>
      <div className="report-list">
        {reports.map((report) => (
          <details className="panel" key={asText(report.record_id)}>
            <summary><div><Status value={report.status} /><strong>{asText(report.title)}</strong><small>{asText(report.created_at_utc)}</small></div><ChevronRight size={18} /></summary>
            <EvidenceButton path={report.source_path} onOpen={onEvidence} />
            <pre>{asText(report.markdown, "Structured record; open the evidence source for exact JSON.")}</pre>
          </details>
        ))}
      </div>
    </section>
  );
}

function Learning({ data }: { data: DashboardState }) {
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">Beginner-first reference</p><h1>Learning Lab</h1></div><span className="count">Evidence boundaries included</span></div>
      <LearningSimulators />
      {data.learning.map((record) => (
        <div key={asText(record.record_id)}>
          <section className="panel learning-intro"><header><div><p className="eyebrow">{asText(record.audience)}</p><h2>{asText(record.title)}</h2></div><Status value={record.status} /></header><p>This page explains the project from the game contract through training and evaluation. It is documentation, not proof of future strength.</p></section>
          <div className="learning-grid">
            {asArray<RecordValue>(record.sections).map((section, index) => (
              <article className="panel learning-card" key={asText(section.id, String(index))}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h2>{asText(section.title)}</h2>
                <p>{asText(section.summary)}</p>
                <div><strong>Why it matters</strong><p>{asText(section.why_it_matters)}</p></div>
              </article>
            ))}
          </div>
          <section className="panel boundary-list"><header><div><p className="eyebrow">Current stop lines</p><h2>Authorization boundaries</h2></div><ShieldAlert size={20} /></header>{asArray<string>(record.boundaries).map((item) => <p key={item}><AlertTriangle size={15} />{item}</p>)}</section>
        </div>
      ))}
    </section>
  );
}

function Submissions({ data }: { data: DashboardState }) {
  const submissionContract = (data.overview.runtime.submission ?? {}) as RecordValue;
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">External qualification</p><h1>Decks & Submissions</h1></div><Status value={data.submissions.length ? "ACTIVE" : "NOT_STARTED"} /></div>
      <section className="metric-strip">
        <Metric label="Candidate decks" value={String(data.decks.length)} note="no deck frozen" />
        <Metric label="Evaluations" value={String(data.evaluations.length)} note="no champion selected" />
        <Metric label="Submissions" value={String(data.submissions.length)} note="explicit approval required" />
        <Metric label="Archive type" value={asText(submissionContract.archive_format)} note={`${String(submissionContract.hard_package_limit_kb ?? "UNKNOWN")} KB ceiling`} />
      </section>
      <div className="content-grid equal">
        <section className="panel empty"><PackageCheck size={24} /><h2>No submission is active in the project ledger</h2><p>The final package must bind an exact deck, checkpoint, configuration and archive hash after G6 qualification.</p></section>
        <section className="panel"><header><div><p className="eyebrow">Protected ladder policy</p><h2>Anchor and challenger</h2></div><ShieldAlert size={20} /></header><p>One trusted anchor and one validated challenger are retained. An experimental or statistically unresolved candidate cannot replace the anchor under DEC-010.</p></section>
      </div>
    </section>
  );
}

function Review({ data, onEvidence }: { data: DashboardState; onEvidence: (path: string) => void }) {
  return (
    <section>
      <div className="page-heading"><div><p className="eyebrow">Human and gate decisions</p><h1>Review Inbox</h1></div><span className="count">{data.review.length} open</span></div>
      {data.review.map((item) => (
        <article className="panel review-item" key={asText(item.gate_id)}>
          <header><div><p className="eyebrow">{asText(item.authorization, "REVIEW")}</p><h2>{asText(item.gate_id)} review</h2></div><Status value={item.status} /></header>
          {asArray<string>(item.blockers).map((blocker) => <p className="blocker-line" key={blocker}><AlertTriangle size={15} />{blocker}</p>)}
          {asArray<string>(item.warnings).map((warning) => <p className="warning-line" key={warning}><Clock3 size={15} />{warning}</p>)}
          <p><strong>Next:</strong> {asText(item.next_action)}</p>
          <EvidenceButton path={item.source_path} onOpen={onEvidence} />
        </article>
      ))}
    </section>
  );
}

export default function App() {
  const [page, setPage] = useState<PageName>(initialPage);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [query, setQuery] = useState("");
  const [data, setData] = useState<DashboardState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [evidencePath, setEvidencePath] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidencePayload | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getJson<DashboardState>("/api/v1/state"));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const openEvidence = useCallback(async (path: string) => {
    setEvidencePath(path);
    setEvidence(null);
    setEvidenceError(null);
    try {
      setEvidence(await getJson<EvidencePayload>(`/api/v1/evidence?path=${encodeURIComponent(path)}`));
    } catch (reason) {
      setEvidenceError(reason instanceof Error ? reason.message : String(reason));
    }
  }, []);

  const go = (next: PageName) => {
    setPage(next);
    location.hash = next;
  };
  const currentTitle = useMemo(() => nav.find(([id]) => id === page)?.[1] ?? "Command Center", [page]);

  if (!data && error) return <main className="fatal"><AlertTriangle /><h1>Dashboard unavailable</h1><p>{error}</p></main>;
  if (!data) return <main className="fatal"><Activity className="spin" /><h1>Loading project evidence</h1></main>;

  const activeNames = data.overview.active_gates.map((gate) => asText(gate.gate_id)).join(" + ") || "NO ACTIVE GATE";
  return (
    <div className="shell">
      <aside>
        <div className="brand"><div className="brand-mark"><ClipboardCheck size={20} /></div><div><strong>PTCG RL</strong><span>Gold campaign cockpit</span></div></div>
        <nav aria-label="Dashboard pages">
          {nav.map(([id, label, Icon]) => (
            <button title={label} aria-label={label} aria-current={page === id ? "page" : undefined} className={page === id ? "active" : ""} key={id} onClick={() => go(id)}>
              <Icon size={18} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer"><div><span>DATA HEALTH</span><Status value={data.overview.data_health.status} /></div><small>Read-only · auto-sync</small></div>
      </aside>
      <div className="workspace">
        <header className="mission-bar">
          <div className="mobile-title"><strong>{currentTitle}</strong></div>
          <div className="search"><Search size={16} /><input aria-label="Search dashboard" placeholder="Search research records" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          <div className="mission-facts">
            <span><Clock3 size={15} />Closes 16 Aug</span>
            <span><CircleDot size={15} />{activeNames}</span>
            <button className="icon-button" title="Refresh evidence" onClick={() => void refresh()}><RefreshCw className={refreshing ? "spin" : ""} size={18} /></button>
            <button className="icon-button" title={`Use ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button>
          </div>
        </header>
        {error && <div className="stale-banner"><AlertTriangle size={15} />Refresh failed: {error}. Displaying the last successful state.</div>}
        <main>
          {page === "command" && <CommandCenter data={data} onEvidence={openEvidence} />}
          {page === "roadmap" && <Roadmap data={data} onEvidence={openEvidence} />}
          {page === "work" && <Work data={data} query={query} />}
          {page === "hypotheses" && <Hypotheses data={data} query={query} />}
          {page === "evidence" && <Evidence data={data} query={query} onEvidence={openEvidence} />}
          {page === "learning" && <Learning data={data} />}
          {page === "submissions" && <Submissions data={data} />}
          {page === "review" && <Review data={data} onEvidence={openEvidence} />}
        </main>
        <footer className="sync-footer">Last evidence scan: {asText(data.generated_at_utc)} · browser refreshes every 15 seconds</footer>
      </div>
      {evidencePath && (
        <div className="drawer-backdrop" onClick={() => setEvidencePath(null)}>
          <aside className="drawer evidence-drawer" onClick={(event) => event.stopPropagation()}>
            <header><div><p className="eyebrow">Evidence source</p><h2>{evidencePath}</h2></div><button className="icon-button" title="Close evidence" onClick={() => setEvidencePath(null)}><X size={18} /></button></header>
            {evidenceError && <p className="drawer-error">{evidenceError}</p>}
            {!evidence && !evidenceError && <p>Loading bounded evidence preview.</p>}
            {evidence && <><code>SHA-256 {evidence.source_sha256}</code><pre>{evidence.text}</pre>{evidence.truncated && <p>Preview truncated at the dashboard safety limit.</p>}</>}
          </aside>
        </div>
      )}
    </div>
  );
}
