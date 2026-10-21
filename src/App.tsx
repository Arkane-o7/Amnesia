import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Cpu,
  Presentation,
  Upload,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  FlaskConical,
  GitBranch,
  Layers3,
  Lightbulb,
  MessageSquare,
  Network,
  Plus,
  RotateCw,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "./api";
import { Graph } from "./Graph";
import { Experiments } from "./Experiments";
import { Engine } from "./Engine";
import { Review } from "./Review";
import { ImportWorkspace } from "./Import";
import { Notes } from "./Notes";
import type {
  Evaluation,
  Fact,
  IngestResult,
  MemoryEvent,
  QueryResult,
  Scenario,
  State,
  Workspace,
} from "./types";
import { date, methods, pct, relations } from "./types";

type Page = "studio" | "ledger" | "experiments" | "notes" | "engine" | "review";
const pages: { id: Page; label: string; icon: typeof Network }[] = [
  { id: "studio", label: "Memory studio", icon: Network },
  { id: "ledger", label: "Memory ledger", icon: Database },
  { id: "experiments", label: "Experiments", icon: FlaskConical },
  { id: "notes", label: "Research notes", icon: BookOpen },
  { id: "engine", label: "AI engine", icon: Cpu },
  { id: "review", label: "Final review", icon: Presentation },
];

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge ${status}`}>
      <i />
      {status === "active"
        ? "Current"
        : status[0].toUpperCase() + status.slice(1)}
    </span>
  );
}

function EventItem({
  event,
  state,
  onSelect,
}: {
  event: MemoryEvent;
  state: State;
  onSelect: (f: Fact) => void;
}) {
  const query = event.role === "query" ? (event.result as QueryResult) : null;
  const result = event.role === "user" ? (event.result as IngestResult) : null;
  const facts = result?.decisions || [];
  return (
    <div className="conversation-event">
      <div className="event-heading">
        <span className="avatar">Y</span>
        <strong>You</strong>
        <time>{date(event.observed_at)}</time>
      </div>
      <p className="event-text">{event.text}</p>
      {result && (
        <div className="event-feedback">
          <span className="feedback-icon">
            <GitBranch size={13} />
          </span>
          <div>
            {facts.length ? (
              <>
                <span>
                  {facts.length} assertion{facts.length === 1 ? "" : "s"}{" "}
                  reconciled
                </span>
                <div className="event-facts">
                  {facts.map((d, i) => (
                    <button
                      key={`${d.fact_id}-${i}`}
                      onClick={() => {
                        const f = state.facts.find((f) => f.id === d.fact_id);
                        if (f) onSelect(f);
                      }}
                    >
                      <span
                        className={`small-status ${d.label.toLowerCase()}`}
                      />
                      {d.value}
                      <span className="event-decision">
                        {d.label.toLowerCase()}
                      </span>
                      <ArrowUpRight size={10} />
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <span>No supported facts extracted.</span>
            )}
            {result.unsupported.length > 0 && (
              <p className="unsupported">
                Not extracted: {result.unsupported.join("; ")}. See Research
                notes for supported phrases.
              </p>
            )}
          </div>
        </div>
      )}
      {query && (
        <div className="answer-bubble">
          <div>
            <span className="small-brand">✳</span>
            <strong>Amnesia</strong>
            <span>{methods[query.method]}</span>
          </div>
          <p>{query.answer}</p>
          <small>
            <ShieldCheck size={11} />
            {query.used_ids.length} evidence source
            {query.used_ids.length === 1 ? "" : "s"} ·{" "}
            {query.latency_ms.toFixed(1)} ms
          </small>
        </div>
      )}
    </div>
  );
}

function Inspector({
  fact,
  state,
  onClose,
  onSelect,
  onResolve,
}: {
  fact: Fact;
  state: State;
  onClose: () => void;
  onSelect: (f: Fact) => void;
  onResolve: (fact: Fact, evidence: string) => Promise<void>;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [resolving, setResolving] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    closeRef.current?.focus();
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const items = [
          ...(closeRef.current
            ?.closest("aside")
            ?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, textarea, select, [tabindex="0"]') || []),
        ];
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      before?.focus();
    };
  }, [onClose]);
  const evidenceEvents = state.events.filter(
    (e) =>
      e.id === fact.event_id ||
      (e.role === "user" &&
        (e.result as IngestResult).decisions.some(
          (d) => d.fact_id === fact.id,
        )),
  );
  return (
    <div className="drawer-scrim" onClick={onClose}>
      <aside
        className="inspector"
        role="dialog"
        aria-modal="true"
        aria-label="Memory inspector"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="inspector-header">
          <span className="eyebrow">MEMORY INSPECTOR</span>
          <button
            ref={closeRef}
            className="icon-button"
            aria-label="Close memory inspector"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </div>
        <StatusBadge status={fact.effective_status} />
        <h2>{fact.value}</h2>
        <p className="fact-triple">
          {fact.subject} <span>{relations[fact.relation]}</span> {fact.value}
        </p>
        {fact.effective_status === "unresolved" && <div className="resolve-box"><h3>Confirm this memory as current</h3><p className="field-note">Only competing facts in this entity, relation, and scope will be retired.</p><textarea aria-label="Conflict confirmation evidence" value={confirmation} onChange={e => setConfirmation(e.target.value)} placeholder={`Confirmed: ${fact.value} is the current value.`}/><button className="primary-button" disabled={resolving || !confirmation.trim()} onClick={async () => { setResolving(true); try { await onResolve(fact, confirmation); } finally { setResolving(false); } }}>{resolving ? "Resolving…" : `Confirm ${fact.value}`}</button></div>}
        <div className="inspector-section">
          <h3>The evidence</h3>
          {evidenceEvents.map((e) => (
            <div className="evidence-box" key={e.id}>
              <blockquote>“{e.text}”</blockquote>
              <span>
                {state.sessions.find((s) => s.id === e.session_id)?.name} ·{" "}
                {new Date(e.observed_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
        <div className="inspector-section">
          <h3>Memory record</h3>
          <dl>
            <dt>Confidence</dt>
            <dd>
              {pct(fact.confidence)} <small>extraction estimate</small>
            </dd>
            <dt>Valid from</dt>
            <dd>{new Date(fact.valid_from).toLocaleString()}</dd>
            <dt>Valid until</dt>
            <dd>
              {fact.valid_until
                ? new Date(fact.valid_until).toLocaleString()
                : "Open-ended"}
            </dd>
            <dt>Observed</dt>
            <dd>{new Date(fact.observed_at).toLocaleString()}</dd>
            <dt>Evidence links</dt>
            <dd>{fact.evidence_count}</dd>
            <dt>Assertion ID</dt>
            <dd>
              <code>{fact.id}</code>
            </dd>
          </dl>
        </div>
        <div className="inspector-section">
          <h3>Why this state?</h3>
          {state.decisions
            .filter((d) => d.fact_id === fact.id || d.existing_id === fact.id)
            .map((d) => (
              <div className="decision-detail" key={d.id}>
                <span className="decision-tag">{d.label}</span>
                <p>{d.reason}</p>
              </div>
            ))}
          {fact.superseded_by && (
            <button
              className="next-memory"
              onClick={() => {
                const next = state.facts.find(
                  (f) => f.id === fact.superseded_by,
                );
                if (next) onSelect(next);
              }}
            >
              Inspect the replacement <ArrowRight size={15} />
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}

function Retrieval({
  state,
  result,
  question,
  setQuestion,
  method,
  setMethod,
  onQuery,
  busy,
  onSelect,
  asOf,
  setAsOf,
  gate,
  setGate,
}: {
  state: State;
  result: QueryResult | null;
  question: string;
  setQuestion: (v: string) => void;
  method: string;
  setMethod: (v: string) => void;
  onQuery: () => void;
  busy: boolean;
  onSelect: (f: Fact) => void;
  asOf: string;
  setAsOf: (v: string) => void;
  gate: boolean;
  setGate: (v: boolean) => void;
}) {
  const [advanced, setAdvanced] = useState(false);
  return (
    <section className="panel retrieval-panel">
      <div className="panel-heading">
        <div>
          <h2>What comes back, and why</h2>
          <p>Follow the evidence from your question to the answer.</p>
        </div>
        <button
          className={`text-button ${advanced ? "purple-text" : ""}`}
          onClick={() => setAdvanced(!advanced)}
          aria-expanded={advanced}
        >
          <SlidersHorizontal size={14} /> Retrieval controls
        </button>
      </div>
      <form
        className="retrieval-form"
        onSubmit={(e) => {
          e.preventDefault();
          onQuery();
        }}
      >
        <Search size={17} />
        <input
          aria-label="Memory question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What would you like to remember?"
          maxLength={2000}
        />
        <select
          aria-label="Retrieval method"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          {Object.entries(methods)
            .filter(([k]) => !k.startsWith("hybrid_no"))
            .map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
        </select>
        <button className="primary-button" disabled={busy || !question.trim()}>
          {busy ? (
            <RotateCw size={14} className="spin" />
          ) : (
            <ArrowRight size={15} />
          )}{" "}
          Ask memory
        </button>
      </form>
      {advanced && (
        <div className="advanced-controls">
          <label>
            Recall as of
            <input
              type="datetime-local"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </label>
          <button className="text-button" onClick={() => setAsOf("")}>
            Use present
          </button>
          <label className="switch-label">
            <input
              type="checkbox"
              checked={gate}
              onChange={(e) => setGate(e.target.checked)}
            />
            <span className="switch" />
            Memory necessity gate
          </label>
          <span className="muted">Applied on the next query.</span>
        </div>
      )}
      {result ? (
        <>
          <div className="retrieval-answer">
            <span className="answer-symbol">
              <Sparkles size={17} />
            </span>
            <div>
              <p>{result.answer}</p>
              <small>
                <CheckCheck size={12} />
                {methods[result.method]} · {result.used_ids.length} supporting
                source{result.used_ids.length === 1 ? "" : "s"} ·{" "}
                {result.latency_ms.toFixed(1)} ms · ~
                {Math.round(result.context_tokens_estimate)} context tokens{" "}
                {asOf &&
                  `· Snapshot ${new Date(result.as_of).toLocaleString()}`}
              </small>
            </div>
            <StatusBadge
              status={
                result.answer_value === "UNRESOLVED"
                  ? "unresolved"
                  : result.candidates.find((f) => f.id === result.used_ids[0])
                      ?.effective_status || "unavailable"
              }
            />
          </div>
          <div className="table-scroll">
            <table className="retrieval-table">
              <thead>
                <tr>
                  <th>Candidate memory</th>
                  <th>State</th>
                  <th>
                    Relevance{" "}
                    <span
                      title={
                        result?.semantic_engine ||
                        "Sparse TF-IDF cosine similarity"
                      }
                    >
                      ⓘ
                    </span>
                  </th>
                  <th>Graph</th>
                  <th>Temporal</th>
                  <th>Final score</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {result.candidates.map((f) => (
                  <tr
                    key={f.id}
                    className={result.used_ids.includes(f.id) ? "used-row" : ""}
                  >
                    <td>
                      <button
                        className="fact-link"
                        onClick={() =>
                          onSelect(state.facts.find((m) => m.id === f.id) || f)
                        }
                      >
                        {f.subject} <span>{relations[f.relation]}</span>{" "}
                        <strong>{f.value}</strong>
                        <ArrowUpRight size={11} />
                      </button>
                    </td>
                    <td>
                      <StatusBadge status={f.effective_status} />
                    </td>
                    <td>{f.components.semantic.toFixed(2)}</td>
                    <td>{f.components.graph.toFixed(2)}</td>
                    <td>{f.components.temporal.toFixed(2)}</td>
                    <td>
                      <strong>{f.score.toFixed(3)}</strong>
                    </td>
                    <td>
                      <span
                        className={`retrieval-decision ${result.used_ids.includes(f.id) ? "used" : ""}`}
                      >
                        {result.used_ids.includes(f.id) ? (
                          <>
                            <Check size={11} /> Used
                          </>
                        ) : !f.eligible ? (
                          "Filtered"
                        ) : result.retrieved.some((r) => r.id === f.id) ? (
                          "Context"
                        ) : (
                          "Below top 5"
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!result.candidates.length && (
              <p className="empty-copy">
                No candidate memories at this point in time. Add a supported
                fact to begin.
              </p>
            )}
          </div>
          <div className="score-note">
            <span>Hybrid score</span>
            <code>
              0.40 relevance + 0.25 graph + 0.20 validity + 0.15 confidence −
              0.65 staleness
            </code>
            <span>
              {result.semantic_engine || "TF-IDF cosine"} ·{" "}
              {result.answer_engine || "evidence template"}
            </span>
          </div>
        </>
      ) : (
        <p className="empty-copy">
          Ask a question to inspect retrieval scores and supporting evidence.
        </p>
      )}
    </section>
  );
}

function Ledger({
  state,
  onSelect,
  search,
  setSearch,
}: {
  state: State;
  onSelect: (f: Fact) => void;
  search: string;
  setSearch: (s: string) => void;
}) {
  const [filter, setFilter] = useState("all");
  const facts = state.facts.filter(
    (f) =>
      (filter === "all" || f.effective_status === filter) &&
      `${f.subject} ${f.value} ${relations[f.relation]} ${f.evidence}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="page-intro">
        <div>
          <span className="eyebrow">NOTHING LOST IN THE UPDATE</span>
          <h1>The memory ledger.</h1>
          <p>Every assertion, its source, and what became of it.</p>
        </div>
        <a
          className="secondary-button"
          href={`/api/export?workspace_id=${state.workspace.id}`}
          download
        >
          <ArrowDownToLine size={15} /> Export workspace
        </a>
      </div>
      <section className="panel">
        <div className="ledger-toolbar">
          <div className="search-field">
            <Search size={16} />
            <input
              aria-label="Search memories"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search facts, entities, or evidence…"
            />
          </div>
          <select
            aria-label="Filter memory status"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All states</option>
            {["active", "superseded", "invalid", "unresolved", "expired"].map(
              (s) => (
                <option key={s} value={s}>
                  {s === "active" ? "Current" : s[0].toUpperCase() + s.slice(1)}
                </option>
              ),
            )}
          </select>
          <span>{facts.length} memories</span>
        </div>
        <div className="table-scroll">
          <table className="ledger-table">
            <thead>
              <tr>
                <th>Assertion</th>
                <th>State</th>
                <th>Confidence</th>
                <th>Observed</th>
                <th>Evidence</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {[...facts].reverse().map((f) => (
                <tr key={f.id}>
                  <td>
                    <button className="fact-link" onClick={() => onSelect(f)}>
                      {f.subject} <span>{relations[f.relation]}</span>{" "}
                      <strong>{f.value}</strong>
                    </button>
                  </td>
                  <td>
                    <StatusBadge status={f.effective_status} />
                  </td>
                  <td>{pct(f.confidence)}</td>
                  <td>{date(f.observed_at)}</td>
                  <td>
                    <span className="evidence-preview">“{f.evidence}”</span>
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`Inspect ${f.value}`}
                      onClick={() => onSelect(f)}
                    >
                      <ArrowUpRight size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!facts.length && (
            <div className="ledger-empty">
              <Database size={30} />
              <h3>
                {search || filter !== "all"
                  ? "No matching memories."
                  : "No memories yet."}
              </h3>
              <p>
                {search || filter !== "all"
                  ? "Try a different search or state filter."
                  : "Add a fact in Memory studio to start a record."}
              </p>
            </div>
          )}
        </div>
      </section>
      <div className="info-callout">
        <ShieldCheck size={18} />
        <p>
          History is preserved. Superseded and invalid assertions stay in the
          ledger with their evidence and replacement links.
        </p>
      </div>
    </>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>(window.location.hash === "#engine" ? "engine" : window.location.hash === "#review" ? "review" : "studio");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [wid, setWid] = useState("");
  const [state, setState] = useState<State | null>(null);
  const [sid, setSid] = useState("");
  const [sessionFilter, setSessionFilter] = useState("all");
  const [health, setHealth] = useState<{
    extractor: string;
    llm_configured: boolean;
    external_enabled: boolean;
    provider: string; chat_model: string; embedding_model: string;
  } | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("location");
  const [report, setReport] = useState<Evaluation | null>(null);
  const [selected, setSelected] = useState<Fact | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [queryBusy, setQueryBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState("add");
  const [question, setQuestion] = useState("Where do I live now?");
  const [method, setMethod] = useState("hybrid");
  const [asOf, setAsOf] = useState("");
  const [gate, setGate] = useState(true);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [search, setSearch] = useState("");
  const [newWorkspace, setNewWorkspace] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [name, setName] = useState("");
  const requestVersion = useRef(0);
  const startupQuestion = useRef("Where do I live now?");
  const conversationRef = useRef<HTMLDivElement>(null);
  const ready = state?.workspace.id === wid;
  const showError = useCallback((message: string) => setError(message), []);
  const closeInspector = useCallback(() => setSelected(null), []);
  const refresh = useCallback(async (id: string) => {
    const next = await api<State>(`state?workspace_id=${id}`);
    setState(next);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<Workspace[]>("workspaces"),
      api<Scenario[]>("scenarios"),
      api<{
        extractor: string;
        llm_configured: boolean;
        external_enabled: boolean;
    provider: string; chat_model: string; embedding_model: string;
      }>("health"),
      api<Evaluation | null>("evaluation"),
    ])
      .then(([ws, sc, h, evaluation]) => {
        if (cancelled) return;
        setWorkspaces(ws);
        setScenarios(sc);
        setHealth(h);
        setReport(evaluation);
        const saved = localStorage.getItem("amnesia.workspace");
        setWid(ws.find((w) => w.id === saved)?.id || ws[0]?.id || "");
      })
      .catch((e) => !cancelled && showError(e.message));
    return () => {
      cancelled = true;
    };
  }, [showError]);
  useEffect(() => {
    if (!wid) return;
    let cancelled = false;
    ++requestVersion.current;
    const firstQuestion = startupQuestion.current;
    startupQuestion.current = "Where do I live now?";
    setQueryBusy(false);
    setSelected(null);
    setResult(null);
    setAsOf("");
    setSessionFilter("all");
    setError("");
    localStorage.setItem("amnesia.workspace", wid);
    api<State>(`state?workspace_id=${wid}`)
      .then(async (next) => {
        if (cancelled) return;
        setState(next);
        setSid(next.sessions.at(-1)?.id || "");
        setQuestion(firstQuestion);
        setMethod("hybrid");
        setResult(null);
      })
      .catch((e) => !cancelled && showError(e.message));
    return () => {
      cancelled = true;
    };
  }, [wid, showError]);
  useEffect(() => {
    if (conversationRef.current)
      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
  }, [state?.events.length, sessionFilter]);

  async function ask(persist = false, q = question) {
    if (!wid || !ready) return false;
    const version = ++requestVersion.current;
    setQueryBusy(true);
    setError("");
    try {
      const next = await api<QueryResult>("query", {
        workspace_id: wid,
        session_id: sid,
        question: q,
        method,
        as_of: asOf ? new Date(asOf).toISOString() : undefined,
        gate,
        persist,
      });
      if (version === requestVersion.current) {
        setResult(next);
        if (persist) await refresh(wid);
      }
      return true;
    } catch (e) {
      showError((e as Error).message);
      return false;
    } finally {
      if (version === requestVersion.current) setQueryBusy(false);
    }
  }
  async function submitDraft() {
    if (!draft.trim() || busy || queryBusy || !ready) return;
    if (mode === "ask") {
      const q = draft;
      setQuestion(q);
      if (await ask(true, q))
        setDraft((current) => (current === q ? "" : current));
      return;
    }
    const sentText = draft;
    setBusy(true);
    setError("");
    try {
      await api("events", {
        workspace_id: wid,
        session_id: sid,
        text: sentText,
      });
      setDraft((current) => (current === sentText ? "" : current));
      await refresh(wid);
      if (result) await ask();
    } catch (e) {
      showError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function addSession() {
    setBusy(true);
    try {
      const session = await api<{ id: string }>("sessions", {
        workspace_id: wid,
      });
      await refresh(wid);
      setSid(session.id);
      setSessionFilter(session.id);
    } catch (e) {
      showError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createWorkspace() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const created = await api<{ id: string }>("workspaces", { name });
      setWorkspaces(await api<Workspace[]>("workspaces"));
      setWid(created.id);
      setNewWorkspace(false);
      setName("");
      setDraft("");
    } catch (e) {
      showError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadScenario() {
    setBusy(true);
    try {
      const created = await api<{ id: string }>("scenarios/load", { scenario });
      setWorkspaces(await api<Workspace[]>("workspaces"));
      startupQuestion.current =
        scenarios.find((s) => s.id === scenario)?.question ||
        "Where do I live now?";
      setWid(created.id);
      setDraft("");
    } catch (e) {
      showError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const active =
    state?.facts.filter((f) => f.effective_status === "active").length || 0;
  const changes =
    state?.decisions.filter((d) => ["UPDATES", "SUPERSEDES"].includes(d.label))
      .length || 0;
  const navLabel = pages.find((p) => p.id === page)?.label;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#studio"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setPage("studio");
          }}
        >
          <svg viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <ellipse
              cx="20"
              cy="20"
              rx="8"
              ry="15"
              transform="rotate(42 20 20)"
            />
            <ellipse
              cx="20"
              cy="20"
              rx="8"
              ry="15"
              transform="rotate(-42 20 20)"
            />
            <circle cx="20" cy="20" r="2.4" fill="currentColor" stroke="none" />
          </svg>
          <span>
            amnesia<span>MEMORY RESEARCH LAB</span>
          </span>
        </a>
        <div className="workspace-switch">
          <span className="workspace-icon">
            <Layers3 size={17} />
          </span>
          <select
            aria-label="Workspace"
            value={wid}
            onChange={(e) => {
              setWid(e.target.value);
              setDraft("");
            }}
            disabled={busy || queryBusy}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <ChevronDown size={13} />
        </div>
        <button
          className="new-workspace text-button"
          onClick={() => setNewWorkspace(true)}
          disabled={busy}
        >
          <Plus size={13} /> New workspace
        </button>
        <button className="text-button import-workspace" onClick={() => setImportOpen(true)}><Upload size={12}/> Import workspace</button>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {pages.map((p) => (
            <button
              key={p.id}
              className={page === p.id ? "nav-item active" : "nav-item"}
              onClick={() => setPage(p.id)}
            >
              <p.icon size={18} />
              <span>{p.label}</span>
              {p.id === "studio" && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="sidebar-note-icon">
            <Lightbulb size={18} />
          </span>
          <h3>Memory is a moving thing.</h3>
          <p>
            Keep the past.
            <br />
            Know what’s true now.
          </p>
          <button onClick={() => setPage("notes")}>
            Behind the research <ArrowUpRight size={12} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <div>
            <span className={health ? "live-dot" : "live-dot offline"} />
            <strong>
              {health ? "Memory server connected" : "Connecting to server…"}
            </strong>
          </div>
          <span>
            SQLite ·{" "}
            {health?.provider === "offline" ? "Offline regression" : health?.provider === "codex" ? "Codex login · local embeddings" : health?.provider === "openai" ? "OpenAI inference" : "Local AI inference"}
          </span>
          <span className="version">
            REVIEW BUILD <span>v1.0.0</span>
          </span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span>Workspace</span>
            <ChevronRight size={12} />
            <strong>{navLabel}</strong>
          </div>
          <div>
            <span className="local-chip">
              <span className="live-dot" /> Local workspace
            </span>
            <button
              className="icon-button"
              aria-label="Open research notes"
              onClick={() => setPage("notes")}
            >
              <CircleHelp size={18} />
            </button>
            <span className="user-avatar">AC</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!ready ? (
            <div className="loading-view">
              <RotateCw size={24} className="spin" />
              <h2>
                {error
                  ? "The workspace is unavailable."
                  : "Opening your memory workspace…"}
              </h2>
              {error && (
                <button
                  className="secondary-button"
                  onClick={() => window.location.reload()}
                >
                  Retry connection
                </button>
              )}
            </div>
          ) : (
            state && (
              <>
                {page === "studio" && (
                  <>
                    <div className="page-intro studio-intro">
                      <div>
                        <span className="eyebrow">
                          <span className="purple-dash" /> THE EVOLVING MEMORY
                          WORKSPACE
                        </span>
                        <h1>A little history. A clearer present.</h1>
                        <p>
                          Turn conversations into connected knowledge that keeps
                          up with you.
                        </p>
                      </div>
                      <a
                        className="secondary-button"
                        href={`/api/export?workspace_id=${wid}`}
                        download
                      >
                        <ArrowDownToLine size={14} /> Export memory
                      </a>
                    </div>
                    <div className="stats-grid">
                      {[
                        {
                          label: "Current memories",
                          value: active,
                          caption: "What’s true right now",
                          icon: Database,
                          color: "purple",
                        },
                        {
                          label: "Connected entities",
                          value: state.entities.length,
                          caption: "People, places, and things",
                          icon: Network,
                          color: "blue",
                        },
                        {
                          label: "Reconciled changes",
                          value: changes,
                          caption: "History, safely preserved",
                          icon: GitBranch,
                          color: "green",
                        },
                        {
                          label: "Conversation sessions",
                          value: state.sessions.length,
                          caption: "Continuity across conversations",
                          icon: MessageSquare,
                          color: "amber",
                        },
                      ].map((s) => (
                        <div className="stat" key={s.label}>
                          <span className={`stat-icon ${s.color}`}>
                            <s.icon size={17} />
                          </span>
                          <span>{s.label}</span>
                          <strong>{s.value.toString().padStart(2, "0")}</strong>
                          <small>{s.caption}</small>
                        </div>
                      ))}
                    </div>
                    <div className="demo-strip">
                      <span className="demo-icon">
                        <PlayIcon />
                      </span>
                      <div>
                        <strong>Watch a memory change.</strong>
                        <span>Try a short, guided scenario.</span>
                      </div>
                      <select
                        aria-label="Demo scenario"
                        value={scenario}
                        onChange={(e) => setScenario(e.target.value)}
                        disabled={busy}
                      >
                        {scenarios.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                      <button
                        className="text-button purple-text"
                        onClick={loadScenario}
                        disabled={busy || queryBusy}
                      >
                        Load scenario <ArrowRight size={14} />
                      </button>
                    </div>
                    <div className="studio-grid">
                      <Graph
                        state={state}
                        onSelect={setSelected}
                        selected={selected?.id}
                      />
                      <section className="panel conversation-panel">
                        <div className="panel-heading">
                          <div>
                            <h2>The conversation</h2>
                            <p>Small statements. Lasting context.</p>
                          </div>
                          <span className="conversation-count">
                            {state.events.length}
                          </span>
                        </div>
                        <div className="session-toolbar">
                          <select
                            aria-label="Conversation session"
                            value={sessionFilter}
                            onChange={(e) => {
                              setSessionFilter(e.target.value);
                              if (e.target.value !== "all")
                                setSid(e.target.value);
                            }}
                          >
                            <option value="all">All sessions</option>
                            {state.sessions.map((s) => (
                              <option key={s.id} value={s.id}>
                                {s.name}
                              </option>
                            ))}
                          </select>
                          <button
                            className="text-button"
                            onClick={addSession}
                            disabled={busy || queryBusy}
                          >
                            <Plus size={13} /> New session
                          </button>
                        </div>
                        <div
                          className="conversation-scroll"
                          ref={conversationRef}
                        >
                          {state.events
                            .filter(
                              (e) =>
                                sessionFilter === "all" ||
                                e.session_id === sessionFilter,
                            )
                            .map((event, i, events) => (
                              <div key={event.id}>
                                {(i === 0 ||
                                  events[i - 1].session_id !==
                                    event.session_id) && (
                                  <div className="session-divider">
                                    <span>
                                      {
                                        state.sessions.find(
                                          (s) => s.id === event.session_id,
                                        )?.name
                                      }
                                    </span>
                                    <i />
                                  </div>
                                )}
                                <EventItem
                                  event={event}
                                  state={state}
                                  onSelect={setSelected}
                                />
                              </div>
                            ))}
                          {!state.events.some(
                            (e) =>
                              sessionFilter === "all" ||
                              e.session_id === sessionFilter,
                          ) && (
                            <div className="conversation-empty">
                              <MessageSquare size={24} />
                              <h3>A new conversation.</h3>
                              <p>
                                Your earlier memories are still here.
                                <br />
                                Add a fact or ask about what you remember.
                              </p>
                            </div>
                          )}
                        </div>
                        <div className="composer">
                          <div className="composer-mode segmented">
                            <button
                              className={mode === "add" ? "selected" : ""}
                              onClick={() => setMode("add")}
                            >
                              <Plus size={12} /> Add memory
                            </button>
                            <button
                              className={mode === "ask" ? "selected" : ""}
                              onClick={() => setMode("ask")}
                            >
                              <Sparkles size={12} /> Ask memory
                            </button>
                          </div>
                          <form
                            onSubmit={(e) => {
                              e.preventDefault();
                              submitDraft();
                            }}
                          >
                            <textarea
                              aria-label={
                                mode === "add"
                                  ? "New memory"
                                  : "Conversation question"
                              }
                              value={draft}
                              onChange={(e) => setDraft(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                  e.preventDefault();
                                  submitDraft();
                                }
                              }}
                              placeholder={
                                mode === "add"
                                  ? "“I moved to Chennai.”"
                                  : "“Where do I live now?”"
                              }
                              rows={2}
                              maxLength={mode === "add" ? 8000 : 2000}
                            />
                            <button
                              className="send-button"
                              aria-label={
                                mode === "add" ? "Save memory" : "Send question"
                              }
                              disabled={busy || queryBusy || !draft.trim()}
                            >
                              {busy || queryBusy ? (
                                <RotateCw size={16} className="spin" />
                              ) : (
                                <Send size={15} />
                              )}
                            </button>
                          </form>
                          <div className="composer-caption">
                            <span>
                              <span className="live-dot" />{" "}
                              {state.sessions.find((s) => s.id === sid)?.name}
                            </span>
                            <span>
                              Enter to send · Shift + Enter for a new line
                            </span>
                          </div>
                        </div>
                      </section>
                    </div>
                    <Retrieval
                      state={state}
                      result={result}
                      question={question}
                      setQuestion={setQuestion}
                      method={method}
                      setMethod={setMethod}
                      onQuery={() => ask()}
                      busy={queryBusy || busy}
                      onSelect={setSelected}
                      asOf={asOf}
                      setAsOf={setAsOf}
                      gate={gate}
                      setGate={setGate}
                    />
                    <footer className="workspace-footer">
                      <span>
                        <ShieldCheck size={13} />{" "}
                        {health?.external_enabled
                          ? "Stored locally · AI processing sends context to OpenAI"
                          : "Your memory stays on this device."}
                      </span>
                      <span>
                        Amnesia · Evolving knowledge, preserved evidence
                      </span>
                    </footer>
                  </>
                )}
                {page === "ledger" && (
                  <Ledger
                    state={state}
                    onSelect={setSelected}
                    search={search}
                    setSearch={setSearch}
                  />
                )}
                {page === "experiments" && (
                  <Experiments
                    report={report}
                    setReport={setReport}
                    onError={showError}
                  />
                )}
                {page === "review" && <Review onError={showError} openWorkspace={async id => { setWorkspaces(await api<Workspace[]>("workspaces")); setWid(id); setPage("studio"); }} />}
                {page === "notes" && <Notes />}
                {page === "engine" && <Engine onError={showError} onSaved={() => { api<typeof health>("health").then(setHealth).catch(e => showError(e.message)); }} />}
              </>
            )
          )}
        </main>
      </div>
      {selected && state && (
        <Inspector
          fact={selected}
          state={state}
          onClose={closeInspector}
          onSelect={setSelected}
          onResolve={async (fact, evidence) => { try { await api("conflicts/resolve", { workspace_id: wid, session_id: sid, fact_id: fact.id, evidence }); await refresh(wid); setSelected(null); if (result) await ask(); } catch (e) { showError((e as Error).message); } }}
        />
      )}
      {importOpen && <ImportWorkspace onClose={() => setImportOpen(false)} onError={showError} onImported={async id => { setWorkspaces(await api<Workspace[]>("workspaces")); setWid(id); setPage("studio"); }} />}
      {newWorkspace && (
        <div className="modal-scrim" onClick={() => setNewWorkspace(false)}>
          <div
            className="workspace-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workspace-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setNewWorkspace(false);
              if (e.key === "Tab") {
                const focusable = [
                  ...e.currentTarget.querySelectorAll<HTMLElement>(
                    "button:not(:disabled), input",
                  ),
                ];
                const first = focusable[0],
                  last = focusable[focusable.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last?.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close new workspace"
              onClick={() => setNewWorkspace(false)}
            >
              <X size={18} />
            </button>
            <span className="modal-icon">
              <Layers3 size={23} />
            </span>
            <h2 id="workspace-title">A fresh memory workspace.</h2>
            <p>
              Start an independent graph with its own conversations and history.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createWorkspace();
              }}
            >
              <label>
                Workspace name
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Research demo"
                  maxLength={100}
                />
              </label>
              <button
                className="primary-button"
                disabled={busy || !name.trim()}
              >
                Create workspace <ArrowRight size={15} />
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function PlayIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M6 3.5 12 8l-6 4.5v-9Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}
