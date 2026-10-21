import { useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, ArrowLeft, ArrowRight, Check, CheckCheck, ExternalLink, Presentation, RotateCw, ShieldCheck } from 'lucide-react';
import { api } from './api';
import { Graph } from './Graph';
import type { EngineConfig } from './Engine';
import type { Evaluation, Fact, QueryResult, State } from './types';
import { methods, pct } from './types';
import { createReviewWriter, createReviewConfirmation } from './reviewProgress';

type ReviewMeta = { engine: EngineConfig; reports: { policy: Evaluation | null; live_ai: Evaluation | null }; report_available: boolean };
const stages = ['Question', 'Remember', 'Update', 'Retrieve', 'Preserve', 'Clarify', 'Evaluate'];
const copy = [
  ['Can an assistant remember what is true now?', 'Amnesia maintains evolving conversational facts with time, evidence, and explicit lifecycle state. This walkthrough executes the real memory pipeline in a new workspace.'],
  ['A conversation becomes a graph.', 'The model extracts atomic facts from ordinary prose. Each assertion stores its source, observation time, validity, confidence, and entity/relation scope.'],
  ['Facts change. Evidence stays.', 'A relocation and preference change retire only the matching current facts. Earlier assertions remain visible as history with links to their replacements.'],
  ['Ask across sessions.', 'The same question is answered from hybrid memory, dense-vector retrieval, and raw conversation context. Every answer below comes from an actual execution. This demonstration uses a top-1 vector budget to stress stale retrieval.'],
  ['Compatible facts remain compatible.', 'Employer, project, and beverage preference are different scopes. Adding them preserves the home and programming-language preference.'],
  ['Uncertainty should remain visible.', 'A speculative move is retained as an unresolved conflict. The agent asks for clarification instead of inventing certainty. A user confirmation resolves only this scoped conflict and preserves the audit trail.'],
  ['Show the measurements, including failures.', 'The policy suite isolates reconciliation with gold assertions. The live suite measures extraction, dense/graph retrieval, and actual LLM answers against curated annotations. These are internal research results, not claims about all conversations.'],
];
const inputs: Record<number, string> = { 1: 'I make my home in Hyderabad. Python is my preferred programming language.', 2: "I've relocated to Chennai. I now prefer Rust for programming.", 4: 'I work at Meridian. I lead Project Atlas. Tea is my favourite drink.', 5: "I'm not certain, but I might be living in Pune now. Please don't treat it as a confirmed move." };

export function Review({ onError, openWorkspace }: { onError: (s: string) => void; openWorkspace: (id: string) => void }) {
  const [meta, setMeta] = useState<ReviewMeta | null>(null);
  const [step, setStep] = useState(0);
  const [snapshots, setSnapshots] = useState<Record<number, State>>({});
  const [wid, setWid] = useState('');
  const [sid, setSid] = useState('');
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(inputs[1]);
  const [comparisons, setComparisons] = useState<QueryResult[]>([]);
  const [uncertain, setUncertain] = useState<QueryResult | null>(null);
  const [selected, setSelected] = useState<Fact | null>(null);
  const writer = useRef(createReviewWriter(api));
  const confirmation = useRef(createReviewConfirmation());
  const comparisonResults = useRef(new Map<string, QueryResult>());
  async function loadMeta() { try { setMeta(await api<ReviewMeta>('review')); } catch (e) { onError((e as Error).message); } }
  useEffect(() => { void loadMeta(); }, []);
  useEffect(() => { setDraft(inputs[step + 1] || ''); setSelected(null); }, [step]);
  const state = snapshots[step];
  async function advance() {
    const next = step + 1;
    if (next > 6 || busy) return;
    if (snapshots[next]) { setStep(next); return; }
    setBusy(true);
    try {
      let workspaceId = wid, sessionId = sid;
      if (!workspaceId) {
        workspaceId = (await api<{ id: string }>('workspaces', { name: `Final review · ${new Date().toLocaleDateString()}` })).id;
        setWid(workspaceId);
      }
      if (!sessionId) {
        const initial = await api<State>(`state?workspace_id=${workspaceId}`);
        sessionId = initial.sessions[0].id;
        setWid(workspaceId); setSid(sessionId);
      }
      if (inputs[next]) {
        const receipt = await writer.current.write(next, workspaceId, sessionId, draft || inputs[next]);
        sessionId = receipt.session_id;
        setSid(sessionId);
      }
      if (next === 3) {
        const results: QueryResult[] = [];
        for (const method of ['hybrid', 'vector', 'context']) {
          let result = comparisonResults.current.get(method);
          if (!result) {
            result = await api<QueryResult>('query', { workspace_id: workspaceId, question: 'Where do I live now?', method, k: method === 'vector' ? 1 : 5 });
            comparisonResults.current.set(method, result);
          }
          results.push(result);
        }
        setComparisons(results);
      }
      if (next === 5) setUncertain(await api<QueryResult>('query', { workspace_id: workspaceId, question: 'Where do I live now?', method: 'hybrid' }));
      if (next === 6) await loadMeta();
      const current = await api<State>(`state?workspace_id=${workspaceId}`);
      setSnapshots(previous => ({ ...previous, [next]: current })); setStep(next);
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  }
  async function confirm() {
    const fact = state?.facts.find(f => f.value === 'Chennai' && f.relation === 'lives_in' && f.effective_status === 'unresolved');
    if (!fact && !confirmation.current.isSaved()) return;
    setBusy(true);
    try {
      await confirmation.current.run(
        () => api('conflicts/resolve', { workspace_id: wid, session_id: sid, fact_id: fact!.id, evidence: 'Confirmed: my permanent home is Chennai. The possible move to Pune is not current.' }),
        async () => {
          setUncertain(null);
          const current = await api<State>(`state?workspace_id=${wid}`);
          setSnapshots(s => ({ ...s, [step]: current }));
          setUncertain(await api<QueryResult>('query', { workspace_id: wid, question: 'Where do I live now?', method: 'hybrid' }));
        },
      );
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  }
  const report = meta?.reports.live_ai;
  return <>
    <div className="page-intro"><div><span className="eyebrow">ABHILAKSH CHAUHAN · VIT · FINAL REVIEW</span><h1>Amnesia, in seven steps.</h1><p>An evolving knowledge graph agent for long-term AI memory.</p></div><span className="outline-chip"><Presentation size={14}/> Presentation mode</span></div>
    <div className="review-readiness"><span><span className={meta?.engine.ready ? 'live-dot' : 'live-dot offline'}/>{meta?.engine.ready ? `${meta.engine.provider} · ${meta.engine.chat_model}` : 'Configure your AI engine before starting the live demo.'}</span><button className="text-button" onClick={loadMeta}><RotateCw size={12}/> Refresh readiness</button>{wid && <button className="text-button" onClick={() => openWorkspace(wid)}>Open this workspace in the studio <ExternalLink size={12}/></button>}</div>
    <div className="review-steps">{stages.map((name, i) => <div key={name} className={`review-step ${i === step ? 'current' : i < step ? 'done' : ''}`}><span>{i < step ? <Check size={11}/> : i + 1}</span>{name}</div>)}</div>
    {step === 0 ? <div className="review-hero"><div><span className="eyebrow">THE RESEARCH QUESTION</span><h1>Can long-term memory keep up when facts change?</h1><p>“I live in Hyderabad” is still relevant after “I moved to Chennai.” Semantic similarity alone cannot tell us which belief is current.</p><div className="review-note">This is a live walkthrough. Starting creates a separate review workspace and executes model calls; your existing workspaces remain available.</div></div><div><button className="primary-button" onClick={advance} disabled={busy || !meta?.engine.ready}>{busy ? <RotateCw size={15} className="spin"/> : <ArrowRight size={15}/>} Start live review</button><a className="secondary-button" href="/api/report" download aria-disabled={!meta?.report_available} onClick={e => { if (!meta?.report_available) e.preventDefault(); }}><ArrowDownToLine size={14}/> Final report PDF</a></div></div> : <>
      <div className="review-content"><div>{state && <Graph state={state} onSelect={setSelected} selected={selected?.id}/>}</div><section className="panel review-explanation"><span className="eyebrow">STEP {step + 1} OF 7 · {stages[step].toUpperCase()}</span><h2 style={{ marginTop: 13 }}>{copy[step][0]}</h2><p>{copy[step][1]}</p>{state && <div className="review-note">{state.facts.filter(f => f.effective_status === 'active').length} current · {state.facts.filter(f => f.effective_status === 'superseded').length} superseded · {state.facts.filter(f => f.effective_status === 'unresolved').length} unresolved · {state.sessions.length} sessions</div>}{draft && <><label className="field-note" htmlFor="review-next-input">Next statement · you can edit this before advancing</label><textarea id="review-next-input" className="review-input" value={draft} disabled={busy || writer.current.isCommitted(step + 1)} onChange={e => setDraft(e.target.value)}/></>}{selected && <div className="review-evidence"><strong>{selected.value}</strong><p>“{selected.evidence}”</p><small>{selected.effective_status} · {selected.scope || selected.relation} · {new Date(selected.observed_at).toLocaleString()}</small></div>}{step === 5 && <><div className="review-evidence">{uncertain?.answer || (confirmation.current.isSaved() ? "Confirmation saved. The updated model answer is pending; retry below if needed." : "Waiting for clarification.")}</div><button className="secondary-button" style={{ marginTop: 14 }} onClick={confirm} disabled={busy || (!confirmation.current.isSaved() && !state?.facts.some(f => f.value === 'Chennai' && f.effective_status === 'unresolved'))}><ShieldCheck size={14}/> {confirmation.current.isSaved() ? "Refresh confirmed answer" : "Confirm Chennai and resolve"}</button></>}
      <div className="review-actions"><button className="secondary-button" disabled={busy || step === 0} onClick={() => setStep(s => s - 1)}><ArrowLeft size={14}/> Previous</button>{step < 6 ? <button className="primary-button" disabled={busy} onClick={advance}>{busy ? <RotateCw size={14} className="spin"/> : <ArrowRight size={14}/>} {busy ? 'Running the real pipeline…' : 'Next step'}</button> : <a className="primary-button" href="/api/report" download><ArrowDownToLine size={14}/> Download final report</a>}</div>{busy && <div className="review-busy"><RotateCw size={12} className="spin"/> Waiting for model inference. The graph updates after validation and commit.</div>}</section></div>
      {step === 3 && <div className="comparison-cards">{comparisons.map(result => <section key={result.method} className="panel comparison-card"><span>{methods[result.method]} {result.method === 'vector' ? '· top 1' : ''}</span><h3>{result.answer}</h3><small>{result.used_ids.length} evidence links · {(result.latency_ms / 1000).toFixed(2)}s · {result.answer_engine}</small></section>)}</div>}
      {step === 6 && <section className="panel review-results"><div className="panel-heading"><div><h2>Completed live AI measurements</h2><p>{report ? `${report.count} curated questions · ${report.engine?.provider} · ${report.engine?.chat_model}` : 'Run the live suite in Experiments to populate this table.'}</p></div></div>{report && <div className="table-scroll"><table className="results-table"><thead><tr><th>Method</th><th>QA accuracy</th><th>Stale error rate</th><th>Mean latency</th></tr></thead><tbody>{Object.entries(report.metrics).map(([method, metric]) => <tr key={method} className={method === 'hybrid' ? 'highlight-row' : ''}><td>{methods[method]}</td><td>{pct(metric.answer_accuracy)}</td><td>{pct(metric.smer)}</td><td>{(metric.mean_latency_ms / 1000).toFixed(2)}s</td></tr>)}</tbody></table></div>}</section>}
    </>}
    <div className="requirements-grid">{[['Structured AI extraction', 'Typed facts, source quotations, confidence, validity, and entities.'], ['Temporal graph and provenance', 'Current state, history, duplicate evidence, scoped updates, and aliases.'], ['Conservative reconciliation', 'Six labels, unresolved conflicts, explicit user confirmation, and separate preference scopes.'], ['Hybrid and graph retrieval', 'Dense cosine similarity, personalized PageRank, temporal validity, and staleness penalties.'], ['Reproducible evaluation', 'Gold-input policy cases, live AI baselines, ablations, metrics, and retained failures.'], ['A complete local application', 'Studio, ledger, backup import/export, engine settings, review mode, and report.']].map(([title, description]) => <div className="requirement" key={title}><h3><CheckCheck size={14}/>{title}</h3><p>{description}</p></div>)}</div>
  </>;
}
