import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Beaker,
  BookOpenText,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  ClipboardCheck,
  Clock3,
  FileText,
  GitBranch,
  History,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Moon,
  Search,
  ServerCog,
  ShieldAlert,
  Sun,
  X,
} from "lucide-react";
import { asText, getJson, Overview, Page, RecordValue, statusClass } from "./api";

type PageName = "command" | "review" | "gates" | "timeline" | "reports" | "work";

const nav = [
  ["command", "Command Center", LayoutDashboard],
  ["review", "Review Inbox", Inbox],
  ["gates", "Gates & Roadmap", ListChecks],
  ["timeline", "Timeline", History],
  ["reports", "Reports", FileText],
  ["work", "Runs & Experiments", Beaker],
] as const;

const roadmap = ["G0", "G1", "R1", "G2", "G3a", "G3b", "D1", "G4", "G5", "G6"];

function Status({ value }: { value: unknown }) {
  const text = asText(value);
  const Icon = text === "BLOCKED" || text === "FAILED" ? AlertTriangle : text === "PASS" || text === "SUCCEEDED" ? CheckCircle2 : CircleDot;
  return <span className={statusClass(text)}><Icon size={14} />{text}</span>;
}

function EvidenceButton({ path, onOpen }: { path: unknown; onOpen: (path: string) => void }) {
  const value = asText(path, "");
  if (!value) return null;
  return <button className="evidence-link" onClick={() => onOpen(value)}><BookOpenText size={14} />{value}</button>;
}

function CommandCenter({ data, onEvidence }: { data: Overview; onEvidence: (path: string) => void }) {
  const gate = data.current_gate ?? {};
  const gateId = asText(gate.gate_id);
  const runtime = (data.runtime.runtime ?? {}) as RecordValue;
  const submission = (data.runtime.submission ?? {}) as RecordValue;
  const resources = (runtime.raw_simulation_settings ?? {}) as RecordValue;
  const blockers = (gate.blockers ?? []) as string[];
  const warnings = (gate.warnings ?? []) as string[];
  const unresolved = (gate.unresolved_questions ?? []) as RecordValue[];
  const checks = (gate.technical_checks ?? []) as RecordValue[];
  const deadline = new Date(asText(data.runtime.close_instant_utc));
  const days = Number.isNaN(deadline.valueOf()) ? null : Math.max(0, Math.floor((deadline.valueOf() - Date.now()) / 86_400_000));
  return <>
    <section className="page-heading">
      <div><p className="eyebrow">Mission control</p><h1>{gateId} readiness</h1></div>
      <Status value={gate.decision} />
    </section>
    <section className="metric-strip" aria-label="mission summary">
      <div><span>Verified close</span><strong>{days === null ? "DEADLINE NOT VERIFIED" : `${days} days`}</strong><small>{asText(data.runtime.close_instant_utc)}</small></div>
      <div><span>Agent package</span><strong>{String(submission.hard_package_limit_kb ?? "UNKNOWN")} KB</strong><small>internal target &lt; {String(submission.internal_package_target_mb ?? "UNKNOWN")} MB</small></div>
      <div><span>Active jobs</span><strong>{data.active_jobs}</strong><small>No training has begun</small></div>
      <div><span>Verified cost</span><strong>USD 0</strong><small>local validation only</small></div>
    </section>
    <div className="content-grid two-one">
      <section className="panel">
        <header><div><p className="eyebrow">Gate evidence</p><h2>Technical checks</h2></div><Status value={gate.status} /></header>
        <div className="check-list">
          {checks.map((check) => <div className="check-row" key={asText(check.name)}><Status value={check.status} /><span>{asText(check.name)}</span><EvidenceButton path={check.evidence} onOpen={onEvidence} /></div>)}
          {!checks.length && <p className="empty-note">No G1 checks have run yet.</p>}
        </div>
      </section>
      <section className="panel attention">
        <header><div><p className="eyebrow">Attention queue</p><h2>{blockers.length + warnings.length + unresolved.length} items</h2></div><ShieldAlert size={20} /></header>
        {blockers.map((item) => <div className="attention-row critical" key={item}><AlertTriangle size={16} /><div><strong>BLOCKER</strong><p>{item}</p></div></div>)}
        {unresolved.map((item) => <div className="attention-row warning" key={asText(item.question)}><Clock3 size={16} /><div><strong>UNKNOWN</strong><p>{asText(item.question)} {asText(item.impact)}</p></div></div>)}
        {warnings.map((item) => <div className="attention-row warning" key={item}><Clock3 size={16} /><div><strong>NOTE</strong><p>{item}</p></div></div>)}
      </section>
    </div>
    <div className="content-grid equal">
      <section className="panel">
        <header><div><p className="eyebrow">Approved next action</p><h2>{gate.status === "SUCCEEDED" ? "Next phase" : `Begin ${gateId}`}</h2></div><ChevronRight size={20} /></header>
        <p className="next-action">{asText(gate.approved_next_action)}</p>
        <EvidenceButton path={gate.source_path} onOpen={onEvidence} />
      </section>
      <section className="panel">
        <header><div><p className="eyebrow">Runtime profile</p><h2>{asText(runtime.python_family)}</h2></div><ServerCog size={20} /></header>
        <dl className="facts"><div><dt>Image</dt><dd>{asText(runtime.image)}</dd></div><div><dt>Disk</dt><dd>{String(resources.agentDiskKb ?? "UNKNOWN")} KB</dd></div><div><dt>RAM</dt><dd>{String(resources.agentRamKb ?? "UNKNOWN")} KB</dd></div><div><dt>CPU</dt><dd>{String(resources.agentCpuCoresPercent ?? "UNKNOWN")}%</dd></div><div><dt>Internet</dt><dd>{String(resources.enableInternet ?? "UNKNOWN")}</dd></div><div><dt>Timeout</dt><dd><Status value={((runtime.timeout_seconds ?? {}) as RecordValue).status} /></dd></div></dl>
      </section>
    </div>
    <section className="panel incidents">
      <header><div><p className="eyebrow">Reliability and incidents</p><h2>Recent history</h2></div><Activity size={20} /></header>
      {data.recent_incidents.map((incident) => <div className="incident-row" key={asText(incident.record_id)}><Status value={incident.state} /><div><strong>{asText(incident.title)}</strong><p>{asText(incident.containment, asText(incident.corrective_action))}</p></div><EvidenceButton path={incident.source_path} onOpen={onEvidence} /></div>)}
    </section>
  </>;
}

function ReviewInbox({ items, onEvidence }: { items: RecordValue[]; onEvidence: (path: string) => void }) {
  return <section><div className="page-heading"><div><p className="eyebrow">Human decisions</p><h1>Review Inbox</h1></div><span className="count">{items.length} open</span></div>{items.map((item) => <article className="panel review-item" key={asText(item.gate_id)}><header><h2>{asText(item.gate_id)} review</h2><Status value={item.decision} /></header>{((item.blockers ?? []) as string[]).map((blocker) => <p className="blocker-line" key={blocker}><AlertTriangle size={15} />{blocker}</p>)}<p><strong>Next:</strong> {asText(item.next_action)}</p><EvidenceButton path={item.source_path} onOpen={onEvidence} /></article>)}</section>;
}

function Gates({ gates, onEvidence }: { gates: RecordValue[]; onEvidence: (path: string) => void }) {
  const current = gates.find((gate) => ["PLANNED", "QUEUED", "RUNNING", "BLOCKED"].includes(asText(gate.status)));
  const records = new Map(gates.map((gate) => [asText(gate.gate_id), gate]));
  const latest = current ?? [...roadmap].reverse().map((gate) => records.get(gate)).find(Boolean);
  return <section><div className="page-heading"><div><p className="eyebrow">Evidence-gated plan</p><h1>Gates & Roadmap</h1></div></div><div className="roadmap">{roadmap.map((gate, index) => {
    const record = records.get(gate);
    const passed = ["PASS", "SUCCEEDED"].includes(asText(record?.decision, asText(record?.status)));
    const active = Boolean(record && record === current);
    return <div className={`roadmap-step ${passed ? "passed" : active ? "current" : "future"}`} key={gate}><span>{index + 1}</span><div><strong>{gate}</strong><small>{passed ? "Passed" : active ? "Approved next" : "Not started"}</small></div></div>;
  })}</div>{latest && <section className="panel"><header><div><p className="eyebrow">{current ? "Current gate" : "Latest gate"}</p><h2>{asText(latest.title)}</h2></div><Status value={latest.status} /></header><p className="next-action">{asText(latest.approved_next_action)}</p><EvidenceButton path={latest.source_path} onOpen={onEvidence} /></section>}</section>;
}

function Timeline({ events, onEvidence }: { events: RecordValue[]; onEvidence: (path: string) => void }) {
  return <section><div className="page-heading"><div><p className="eyebrow">Append-only record</p><h1>Timeline</h1></div></div><div className="timeline">{events.map((event) => <article key={asText(event.record_id)}><time>{asText(event.created_at_utc)}</time><span className="timeline-dot" /><div><Status value={event.status_after} /><h2>{asText(event.title)}</h2><p>{asText(event.summary)}</p><EvidenceButton path={event.source_path} onOpen={onEvidence} /></div></article>)}</div></section>;
}

function Reports({ reports, query, onEvidence }: { reports: RecordValue[]; query: string; onEvidence: (path: string) => void }) {
  const filtered = reports.filter((report) => JSON.stringify(report).toLowerCase().includes(query.toLowerCase()));
  return <section><div className="page-heading"><div><p className="eyebrow">Source reports</p><h1>Reports</h1></div><span className="count">{filtered.length} records</span></div><div className="report-list">{filtered.map((report) => <details className="panel" key={asText(report.record_id)}><summary><div><Status value={report.status} /><strong>{asText(report.title)}</strong><small>{asText(report.created_at_utc)}</small></div><ChevronRight size={18} /></summary><EvidenceButton path={report.source_path} onOpen={onEvidence} /><pre>{asText(report.markdown, "Structured record; no Markdown body.")}</pre></details>)}</div></section>;
}

function Work({ runs, experiments, jobs }: { runs: RecordValue[]; experiments: RecordValue[]; jobs: RecordValue[] }) {
  return <section><div className="page-heading"><div><p className="eyebrow">Execution ledger</p><h1>Runs & Experiments</h1></div></div><div className="content-grid equal"><section className="panel empty"><GitBranch size={24} /><h2>Runs</h2>{runs.length ? <p>{runs.length} indexed</p> : <p>Not started. No run manifest producer has emitted a record.</p>}</section><section className="panel empty"><Beaker size={24} /><h2>Experiments</h2>{experiments.length ? <p>{experiments.length} indexed</p> : <p>Not started. No hypothesis or verdict has been recorded.</p>}</section></div><section className="panel"><header><h2>Jobs</h2><Status value={jobs.length ? "RUNNING" : "NOT_STARTED"} /></header>{jobs.length ? jobs.map((job) => <p key={asText(job.record_id)}>{asText(job.title)}</p>) : <p>No local or cloud jobs are active. A missing job is not reported as zero throughput or cost.</p>}</section></section>;
}

export default function App() {
  const [page, setPage] = useState<PageName>(() => (location.hash.slice(1) as PageName) || "command");
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [query, setQuery] = useState("");
  const [evidence, setEvidence] = useState<string | null>(null);
  const [data, setData] = useState<{ overview: Overview; review: RecordValue[]; gates: RecordValue[]; events: RecordValue[]; reports: RecordValue[]; runs: RecordValue[]; experiments: RecordValue[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
  useEffect(() => {
    Promise.all([
      getJson<Overview>("/api/v1/overview"),
      getJson<{ items: RecordValue[] }>("/api/v1/review-inbox"),
      getJson<Page>("/api/v1/gates"),
      getJson<Page>("/api/v1/events"),
      getJson<Page>("/api/v1/reports"),
      getJson<Page>("/api/v1/runs"),
      getJson<Page>("/api/v1/experiments"),
    ]).then(([overview, review, gates, events, reports, runs, experiments]) => setData({ overview, review: review.items, gates: gates.items, events: events.items, reports: reports.items, runs: runs.items, experiments: experiments.items })).catch((reason: Error) => setError(reason.message));
  }, []);

  const go = (next: PageName) => { setPage(next); location.hash = next; };
  const currentTitle = useMemo(() => nav.find(([id]) => id === page)?.[1] ?? "Command Center", [page]);
  if (error) return <main className="fatal"><AlertTriangle /><h1>Dashboard unavailable</h1><p>{error}</p></main>;
  if (!data) return <main className="fatal"><Activity className="spin" /><h1>Loading project evidence</h1></main>;

  const activeGate = data.overview.current_gate ?? {};
  return <div className="shell">
    <aside>
      <div className="brand"><div className="brand-mark"><ClipboardCheck size={20} /></div><div><strong>PTCG RL</strong><span>Research cockpit</span></div></div>
      <nav aria-label="Dashboard pages">{nav.map(([id, label, Icon]) => <button title={label} aria-current={page === id ? "page" : undefined} className={page === id ? "active" : ""} key={id} onClick={() => go(id)}><Icon size={18} /><span>{label}</span></button>)}</nav>
      <div className="sidebar-footer"><div><span>DATA HEALTH</span><Status value={data.overview.data_health.status} /></div><small>Local read-only</small></div>
    </aside>
    <div className="workspace">
      <header className="mission-bar"><div className="mobile-title"><strong>{currentTitle}</strong></div><div className="search"><Search size={16} /><input aria-label="Search dashboard" placeholder="Search evidence" value={query} onChange={(event) => setQuery(event.target.value)} /></div><div className="mission-facts"><span><Clock3 size={15} />Closes 16 Aug</span><span><CircleDot size={15} />{asText(activeGate.gate_id)}</span><Status value={activeGate.status} /><button className="icon-button" title={`Use ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}</button></div></header>
      <main>{page === "command" && <CommandCenter data={data.overview} onEvidence={setEvidence} />}{page === "review" && <ReviewInbox items={data.review} onEvidence={setEvidence} />}{page === "gates" && <Gates gates={data.gates} onEvidence={setEvidence} />}{page === "timeline" && <Timeline events={data.events} onEvidence={setEvidence} />}{page === "reports" && <Reports reports={data.reports} query={query} onEvidence={setEvidence} />}{page === "work" && <Work runs={data.runs} experiments={data.experiments} jobs={data.overview.jobs} />}</main>
    </div>
    {evidence && <div className="drawer-backdrop" onClick={() => setEvidence(null)}><aside className="drawer" onClick={(event) => event.stopPropagation()}><header><div><p className="eyebrow">Evidence source</p><h2>Traceable project record</h2></div><button className="icon-button" title="Close evidence" onClick={() => setEvidence(null)}><X size={18} /></button></header><code>{evidence}</code><p>Preview is intentionally bounded to allowlisted Markdown and JSON. Private assets, replay bodies, checkpoints and credentials are never served.</p></aside></div>}
  </div>;
}
