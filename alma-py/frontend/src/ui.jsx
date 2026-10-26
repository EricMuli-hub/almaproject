import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { Check, X, Copy, ChevronDown, Loader2, AlertTriangle, Info } from 'lucide-react'
import { api, getSession, setSession, short } from './lib'

// ---------- session ----------
const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)
export function AuthProvider({ children }) {
  const [user, setUser] = useState(getSession())
  const [tech, setTech] = useState(false)
  useEffect(() => { const f = () => setUser(null); window.addEventListener('alma-signout', f); return () => window.removeEventListener('alma-signout', f) }, [])
  const login = async (email, password) => {
    const r = await api('/auth/login', { method: 'POST', body: { email, password }, token: null })
    const me = await api('/me', { token: r.token })
    const s = { token: r.token, role: r.role, name: r.name || me.name, email: me.email, address: me.chain_address }
    setSession(s); setUser(s); return s
  }
  const logout = () => { setSession(null); setUser(null) }
  return <AuthCtx.Provider value={{ user, login, logout, tech, setTech }}>{children}</AuthCtx.Provider>
}

// ---------- small pieces ----------
export function Logo({ dark = false, size = 28 }) {
  return (
    <span className="inline-flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="9" fill={dark ? '#0b1220' : '#2dd4bf'} />
        <path d="M16 6.5l8.5 3.7v5.6c0 4.8-3.6 8.2-8.5 9.7-4.9-1.5-8.5-4.9-8.5-9.7v-5.6z" fill={dark ? '#2dd4bf' : '#0b1220'} />
        <path d="M12.5 16.2l2.4 2.4 4.6-4.9" stroke={dark ? '#0b1220' : '#2dd4bf'} strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Alma
    </span>
  )
}

export function Spinner({ label = 'Loading' }) {
  return <div role="status" className="flex items-center gap-2 py-8 text-sm text-ink-900/60"><Loader2 className="h-4 w-4 animate-spin" /> {label}…</div>
}

export function Badge({ tone = 'gray', children }) {
  const t = { gray: 'bg-ink-900/8 text-ink-900/70', green: 'bg-emerald-100 text-emerald-800', red: 'bg-red-100 text-red-800', amber: 'bg-amber-100 text-amber-800', teal: 'bg-brand-300/40 text-brand-700', blue: 'bg-sky-100 text-sky-800' }[tone]
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${t}`}>{children}</span>
}
export const statusTone = (s) => ({ issued: 'green', active: 'green', revoked: 'red', erased: 'gray', queued: 'amber', held: 'amber', suspended: 'red', pending: 'amber', invited: 'blue', open: 'amber', confirmed: 'red', dismissed: 'gray', critical: 'red', high: 'amber', medium: 'blue' }[s] || 'gray')

export function Field({ label, children, hint }) {
  return <label className="block"><span className="label">{label}</span>{children}{hint && <span className="mt-1 block text-xs text-ink-900/50">{hint}</span>}</label>
}

export function Alert({ tone = 'info', children }) {
  const m = { info: ['bg-sky-50 text-sky-900 border-sky-200', Info], error: ['bg-red-50 text-red-900 border-red-200', AlertTriangle], ok: ['bg-emerald-50 text-emerald-900 border-emerald-200', Check], warn: ['bg-amber-50 text-amber-900 border-amber-200', AlertTriangle] }[tone]
  const Icon = m[1]
  return <div role={tone === 'error' ? 'alert' : 'status'} className={`flex gap-2 rounded-xl border px-3.5 py-3 text-sm ${m[0]}`}><Icon className="mt-0.5 h-4 w-4 shrink-0" /><div className="min-w-0">{children}</div></div>
}

export function Stat({ label, value, sub, tone }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`font-display text-3xl font-semibold ${tone === 'bad' ? 'text-red-600' : tone === 'good' ? 'text-brand-700' : ''}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-900/55">{sub}</div>}
    </div>
  )
}

export function Page({ title, intro, actions, children }) {
  return (
    <div className="animate-rise">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="font-display text-3xl font-semibold tracking-tight">{title}</h1>{intro && <p className="mt-1 max-w-2xl text-sm text-ink-900/65">{intro}</p>}</div>
        {actions}
      </div>
      <div className="space-y-6">{children}</div>
    </div>
  )
}

export function Table({ cols, rows, empty = 'Nothing here yet.' }) {
  if (!rows?.length) return <div className="rounded-xl border border-dashed border-ink-900/20 p-8 text-center text-sm text-ink-900/55">{empty}</div>
  return (
    <div className="overflow-x-auto rounded-xl border border-ink-900/10 bg-white">
      <table className="w-full min-w-[560px]">
        <thead className="border-b border-ink-900/10 bg-sand-50"><tr>{cols.map((c) => <th key={c.k} className="th">{c.h}</th>)}</tr></thead>
        <tbody className="divide-y divide-ink-900/5">{rows.map((r, i) => <tr key={r.id ?? i} className="hover:bg-sand-50/60">{cols.map((c) => <td key={c.k} className="td">{c.r ? c.r(r) : r[c.k]}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

export function CopyButton({ text, label = 'Copy' }) {
  const [done, setDone] = useState(false)
  return <button type="button" className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-brand-700 hover:bg-brand-300/30" onClick={async () => { try { await navigator.clipboard.writeText(text) } catch { /* ignore */ } setDone(true); setTimeout(() => setDone(false), 1500) }}>
    {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{done ? 'Copied' : label}
  </button>
}

export function Mono({ children, n = 22 }) { return <code className="break-all rounded bg-ink-900/5 px-1.5 py-0.5 font-mono text-xs">{typeof children === 'string' ? short(children, n, 6) : children}</code> }

// Shows the Web3 detail behind a friendly action (tx hash, gas, CID...). Always visible when Technical view is on.
export function UnderTheHood({ title = 'Under the hood', rows }) {
  const { tech } = useAuth() || {}
  const [open, setOpen] = useState(false)
  const shown = open || tech
  return (
    <div className="rounded-xl border border-ink-900/10 bg-ink-900 text-white">
      <button type="button" className="flex w-full items-center justify-between px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-brand-300" onClick={() => setOpen(!open)} aria-expanded={shown}>
        {title}<ChevronDown className={`h-4 w-4 transition ${shown ? 'rotate-180' : ''}`} />
      </button>
      {shown && <dl className="grid gap-x-4 gap-y-1.5 px-4 pb-4 pt-1 text-xs sm:grid-cols-[150px_1fr]">{rows.filter((r) => r[1] !== undefined && r[1] !== null && r[1] !== '').map(([k, v]) => <div key={k} className="contents"><dt className="text-white/50">{k}</dt><dd className="break-all font-mono text-white/90">{String(v)}</dd></div>)}</dl>}
    </div>
  )
}

export function Check1({ ok, label, detail }) {
  return (
    <li className="flex items-start gap-2.5 py-1.5">
      <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full ${ok === null ? 'bg-ink-900/10 text-ink-900/50' : ok ? 'bg-emerald-500 text-white animate-tick' : 'bg-red-500 text-white animate-tick'}`}>{ok === null ? '–' : ok ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}</span>
      <span className="text-sm"><span className="font-medium">{label}</span>{detail && <span className="block text-xs text-ink-900/55">{detail}</span>}</span>
    </li>
  )
}

export const CHECK_TEXT = {
  on_chain: ['Found on the ledger', 'The hash or its batch root exists on the blockchain.'],
  merkle_proof: ['Record belongs to its batch', 'The proof path rebuilds the exact root stored on the ledger.'],
  batch_not_revoked: ['Batch still in force', 'The issuing batch has not been withdrawn.'],
  not_revoked: ['Not revoked', 'The institution has not withdrawn this record.'],
  issuer_active: ['Issuer in good standing', 'The institution is active and not on hold.'],
}

// run an async action with loading and error state
export function useAction(fn) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const run = useCallback(async (...a) => { setBusy(true); setError(''); try { return await fn(...a) } catch (e) { setError(e.message); return undefined } finally { setBusy(false) } }, [fn])
  return { run, busy, error, setError }
}

export function useLoad(fn, deps = [], every = 0) {
  const [data, setData] = useState(null); const [error, setError] = useState(''); const [loading, setLoading] = useState(true)
  const load = useCallback(async () => { try { setData(await fn()); setError('') } catch (e) { setError(e.message) } finally { setLoading(false) } }, deps) // eslint-disable-line
  useEffect(() => { load(); if (!every) return; const t = setInterval(load, every); return () => clearInterval(t) }, [load, every])
  return { data, error, loading, reload: load, setData }
}
