import { useState } from 'react'
import { Link } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { Download, ShieldCheck, Send, Trash2, FileJson } from 'lucide-react'
import { api, when, shareLink, download, checkPackageInBrowser, short } from '../lib'
import { Page, Table, Badge, statusTone, Alert, Field, useAction, useLoad, Spinner, UnderTheHood, Mono, CopyButton, Check1, CHECK_TEXT } from '../ui'

function RecordCard({ c }) {
  const [res, setRes] = useState(null)
  const pkg = useAction(async () => { const p = await api(`/student/credentials/${c.id}/package`); download(`${c.id}.alma-package.json`, p) })
  const check = useAction(async () => { const p = await api(`/student/credentials/${c.id}/package`); setRes(await checkPackageInBrowser(p)) })
  const live = c.status === 'issued' || c.status === 'revoked'
  return (
    <article className="card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="font-display text-xl font-semibold">{c.type || 'Record'}</div><div className="mt-0.5 text-xs text-ink-900/55">Issued {when(c.issued_at)}</div><div className="mt-2"><Mono n={30}>{c.id}</Mono> <CopyButton text={c.id} /></div></div>
        <div className="flex items-center gap-3"><Badge tone={statusTone(c.status)}>{c.status}</Badge>{live && <QRCodeSVG value={shareLink(c.id)} size={64} />}</div>
      </div>
      {live && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-900/10 pt-3">
          <Link className="btn-ghost !py-1.5" to={`/verify/${c.id}`}><ShieldCheck className="h-4 w-4" /> Public check page</Link>
          <button className="btn-ghost !py-1.5" onClick={() => pkg.run()} disabled={pkg.busy}><Download className="h-4 w-4" /> Download my copy</button>
          <button className="btn-ghost !py-1.5" onClick={() => check.run()} disabled={check.busy}><FileJson className="h-4 w-4" /> Check it in this browser</button>
        </div>
      )}
      {(pkg.error || check.error) && <div className="mt-3"><Alert tone="error">{pkg.error || check.error}</Alert></div>}
      {res && (
        <div className="mt-3 space-y-3 animate-rise" data-testid="browser-check">
          <Alert tone={res.valid ? 'ok' : 'error'}>{res.valid ? 'Valid. Your browser rebuilt the proof and read the ledger itself.' : 'This copy did not check out.'}</Alert>
          <ul>{Object.entries(res.checks).map(([k, v]) => <Check1 key={k} ok={v} label={(CHECK_TEXT[k] || [k])[0]} detail={(CHECK_TEXT[k] || [])[1]} />)}</ul>
          <UnderTheHood rows={[['read through', res.source], ['leaf (sha256)', res.leaf], ['recomputed root', res.computedRoot], ['proof steps', res.steps.length]]} />
        </div>
      )}
    </article>
  )
}

export function StudentRecords() {
  const { data, loading } = useLoad(() => api('/student/credentials'), [])
  return (
    <Page title="My records" intro="These are yours. The downloaded copy lets anyone verify a record even if Alma were offline.">
      {loading ? <Spinner /> : data.length === 0 ? <div className="rounded-xl border border-dashed border-ink-900/20 p-10 text-center text-sm text-ink-900/60">Nothing has been issued to you yet.</div> : <div className="grid gap-5 lg:grid-cols-2">{data.map((c) => <RecordCard key={c.id} c={c} />)}</div>}
    </Page>
  )
}

export function StudentSharing() {
  const recs = useLoad(() => api('/student/credentials'), [])
  const cons = useLoad(() => api('/student/consents'), [])
  const [f, setF] = useState({ cid: '', verifier_email: '', days: 30, purpose: 'Employment check' }); const [ok, setOk] = useState('')
  const grant = useAction(async () => { const r = await api(`/student/credentials/${f.cid}/consent`, { method: 'POST', body: { verifier_email: f.verifier_email, days: Number(f.days), purpose: f.purpose } }); setOk(`Shared with ${f.verifier_email} until ${when(r.until)}.`); setLast(r); cons.reload() })
  const [last, setLast] = useState(null)
  const stop = useAction(async (c) => { await api(`/student/credentials/${c.credential_id}/consent/${encodeURIComponent(c.verifier)}`, { method: 'DELETE' }); setOk(`Access withdrawn from ${c.verifier}.`); cons.reload() })
  const issued = (recs.data || []).filter((r) => r.status === 'issued')
  const now = Date.now() / 1000
  return (
    <Page title="Sharing" intro="An employer can always check that a record is real. They only see its contents if you allow it, for the time you choose, and you can take it back.">
      <form className="card grid gap-3 lg:grid-cols-2" onSubmit={(e) => { e.preventDefault(); grant.run() }}>
        <Field label="Record to share"><select className="input" aria-label="Record to share" value={f.cid} onChange={(e) => setF({ ...f, cid: e.target.value })} required><option value="">Choose a record…</option>{issued.map((r) => <option key={r.id} value={r.id}>{r.type} · {r.id}</option>)}</select></Field>
        <Field label="Employer’s email" hint="They must have an approved Alma employer account."><input type="email" className="input" aria-label="Employer email" value={f.verifier_email} onChange={(e) => setF({ ...f, verifier_email: e.target.value })} required /></Field>
        <Field label="For how many days"><input type="number" min="0.01" step="any" className="input" aria-label="Days" value={f.days} onChange={(e) => setF({ ...f, days: e.target.value })} required /></Field>
        <Field label="Purpose"><input className="input" aria-label="Purpose" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} required /></Field>
        <div className="lg:col-span-2 space-y-3">{grant.error && <Alert tone="error">{grant.error}</Alert>}{ok && <Alert tone="ok">{ok}</Alert>}<button className="btn-primary" disabled={grant.busy}><Send className="h-4 w-4" /> Share</button>
          {last && <UnderTheHood title="Recorded on the ledger" rows={[['consent transaction', last.tx], ['expires (unix)', last.until]]} />}</div>
      </form>
      <section><h2 className="mb-2 font-display text-xl font-semibold">Who can see what</h2>
        {cons.loading ? <Spinner /> : <Table rows={cons.data} empty="You have not shared anything." cols={[
          { k: 'verifier', h: 'Employer' }, { k: 'credential_id', h: 'Record', r: (x) => <Mono n={30}>{x.credential_id}</Mono> }, { k: 'purpose', h: 'Purpose' },
          { k: 'until', h: 'Until', r: (x) => when(x.until) },
          { k: 's', h: 'State', r: (x) => x.revoked ? <Badge>withdrawn</Badge> : x.until < now ? <Badge tone="amber">expired</Badge> : <Badge tone="green">active</Badge> },
          { k: 'a', h: '', r: (x) => !x.revoked && x.until >= now && <button className="btn-ghost !px-2 !py-1" onClick={() => stop.run(x)} disabled={stop.busy}>Withdraw</button> }]} />}
        {stop.error && <div className="mt-2"><Alert tone="error">{stop.error}</Alert></div>}
      </section>
    </Page>
  )
}

export function StudentData() {
  const recs = useLoad(() => api('/student/credentials'), [])
  const [cid, setCid] = useState(''); const [typed, setTyped] = useState(''); const [done, setDone] = useState(null)
  const exp = useAction(async () => { const d = await api('/student/export'); download('my-alma-data.json', d) })
  const erase = useAction(async () => { setDone(await api(`/student/credentials/${cid}`, { method: 'DELETE' })); setTyped(''); setCid(''); recs.reload() })
  const live = (recs.data || []).filter((r) => r.status === 'issued' || r.status === 'revoked')
  return (
    <Page title="My data" intro="You own your records. Take a full copy, or erase one for good.">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card"><h2 className="font-display text-xl font-semibold">Take a copy</h2><p className="mt-1 text-sm text-ink-900/65">Your records, their proofs and who you shared them with, as one file you can keep anywhere.</p>
          <button className="btn-dark mt-4" onClick={() => exp.run()} disabled={exp.busy}><Download className="h-4 w-4" /> Download everything</button>{exp.error && <div className="mt-3"><Alert tone="error">{exp.error}</Alert></div>}</section>
        <section className="card"><h2 className="font-display text-xl font-semibold">What the ledger holds about you</h2><p className="mt-1 text-sm text-ink-900/65">Only salted fingerprints, which cannot be turned back into your name or marks, plus the consent entries you created.</p>
          <ul className="mt-3 space-y-1 text-xs">{live.map((r) => <li key={r.id}><Mono n={20}>{r.id}</Mono></li>)}</ul></section>
      </div>
      <section className="card border-red-200">
        <h2 className="font-display text-xl font-semibold text-red-700">Erase a record</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink-900/70">This destroys the key that opens the record. The encrypted copy can never be read again, by anyone, including Alma. The fingerprint on the ledger stays, but it only ever pointed at a salted hash. Employers lose access, and the check page will say the holder erased it. This cannot be undone.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label="Record"><select className="input" aria-label="Record to erase" value={cid} onChange={(e) => setCid(e.target.value)}><option value="">Choose…</option>{live.map((r) => <option key={r.id} value={r.id}>{r.type} · {r.id}</option>)}</select></Field>
          <Field label="Type ERASE to confirm"><input className="input" aria-label="Confirm erase" value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
          <button className="btn-danger" disabled={!cid || typed !== 'ERASE' || erase.busy} onClick={() => erase.run()}><Trash2 className="h-4 w-4" /> Erase</button>
        </div>
        {erase.error && <div className="mt-3"><Alert tone="error">{erase.error}</Alert></div>}
        {done && <div className="mt-3 space-y-2"><Alert tone="ok">Erased. {done.key_destroyed ? 'The key is destroyed.' : ''}</Alert><UnderTheHood rows={[['record', done.credential_id], ['key destroyed', String(done.key_destroyed)], ['local encrypted copy removed', String(done.local_copy_removed)]]} /></div>}
      </section>
    </Page>
  )
}
