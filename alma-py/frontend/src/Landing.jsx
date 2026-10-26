import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ShieldCheck, FileCheck2, GraduationCap, Building2, Briefcase, Scale, Fingerprint, Radar, Database, Lock, Gauge, ArrowRight, QrCode, Check } from 'lucide-react'
import { Logo, useLoad } from './ui'
import { api, num } from './lib'

function Nav() {
  return (
    <header className="absolute inset-x-0 top-0 z-20">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 text-white">
        <Link to="/" aria-label="Alma home"><Logo size={30} /></Link>
        <nav className="hidden items-center gap-7 text-sm text-white/75 md:flex" aria-label="Main">
          <a href="#how" className="hover:text-white">How it works</a>
          <a href="#roles" className="hover:text-white">Who uses it</a>
          <a href="#proof" className="hover:text-white">What it proves</a>
          <a href="#privacy" className="hover:text-white">Privacy</a>
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/verify" className="hidden rounded-lg px-3 py-2 text-sm text-white/85 hover:text-white sm:block">Verify a record</Link>
          <Link to="/login" className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-ink-900 hover:bg-brand-300">Sign in</Link>
        </div>
      </div>
    </header>
  )
}

function RecordCard() {
  const rows = [['Issued by', 'University of Nairobi'], ['Record', 'BSc Computer Science'], ['Class', 'First Class Honours'], ['Year', '2025']]
  const checks = ['Found on the ledger', 'Proof matches the batch root', 'Not revoked', 'Issuer in good standing']
  return (
    <div className="relative animate-drift" aria-hidden="true">
      <div className="absolute -inset-6 rounded-[2rem] bg-brand-400/20 blur-3xl" />
      <div className="relative rounded-2xl border border-white/15 bg-white p-5 text-ink-900 shadow-2xl">
        <div className="flex items-center justify-between"><span className="label !mb-0">Alma record</span><span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">Valid</span></div>
        <div className="mt-3 font-display text-2xl font-semibold">Degree certificate</div>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">{rows.map(([k, v]) => <div key={k}><dt className="text-xs text-ink-900/50">{k}</dt><dd className="font-medium">{v}</dd></div>)}</dl>
        <ul className="mt-4 space-y-1.5 border-t border-ink-900/10 pt-3">
          {checks.map((c, i) => <li key={c} className="flex items-center gap-2 text-sm opacity-0 animate-rise" style={{ animationDelay: `${0.5 + i * 0.35}s`, animationFillMode: 'forwards' }}><span className="grid h-4 w-4 place-items-center rounded-full bg-emerald-500 text-white"><Check className="h-3 w-3" /></span>{c}</li>)}
        </ul>
        <div className="mt-4 flex items-center gap-3 rounded-lg bg-sand-100 p-3 text-xs text-ink-900/60"><QrCode className="h-9 w-9 text-ink-900" /> Scan to check this record. No account needed.</div>
      </div>
    </div>
  )
}

function Hero() {
  const nav = useNavigate(); const [id, setId] = useState('')
  const go = (e) => { e.preventDefault(); if (id.trim()) nav('/verify/' + encodeURIComponent(id.trim())) }
  return (
    <section className="grid-bg relative overflow-hidden bg-ink-950 pb-24 pt-32 text-white">
      <div className="absolute -left-40 top-10 h-96 w-96 rounded-full bg-brand-500/25 blur-3xl" />
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 lg:grid-cols-[1.1fr_.9fr]">
        <div className="animate-rise">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 px-3 py-1 text-xs text-brand-300"><ShieldCheck className="h-3.5 w-3.5" /> Built for schools, colleges and universities</p>
          <h1 className="font-display text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">Records you can trust,<br /><span className="text-brand-400">without phoning anyone.</span></h1>
          <p className="mt-5 max-w-xl text-lg text-white/70">Alma lets an institution issue a certificate that anyone can check in a second and nobody can fake. Students decide who sees what. Odd behaviour is spotted as it happens.</p>
          <form onSubmit={go} className="mt-8 flex max-w-xl flex-col gap-2 sm:flex-row" aria-label="Check a record">
            <input aria-label="Credential ID" value={id} onChange={(e) => setId(e.target.value)} placeholder="Paste a credential ID, e.g. ALM-3F9A1C2B7D10" className="input !border-white/20 !bg-white/10 !text-white placeholder:!text-white/40" />
            <button className="btn-primary shrink-0" type="submit">Check record <ArrowRight className="h-4 w-4" /></button>
          </form>
          <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/60">
            {['No wallet or seed phrase', 'No personal data on the blockchain', 'Checked by AI around the clock'].map((t) => <li key={t} className="flex items-center gap-1.5"><Check className="h-4 w-4 text-brand-400" />{t}</li>)}
          </ul>
        </div>
        <RecordCard />
      </div>
    </section>
  )
}

function Numbers() {
  const { data: b } = useLoad(() => api('/system/benchmark', { token: null }), [])
  const { data: h } = useLoad(() => api('/system/health', { token: null }), [])
  const items = [
    ['Gas per record in a batch', b ? num(b.gas.batch_1000_per_record) : '—', `against ${b ? num(b.gas.single_issue) : '—'} when anchored one by one`],
    ['Records per ledger transaction', 'up to 5,000', 'one Merkle root covers the whole batch'],
    ['Hash steps to prove one record', b ? b.merkle['100000'].proof_hashes : '—', 'even among 100,000 records'],
    ['Ledger', h ? (h.chain === 'rpc' ? 'Live node' : 'Test chain') : '…', h ? `contract ${h.contract.slice(0, 8)}…` : 'checking'],
  ]
  return (
    <section className="border-b border-ink-900/10 bg-white" aria-label="Live figures">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-6 px-5 py-8 lg:grid-cols-4">
        {items.map(([k, v, s]) => <div key={k}><div className="font-display text-3xl font-semibold text-brand-700">{v}</div><div className="text-sm font-medium">{k}</div><div className="text-xs text-ink-900/55">{s}</div></div>)}
      </div>
    </section>
  )
}

const steps = [
  ['Issue', 'The registrar fills a form or uploads a spreadsheet. Alma locks the record with a private key and a salt.', FileCheck2],
  ['Anchor', 'Only a fingerprint goes on the ledger. The record itself is encrypted and stored by content ID.', Fingerprint],
  ['Share', 'The student gets the record and decides who may read it, for how long, and for what.', GraduationCap],
  ['Verify', 'Anyone scans the QR code or pastes the ID. Alma rebuilds the proof and reads the ledger. About a second.', ShieldCheck],
]

function How() {
  return (
    <section id="how" className="mx-auto max-w-6xl px-5 py-20">
      <h2 className="font-display text-4xl font-semibold tracking-tight">Four steps, no blockchain lessons.</h2>
      <p className="mt-2 max-w-2xl text-ink-900/65">People sign in with an email and password like any portal. The keys, hashes and transactions happen behind the screen. Turn on “Technical view” after signing in to watch them.</p>
      <ol className="mt-10 grid gap-5 md:grid-cols-4">
        {steps.map(([t, d, Icon], i) => (
          <li key={t} className="card relative"><span className="absolute right-4 top-3 font-display text-5xl font-semibold text-ink-900/5">{i + 1}</span><Icon className="h-6 w-6 text-brand-600" /><h3 className="mt-3 font-display text-xl font-semibold">{t}</h3><p className="mt-1 text-sm text-ink-900/65">{d}</p></li>
        ))}
      </ol>
    </section>
  )
}

const roles = [
  [Building2, 'Institutions', 'Register students, issue one record or ten thousand, revoke, and see exactly what was anchored.'],
  [GraduationCap, 'Students', 'Hold your records, share one with one employer for thirty days, withdraw it, export or erase it.'],
  [Briefcase, 'Employers', 'Check any record without an account. Ask the student for more, and only see what they allow.'],
  [Scale, 'Regulators', 'Watch the AI alerts, suspend an institution, check the audit trail and the performance figures.'],
]
function Roles() {
  return (
    <section id="roles" className="bg-sand-100 py-20">
      <div className="mx-auto max-w-6xl px-5">
        <h2 className="font-display text-4xl font-semibold tracking-tight">One system, four ways in.</h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {roles.map(([Icon, t, d]) => <div key={t} className="card"><span className="grid h-10 w-10 place-items-center rounded-xl bg-ink-900 text-brand-300"><Icon className="h-5 w-5" /></span><h3 className="mt-3 font-display text-xl font-semibold">{t}</h3><p className="mt-1 text-sm text-ink-900/65">{d}</p></div>)}
        </div>
        <p className="mt-6 text-sm text-ink-900/60">What each role may do is written into the smart contract, not only into this website. Skip the website and the contract still says no.</p>
      </div>
    </section>
  )
}

const objectives = [
  [Lock, '1', 'Access rules the ledger enforces', 'Five roles live in the smart contract. A student cannot issue, an employer cannot anchor, one institution cannot touch another’s records.', 'See it: sign in as a registrar, then try a forbidden action under Access rules.'],
  [Radar, '2', 'AI that watches the ledger', 'An Isolation Forest learns normal administrator behaviour and scores every action live. A critical score puts the institution on hold until a regulator looks.', 'See it: the AI alerts and AI model pages.'],
  [Database, '3', 'Storage that survives a server loss', 'Records are encrypted and kept by content ID, the fingerprint is on the ledger. Lose the database and the index is rebuilt from both.', 'See it: Records and Anchors, then Recover in the system page.'],
  [ShieldCheck, '4', 'Immutable, yet private', 'Nothing personal is on the chain. Consent has an expiry. Erasing a record destroys its key, so the copy can never be read again.', 'See it: Sharing and My data pages.'],
  [Gauge, '5', 'Fast enough, cheap enough', 'One transaction can anchor thousands of records. Measured latency, throughput and gas are shown next to a plain database lookup.', 'See it: the Performance page.'],
]
function Proof() {
  return (
    <section id="proof" className="mx-auto max-w-6xl px-5 py-20">
      <h2 className="font-display text-4xl font-semibold tracking-tight">Five things it has to prove, and where to see each.</h2>
      <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {objectives.map(([Icon, n, t, d, see]) => (
          <article key={n} className="card flex flex-col">
            <div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-full bg-brand-500 font-display text-lg font-semibold text-ink-950">{n}</span><Icon className="h-5 w-5 text-ink-900/40" /></div>
            <h3 className="mt-3 font-display text-xl font-semibold">{t}</h3>
            <p className="mt-1 flex-1 text-sm text-ink-900/70">{d}</p>
            <p className="mt-3 border-t border-ink-900/10 pt-3 text-xs font-medium text-brand-700">{see}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

function Privacy() {
  const on = ['A salted SHA-256 fingerprint', 'A batch Merkle root', 'Role and institution status', 'Consent grants with expiry dates']
  const off = ['Names, emails, student numbers', 'Marks, classes and awards', 'The encrypted record itself (content store)', 'The key that opens it (platform database)']
  return (
    <section id="privacy" className="bg-ink-900 py-20 text-white">
      <div className="mx-auto max-w-6xl px-5">
        <h2 className="font-display text-4xl font-semibold tracking-tight">The ledger never holds a name.</h2>
        <p className="mt-2 max-w-2xl text-white/65">Built around the Kenya Data Protection Act, 2019 and the GDPR. Permanent records and the right to erasure usually collide. Here they do not, because the permanent part is only a fingerprint nobody can read.</p>
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-6"><h3 className="font-semibold text-brand-300">On the blockchain (permanent)</h3><ul className="mt-3 space-y-2 text-sm text-white/80">{on.map((x) => <li key={x} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" />{x}</li>)}</ul></div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-6"><h3 className="font-semibold text-gold-400">Off the chain (erasable)</h3><ul className="mt-3 space-y-2 text-sm text-white/80">{off.map((x) => <li key={x} className="flex gap-2"><Lock className="mt-0.5 h-4 w-4 shrink-0 text-gold-400" />{x}</li>)}</ul></div>
        </div>
      </div>
    </section>
  )
}

function Cta() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20 text-center">
      <h2 className="font-display text-4xl font-semibold tracking-tight">Ready to check a record, or issue one?</h2>
      <div className="mt-6 flex flex-wrap justify-center gap-3"><Link to="/verify" className="btn-primary">Check a record</Link><Link to="/login" className="btn-dark">Sign in</Link><Link to="/login?tab=employer" className="btn-ghost">Employer sign-up</Link></div>
    </section>
  )
}

export default function Landing() {
  return (
    <div>
      <Nav />
      <main>
        <Hero /><Numbers /><How /><Roles /><Proof /><Privacy /><Cta />
      </main>
      <footer className="border-t border-ink-900/10 bg-white py-8 text-sm text-ink-900/60">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5"><Logo dark /><span>React · Ethers.js · FastAPI · Solidity · IPFS · Scikit-learn</span><span>Prototype for research and demonstration.</span></div>
      </footer>
    </div>
  )
}
