import { useEffect, useState } from 'react';
import { Check, Cpu, KeyRound, RotateCw, ShieldCheck, Wifi } from 'lucide-react';
import { api } from './api';

export type EngineConfig = { provider: 'codex' | 'openai' | 'ollama' | 'offline'; chat_model: string; embedding_model: string; ollama_url: string; reconciliation: string; ready: boolean; message: string; key_configured?: boolean; codex_authenticated?: boolean; cli_version?: string; models: { name: string; size: number }[] };

export function Engine({ onError, onSaved }: { onError: (s: string) => void; onSaved: () => void }) {
  const [config, setConfig] = useState<EngineConfig | null>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  async function refresh() { try { setConfig(await api<EngineConfig>('engine')); } catch (e) { onError((e as Error).message); } }
  useEffect(() => { void refresh(); }, []);
  async function save(test = false) {
    if (!config) return;
    setBusy(true); setNotice('');
    try {
      if (key) { await api('engine/credentials', { api_key: key }); setKey(''); }
      const updated = await api<EngineConfig>('engine', { provider: config.provider, chat_model: config.chat_model, embedding_model: config.embedding_model, ollama_url: config.ollama_url, reconciliation: config.reconciliation });
      setConfig(updated); onSaved();
      if (test) { const checked = await api<{ message: string; dimensions?: number; latency_ms: number }>('engine/test', {}); setNotice(`${checked.message}${checked.dimensions ? ` ${checked.dimensions}-dimension vectors; ${(checked.latency_ms / 1000).toFixed(1)}s.` : ''}`); }
      else setNotice('Engine settings saved. New conversations and queries use this configuration.');
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  }
  return <>
    <div className="page-intro"><div><span className="eyebrow">THE INTELLIGENCE BEHIND THE MEMORY</span><h1>Connect your AI engine.</h1><p>Choose how conversations become knowledge and how memories become answers.</p></div><span className="outline-chip"><Cpu size={14}/> Live inference</span></div>
    {!config ? <p className="empty-copy">Checking engine configuration…</p> : <div className="engine-grid"><section className="panel engine-form"><h2>Model configuration</h2><label>Provider<select aria-label="AI provider" value={config.provider} onChange={e => { const provider = e.target.value as EngineConfig['provider']; setConfig({ ...config, provider, chat_model: provider === 'codex' ? 'gpt-5.6-sol' : provider === 'ollama' ? 'qwen3.5:9b' : 'gpt-4.1-mini', embedding_model: provider === 'codex' || provider === 'ollama' ? 'nomic-embed-text:latest' : 'text-embedding-3-small' }); }}><option value="codex">Codex · ChatGPT login</option><option value="openai">OpenAI API</option><option value="ollama">Local AI · Ollama</option><option value="offline">Offline rules · regression only</option></select></label>
      {config.provider !== 'offline' && <><label>Language model<input aria-label="Language model" value={config.chat_model} onChange={e => setConfig({ ...config, chat_model: e.target.value })}/></label><label>Embedding model<input aria-label="Embedding model" value={config.embedding_model} onChange={e => setConfig({ ...config, embedding_model: e.target.value })}/></label></>}
      {config.provider === 'openai' && <div className="key-entry"><label><span><KeyRound size={14}/> OpenAI API key {config.key_configured && <small>Key already configured</small>}</span><input aria-label="OpenAI API key" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder={config.key_configured ? 'Enter a new key to replace it' : 'Paste your API key here'}/></label><p>Stored only on this Mac with owner-only file permissions. The key is never returned to the browser or included in workspace exports.</p></div>}
      {config.provider === 'codex' && <div className="key-entry"><ShieldCheck size={18}/><h3 style={{ marginTop: 8 }}>Use your existing Codex login.</h3><p>{config.codex_authenticated ? `Signed in with ChatGPT · ${config.cli_version || 'Codex CLI'}` : 'Run codex login in a terminal, choose Sign in with ChatGPT, then refresh status.'}</p><p>Fact extraction and answers use the official Codex CLI and your plan usage. Dense embeddings run locally through Nomic. Amnesia never reads or copies Codex tokens, and does not need an API key in this mode.</p></div>}
      {(config.provider === 'ollama' || config.provider === 'codex') && <><label>{config.provider === 'codex' ? 'Local embedding endpoint' : 'Local model endpoint'}<input aria-label="Local model endpoint" value={config.ollama_url} onChange={e => setConfig({ ...config, ollama_url: e.target.value })}/></label><p className="field-note">The launcher uses port 11435 for the local models. Codex mode needs the installed Nomic embedding model; Ollama mode also needs a local language model.</p></>}
      <div className="engine-actions"><button className="secondary-button" disabled={busy} onClick={() => save()}>Save configuration</button><button className="primary-button" disabled={busy} onClick={() => save(true)}>{busy ? <RotateCw size={14} className="spin"/> : <Wifi size={14}/>} {busy ? 'Checking inference…' : 'Save & test engine'}</button></div>
      {notice && <div className="success-notice" role="status"><Check size={15}/>{notice}</div>}
    </section><div><section className="panel engine-status"><span className="eyebrow">CONNECTION STATUS</span><h2><span className={config.ready ? 'live-dot' : 'live-dot offline'}/>{config.ready ? 'Configuration ready' : 'Setup needed'}</h2><p>{config.message}</p><button className="text-button" disabled={busy} onClick={refresh}><RotateCw size={13}/> Refresh status</button></section><section className="panel engine-details"><ShieldCheck size={22}/><h2>What runs where?</h2><p><strong>Codex login:</strong> extraction and answers run through your signed-in Codex CLI. Text is sent to OpenAI; embeddings and the persistent graph stay local. Calls consume your Codex plan usage.</p><p><strong>OpenAI API:</strong> extraction, embeddings, and answers run through a separately configured API account.</p><p><strong>Local AI:</strong> the complete pipeline runs through installed Ollama models without internet after setup.</p><p><strong>Offline rules:</strong> a bounded fallback for regression tests, labeled explicitly.</p><p>Reconciliation applies conservative entity/relation/scope rules in every mode. Changing providers does not erase memories. Codex requests run in an ephemeral read-only directory with command, browser, app, and delegation tools disabled.</p></section></div></div>}
  </>;
}
