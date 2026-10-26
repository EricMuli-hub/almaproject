import { useState } from 'react'
import { api, when } from '../lib'
import { Page, Alert, useAction, Table, Badge } from '../ui'
import { VerdictBanner } from '../Verify'

export function EmployerCheck() {
  const [id, setId] = useState(''); const [res, setRes] = useState(null); const [disc, setDisc] = useState(null); const [denied, setDenied] = useState('')
  const [history, setHistory] = useState([])
  const check = useAction(async () => {
    setDisc(null); setDenied('')
    const r = await api('/verify/' + encodeURIComponent(id.trim()), { token: null }); setRes(r)
    setHistory((h) => [{ id: r.credential_id || id.trim(), at: Math.floor(Date.now() / 1000), valid: r.valid, issuer: r.issuer }, ...h.filter((x) => x.id !== (r.credential_id || id.trim()))].slice(0, 10))
  })
  const ask = useAction(async () => {
    setDenied('')
    try { setDisc(await api('/employer/credentials/' + encodeURIComponent(res.credential_id))) }
    catch (e) { setDenied(e.status === 410 ? 'The holder erased this record, so there is nothing to show.' : e.status === 403 ? 'The holder has not shared this record with you, or the access has expired. Ask them to share it from their Sharing page using your account email.' : e.message) }
  })
  return (
    <Page title="Check a record" intro="Checking that a record is real needs nothing from the student. Reading what is in it needs their permission.">
      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (id.trim()) check.run() }}>
        <input className="input" aria-label="Credential ID" placeholder="ALM-XXXXXXXXXXXX" value={id} onChange={(e) => setId(e.target.value)} />
        <button className="btn-primary shrink-0" disabled={check.busy}>{check.busy ? 'Checking…' : 'Check'}</button>
      </form>
      {check.error && <Alert tone="error">{check.error}</Alert>}
      {res && (
        <div className="space-y-4 animate-rise">
          <VerdictBanner r={res} />
          {res.found && <div className="card"><dl className="grid gap-4 sm:grid-cols-3"><div><dt className="label">Issued by</dt><dd className="font-medium">{res.issuer}</dd></div><div><dt className="label">Type</dt><dd className="font-medium">{res.type}</dd></div><div><dt className="label">Issued</dt><dd className="font-medium">{when(res.issued_at)}</dd></div></dl>
            {res.valid && <div className="mt-4 border-t border-ink-900/10 pt-4"><button className="btn-dark" onClick={() => ask.run()} disabled={ask.busy}>Ask to read the full record</button><p className="mt-2 text-xs text-ink-900/55">Works only if the student has shared it with your account.</p></div>}</div>}
          {denied && <Alert tone="warn">{denied}</Alert>}
          {ask.error && <Alert tone="error">{ask.error}</Alert>}
          {disc && (
            <div className="card animate-rise" data-testid="disclosed">
              <div className="mb-2 flex items-center justify-between"><h2 className="font-display text-xl font-semibold">Shared with you</h2><Badge tone="green">verified again</Badge></div>
              <dl className="grid gap-3 sm:grid-cols-2">{Object.entries(disc.record).map(([k, v]) => <div key={k}><dt className="label">{k.replace(/_/g, ' ')}</dt><dd className="font-medium">{String(v)}</dd></div>)}</dl>
              <p className="mt-3 text-xs text-ink-900/55">Use it only for the purpose the student gave. The access is logged.</p>
            </div>
          )}
        </div>
      )}
      {history.length > 0 && <section><h2 className="mb-2 font-display text-xl font-semibold">Checked this session</h2><Table rows={history} cols={[{ k: 'id', h: 'Record', r: (x) => <code className="text-xs">{x.id}</code> }, { k: 'issuer', h: 'Issuer' }, { k: 'at', h: 'When', r: (x) => when(x.at) }, { k: 'valid', h: 'Result', r: (x) => <Badge tone={x.valid ? 'green' : 'red'}>{x.valid ? 'valid' : 'not valid'}</Badge> }]} /></section>}
    </Page>
  )
}
