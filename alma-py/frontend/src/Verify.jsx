import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { ShieldCheck, ShieldX, Hourglass, Eraser, FlaskConical } from 'lucide-react'
import { api, checkPackageInBrowser, shareLink, when, short } from './lib'
import { Logo, Check1, CHECK_TEXT, Alert, Field, Mono, UnderTheHood, useAction, Badge, CopyButton } from './ui'

export function VerdictBanner({ r }) {
  const erased = r.reason?.includes('erased'); const queued = r.reason?.includes('waiting')
  const tone = r.valid ? 'bg-emerald-600' : queued ? 'bg-amber-500' : 'bg-red-600'
  const Icon = r.valid ? ShieldCheck : queued ? Hourglass : erased ? Eraser : ShieldX
  const text = r.valid ? 'Valid record' : queued ? 'Not anchored yet' : erased ? 'Record erased by its holder' : r.found === false ? 'No such record' : 'Not valid'
  return (
    <div role="status" aria-live="polite" className={`flex items-center gap-4 rounded-2xl ${tone} px-5 py-4 text-white`}>
      <Icon className="h-9 w-9 shrink-0" /><div><div className="font-display text-2xl font-semibold" data-testid="verdict">{text}</div><div className="text-sm text-white/85">{r.valid ? 'Every check below passed.' : r.reason || 'This could not be confirmed.'}</div></div>
    </div>
  )
}

function Checks({ checks }) {
  return <ul className="divide-y divide-ink-900/5">{Object.entries(checks || {}).map(([k, v]) => <Check1 key={k} ok={v} label={(CHECK_TEXT[k] || [k])[0]} detail={(CHECK_TEXT[k] || [])[1]} />)}</ul>
}

function ById({ initial }) {
  const nav = useNavigate()
  const [id, setId] = useState(initial || '')
  const [res, setRes] = useState(null)
  const act = useAction(async (v) => { setRes(await api('/verify/' + encodeURIComponent(v), { token: null })) })
  useEffect(() => { if (initial) { setId(initial); act.run(initial) } }, [initial]) // eslint-disable-line
  return (
    <div className="space-y-5">
      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (id.trim()) { nav('/verify/' + encodeURIComponent(id.trim())); act.run(id.trim()) } }}>
        <input className="input" aria-label="Credential ID" placeholder="ALM-XXXXXXXXXXXX" value={id} onChange={(e) => setId(e.target.value)} />
        <button className="btn-primary shrink-0" disabled={act.busy}>{act.busy ? 'Checking…' : 'Check record'}</button>
      </form>
      {act.error && <Alert tone="error">{act.error}</Alert>}
      {res && (
        <div className="space-y-5 animate-rise">
          <VerdictBanner r={res} />
          {res.found && (
            <div className="grid gap-5 md:grid-cols-[1fr_auto]">
              <div className="card">
                <dl className="grid gap-4 sm:grid-cols-3">
                  <div><dt className="label">Issued by</dt><dd className="font-medium">{res.issuer || '—'}</dd></div>
                  <div><dt className="label">Record type</dt><dd className="font-medium">{res.type || '—'}</dd></div>
                  <div><dt className="label">Issued</dt><dd className="font-medium">{when(res.issued_at)}</dd></div>
                </dl>
                {res.checks && <div className="mt-4 border-t border-ink-900/10 pt-3"><div className="label">What was checked</div><Checks checks={res.checks} /></div>}
                <p className="mt-3 text-xs text-ink-900/50">This page never shows names, marks or numbers. Only the holder can share those.</p>
              </div>
              <div className="card flex flex-col items-center gap-2 self-start"><QRCodeSVG value={shareLink(res.credential_id)} size={132} /><div className="text-xs text-ink-900/55">Share this check</div><CopyButton text={shareLink(res.credential_id)} label="Copy link" /></div>
            </div>
          )}
          {res.found && <UnderTheHood rows={[['credential id', res.credential_id], ['anchored as', res.anchored], ['status in index', res.status]]} />}
        </div>
      )}
    </div>
  )
}

function FromPackage() {
  const [text, setText] = useState('')
  const [out, setOut] = useState(null)
  const act = useAction(async (tamper) => {
    let pkg
    try { pkg = JSON.parse(text) } catch { throw new Error('That is not valid JSON. Paste the package file the student downloaded.') }
    if (!pkg.record || !pkg.salt) throw new Error('A package needs "record" and "salt".')
    if (tamper) pkg = { ...pkg, record: { ...pkg.record, tampered: 'yes' } }
    const body = { record: pkg.record, salt: pkg.salt, proof: pkg.proof ?? null, root: pkg.root ?? null }
    const [server, browser] = await Promise.all([api('/verify/package', { method: 'POST', body, token: null }), checkPackageInBrowser(pkg)])
    setOut({ server, browser, tampered: !!tamper })
  })
  return (
    <div className="space-y-4">
      <Alert>A holder’s package is the record, a random salt and a proof. It is checked twice: by the Alma server, and again in this browser with Ethers.js reading the ledger directly, so you do not have to take Alma’s word for it.</Alert>
      <Field label="Package JSON"><textarea className="input h-40 font-mono text-xs" aria-label="Package JSON" value={text} onChange={(e) => setText(e.target.value)} placeholder='{"record": {...}, "salt": "…", "proof": [...], "root": "0x…"}' /></Field>
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled={act.busy || !text} onClick={() => act.run(false)}>Check package</button>
        <button className="btn-ghost" disabled={act.busy || !text} onClick={() => act.run(true)} title="Changes one field before checking, to show that any edit is caught"><FlaskConical className="h-4 w-4" /> Try with an edited record</button>
      </div>
      {act.error && <Alert tone="error">{act.error}</Alert>}
      {out && (
        <div className="grid gap-5 md:grid-cols-2 animate-rise">
          <div className="card"><div className="mb-2 flex items-center justify-between"><span className="label !mb-0">Alma server says</span><Badge tone={out.server.valid ? 'green' : 'red'}>{out.server.valid ? 'valid' : 'not valid'}</Badge></div><Checks checks={out.server.checks} /></div>
          <div className="card"><div className="mb-2 flex items-center justify-between"><span className="label !mb-0">This browser says</span><Badge tone={out.browser.valid ? 'green' : 'red'}>{out.browser.valid ? 'valid' : 'not valid'}</Badge></div><Checks checks={out.browser.checks} /><p className="mt-2 text-xs text-ink-900/50" data-testid="chain-source">Ledger read through: {out.browser.source === 'ethers' ? 'Ethers.js, straight from the node' : out.browser.source === 'api' ? 'the Alma API (node not reachable from this browser)' : 'not available'}</p></div>
          <div className="md:col-span-2"><UnderTheHood rows={[['leaf (sha256)', out.browser.leaf], ['recomputed root', out.browser.computedRoot], ['proof steps', out.browser.steps.length], ...out.browser.steps.map((s, i) => [`step ${i + 1} (${s.side})`, short(s.result, 14, 8)])]} title="The proof, step by step" /></div>
        </div>
      )}
    </div>
  )
}

export default function Verify() {
  const { id } = useParams(); const [sp, setSp] = useSearchParams()
  const [tab, setTab] = useState(sp.get('tab') === 'package' ? 'package' : 'id')
  return (
    <div className="min-h-screen bg-sand-50">
      <header className="border-b border-ink-900/10 bg-white"><div className="mx-auto flex max-w-4xl items-center justify-between px-5 py-4"><Link to="/"><Logo dark /></Link><Link to="/login" className="text-sm font-medium text-brand-700">Sign in</Link></div></header>
      <main className="mx-auto max-w-4xl px-5 py-10">
        <h1 className="font-display text-4xl font-semibold tracking-tight">Check a record</h1>
        <p className="mt-1 text-ink-900/65">No account needed. You get a yes or a no and who issued it.</p>
        <div role="tablist" className="mt-6 inline-flex rounded-xl bg-ink-900/8 p-1">
          {[['id', 'By ID or QR link'], ['package', 'From a package file']].map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={`rounded-lg px-4 py-2 text-sm font-semibold ${tab === k ? 'bg-white shadow' : 'text-ink-900/60'}`} onClick={() => { setTab(k); setSp(k === 'package' ? { tab: 'package' } : {}) }}>{l}</button>)}
        </div>
        <div className="mt-6">{tab === 'id' ? <ById initial={id} /> : <FromPackage />}</div>
      </main>
    </div>
  )
}
