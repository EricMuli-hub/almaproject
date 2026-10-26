import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { UserPlus, Upload, FileDown, Zap, Ban, ShieldCheck, ShieldX } from 'lucide-react'
import { api, short, when, num, shareLink, download, chainDetails } from '../lib'
import { Page, Stat, Table, Badge, statusTone, Alert, Field, useAction, useLoad, Spinner, UnderTheHood, Mono, CopyButton, useAuth } from '../ui'

const TYPES = ['Degree certificate', 'Diploma', 'Transcript', 'Certificate of completion', 'School leaving certificate', 'Other']

export function InstOverview() {
  const { data, loading, reload } = useLoad(() => api('/institution/overview'), [], 8000)
  const flush = useAction(async () => { await api('/institution/queue/flush', { method: 'POST' }); reload() })
  if (loading) return <Spinner />
  const d = data
  return (
    <Page title={d.name} intro="What your institution has issued, and what is waiting to be anchored.">
      {d.status !== 'active' && <Alert tone="warn"><strong>Issuing is paused.</strong> Your institution is {d.status}{d.status === 'held' ? ': the AI monitor saw unusual activity and a regulator must review it.' : ' by a regulator.'} Existing records stay valid unless revoked.</Alert>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Issued" value={num(d.issued)} tone="good" /><Stat label="Waiting" value={num(d.queued)} sub="queued for the next batch" /><Stat label="Revoked" value={num(d.revoked)} /><Stat label="Students" value={num(d.students)} />
      </div>
      {d.queued > 0 && <Alert tone="info"><div className="flex flex-wrap items-center justify-between gap-3"><span>{d.queued} records are queued. Anchoring them together costs one ledger transaction.</span><button className="btn-dark" onClick={() => flush.run()} disabled={flush.busy}><Zap className="h-4 w-4" /> Anchor now</button></div></Alert>}
      <section><h2 className="mb-2 font-display text-xl font-semibold">Latest anchors</h2>
        <Table rows={d.recent_anchors} empty="Nothing anchored yet. Issue a record to begin." cols={[{ k: 'at', h: 'When', r: (x) => when(x.at) }, { k: 'count', h: 'Records' }, { k: 'gas', h: 'Gas', r: (x) => num(x.gas) }, { k: 'root', h: 'Merkle root', r: (x) => <Mono>{x.root}</Mono> }]} /></section>
    </Page>
  )
}

export function InstStudents() {
  const { data, loading, reload } = useLoad(() => api('/institution/students'), [])
  const [f, setF] = useState({ email: '', name: '' }); const [last, setLast] = useState(null)
  const add = useAction(async () => { const r = await api('/institution/students', { method: 'POST', body: f }); setLast({ ...f, ...r }); setF({ email: '', name: '' }); reload() })
  return (
    <Page title="Students" intro="Students can only sign up if your institution registered them first. Give each one their invitation code.">
      <form className="card grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); add.run() }}>
        <Field label="Full name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
        <Field label="Email"><input type="email" className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></Field>
        <button className="btn-primary" disabled={add.busy}><UserPlus className="h-4 w-4" /> Register student</button>
      </form>
      {add.error && <Alert tone="error">{add.error}</Alert>}
      {last && <Alert tone="ok"><div>Registered {last.name}. Invitation code: <Mono n={30}>{last.invite_code}</Mono> <CopyButton text={last.invite_code} /></div></Alert>}
      {loading ? <Spinner /> : <Table rows={data} empty="No students yet." cols={[{ k: 'name', h: 'Name' }, { k: 'email', h: 'Email' }, { k: 's', h: 'Account', r: (x) => <Badge tone={statusTone(x.status)}>{x.status}</Badge> }, { k: 'c', h: 'Invitation code', r: (x) => x.invite_code ? <span className="inline-flex items-center gap-1"><Mono n={30}>{x.invite_code}</Mono><CopyButton text={x.invite_code} /></span> : '—' }]} />}
    </Page>
  )
}

function parseCsv(text) {
  const rows = text.trim().split(/\r?\n/).filter(Boolean).map((l) => { const out = []; let cur = '', q = false; for (const ch of l) { if (ch === '"') q = !q; else if (ch === ',' && !q) { out.push(cur.trim()); cur = '' } else cur += ch } out.push(cur.trim()); return out })
  const head = rows.shift().map((h) => h.toLowerCase())
  const ei = head.indexOf('email'); if (ei < 0) throw new Error('The first row must be a header with an "email" column.')
  const ti = head.indexOf('type')
  return rows.map((r, n) => {
    if (!r[ei]) throw new Error(`Row ${n + 2} has no email.`)
    const record = {}; head.forEach((h, i) => { if (i !== ei && i !== ti && r[i] !== undefined && r[i] !== '') record[h] = /^\d+$/.test(r[i]) ? Number(r[i]) : r[i] })
    return { holder_email: r[ei], record, label: ti >= 0 && r[ti] ? r[ti] : 'Record' }
  })
}
const SAMPLE = 'email,type,student_no,award,grade,year\nstudent1@example.com,Degree certificate,S-1001,BSc Computer Science,First Class,2025\nstudent2@example.com,Transcript,S-1002,BSc Computer Science,Second Class Upper,2025\n'

export function InstIssue() {
  const [mode, setMode] = useState('one')
  const students = useLoad(() => api('/institution/students'), [])
  const bench = useLoad(() => api('/system/benchmark', { token: null }).catch(() => null), [])
  const active = (students.data || []).filter((s) => s.status === 'active')
  const [f, setF] = useState({ holder_email: '', type: TYPES[0], award: '', grade: '', year: new Date().getFullYear(), student_no: '', extra: '' })
  const [queueOnly, setQueueOnly] = useState(false); const [one, setOne] = useState(null)
  const [csv, setCsv] = useState(''); const [many, setMany] = useState(null); const file = useRef()
  const rec = () => { const r = { student_no: f.student_no, award: f.award, grade: f.grade, year: Number(f.year) }; f.extra.split('\n').forEach((l) => { const i = l.indexOf(':'); if (i > 0) r[l.slice(0, i).trim()] = l.slice(i + 1).trim() }); Object.keys(r).forEach((k) => (r[k] === '' || r[k] === undefined) && delete r[k]); return r }
  const issue = useAction(async () => {
    const body = { holder_email: f.holder_email, record: rec(), label: f.type }
    setOne(await api(queueOnly ? '/institution/credentials/queue' : '/institution/credentials', { method: 'POST', body }))
  })
  const bulk = useAction(async (queueMode) => {
    const items = parseCsv(csv)
    if (!items.length) throw new Error('No data rows found.')
    if (queueMode) { for (const it of items) await api('/institution/credentials/queue', { method: 'POST', body: it }); setMany({ queued: items.length }) }
    else setMany(await api('/institution/credentials/batch', { method: 'POST', body: { items } }))
  })
  const flush = useAction(async () => setMany({ anchors: (await api('/institution/queue/flush', { method: 'POST' })).anchors, credential_ids: [] }))
  const onFile = (e) => { const fl = e.target.files?.[0]; if (!fl) return; const r = new FileReader(); r.onload = () => setCsv(String(r.result)); r.readAsText(fl) }
  const single = bench.data?.gas?.single_issue
  return (
    <Page title="Issue records" intro="Type one in, upload a spreadsheet, or queue records and anchor them together. Each is locked with its own key; only a fingerprint reaches the ledger.">
      <div role="tablist" className="inline-flex rounded-xl bg-ink-900/8 p-1">
        {[['one', 'One record'], ['many', 'Spreadsheet (many)']].map(([k, l]) => <button key={k} role="tab" aria-selected={mode === k} className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === k ? 'bg-white shadow' : 'text-ink-900/60'}`} onClick={() => setMode(k)}>{l}</button>)}
      </div>
      {mode === 'one' ? (
        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); issue.run() }}>
            <Field label="Student"><select className="input" value={f.holder_email} onChange={(e) => setF({ ...f, holder_email: e.target.value })} required aria-label="Student"><option value="">Choose a registered student…</option>{active.map((s) => <option key={s.id} value={s.email}>{s.name} ({s.email})</option>)}</select></Field>
            {!students.loading && !active.length && <p className="text-xs text-amber-700">No student has activated an account yet. Register students first and give them their code.</p>}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Type"><select className="input" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })} aria-label="Type">{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
              <Field label="Student number"><input className="input" value={f.student_no} onChange={(e) => setF({ ...f, student_no: e.target.value })} aria-label="Student number" /></Field>
              <Field label="Award or title"><input className="input" value={f.award} onChange={(e) => setF({ ...f, award: e.target.value })} required aria-label="Award or title" /></Field>
              <Field label="Class or grade"><input className="input" value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })} aria-label="Class or grade" /></Field>
              <Field label="Year"><input className="input" type="number" value={f.year} onChange={(e) => setF({ ...f, year: e.target.value })} aria-label="Year" /></Field>
            </div>
            <Field label="Anything else" hint="One per line as name: value, for example Unit: Algorithms"><textarea className="input h-20" value={f.extra} onChange={(e) => setF({ ...f, extra: e.target.value })} /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={queueOnly} onChange={(e) => setQueueOnly(e.target.checked)} className="h-4 w-4 accent-teal-500" /> Queue it and anchor with others later (cheaper per record)</label>
            {issue.error && <Alert tone="error">{issue.error}</Alert>}
            <button className="btn-primary" disabled={issue.busy}>{issue.busy ? 'Issuing…' : queueOnly ? 'Add to queue' : 'Issue record'}</button>
          </form>
          <div>
            {one && (
              <div className="card space-y-3 animate-rise" data-testid="issued">
                <Alert tone="ok">{one.status === 'queued' ? 'Queued. It becomes verifiable when the queue is anchored.' : 'Issued and anchored on the ledger.'}</Alert>
                <div className="text-sm">Credential ID <Mono n={30}>{one.credential_id}</Mono> <CopyButton text={one.credential_id} /></div>
                {one.status !== 'queued' && <div className="flex items-center gap-4"><QRCodeSVG value={shareLink(one.credential_id)} size={112} /><div className="space-y-2 text-sm"><p className="text-ink-900/65">Anyone can scan this to check the record.</p><Link className="btn-ghost !py-1.5" to={`/verify/${one.credential_id}`}>Open check page</Link></div></div>}
                <UnderTheHood rows={[['leaf fingerprint', one.leaf], ['content id (CID)', one.record_cid], ['gas used', one.gas], ['transaction', one.tx]]} />
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="card space-y-3">
            <p className="text-sm text-ink-900/70">First row is a header. It needs an <code className="rounded bg-ink-900/5 px-1">email</code> column. An optional <code className="rounded bg-ink-900/5 px-1">type</code> column names the record. Every other column becomes a field of the record.</p>
            <div className="flex flex-wrap gap-2"><button className="btn-ghost" onClick={() => file.current.click()} type="button"><Upload className="h-4 w-4" /> Upload CSV</button><input ref={file} type="file" accept=".csv,text/csv,text/plain" className="hidden" onChange={onFile} aria-label="CSV file" /><button className="btn-ghost" type="button" onClick={() => download('alma-sample.csv', SAMPLE)}><FileDown className="h-4 w-4" /> Sample file</button></div>
            <textarea className="input h-48 font-mono text-xs" aria-label="CSV data" value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={SAMPLE} />
            {bulk.error && <Alert tone="error">{bulk.error}</Alert>}
            <div className="flex flex-wrap gap-2"><button className="btn-primary" disabled={bulk.busy || !csv.trim()} onClick={() => bulk.run(false)}><Zap className="h-4 w-4" /> {bulk.busy ? 'Working…' : 'Issue and anchor now'}</button><button className="btn-ghost" disabled={bulk.busy || !csv.trim()} onClick={() => bulk.run(true)}>Only add to the queue</button><button className="btn-ghost" disabled={flush.busy} onClick={() => flush.run()}>Anchor what is queued</button></div>
            {flush.error && <Alert tone="error">{flush.error}</Alert>}
          </div>
          {many?.queued && <Alert tone="ok">{many.queued} records queued. Use “Anchor what is queued” when ready.</Alert>}
          {many?.anchors?.length > 0 && (
            <div className="card space-y-3 animate-rise" data-testid="anchored">
              <Alert tone="ok">Anchored {many.anchors.reduce((a, b) => a + b.count, 0)} records in {many.anchors.length} ledger transaction{many.anchors.length > 1 ? 's' : ''}.</Alert>
              {many.anchors.map((a) => (
                <div key={a.root} className="grid gap-3 text-sm sm:grid-cols-4"><div><div className="label">Records</div>{num(a.count)}</div><div><div className="label">Gas in total</div>{num(a.gas)}</div><div><div className="label">Gas per record</div><strong className="text-brand-700">{num(a.gas_per_record)}</strong>{single ? <span className="text-xs text-ink-900/55"> against {num(single)} on its own</span> : null}</div><div><div className="label">Merkle root</div><Mono>{a.root}</Mono></div></div>
              ))}
              <UnderTheHood rows={many.anchors.flatMap((a, i) => [[`batch ${i + 1} manifest CID`, a.manifest_cid], [`batch ${i + 1} transaction`, a.tx]])} />
            </div>
          )}
        </div>
      )}
    </Page>
  )
}

export function InstRecords() {
  const { data, loading, reload } = useLoad(() => api('/institution/records?limit=500'), [])
  const [q, setQ] = useState(''); const [st, setSt] = useState(''); const [ask, setAsk] = useState(null)
  const rev = useAction(async (id) => { await api(`/institution/credentials/${id}/revoke`, { method: 'POST' }); setAsk(null); reload() })
  const rows = (data || []).filter((r) => (!st || r.status === st) && (!q || (r.id + (r.holder || '') + (r.type || '')).toLowerCase().includes(q.toLowerCase())))
  return (
    <Page title="Records" intro="Everything your institution has issued. Revoking is permanent and shows up in every check at once.">
      <div className="flex flex-wrap gap-2"><input className="input max-w-xs" placeholder="Search by ID, student or type" aria-label="Search records" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input max-w-[11rem]" value={st} onChange={(e) => setSt(e.target.value)} aria-label="Status filter"><option value="">All statuses</option>{['issued', 'queued', 'revoked', 'erased'].map((s) => <option key={s}>{s}</option>)}</select></div>
      {rev.error && <Alert tone="error">{rev.error}</Alert>}
      {loading ? <Spinner /> : <Table rows={rows} empty="No records match." cols={[
        { k: 'id', h: 'ID', r: (x) => <Link className="font-mono text-xs text-brand-700 hover:underline" to={`/verify/${x.id}`}>{x.id}</Link> }, { k: 'type', h: 'Type' }, { k: 'holder', h: 'Student' },
        { k: 'kind', h: 'Anchored as', r: (x) => x.kind === 'batch' ? 'batch leaf' : 'single hash' }, { k: 'issued_at', h: 'Issued', r: (x) => when(x.issued_at) },
        { k: 'status', h: 'Status', r: (x) => <Badge tone={statusTone(x.status)}>{x.status}</Badge> },
        { k: 'a', h: '', r: (x) => x.status === 'issued' && (ask === x.id ? <span className="inline-flex gap-1"><button className="btn-danger !px-2 !py-1" onClick={() => rev.run(x.id)} disabled={rev.busy}>Confirm revoke</button><button className="btn-ghost !px-2 !py-1" onClick={() => setAsk(null)}>Cancel</button></span> : <button className="btn-ghost !px-2 !py-1" onClick={() => setAsk(x.id)}><Ban className="h-3.5 w-3.5" /> Revoke</button>) }]} />}
    </Page>
  )
}

export function InstAnchors() {
  const { data, loading } = useLoad(() => api('/institution/anchors'), [])
  const bench = useLoad(() => api('/system/benchmark', { token: null }).catch(() => null), [])
  const single = bench.data?.gas?.single_issue
  return (
    <Page title="Anchors" intro="Each row is one ledger transaction. The Merkle root commits to every record in the batch, and the manifest (fingerprints only) is stored by content ID so the index can be rebuilt.">
      {loading ? <Spinner /> : <Table rows={data} empty="No batches yet." cols={[
        { k: 'at', h: 'When', r: (x) => when(x.at) }, { k: 'count', h: 'Records', r: (x) => num(x.count) }, { k: 'gas', h: 'Gas', r: (x) => num(x.gas) },
        { k: 'g', h: 'Gas per record', r: (x) => <span className="font-semibold text-brand-700">{num(x.gas_per_record)}{single ? <span className="ml-1 text-xs font-normal text-ink-900/50">({Math.round(single / Math.max(1, x.gas_per_record))}× cheaper)</span> : null}</span> },
        { k: 'root', h: 'Merkle root', r: (x) => <Mono>{x.root}</Mono> }, { k: 'cid', h: 'Manifest CID', r: (x) => <Mono n={12}>{x.cid}</Mono> }]} />}
    </Page>
  )
}

const MATRIX = [
  ['Register institutions, employers, regulators', 'Platform owner'], ['Register students at your institution', 'Institution administrator'], ['Issue, anchor and revoke records', 'Institution administrator (own institution only)'],
  ['Suspend or reinstate an institution', 'Regulator, platform owner'], ['Share a record with an employer', 'The student who holds it'],
]
export function InstAccess() {
  const { user } = useAuth()
  const probe = useLoad(() => api('/me/rbac-probe'), [])
  const [onchain, setOnchain] = useState(null)
  const read = useAction(async () => {
    const info = await chainDetails(); const { JsonRpcProvider, Contract } = await import('ethers')
    if (!info.rpc_url) throw new Error('This server uses the built-in test chain, which has no public node address. The API answered above instead.')
    const c = new Contract(info.address, info.abi, new JsonRpcProvider(info.rpc_url, undefined, { staticNetwork: true }))
    const [role, inst] = await Promise.all([c.roleOf(user.address), c.instOfAdmin(user.address)])
    setOnchain({ role: ['None', 'PlatformAdmin', 'UniversityAdmin', 'Student', 'Employer', 'Regulator'][Number(role)], inst: Number(inst) })
  })
  return (
    <Page title="Access rules" intro="Permissions are not only hidden buttons on this website. The smart contract decides from the sender’s address. This page asks the contract what it would allow your account to do. Nothing is sent.">
      <section><h2 className="mb-2 font-display text-xl font-semibold">Who may do what</h2><Table rows={MATRIX.map(([a, b], id) => ({ id, a, b }))} cols={[{ k: 'a', h: 'Action' }, { k: 'b', h: 'Allowed for' }]} /></section>
      <section>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h2 className="font-display text-xl font-semibold">Ask the contract about your account</h2><span className="text-sm text-ink-900/60">On-chain role: <Badge tone="teal">{probe.data?.role_on_chain || '…'}</Badge></span></div>
        {probe.loading ? <Spinner /> : <Table rows={probe.data.checks.map((c) => ({ ...c, id: c.action }))} cols={[
          { k: 'action', h: 'Action', r: (x) => <code className="text-xs">{x.action}</code> }, { k: 'needs', h: 'Contract requires' },
          { k: 'allowed', h: 'For you', r: (x) => x.allowed ? <Badge tone="green"><ShieldCheck className="mr-1 h-3 w-3" />accepted</Badge> : <Badge tone="red"><ShieldX className="mr-1 h-3 w-3" />refused</Badge> },
          { k: 'contract_says', h: 'Contract’s own answer', r: (x) => <span className="text-xs text-ink-900/60">{x.contract_says}</span> }]} />}
      </section>
      <section className="card"><h3 className="font-semibold">Read your role straight from the ledger</h3><p className="mt-1 text-sm text-ink-900/65">Uses Ethers.js in this browser, without going through the Alma server.</p>
        <button className="btn-dark mt-3" onClick={() => read.run()} disabled={read.busy}>Read from the node</button>
        {read.error && <div className="mt-3"><Alert tone="warn">{read.error}</Alert></div>}
        {onchain && <div className="mt-3"><Alert tone="ok">The ledger says your address is <strong>{onchain.role}</strong>{onchain.inst ? `, institution ${onchain.inst}` : ''}.</Alert></div>}
      </section>
    </Page>
  )
}
