import { useEffect, useMemo, useState } from 'react';
import type { AuditReport, Finding, ReviewedPage } from './types';

const API = import.meta.env.VITE_API_BASE || '';
const severityOrder = ['critical', 'high', 'medium', 'low', 'not_observed'];

export default function App() {
  const [mode, setMode] = useState<'url' | 'screenshot'>('url');
  const [url, setUrl] = useState('https://example.com');
  const [viewport, setViewport] = useState<'desktop' | 'mobile'>('desktop');
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [providerLabel, setProviderLabel] = useState('Checking model…');
  const [providerDetail, setProviderDetail] = useState('');

  useEffect(() => {
    let active = true;
    fetch(`${API}/api/provider`)
      .then(response => response.json())
      .then(info => {
        if (!active) return;
        if (info.ready) {
          setProviderLabel(info.label);
          setProviderDetail('');
        } else {
          setProviderLabel('Model not configured');
          setProviderDetail(info.detail || 'Model provider is not configured');
        }
      })
      .catch(() => { if (active) setProviderLabel('Model unavailable'); });
    return () => { active = false; };
  }, []);

  const filtered = useMemo(() => (report?.findings || []).filter(f => filter === 'all' || f.severity === filter), [report, filter]);

  async function runAudit() {
    setError(''); setReport(null); setBusy(true);
    try {
      let response: Response;
      if (mode === 'url') {
        response = await fetch(`${API}/api/audits/url`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, viewport }) });
      } else {
        if (!file) throw new Error('Choose a PNG or JPEG screenshot first.');
        const form = new FormData(); form.append('file', file);
        response = await fetch(`${API}/api/audits/screenshot`, { method: 'POST', body: form });
      }
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `Audit failed (${response.status})`);
      setReport(payload as AuditReport);
    } catch (e) { setError(e instanceof Error ? e.message : 'An unexpected error occurred.'); }
    finally { setBusy(false); }
  }

  function downloadJson() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const href = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = href; a.download = 'website-ux-audit.json'; a.click(); URL.revokeObjectURL(href);
  }

  const counts = (report?.findings || []).reduce<Record<string, number>>((acc, f) => { acc[f.severity] = (acc[f.severity] || 0) + 1; return acc; }, {});

  return <main className="shell">
    <header className="topbar"><div className="brand-mark">UX</div><div><div className="brand">Heuristic Lens</div><div className="brand-sub">Evidence-based website usability audit</div></div><span className="top-pill">{providerLabel}</span></header>
    <section className="hero"><div className="eyebrow"><span className="pulse"/> UX REVIEW WORKSPACE</div><h1>Find friction.<br/><em>Improve experiences.</em></h1><p className="hero-copy">Audit a website or screenshot against Jakob Nielsen’s 10 usability heuristics. Get evidence, severity, confidence, and practical recommendations.</p></section>
    <section className="panel input-panel">
      <div className="section-head"><div><span className="step">01</span><h2>Choose an audit source</h2></div><span className="muted small">AI-assisted heuristic review</span></div>
      <div className="mode-switch"><button className={mode === 'url' ? 'mode active' : 'mode'} onClick={() => setMode('url')}>↗ Website URL</button><button className={mode === 'screenshot' ? 'mode active' : 'mode'} onClick={() => setMode('screenshot')}>▧ Screenshot</button></div>
      {mode === 'url' ? <><label htmlFor="url">Website address</label><input id="url" type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://yourwebsite.com"/><div className="input-row"><div><label htmlFor="viewport">Viewport</label><select id="viewport" value={viewport} onChange={e => setViewport(e.target.value as 'desktop' | 'mobile')}><option value="desktop">Desktop · 1440 × 1000</option><option value="mobile">Mobile · 390 × 844</option></select></div><div className="hint-box">Only audit websites you’re authorized to inspect. A URL review covers the address you enter and up to two more pages on the same site.</div></div></> : <label className="dropzone"><input type="file" accept="image/png,image/jpeg" onChange={e => setFile(e.target.files?.[0] || null)}/><span className="upload-icon">↑</span><strong>{file ? file.name : 'Choose a screenshot'}</strong><span className="muted">PNG or JPEG · maximum 8 MB by default</span><span className="browse">Browse files</span></label>}
      {(error || providerDetail) && <div className="error">{error || providerDetail}</div>}
      <button className="primary" disabled={busy || (mode === 'url' && !url.trim()) || (mode === 'screenshot' && !file)} onClick={runAudit}>{busy ? <><span className="spinner"/> Analyzing evidence…</> : <>Run heuristic audit <span>→</span></>}</button>
      <div className="privacy-note">◇ Findings are AI-generated and should be reviewed by a UX practitioner. No finding is proof of a defect unless supported by the available evidence.</div>
    </section>

    {busy && <section className="panel loading-panel"><div className="spinner dark"/><div><strong>Reviewing the interface</strong><p className="muted">Capturing evidence and evaluating the 10 heuristics. This can take a little while.</p></div></section>}

    {report && <section className="results" aria-live="polite">
      <div className="results-title"><div><span className="step">02</span><h2>Audit report</h2><p className="muted">{report.page_title || report.source} · {report.viewport}</p></div><button className="secondary" onClick={downloadJson}>↓ Export JSON</button></div>
      <div className="summary-card"><div className="summary-top"><span className="eyebrow">EXECUTIVE SUMMARY</span><span className="model-label">{report.model}</span></div><p>{report.summary}</p><div className="metrics">{severityOrder.map(s => <button type="button" className={`metric ${filter === s ? 'on' : ''}`} key={s} onClick={() => setFilter(filter === s ? 'all' : s)}><span className={`dot ${s}`}/><strong>{counts[s] || 0}</strong><span>{s.replace('_', ' ')}</span></button>)}</div></div>
      <PageReview pages={report.pages || []} />
      <div className="findings-head"><div><h2>Heuristic findings</h2><p className="muted">Open a finding to read the evidence, impact, and what to change. Click a severity count to filter.</p></div><select aria-label="Filter findings" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All findings</option>{severityOrder.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}</select></div>
      <div className="finding-list">{filtered.map(f => <FindingCard key={f.heuristic_id} finding={f} pages={report.pages || []}/>)}</div>
      <div className="method-note"><strong>Methodology & limitations</strong><p>{report.methodology_note}</p><p>Confidence is an estimate of the assessment’s certainty, not a usability score. A static screenshot cannot prove unseen interaction behavior.</p></div>
    </section>}
    <footer><span>HEURISTIC LENS · STARTER EDITION</span><span>Based on Jakob Nielsen’s 10 usability heuristics</span></footer>
  </main>;
}

function PageReview({ pages }: { pages: ReviewedPage[] }) {
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const page = pages[active];
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) { if (event.key === 'Escape') setOpen(false); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  if (!page) return null;
  return <section className="page-review">
    <div className="findings-head"><div><h2>Reviewed screenshots</h2><p className="muted">{pages.length === 1 ? '1 page captured' : `${pages.length} pages captured`} · select a page, then open it for a closer look.</p></div></div>
    <div className="page-stage">
      <button type="button" className="shot-frame" onClick={() => setOpen(true)} aria-label={`Open screenshot of ${page.title || page.url}`}>
        <img src={page.image} alt={page.title || page.url} />
      </button>
      <div className="shot-meta">
        <span className="eyebrow">PAGE {String(active + 1).padStart(2, '0')}</span>
        <strong>{page.title || 'Untitled page'}</strong>
        {page.url.startsWith('http') ? <a href={page.url} target="_blank" rel="noreferrer">{page.url}</a> : <p>{page.url}</p>}
        <p className="muted">This is the screenshot the audit used. Click it to inspect the page.</p>
        {pages.length > 1 && <div className="shot-nav"><button type="button" onClick={() => setActive((active + pages.length - 1) % pages.length)}>Previous</button><button type="button" onClick={() => setActive((active + 1) % pages.length)}>Next</button></div>}
      </div>
    </div>
    {pages.length > 1 && <div className="shot-thumbs">{pages.map((item, index) => <button type="button" key={`${item.url}-${index}`} className={index === active ? 'thumb active' : 'thumb'} onClick={() => setActive(index)}><img src={item.image} alt="" /><span>{item.title || `Page ${index + 1}`}</span></button>)}</div>}
    {open && <div className="lightbox" role="dialog" aria-modal="true" aria-label="Reviewed screenshot" onClick={() => setOpen(false)}>
      <button type="button" className="lightbox-close" onClick={() => setOpen(false)}>Close</button>
      <img src={page.image} alt={page.title || page.url} onClick={event => event.stopPropagation()} />
      <p>{page.title || 'Untitled page'}{page.url.startsWith('http') ? ` · ${page.url}` : ''}</p>
    </div>}
  </section>;
}

function FindingCard({ finding: f, pages }: { finding: Finding; pages: ReviewedPage[] }) {
  const [open, setOpen] = useState(f.severity === 'critical' || f.severity === 'high');
  const [shot, setShot] = useState(0);
  const page = pages[shot];
  return <article className="finding"><button className="finding-toggle" onClick={() => setOpen(!open)} aria-expanded={open}><span className="heuristic-number">{String(f.heuristic_id).padStart(2, '0')}</span><span className="finding-main"><span className="heuristic-name">{f.heuristic_name}</span><strong>{f.title}</strong><span className="finding-status">{f.status.replaceAll('_', ' ')} · {f.evidence.length} evidence item{f.evidence.length === 1 ? '' : 's'}</span></span><span className={`severity ${f.severity}`}>{f.severity.replace('_', ' ')}</span><span className="chevron">{open ? '−' : '+'}</span></button>
    {open && <div className="finding-detail"><div className="detail-grid">{page && <figure className="finding-shot"><img src={page.image} alt="" />{pages.length > 1 && <div className="shot-nav">{pages.map((item, index) => <button type="button" key={`${item.url}-${index}`} className={index === shot ? 'active' : ''} onClick={() => setShot(index)}>{index + 1}</button>)}</div>}<figcaption>{page.title || page.url}</figcaption></figure>}<div><h4>Evidence</h4>{f.evidence.length ? <ul>{f.evidence.map((e, i) => <li key={i}><span className="evidence-type">{e.type}</span> {e.description}{e.location && <small>Location: {e.location}</small>}</li>)}</ul> : <p className="muted">No direct evidence was provided.</p>}<h4>User impact</h4><p>{f.user_impact || 'Not specified.'}</p><h4>Recommended improvement</h4><p>{f.recommendation || 'No recommendation available.'}</p></div></div><div className="confidence-row"><span>Assessment confidence</span><div className="confidence-track"><div style={{ width: `${Math.round(f.confidence * 100)}%` }}/></div><strong>{Math.round(f.confidence * 100)}%</strong></div>{f.limitations.length > 0 && <div className="limitations"><strong>Limitations:</strong> {f.limitations.join(' · ')}</div>}</div>}</article>;
}
