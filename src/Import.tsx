import { useState } from 'react';
import { ArrowRight, Upload, X } from 'lucide-react';
import { api } from './api';

export function ImportWorkspace({ onClose, onImported, onError }: { onClose: () => void; onImported: (id: string) => void; onError: (s: string) => void }) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [filename, setFilename] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  async function select(file?: File) {
    if (!file) return;
    try {
      if (file.size > 7.5 * 1024 * 1024) throw new Error('Choose a workspace export smaller than 7.5 MB.');
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
      if (parsed.format !== 'amnesia.workspace' || parsed.schema_version !== 2) throw new Error('Choose an Amnesia version 2 workspace export.');
      setPayload(parsed); setFilename(file.name); setName(`${(parsed.workspace as { name: string }).name} (imported)`);
    } catch (e) { setPayload(null); onError((e as Error).message); }
  }
  async function restore() { if (!payload) return; setBusy(true); try { const result = await api<{ id: string }>('import', { workspace: payload, name }); onImported(result.id); onClose(); } catch (e) { onError((e as Error).message); } finally { setBusy(false); } }
  return <div className="modal-scrim" onClick={onClose}><div className="workspace-modal" role="dialog" aria-modal="true" aria-label="Import workspace" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') onClose(); if (e.key === 'Tab') { const controls = [...e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input')]; const first = controls[0], last = controls.at(-1); if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); } } }}><button className="modal-close icon-button" aria-label="Close import workspace" onClick={onClose}><X size={18}/></button><span className="modal-icon"><Upload size={22}/></span><h2>Bring a memory workspace back.</h2><p>Restore graph, sessions, sources, aliases, and lifecycle history into a new workspace.</p><label className="import-box">Choose an exported workspace JSON<input autoFocus type="file" accept="application/json,.json" aria-label="Workspace export file" onChange={e => select(e.target.files?.[0])}/></label>{payload && <><p>{filename} · {(payload.facts as unknown[]).length} assertions · {(payload.events as unknown[]).length} events</p><label>New workspace name<input value={name} onChange={e => setName(e.target.value)} maxLength={100}/></label></>}<button className="primary-button" disabled={!payload || busy || !name.trim()} onClick={restore}>{busy ? 'Restoring…' : 'Import as a new workspace'}<ArrowRight size={14}/></button></div></div>;
}
