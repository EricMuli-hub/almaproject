import { useState } from 'react'
import { Check, Building2, Cpu, DatabaseZap } from 'lucide-react'
import { api, short, num } from '../lib'
import { Page, Stat, Table, Badge, statusTone, Alert, Field, useAction, useLoad, Spinner, UnderTheHood, Mono } from '../ui'

export function OwnerOverview() {
  const health = useLoad(() => api('/system/health', { token: null }), [])
  const stats = useLoad(() => api('/regulator/stats'), [])
  const chain = useLoad(() => api('/system/chain', { token: null }), [])
  const rec = useAction(async () => setMsg(await api('/system/recover', { method: 'POST' })))
  const [msg, setMsg] = useState(null)
  if (health.loading || stats.loading) return <Spinner />
  const h = health.data, s = stats.data
  return (
    <Page title="System" intro="The state of the whole platform. Only you see this page.">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Institutions" value={num(s?.institutions?.length)} /><Stat label="Records" value={num(s?.credentials)} sub={`${num(s?.batches)} anchored batches`} />
        <Stat label="Ledger events" value={num(s?.ledger_events)} sub={`${num(s?.total_gas)} gas in total`} /><Stat label="Open AI alerts" value={num(s?.open_anomalies)} tone={s?.open_anomalies ? 'bad' : 'good'} />
      </div>
      <div className="card">
        <h2 className="font-display text-xl font-semibold">Where things live</h2>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="label">Ledger</dt><dd>{h?.chain === 'rpc' ? 'JSON-RPC node (Hardhat, Ganache or a testnet)' : 'Built-in test chain (resets when the server stops)'}</dd></div>
          <div><dt className="label">Contract</dt><dd><Mono>{h?.contract}</Mono></dd></div>
          <div><dt className="label">Document store</dt><dd>{h?.store}</dd></div>
          <div><dt className="label">Region</dt><dd>{s?.region}</dd></div>
        </dl>
        {chain.data && <div className="mt-4"><UnderTheHood title="Chain details" rows={[['rpc url', chain.data.rpc_url || '(in-process)'], ['chain id', chain.data.chain_id], ['block height', chain.data.block], ['contract', chain.data.address]]} /></div>}
      </div>
      <div className="card">
        <h2 className="font-display text-xl font-semibold">Rebuild the index from the ledger</h2>
        <p className="mt-1 max-w-2xl text-sm text-ink-900/65">If the database is ever lost, batches and record fingerprints are rebuilt from the chain’s events and the manifests on the content store. Holders’ own packages keep verifying even without it.</p>
        <button className="btn-dark mt-3" onClick={() => rec.run()} disabled={rec.busy}><DatabaseZap className="h-4 w-4" /> {rec.busy ? 'Rebuilding…' : 'Rebuild index'}</button>
        {msg && <div className="mt-3"><Alert tone="ok">Rebuilt {msg.rebuilt_credentials} missing record entries.</Alert></div>}
        {rec.error && <div className="mt-3"><Alert tone="error">{rec.error}</Alert></div>}
      </div>
    </Page>
  )
}

export function OwnerDirectory() {
  const { data, loading, reload } = useLoad(() => api('/admin/overview'), [])
  const [i, setI] = useState({ name: '', admin_email: '', password: '' }); const [r, setR] = useState({ name: '', email: '', password: '' }); const [ok, setOk] = useState('')
  const mkI = useAction(async () => { const x = await api('/admin/institutions', { method: 'POST', body: i }); setOk(`${x.name} registered on the ledger (institution ${x.chain_id}).`); setI({ name: '', admin_email: '', password: '' }); reload() })
  const mkR = useAction(async () => { await api('/admin/regulators', { method: 'POST', body: r }); setOk('Regulator added.'); setR({ name: '', email: '', password: '' }); reload() })
  const appr = useAction(async (id) => { await api(`/admin/employers/${id}/approve`, { method: 'POST' }); setOk('Employer approved and registered on the ledger.'); reload() })
  if (loading) return <Spinner />
  return (
    <Page title="Directory" intro="Register institutions and regulators, and approve employers. Each one is also given its role on the ledger.">
      {ok && <Alert tone="ok">{ok}</Alert>}
      <div className="grid gap-6 lg:grid-cols-2">
        <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); mkI.run() }}>
          <h2 className="font-display text-xl font-semibold">Register an institution</h2>
          <Field label="Institution name"><input className="input" value={i.name} onChange={(e) => setI({ ...i, name: e.target.value })} required /></Field>
          <Field label="Administrator email"><input type="email" className="input" value={i.admin_email} onChange={(e) => setI({ ...i, admin_email: e.target.value })} required /></Field>
          <Field label="Starting password" hint="At least 8 characters. They can keep it or ask you to reset it."><input className="input" value={i.password} minLength={8} onChange={(e) => setI({ ...i, password: e.target.value })} required /></Field>
          {mkI.error && <Alert tone="error">{mkI.error}</Alert>}
          <button className="btn-primary" disabled={mkI.busy}><Building2 className="h-4 w-4" /> Register</button>
        </form>
        <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); mkR.run() }}>
          <h2 className="font-display text-xl font-semibold">Add a regulator</h2>
          <Field label="Name"><input className="input" value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} required /></Field>
          <Field label="Email"><input type="email" className="input" value={r.email} onChange={(e) => setR({ ...r, email: e.target.value })} required /></Field>
          <Field label="Starting password"><input className="input" value={r.password} minLength={8} onChange={(e) => setR({ ...r, password: e.target.value })} required /></Field>
          {mkR.error && <Alert tone="error">{mkR.error}</Alert>}
          <button className="btn-primary" disabled={mkR.busy}>Add regulator</button>
        </form>
      </div>
      <section><h2 className="mb-2 font-display text-xl font-semibold">Institutions</h2>
        <Table rows={data.institutions} empty="No institutions yet." cols={[{ k: 'name', h: 'Name' }, { k: 'admin', h: 'Administrator' }, { k: 'chain_id', h: 'Ledger ID' }, { k: 's', h: 'Status', r: (x) => <Badge tone={statusTone(x.status)}>{x.status}</Badge> }]} /></section>
      <section><h2 className="mb-2 font-display text-xl font-semibold">Employers</h2>
        <Table rows={data.employers} empty="No employer has registered." cols={[{ k: 'name', h: 'Name' }, { k: 'email', h: 'Email' }, { k: 's', h: 'Status', r: (x) => <Badge tone={statusTone(x.status)}>{x.status}</Badge> }, { k: 'a', h: '', r: (x) => x.status === 'pending' && <button className="btn-primary !py-1.5" onClick={() => appr.run(x.id)} disabled={appr.busy}><Check className="h-4 w-4" /> Approve</button> }]} />
        {appr.error && <div className="mt-2"><Alert tone="error">{appr.error}</Alert></div>}</section>
      <section><h2 className="mb-2 font-display text-xl font-semibold">Regulators</h2>
        <Table rows={data.regulators} empty="No regulators yet." cols={[{ k: 'name', h: 'Name' }, { k: 'email', h: 'Email' }]} /></section>
    </Page>
  )
}
