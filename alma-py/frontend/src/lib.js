// API client, session store, and the in-browser verification helpers (Ethers.js).
import { toUtf8Bytes, getBytes, concat, hexlify, JsonRpcProvider, Contract } from 'ethers'
import { sha256 as nobleSha256 } from '@noble/hashes/sha256'

// sha-256 over bytes or a 0x hex string, returned as 0x hex (the same function the browser build of Ethers.js uses)
const sha256 = (data) => hexlify(nobleSha256(getBytes(data)))

export const apiBase = () => (typeof window !== 'undefined' && window.__ALMA_API__) || import.meta.env.VITE_API || ''

const KEY = 'alma.session'
let session = null
try { session = JSON.parse(localStorage.getItem(KEY) || 'null') } catch { session = null }
export const getSession = () => session
export const setSession = (s) => { session = s; try { s ? localStorage.setItem(KEY, JSON.stringify(s)) : localStorage.removeItem(KEY) } catch { /* private mode */ } }

export async function api(path, { method = 'GET', body, token = session?.token, raw = false } = {}) {
  const res = await fetch(apiBase() + path, {
    method,
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  let data = null
  try { data = await res.json() } catch { /* empty */ }
  if (!res.ok) {
    if (res.status === 401 && session) { setSession(null); window.dispatchEvent(new Event('alma-signout')) }
    const d = data?.detail
    const err = new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join(', ') : 'Request failed (' + res.status + ')')
    err.status = res.status
    throw err
  }
  return raw ? res : data
}

// ---- formatting ----
export const short = (s, a = 8, b = 6) => (s && s.length > a + b + 3 ? s.slice(0, a) + '…' + s.slice(-b) : s || '')
export const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—')
export const num = (n) => (n == null ? '—' : Number(n).toLocaleString())
export const download = (name, obj) => {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)], { type: 'application/json' }))
  a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
export const shareLink = (id) => `${location.origin}${location.pathname}#/verify/${id}`

// ---- the same hashing the server uses, run in the browser ----
export function canonical(v) {
  if (v === null || typeof v !== 'object') return JSON.stringify(v)
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']'
  return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}'
}
const hexBytes = (h) => getBytes(h.startsWith('0x') ? h : '0x' + h)
export const leafOf = (record, saltHex) => sha256(concat([toUtf8Bytes('alma:leaf:'), toUtf8Bytes(canonical(record)), hexBytes(saltHex)]))
export function climb(leaf, proof) {
  let h = leaf
  const steps = []
  for (const [side, sib] of proof) {
    const s = hexBytes(sib)
    h = side === 'R' ? sha256(concat(['0x01', h, s])) : sha256(concat(['0x01', s, h]))
    steps.push({ side, sibling: hexlify(s), result: h })
  }
  return { root: h, steps }
}

// ---- chain access through Ethers.js (direct to the node when it is reachable) ----
let chainInfo = null
export async function chainDetails() { return (chainInfo ||= await api('/system/chain', { token: null })) }
export async function chainBatch(root) {
  const info = await chainDetails()
  if (info.rpc_url) {
    try {
      const provider = new JsonRpcProvider(info.rpc_url, undefined, { staticNetwork: true })
      const c = new Contract(info.address, info.abi, provider)
      const [exists, revoked, instId, issuerActive] = await c.batchStatus(root)
      return { source: 'ethers', exists, revoked, inst_id: Number(instId), issuer_active: issuerActive }
    } catch { /* node not reachable from this browser, fall back to the API */ }
  }
  return { source: 'api', ...(await api('/system/chain/batch/' + root.replace(/^0x/, ''), { token: null })) }
}
export async function chainCredential(hash) {
  const info = await chainDetails()
  if (info.rpc_url) {
    try {
      const provider = new JsonRpcProvider(info.rpc_url, undefined, { staticNetwork: true })
      const c = new Contract(info.address, info.abi, provider)
      const [exists, revoked, instId, holder, issuerActive] = await c.credentialStatus(hash)
      return { source: 'ethers', exists, revoked, inst_id: Number(instId), issuer_active: issuerActive }
    } catch { /* fall through */ }
  }
  return null
}

// Full check of a holder's package without trusting the Alma server.
export async function checkPackageInBrowser(pkg) {
  const leaf = leafOf(pkg.record, pkg.salt)
  const out = { leaf, steps: [], checks: {} }
  if (pkg.proof) {
    const { root, steps } = climb(leaf, pkg.proof)
    out.steps = steps; out.computedRoot = root
    out.checks.merkle_proof = root.toLowerCase() === (pkg.root || '').toLowerCase()
    const st = await chainBatch(pkg.root)
    out.source = st.source
    Object.assign(out.checks, { on_chain: st.exists, batch_not_revoked: !st.revoked, issuer_active: st.issuer_active })
  } else {
    const st = await chainCredential(leaf)
    out.source = st?.source || 'unavailable'
    if (st) Object.assign(out.checks, { on_chain: st.exists, not_revoked: !st.revoked, issuer_active: st.issuer_active })
    else out.checks.on_chain = null
  }
  out.valid = Object.values(out.checks).every((v) => v === true)
  return out
}
