import { useMemo, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Legend, Cell } from 'recharts'
import { Play, Pause, ShieldCheck, ScanSearch, CheckCircle2, XCircle } from 'lucide-react'
import { api, when, num, short } from '../lib'
import { Page, Stat, Table, Badge, statusTone, Alert, Field, useAction, useLoad, Spinner, Mono, UnderTheHood, useAuth } from '../ui'

const C = { teal: '#14b8a6', ink: '#111a2e', gold: '#e0a82e', red: '#dc2626', sky: '#0284c7', gray: '#94a3b8' }
const ChartBox = ({ title, children, note, h = 260 }) => <div className="card"><h3 className="font-semibold">{title}</h3>{note && <p className="text-xs text-ink-900/55">{note}</p>}<div style={{ height: h }} className="mt-3">{children}</div></div>

export function RegDashboard() {
  const st = useLoad(() => api('/regulator/stats'), [], 10000)
  const ev = useLoad(() => api('/regulator/events?limit=300'), [], 10000)
  const an = useLoad(() => api('/regulator/anomalies'), [], 10000)
  const [reason, setReason] = useState('Under review'); const [msg, setMsg] = useState('')
  const set = useAction(async (id, active) => { const r = await api(`/regulator/institutions/${id}/status`, { method: 'POST', body: { active, reason } }); setMsg(`${r.institution} is now ${r.status}.`); st.reload() })
  const byAction = useMemo(() => { const m = {}; (ev.data || []).forEach((e) => { m[e.name] = (m[e.name] || 0) + 1 }); return Object.entries(m).map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n).slice(0, 8) }, [ev.data])
  const sev = useMemo(() => ['critical', 'high', 'medium'].map((s) => ({ s, n: (an.data || []).filter((a) => a.severity === s).length })), [an.data])
  if (st.loading) return <Spinner />
  const d = st.data
  return (
    <Page title="Dashboard" intro="The whole ledger at a glance. Updates every ten seconds.">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Institutions" value={num(d.institutions.length)} /><Stat label="Records" value={num(d.credentials)} sub={`${num(d.batches)} batches`} /><Stat label="Ledger events" value={num(d.ledger_events)} /><Stat label="Open alerts" value={num(d.open_anomalies)} tone={d.open_anomalies ? 'bad' : 'good'} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartBox title="What is happening on the ledger" note="Most recent 300 events, by action"><ResponsiveContainer><BarChart data={byAction} layout="vertical" margin={{ left: 40 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="n" fill={C.teal} radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></ChartBox>
        <ChartBox title="AI alerts by severity" note="All alerts raised so far"><ResponsiveContainer><BarChart data={sev}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="s" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="n" radius={[4, 4, 0, 0]}>{sev.map((x) => <Cell key={x.s} fill={x.s === 'critical' ? C.red : x.s === 'high' ? C.gold : C.sky} />)}</Bar></BarChart></ResponsiveContainer></ChartBox>
      </div>
      <section>
        <div className="mb-2 flex flex-wrap items-end justify-between gap-3"><h2 className="font-display text-xl font-semibold">Institutions</h2><div className="w-64"><Field label="Reason for a status change"><input className="input !py-1.5" aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} /></Field></div></div>
        {msg && <div className="mb-2"><Alert tone="ok">{msg}</Alert></div>}{set.error && <div className="mb-2"><Alert tone="error">{set.error}</Alert></div>}
        <Table rows={d.institutions} empty="No institutions." cols={[{ k: 'name', h: 'Institution' }, { k: 'status', h: 'Status', r: (x) => <Badge tone={statusTone(x.status)}>{x.status}</Badge> }, { k: 'issued', h: 'Issued' }, { k: 'revoked', h: 'Revoked' }, { k: 'anomalies', h: 'Alerts' },
          { k: 'a', h: '', r: (x) => x.status === 'active' ? <button className="btn-ghost !px-2 !py-1" onClick={() => set.run(x.id, false)} disabled={set.busy}>Suspend</button> : <button className="btn-primary !px-2 !py-1" onClick={() => set.run(x.id, true)} disabled={set.busy}>Reinstate</button> }]} />
      </section>
    </Page>
  )
}

export function RegAlerts() {
  const [live, setLive] = useState(true)
  const { data, loading, reload } = useLoad(() => api('/regulator/anomalies'), [], live ? 4000 : 0)
  const decide = useAction(async (id, d) => { await api(`/regulator/anomalies/${id}/${d}`, { method: 'POST' }); reload() })
  return (
    <Page title="AI alerts" intro="Every action is scored by an Isolation Forest the moment it happens. Medium alerts are for your eyes. A critical alert puts the institution on hold until you decide."
      actions={<button className="btn-ghost" onClick={() => setLive(!live)} aria-pressed={live}>{live ? <><Pause className="h-4 w-4" /> Live</> : <><Play className="h-4 w-4" /> Paused</>}</button>}>
      {decide.error && <Alert tone="error">{decide.error}</Alert>}
      {loading ? <Spinner /> : <Table rows={data} empty="No alerts. Quiet is good." cols={[
        { k: 'ts', h: 'When', r: (x) => when(x.ts) }, { k: 'severity', h: 'Severity', r: (x) => <Badge tone={statusTone(x.severity)}>{x.severity}</Badge> },
        { k: 'score', h: 'Score', r: (x) => <span className="font-mono text-xs">{x.score}</span> }, { k: 'actor', h: 'Actor', r: (x) => <Mono>{x.actor}</Mono> },
        { k: 'reasons', h: 'Why', r: (x) => <div className="max-w-sm text-xs">{x.reasons}{x.action && <div className="mt-1 font-medium text-amber-700">{x.action}</div>}</div> },
        { k: 'status', h: 'Decision', r: (x) => x.status === 'open' ? <span className="inline-flex gap-1"><button className="btn-ghost !px-2 !py-1" onClick={() => decide.run(x.id, 'confirmed')}>Confirm</button><button className="btn-ghost !px-2 !py-1" onClick={() => decide.run(x.id, 'dismissed')}>Dismiss</button></span> : <Badge tone={statusTone(x.status)}>{x.status}</Badge> }]} />}
    </Page>
  )
}

export function RegEvents() {
  const [live, setLive] = useState(true); const [src, setSrc] = useState('')
  const { data, loading } = useLoad(() => api('/regulator/events?limit=200'), [], live ? 4000 : 0)
  const rows = (data || []).filter((e) => !src || e.source === src)
  return (
    <Page title="Ledger events" intro="Every action the AI sees. “api” means it came through this platform. “ledger” means the watcher found it on the node directly, which is how a stolen key used outside the website would show up."
      actions={<div className="flex gap-2"><select className="input !w-40" aria-label="Source" value={src} onChange={(e) => setSrc(e.target.value)}><option value="">All sources</option><option value="api">api</option><option value="ledger">ledger</option></select><button className="btn-ghost" onClick={() => setLive(!live)}>{live ? <><Pause className="h-4 w-4" /> Live</> : <><Play className="h-4 w-4" /> Paused</>}</button></div>}>
      {loading ? <Spinner /> : <Table rows={rows} empty="No events yet." cols={[{ k: 'ts', h: 'When', r: (x) => when(x.ts) }, { k: 'name', h: 'Action', r: (x) => <code className="text-xs">{x.name}</code> }, { k: 'actor', h: 'Actor', r: (x) => <Mono>{x.actor}</Mono> }, { k: 'size', h: 'Records' },
        { k: 'ok', h: 'Result', r: (x) => x.success ? <Badge tone="green">ok</Badge> : <span title={x.error}><Badge tone="red">refused</Badge></span> }, { k: 'gas', h: 'Gas', r: (x) => num(x.gas) }, { k: 'source', h: 'Source', r: (x) => <Badge tone={x.source === 'ledger' ? 'amber' : 'gray'}>{x.source}</Badge> }]} />}
    </Page>
  )
}

function Confusion({ c }) {
  const cell = (label, v, good) => <div className={`rounded-lg p-3 text-center ${good ? 'bg-emerald-50' : 'bg-red-50'}`}><div className="font-display text-2xl font-semibold">{num(v)}</div><div className="text-xs text-ink-900/60">{label}</div></div>
  return <div className="grid grid-cols-2 gap-2" aria-label="Confusion matrix">{cell('caught (true positive)', c.TP, true)}{cell('false alarm', c.FP, false)}{cell('missed', c.FN, false)}{cell('correctly left alone', c.TN, true)}</div>
}

export function RegModel() {
  const ev = useLoad(() => api('/regulator/ai/evaluation'), [])
  const [hard, setHard] = useState(0)
  const ex = useLoad(() => api(`/regulator/ai/experiment?hard=${hard}`), [hard])
  return (
    <Page title="AI model" intro="What the monitor has been tested on, and how it did. All data here is synthetic. Real traffic will behave differently, so treat these as a baseline, not a promise.">
      <section className="card">
        <h2 className="font-display text-xl font-semibold">Behaviour monitor: four attack patterns</h2>
        <p className="mt-1 text-sm text-ink-900/65">Held-out normal days plus four attacks. Features: burst rate, hourly and daily volume, off-hours, failures, revocation share, batch size, unauthorized attempts, gap between actions.</p>
        {ev.loading ? <Spinner label="Running the evaluation" /> : ev.error ? <Alert tone="error">{ev.error}</Alert> : (<>
          <div className="mt-4 grid gap-4 sm:grid-cols-3"><Stat label="Attack patterns caught" value={`${ev.data.detected} of ${ev.data.scenarios}`} tone="good" /><Stat label="False alarms" value={`${(ev.data.false_alarm_rate * 100).toFixed(2)}%`} sub={`${ev.data.false_alarms} of ${num(ev.data.normal_events)} normal events`} /><Stat label="Method" value="Isolation Forest" sub="plus z-score deviation and rules" /></div>
          <div className="mt-4"><Table rows={Object.entries(ev.data.attacks).map(([k, v]) => ({ id: k, k, ...v }))} cols={[{ k: 'k', h: 'Attack', r: (x) => x.k.replace(/_/g, ' ') }, { k: 'worst', h: 'Worst severity', r: (x) => <Badge tone={statusTone(x.worst)}>{x.worst}</Badge> }, { k: 'detected_at_event', h: 'Flagged at event' }, { k: 'events', h: 'Of events' }]} /></div>
        </>)}
      </section>
      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-display text-xl font-semibold">Proposal experiment: 10,000 transactions</h2>
          <div role="group" aria-label="Variant" className="inline-flex rounded-xl bg-ink-900/8 p-1">{[[0, 'As specified'], [1, 'Harder data']].map(([v, l]) => <button key={v} aria-pressed={hard === v} onClick={() => setHard(v)} className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${hard === v ? 'bg-white shadow' : 'text-ink-900/60'}`}>{l}</button>)}</div></div>
        <p className="mt-1 text-sm text-ink-900/65">9,500 normal, 250 insider and 250 script transactions, 70/30 split. Features: temporal fraction, invocation velocity, payload entropy. The harder variant blurs the boundaries so the numbers are not flattering by construction.</p>
        {ex.loading ? <Spinner label="Training" /> : ex.error ? <Alert tone="error">{ex.error}</Alert> : (
          <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_1fr]"><div className="grid grid-cols-3 gap-3"><Stat label="Precision" value={Number(ex.data.precision).toFixed(3)} /><Stat label="Recall" value={Number(ex.data.recall).toFixed(3)} /><Stat label="F1" value={Number(ex.data.f1).toFixed(3)} tone="good" /><div className="col-span-3 text-xs text-ink-900/55">Trained on {num(ex.data.train)}, tested on {num(ex.data.test)}.</div></div><Confusion c={ex.data.confusion} /></div>)}
      </section>
    </Page>
  )
}

export function RegCompliance() {
  const [audit, setAudit] = useState(null); const [priv, setPriv] = useState(null)
  const a = useAction(async () => setAudit(await api('/system/audit/verify')))
  const p = useAction(async () => setPriv(await api('/system/privacy/chain-check')))
  const rows = [['Data minimisation', 'Only salted fingerprints on chain, no personal fields'], ['Consent and purpose', 'Per record, per employer, with expiry, recorded on chain'], ['Access and portability', 'Student export of records, proofs and consents'], ['Erasure', 'Record key destroyed; encrypted copy unreadable'], ['Integrity', 'Merkle proofs, content IDs, hash-chained audit log'], ['Storage location', 'Region is a setting on the platform'], ['Accountability', 'Audit log of issuing, consent, disclosure, erasure']]
  return (
    <Page title="Audit and privacy" intro="Two checks you can run any time, and how the design maps to data protection principles (Kenya Data Protection Act, 2019 and GDPR). This is a technical design, not legal advice.">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card"><h2 className="font-display text-xl font-semibold">Is the audit trail intact?</h2><p className="mt-1 text-sm text-ink-900/65">Each entry carries the hash of the one before it. Changing any past entry breaks the chain.</p>
          <button className="btn-dark mt-3" onClick={() => a.run()} disabled={a.busy}><ShieldCheck className="h-4 w-4" /> Verify audit chain</button>{a.error && <div className="mt-3"><Alert tone="error">{a.error}</Alert></div>}
          {audit && <div className="mt-3"><Alert tone={audit.intact ? 'ok' : 'error'}>{audit.intact ? `Intact. ${audit.entries} entries, each linked to the last.` : `Broken at entry ${audit.broken_at}. Someone changed history.`}</Alert></div>}</section>
        <section className="card"><h2 className="font-display text-xl font-semibold">Is any personal data on the chain?</h2><p className="mt-1 text-sm text-ink-900/65">Searches everything the contract ever logged for every stored name and email.</p>
          <button className="btn-dark mt-3" onClick={() => p.run()} disabled={p.busy}><ScanSearch className="h-4 w-4" /> Scan the chain</button>{p.error && <div className="mt-3"><Alert tone="error">{p.error}</Alert></div>}
          {priv && <div className="mt-3"><Alert tone={priv.personal_data_found_on_chain ? 'error' : 'ok'}>{priv.personal_data_found_on_chain ? `Found: ${priv.hits.join(', ')}` : 'None found. The ledger holds only fingerprints, roles and consent entries.'}</Alert></div>}</section>
      </div>
      <Table rows={rows.map(([a, b], id) => ({ id, a, b }))} cols={[{ k: 'a', h: 'Principle' }, { k: 'b', h: 'What Alma does' }]} />
    </Page>
  )
}

export function RegPerformance() {
  const { data: b, loading, error } = useLoad(() => api('/system/benchmark', { token: null }), [])
  if (loading) return <Spinner />
  if (error) return <Page title="Performance"><Alert tone="warn">{error}</Alert></Page>
  const gas = [{ name: 'One by one', gas: b.gas.single_issue }, { name: 'In a batch of 1,000', gas: b.gas.batch_1000_per_record }]
  const merkle = Object.entries(b.merkle).map(([n, m]) => ({ records: Number(n), hashes: m.proof_hashes, build: m.build_s }))
  const rows = (k) => (b[k]?.rows || []).map((r) => ({ c: r.concurrent, p50: r.median_ms, p95: r.p95_ms, tps: r.tps }))
  const noc = rows('concurrency_nocache'), cac = rows('concurrency_cache5s')
  const conc = noc.map((r, i) => ({ concurrent: r.c, 'no cache': r.p95, 'cached': cac[i]?.p95 }))
  const tput = noc.map((r, i) => ({ concurrent: r.c, 'no cache': r.tps, 'cached': cac[i]?.tps }))
  const v = b.verify
  return (
    <Page title="Performance" intro={`Measured on: ${b.chain}. A simulated chain answers instantly, so latency here is the software around the chain, not block time. Real networks add confirmation time to issuing and revoking, never to reading.`}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Gas, one record alone" value={num(b.gas.single_issue)} /><Stat label="Gas per record, batch of 1,000" value={num(b.gas.batch_1000_per_record)} tone="good" sub={`${Math.round(b.gas.single_issue / b.gas.batch_1000_per_record)}× cheaper`} />
        <Stat label="Verify, median" value={`${v.hybrid_p50_ms} ms`} sub={`${v.cached_p50_ms} ms with status cache`} /><Stat label="Plain database lookup" value={`${v.central_p50_ms} ms`} sub="no proof, no integrity check" />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartBox title="Gas per record" note="Lower is better. One ledger transaction covers the whole batch."><ResponsiveContainer><BarChart data={gas}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" /><YAxis /><Tooltip formatter={(x) => num(x)} /><Bar dataKey="gas" radius={[4, 4, 0, 0]}><Cell fill={C.gray} /><Cell fill={C.teal} /></Bar></BarChart></ResponsiveContainer></ChartBox>
        <ChartBox title="Proof size as records grow" note="Hashes needed to prove one record. It grows with the logarithm."><ResponsiveContainer><LineChart data={merkle}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="records" scale="log" type="number" domain={['auto', 'auto']} tickFormatter={(x) => num(x)} /><YAxis allowDecimals={false} /><Tooltip /><Line dataKey="hashes" stroke={C.teal} strokeWidth={2.5} dot /></LineChart></ResponsiveContainer></ChartBox>
        {conc.length > 0 && <ChartBox title="Verify latency under load" note="95th percentile in ms by simultaneous requests (single process, simulated chain)."><ResponsiveContainer><LineChart data={conc}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="concurrent" /><YAxis /><Tooltip /><Legend /><Line dataKey="no cache" stroke={C.red} strokeWidth={2} /><Line dataKey="cached" stroke={C.teal} strokeWidth={2} /></LineChart></ResponsiveContainer></ChartBox>}
        {tput.length > 0 && <ChartBox title="Verifications per second" note="Higher is better."><ResponsiveContainer><LineChart data={tput}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="concurrent" /><YAxis /><Tooltip /><Legend /><Line dataKey="no cache" stroke={C.red} strokeWidth={2} /><Line dataKey="cached" stroke={C.teal} strokeWidth={2} /></LineChart></ResponsiveContainer></ChartBox>}
      </div>
      <section><h2 className="mb-2 font-display text-xl font-semibold">Cost for 10,000 records</h2>
        <Table rows={b.cost_per_10000_records.rows.map((r, id) => ({ id, ...r }))} cols={[{ k: 'network', h: 'Assumed network' }, { k: 'gas_price_gwei', h: 'Gas price (gwei)' }, { k: 'one_tx_each_usd', h: 'One transaction each', r: (x) => `$${num(x.one_tx_each_usd)}` }, { k: 'one_batch_usd', h: 'Batches of 1,000', r: (x) => `$${num(x.one_batch_usd)}` }]} />
        <p className="mt-2 text-xs text-ink-900/55">Gas is measured. Prices are assumptions ({b.cost_per_10000_records.assumed_coin_usd} USD per coin); replace them with current values before quoting any figure.</p></section>
      <section><h2 className="mb-2 font-display text-xl font-semibold">Gas by function</h2>
        <Table rows={Object.entries(b.gas_table).map(([k, g], id) => ({ id, k, ...g }))} cols={[{ k: 'k', h: 'Function' }, { k: 'standard', h: 'Standard compile', r: (x) => num(x.standard) }, { k: 'optimized', h: 'Optimized', r: (x) => num(x.optimized) }]} /></section>
      <Alert tone="warn">The design scales out because the API keeps no state, one transaction anchors thousands of records, and reads can be cached. These numbers come from one process on a simulated chain, so they show the software, not the limit. Measure against a real node with several API copies before quoting capacity.</Alert>
    </Page>
  )
}
