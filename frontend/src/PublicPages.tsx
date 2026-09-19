import { useEffect, useState } from 'react'
import type { User } from './types'
import demoCredentials from './demo_accounts.json'

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export function Landing({ navigate }: { navigate: (path: string) => void }) {
  useEffect(() => {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target) } }), { threshold: .12 })
    document.querySelectorAll('.reveal').forEach(element => observer.observe(element))
    return () => observer.disconnect()
  }, [])
  return <div className="public-site"><header className="public-nav"><a href="/" className="public-brand" onClick={e => { e.preventDefault(); navigate('/') }}><img src="/atmotrust.svg" alt="" /><span>AtmoTrust<small>Weather data assurance</small></span></a><button className="primary" onClick={() => navigate('/login')}>Login →</button></header>
    <main className="public-main"><section className="hero"><div className="hero-copy"><p className="eyebrow">WEATHER NETWORK OPERATIONS</p><h1>Know when a weather reading can be trusted.</h1><p>AtmoTrust compares each observation with its history, neighbouring locations and learned normal patterns. It helps teams investigate sensor faults and coordinate maintenance with clear evidence.</p><div className="button-row"><button className="primary" onClick={() => navigate('/login')}>Open AtmoTrust</button><a href="#how-it-works">See how it works ↓</a></div><p className="hero-note">Historical replay uses clearly labelled gridded weather data. Live values come from Open-Meteo Current Weather.</p></div><div className="weather-visual" aria-label="Illustration of stations sending signals to an analysis centre"><div className="weather-grid" /><div className="signal signal-one" /><div className="signal signal-two" /><div className="signal signal-three" /><div className="visual-core"><img src="/atmotrust.svg" alt="" /><span>Trust Engine<small>Evidence in context</small></span></div><div className="visual-station one"><span className="station-icon">⌁</span> Station 01<small>Reading received</small></div><div className="visual-station two"><span className="station-icon">⌁</span> Station 02<small>Peer comparison</small></div><div className="visual-station three"><span className="station-icon">⌁</span> Station 03<small>Sensor anomaly</small><b className="anomaly-dot" /></div></div></section>
      <section id="how-it-works" className="public-section reveal"><p className="eyebrow">HOW ATMOTRUST WORKS</p><h2>From observation to action</h2><div className="public-steps"><article><span>01</span><h3>Observe</h3><p>Collect temperature, pressure and humidity from each logical location with source and time attached.</p></article><article><span>02</span><h3>Compare</h3><p>Check physical limits, causal history, nearby peers and saved anomaly models.</p></article><article><span>03</span><h3>Explain</h3><p>Show Trust Score, probable fault type, evidence confidence and the measured evidence behind a decision.</p></article><article><span>04</span><h3>Maintain</h3><p>Open an assigned task, alert the station contact and track repair progress across both portals.</p></article></div></section>
      <section className="public-section public-features reveal"><p className="eyebrow">OPERATIONS</p><h2>One view across the network</h2><div className="feature-grid"><article><h3>Live network map</h3><p>See stations and their current status with connected charts and investigations.</p></article><article><h3>Fault investigations</h3><p>Compare observed, expected and peer values alongside an evidence trail.</p></article><article><h3>Controlled simulation</h3><p>Replay historical weather and apply six repeatable sensor fault patterns.</p></article><article><h3>Maintenance handoff</h3><p>Assign employees to poles, send one alert per incident and track resolution.</p></article></div></section>
      <section className="public-cta reveal"><div><p className="eyebrow">READY TO INVESTIGATE?</p><h2>Turn uncertain data into a clear maintenance decision.</h2></div><button className="primary" onClick={() => navigate('/login')}>Login to AtmoTrust →</button></section></main><footer className="public-footer">AtmoTrust · Historical and current gridded weather are labelled by source. Logical locations are not physical AWS stations.</footer></div>
}

export function Login({ navigate, onLogin }: { navigate: (path: string) => void; onLogin: (user: User) => void }) {
  const [role, setRole] = useState<'authority' | 'employee'>('authority')
  const [username, setUsername] = useState<string>(demoCredentials.authority.username)
  const [password, setPassword] = useState<string>(demoCredentials.authority.password)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const selectRole = (selected: 'authority' | 'employee') => {
    setRole(selected)
    setUsername(demoCredentials[selected].username)
    setPassword(demoCredentials[selected].password)
    setError('')
  }
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/api/v1/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ username, password, role }) })
      if (!response.ok) throw new Error('Incorrect username, password, or role')
      onLogin(await response.json() as User)
    } catch (cause) { setError(String(cause)) } finally { setBusy(false) }
  }
  return <div className="login-page"><header className="public-nav"><button className="public-brand" onClick={() => navigate('/')}><img src="/atmotrust.svg" alt="" /><span>AtmoTrust<small>Weather data assurance</small></span></button><button onClick={() => navigate('/')}>← Home</button></header><main className="login-main"><div className="login-intro"><p className="eyebrow">PUBLIC DEMO ACCESS</p><h1>Welcome to AtmoTrust</h1><p>Both demo accounts are shown below. Select a role to fill its login details.</p></div><div className="role-cards"><button className={`role-card ${role === 'authority' ? 'selected' : ''}`} onClick={() => selectRole('authority')} aria-pressed={role === 'authority'}><span>◈</span><strong>Authority Login</strong><small>Network control, investigations and management</small><span className="demo-credentials">Username: <code>{demoCredentials.authority.username}</code><br />Password: <code>{demoCredentials.authority.password}</code></span></button><button className={`role-card ${role === 'employee' ? 'selected' : ''}`} onClick={() => selectRole('employee')} aria-pressed={role === 'employee'}><span>◇</span><strong>Employee Login</strong><small>Assigned maintenance and task history</small><span className="demo-credentials">Username: <code>{demoCredentials.employee.username}</code><br />Password: <code>{demoCredentials.employee.password}</code></span></button></div><form className="login-form" onSubmit={submit}><h2>{role === 'authority' ? 'Authority' : 'Employee'} sign in</h2><label>Username<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="warning" role="alert">{error}</p>}<button className="primary" disabled={busy} type="submit">{busy ? 'Signing in…' : 'Sign in →'}</button><p className="muted">These public demo accounts should only be used with demo data.</p></form></main></div>
}
