import { useState } from 'react'
import { HashRouter, Routes, Route, Navigate, NavLink, Link, Outlet, useNavigate, useSearchParams } from 'react-router-dom'
import { LayoutDashboard, Users, FilePlus2, FileText, Layers, Wallet, Share2, UserCog, Search, Radar, ListTree, Brain, Scale, Gauge, LogOut, Building2, Cpu, Menu, X } from 'lucide-react'
import { AuthProvider, useAuth, Logo, Field, Alert, useAction, Badge } from './ui'
import { api } from './lib'
import Landing from './Landing'
import Verify from './Verify'
import { OwnerOverview, OwnerDirectory } from './pages/owner'
import { InstOverview, InstStudents, InstIssue, InstRecords, InstAnchors, InstAccess } from './pages/institution'
import { StudentRecords, StudentSharing, StudentData } from './pages/student'
import { EmployerCheck } from './pages/employer'
import { RegDashboard, RegAlerts, RegEvents, RegModel, RegCompliance, RegPerformance } from './pages/regulator'

const ROLE_LABEL = { platform_admin: 'Platform owner', university_admin: 'Institution', student: 'Student', employer: 'Employer', regulator: 'Regulator' }
const NAV = {
  platform_admin: [['overview', 'System', LayoutDashboard], ['directory', 'Directory', Users], ['dashboard', 'Dashboard', Building2], ['alerts', 'AI alerts', Radar], ['events', 'Ledger events', ListTree], ['model', 'AI model', Brain], ['compliance', 'Audit and privacy', Scale], ['performance', 'Performance', Gauge]],
  university_admin: [['overview', 'Overview', LayoutDashboard], ['students', 'Students', Users], ['issue', 'Issue records', FilePlus2], ['records', 'Records', FileText], ['anchors', 'Anchors', Layers], ['access', 'Access rules', UserCog]],
  student: [['records', 'My records', Wallet], ['sharing', 'Sharing', Share2], ['data', 'My data', FileText]],
  employer: [['check', 'Check a record', Search]],
  regulator: [['dashboard', 'Dashboard', LayoutDashboard], ['alerts', 'AI alerts', Radar], ['events', 'Ledger events', ListTree], ['model', 'AI model', Brain], ['compliance', 'Audit and privacy', Scale], ['performance', 'Performance', Gauge]],
}

function Login() {
  const { login, user } = useAuth(); const nav = useNavigate(); const [sp] = useSearchParams()
  const [tab, setTab] = useState(sp.get('tab') || 'signin')
  const [f, setF] = useState({ email: '', password: '', name: '', invite: '' }); const [done, setDone] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const act = useAction(async () => {
    if (tab === 'signin') { await login(f.email, f.password); nav('/app') }
    else if (tab === 'employer') { await api('/auth/employer', { method: 'POST', body: { email: f.email, name: f.name, password: f.password }, token: null }); setDone('Thank you. Your account is waiting for approval. You can sign in once the platform team approves it.') }
    else { await api('/auth/activate', { method: 'POST', body: { email: f.email, invite: f.invite, password: f.password }, token: null }); setDone('Your account is ready. You can sign in now.'); setTab('signin') }
  })
  if (user) return <Navigate to="/app" replace />
  const tabs = [['signin', 'Sign in'], ['employer', 'Employer sign-up'], ['activate', 'Student activation']]
  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1fr]">
      <div className="grid-bg relative hidden bg-ink-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Link to="/"><Logo size={32} /></Link>
        <div><h2 className="font-display text-4xl font-semibold leading-tight">An email and a password.<br /><span className="text-brand-400">That is all you need.</span></h2><p className="mt-4 max-w-md text-white/65">Keys and transactions are handled for you. Open the Technical view after signing in if you want to see them.</p></div>
        <p className="text-xs text-white/40">Prototype for research and demonstration.</p>
      </div>
      <div className="flex items-center justify-center bg-sand-50 p-6">
        <div className="w-full max-w-md">
          <div className="mb-6 lg:hidden"><Logo dark /></div>
          <div role="tablist" className="mb-6 flex gap-1 rounded-xl bg-ink-900/8 p-1">
            {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setDone(''); act.setError('') }} className={`flex-1 rounded-lg px-2 py-2 text-xs font-semibold sm:text-sm ${tab === k ? 'bg-white shadow' : 'text-ink-900/60'}`}>{l}</button>)}
          </div>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); act.run() }}>
            <h1 className="font-display text-3xl font-semibold">{tab === 'signin' ? 'Welcome back' : tab === 'employer' ? 'Register as an employer' : 'Activate your student account'}</h1>
            {tab === 'activate' && <p className="text-sm text-ink-900/60">Your institution registered you and gave you an invitation code. Choose a password to finish.</p>}
            {tab === 'employer' && <><p className="text-sm text-ink-900/60">Anyone can check a record without an account. An account lets you ask students for fuller access.</p><Field label="Organisation or your name"><input className="input" value={f.name} onChange={set('name')} required /></Field></>}
            <Field label="Email"><input className="input" type="email" autoComplete="username" value={f.email} onChange={set('email')} required /></Field>
            {tab === 'activate' && <Field label="Invitation code"><input className="input font-mono" value={f.invite} onChange={set('invite')} required /></Field>}
            <Field label={tab === 'signin' ? 'Password' : 'Choose a password'} hint={tab !== 'signin' ? 'At least 8 characters.' : ''}><input className="input" type="password" autoComplete={tab === 'signin' ? 'current-password' : 'new-password'} minLength={tab === 'signin' ? 1 : 8} value={f.password} onChange={set('password')} required /></Field>
            {act.error && <Alert tone="error">{act.error}</Alert>}
            {done && <Alert tone="ok">{done}</Alert>}
            <button className="btn-primary w-full" disabled={act.busy}>{act.busy ? 'One moment…' : tab === 'signin' ? 'Sign in' : tab === 'employer' ? 'Send for approval' : 'Activate account'}</button>
          </form>
          <p className="mt-6 text-center text-sm text-ink-900/60"><Link to="/verify" className="font-medium text-brand-700">Just checking a record? No account needed →</Link></p>
        </div>
      </div>
    </div>
  )
}

function Shell() {
  const { user, logout, tech, setTech } = useAuth(); const [open, setOpen] = useState(false)
  if (!user) return <Navigate to="/login" replace />
  const items = NAV[user.role] || []
  const Side = (
    <nav aria-label="Portal" className="flex h-full flex-col">
      <div className="px-4 py-5"><Link to="/"><Logo size={28} /></Link></div>
      <div className="px-4 pb-3"><Badge tone="teal">{ROLE_LABEL[user.role]}</Badge></div>
      <ul className="flex-1 space-y-0.5 px-2">{items.map(([to, label, Icon]) => <li key={to}><NavLink to={`/app/${to}`} onClick={() => setOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${isActive ? 'bg-brand-500 text-ink-950' : 'text-white/75 hover:bg-white/8 hover:text-white'}`}><Icon className="h-4 w-4" />{label}</NavLink></li>)}</ul>
      <div className="border-t border-white/10 p-4 text-sm text-white/70">
        <label className="mb-3 flex cursor-pointer items-center gap-2 text-xs"><input type="checkbox" checked={tech} onChange={(e) => setTech(e.target.checked)} className="h-4 w-4 accent-teal-400" /><Cpu className="h-3.5 w-3.5" /> Technical view</label>
        <div className="truncate font-medium text-white">{user.name || user.email}</div><div className="truncate text-xs text-white/50">{user.email}</div>
        <button onClick={() => { logout() }} className="mt-3 flex items-center gap-2 text-xs text-white/70 hover:text-white"><LogOut className="h-3.5 w-3.5" /> Sign out</button>
      </div>
    </nav>
  )
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
      <aside className="hidden bg-ink-900 lg:block"><div className="sticky top-0 h-screen">{Side}</div></aside>
      <div className="lg:hidden flex items-center justify-between bg-ink-900 px-4 py-3 text-white"><Logo size={24} /><button aria-label="Menu" onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button></div>
      {open && <div className="bg-ink-900 lg:hidden">{Side}</div>}
      <main className="min-w-0 p-5 sm:p-8"><div className="mx-auto max-w-6xl"><Outlet /></div></main>
    </div>
  )
}

const Home = () => { const { user } = useAuth(); const first = { platform_admin: 'overview', university_admin: 'overview', student: 'records', employer: 'check', regulator: 'dashboard' }[user?.role]; return <Navigate to={`/app/${first}`} replace /> }
const Guard = ({ roles, children }) => { const { user } = useAuth(); return roles.includes(user?.role) ? children : <Alert tone="warn">This page is not part of your role.</Alert> }

export default function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/verify/:id" element={<Verify />} />
          <Route path="/login" element={<Login />} />
          <Route path="/app" element={<Shell />}>
            <Route index element={<Home />} />
            <Route path="overview" element={<Guard roles={['platform_admin', 'university_admin']}><OverviewSwitch /></Guard>} />
            <Route path="directory" element={<Guard roles={['platform_admin']}><OwnerDirectory /></Guard>} />
            <Route path="students" element={<Guard roles={['university_admin']}><InstStudents /></Guard>} />
            <Route path="issue" element={<Guard roles={['university_admin']}><InstIssue /></Guard>} />
            <Route path="records" element={<Guard roles={['university_admin', 'student']}><RecordsSwitch /></Guard>} />
            <Route path="anchors" element={<Guard roles={['university_admin']}><InstAnchors /></Guard>} />
            <Route path="access" element={<Guard roles={['university_admin']}><InstAccess /></Guard>} />
            <Route path="sharing" element={<Guard roles={['student']}><StudentSharing /></Guard>} />
            <Route path="data" element={<Guard roles={['student']}><StudentData /></Guard>} />
            <Route path="check" element={<Guard roles={['employer']}><EmployerCheck /></Guard>} />
            <Route path="dashboard" element={<Guard roles={['regulator', 'platform_admin']}><RegDashboard /></Guard>} />
            <Route path="alerts" element={<Guard roles={['regulator', 'platform_admin']}><RegAlerts /></Guard>} />
            <Route path="events" element={<Guard roles={['regulator', 'platform_admin']}><RegEvents /></Guard>} />
            <Route path="model" element={<Guard roles={['regulator', 'platform_admin']}><RegModel /></Guard>} />
            <Route path="compliance" element={<Guard roles={['regulator', 'platform_admin']}><RegCompliance /></Guard>} />
            <Route path="performance" element={<Guard roles={['regulator', 'platform_admin']}><RegPerformance /></Guard>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  )
}
function OverviewSwitch() { const { user } = useAuth(); return user.role === 'platform_admin' ? <OwnerOverview /> : <InstOverview /> }
function RecordsSwitch() { const { user } = useAuth(); return user.role === 'student' ? <StudentRecords /> : <InstRecords /> }
