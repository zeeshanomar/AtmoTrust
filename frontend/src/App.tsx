import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { State, User, Variable } from './types'
import SimulationLab from './SimulationLab'
import { Landing, Login } from './PublicPages'
import { AuthorityBell, AuthorityTasks, EmailAlerts, EmployeeTasks, ModelInformation, request, StationsEmployees } from './PortalExtras'
import { evidenceConfidence, FlatMeter, severityLevel } from './Meters'

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const WS = (import.meta.env.VITE_WS_BASE_URL || `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`).replace(/\/$/, '')
const variables: Variable[] = ['temperature_c', 'pressure_hpa', 'humidity_pct']
const names: Record<Variable, string> = { temperature_c: 'Temperature', pressure_hpa: 'Pressure', humidity_pct: 'Humidity' }
const units: Record<Variable, string> = { temperature_c: '°C', pressure_hpa: 'hPa', humidity_pct: '%' }
const colors = ['#075e9e', '#6e55a1', '#c17214', '#458676', '#ad5462', '#7c5a31', '#37769c', '#8d6591']
const shortTime = (s: string | null) => s ? new Date(s).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC' : 'N/A'
const label = (s: string) => s.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
const valueText = (v: number | null | undefined, unit = '') => v == null ? 'N/A' : `${v.toFixed(1)}${unit ? ` ${unit}` : ''}`

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}/api/v1${path}`, { ...init, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: string | { loc?: (string | number)[]; msg?: string }[] }
    const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map(item => `${item.loc?.at(-1) ?? 'Field'}: ${item.msg ?? 'invalid'}`).join('; ') : `Request failed (${res.status})`
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

function useRun() {
  const [state, setState] = useState<State | null>(null)
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'reconnecting'>('connecting')
  const [error, setError] = useState('')
  useEffect(() => {
    let closed = false
    let socket: WebSocket | null = null
    let timeout: number | undefined
    let attempts = 0
    const apply = (incoming: State) => setState(previous => {
      if (previous && incoming.run_id !== previous.run_id) return incoming
      if (previous && (incoming.generation < previous.generation || (incoming.generation === previous.generation && incoming.state_version <= previous.state_version))) return previous
      return incoming
    })
    const connect = (runId: string) => {
      if (closed) return
      socket = new WebSocket(`${WS}/api/v1/runs/${runId}/ws?contract_version=2.0.0`)
      socket.onopen = async () => {
        attempts = 0
        setConnection('connected')
        try { apply(await api<State>(`/runs/${runId}/state`)) } catch (e) { setError(String(e)) }
      }
      socket.onmessage = event => {
        const message = JSON.parse(event.data) as { state?: State }
        if (message.state) apply(message.state)
      }
      socket.onclose = () => {
        if (closed) return
        setConnection('reconnecting')
        timeout = window.setTimeout(async () => {
          try {
            const current = await api<State>('/runs', { method: 'POST' })
            apply(current)
            connect(current.run_id)
          } catch { connect(runId) }
        }, Math.min(10000, 500 * 2 ** attempts++))
      }
    }
    api<State>('/runs', { method: 'POST' }).then(initial => {
      if (closed) return
      apply(initial)
      setError('')
      connect(initial.run_id)
    }).catch(e => { if (!closed) { setError(String(e)); setConnection('reconnecting'); timeout = window.setTimeout(() => location.reload(), 4000) } })
    return () => { closed = true; socket?.close(); if (timeout) window.clearTimeout(timeout) }
  }, [])
  const mutate = useCallback(async (path: string, init: RequestInit) => {
    setError('')
    try {
      const next = await api<State>(path, init)
      setState(previous => previous && (next.generation < previous.generation || (next.generation === previous.generation && next.state_version < previous.state_version)) ? previous : next)
      return next
    } catch (e) { setError(String(e)); throw e }
  }, [])
  return { state, connection, error, mutate, clearError: () => setError('') }
}

function ObservationChart({ state, variable, selected, investigation = false }: { state: State; variable: Variable; selected: string; investigation?: boolean }) {
  const data = useMemo(() => {
    const rows = state.recent_observations.filter(o => o.variable === variable && o.source_mode === state.source_mode)
    const last = [...new Set(rows.map(o => o.sequence))].slice(-60)
    return last.map(sequence => {
      const group = rows.filter(o => o.sequence === sequence)
      const point: Record<string, number | string | null> = { sequence, time: group[0] ? shortTime(group[0].source_timestamp) : String(sequence) }
      group.forEach(o => { point[o.station_id] = o.value })
      if (investigation) {
        const observation = group.find(o => o.station_id === selected)
        const assessment = state.recent_assessments.find(a => a.sample_id === observation?.sample_id)
        point.expected = assessment?.expected_value ?? null
        point.peer = assessment?.peer_value ?? null
      }
      return point
    })
  }, [state.recent_observations, state.recent_assessments, state.source_mode, variable, investigation, selected])
  return <div className="chart-box" aria-label={`${names[variable]} history chart`}>
    <div className="panel-head"><h3>{names[variable]}</h3><span>{units[variable]} · latest {data.at(-1)?.time ?? 'N/A'}</span></div>
    {data.length === 0 ? <p className="empty">Waiting for backend observations.</p> : <ResponsiveContainer width="100%" height={205}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
        <CartesianGrid stroke="#e5eaf0" strokeDasharray="3 4" />
        <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={42} />
        <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
        <Tooltip formatter={(value, name) => [value == null ? 'N/A' : `${Number(value).toFixed(2)} ${units[variable]}`, name]} />
        {investigation ? <>
          <Line dataKey={selected} name="Observed" stroke="#075e9e" strokeWidth={2.4} dot={false} connectNulls={false} isAnimationActive={false} />
          <Line dataKey="expected" name="Expected" stroke="#c17214" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={false} />
          <Line dataKey="peer" name="Peer median" stroke="#458676" strokeWidth={1.8} dot={false} connectNulls={false} isAnimationActive={false} />
          <Legend />
        </> : state.stations.map((s, i) => <Line key={s.station_id} dataKey={s.station_id} name={s.name} stroke={colors[i % colors.length]} strokeWidth={s.station_id === selected ? 3.2 : 1.1} strokeOpacity={s.station_id === selected ? 1 : 0.35} dot={false} connectNulls={false} isAnimationActive={false} />)}
        {typeof data.at(-1)?.[selected] === 'number' && <ReferenceDot x={data.at(-1)?.time ?? undefined} y={Number(data.at(-1)?.[selected])} r={5} fill="#075e9e" stroke="#fff" strokeWidth={2} />}
      </LineChart>
    </ResponsiveContainer>}
  </div>
}

function MapFocus({ state, selected }: { state: State; selected: string }) {
  const map = useMap()
  const mounted = useRef(false)
  const networkKey = state.stations.map(s => `${s.station_id}:${s.latitude}:${s.longitude}`).join('|')
  useEffect(() => {
    if (!state.stations.length) return
    map.fitBounds(state.stations.map(s => [s.latitude, s.longitude] as [number, number]), { padding: [28, 28], maxZoom: 11 })
  }, [map, networkKey])
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    const station = state.stations.find(s => s.station_id === selected)
    if (station) map.flyTo([station.latitude, station.longitude], 11, { duration: 0.35 })
  }, [map, selected, networkKey])
  return null
}

function StationMap({ state, selected, onSelect, onInvestigate }: { state: State; selected: string; onSelect: (id: string) => void; onInvestigate: () => void }) {
  const [tiles, setTiles] = useState(true)
  const selectedStation = state.stations.find(s => s.station_id === selected)
  return <section className="panel map-panel">
    <div className="panel-head"><h3>Monitoring Network</h3><span>{tiles ? 'Map tiles' : 'Offline coordinate layout'}</span></div>
    <MapContainer center={[state.stations[0].latitude, state.stations[0].longitude]} zoom={10} scrollWheelZoom={false} className="map" zoomControl={false}>
      <MapFocus state={state} selected={selected} />
      {tiles && <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap contributors" eventHandlers={{ tileerror: () => setTiles(false) }} />}
      {state.stations.map(station => <CircleMarker key={station.station_id} center={[station.latitude, station.longitude]} radius={station.station_id === selected ? 12 : 9} pathOptions={{ color: station.status === 'fault' ? '#b42332' : station.status === 'review' ? '#b16b08' : station.status === 'genuine' ? '#147448' : '#64748b', fillOpacity: 0.85, weight: station.station_id === selected ? 3 : 1 }} eventHandlers={{ click: () => onSelect(station.station_id) }}>
        <Popup><strong>{station.name}</strong><br />{label(station.status)}<br />{variables.map(v => { const o = state.recent_observations.findLast(row => row.station_id === station.station_id && row.variable === v); return <span key={v}>{names[v]}: {valueText(o?.value, units[v])}<br /></span> })}<small>{shortTime(state.source_timestamp)}</small><br /><button onClick={() => { onSelect(station.station_id); onInvestigate() }}>Investigate</button></Popup>
      </CircleMarker>)}
    </MapContainer>
    {selectedStation && <div className="station-focus"><span><strong>{selectedStation.name}</strong> · {label(selectedStation.status)}<small>{variables.map(v => `${names[v]} ${valueText(state.recent_observations.findLast(o => o.station_id === selected && o.variable === v)?.value, units[v])}`).join(' · ')}</small></span><button className="link" onClick={onInvestigate}>View Station →</button></div>}
    {!tiles && <p className="muted">Map tiles unavailable. Markers retain geographic coordinates.</p>}
  </section>
}

function CommandCentre({ state, selected, select, navigate }: { state: State; selected: string; select: (id: string) => void; navigate: (page: string) => void }) {
  if (!state.stations.length) return <section className="panel loading"><h1>No assigned stations</h1><p>Ask an authority operator to assign your account to a station/pole.</p></section>
  const faults = state.stations.filter(s => s.status === 'fault').length
  const reviews = state.stations.filter(s => s.status === 'review').length
  return <>
    <div className="page-head"><div><p className="eyebrow">NETWORK OVERVIEW</p><h1>Command Centre</h1><p>{state.stations.length} monitored gridded locations · {label(state.source_mode)} data</p></div><span className="timestamp">Frame {state.sequence} · Source time {shortTime(state.source_timestamp)}</span></div>
    <div className="summary-grid">
      {[['Monitored locations', state.stations.length], ['Likely faults', faults], ['Needs review', reviews], ['Open maintenance items', state.maintenance_items.length]].map(([name, value]) => <div className="summary-card" key={name}><span>{name}</span><strong>{value}</strong></div>)}
    </div>
    <div className="two-col"><StationMap state={state} selected={selected} onSelect={select} onInvestigate={() => navigate('investigation')} /><section className="panel"><div className="panel-head"><h3>Recent incidents</h3><span>{state.active_incidents.length} total</span></div>{state.active_incidents.length ? state.active_incidents.slice(-6).reverse().map(i => <button className="alert-row" key={i.incident_id} onClick={() => { select(i.station_id); navigate('investigation') }}><span className={`status-dot ${i.severity}`} /><span><strong>{i.station_id} · {names[i.variable]}</strong><small>{label(i.fault_type)} · {label(i.severity)} · {shortTime(i.last_seen_at)}</small></span><b>Investigate →</b></button>) : <p className="empty">No incidents in this run.</p>}</section></div>
    <div className="chart-grid">{variables.map(v => <ObservationChart key={v} state={state} variable={v} selected={selected} />)}</div>
    <div className="two-col"><section className="panel"><div className="panel-head"><h3>Stations</h3><span>Select to focus map and charts</span></div><div className="table-wrap"><table><thead><tr><th>Station</th><th>Temperature</th><th>Pressure</th><th>Humidity</th><th>Status</th><th></th></tr></thead><tbody>{state.stations.map(s => <tr key={s.station_id} onClick={() => select(s.station_id)} className={`clickable ${s.station_id === selected ? 'selected-row' : ''}`}><td><strong>{s.name}</strong><small>{s.station_id}</small></td>{variables.map(v => <td key={v}>{valueText(state.recent_observations.findLast(o => o.station_id === s.station_id && o.variable === v)?.value, units[v])}</td>)}<td><span className={`pill ${s.status}`}>{label(s.status)}</span></td><td><button className="link" onClick={e => { e.stopPropagation(); select(s.station_id); navigate('investigation') }}>Investigate →</button></td></tr>)}</tbody></table></div></section><section className="panel"><div className="panel-head"><h3>Maintenance priority</h3><button className="link" onClick={() => navigate('maintenance')}>View all →</button></div>{state.maintenance_items.length ? state.maintenance_items.slice(0, 4).map(i => <div className="priority-row" key={i.incident_id}><span><strong>{i.station_id} · {names[i.variable]}</strong><small>{label(i.fault_type)} · Health {i.health_score ?? 'N/A'}</small></span><b>{i.maintenance_priority}</b></div>) : <p className="empty">No open maintenance issues.</p>}</section></div>
  </>
}

function Investigation({ state, selected, setSelected, variable, setVariable, act }: { state: State; selected: string; setSelected: (v: string) => void; variable: Variable; setVariable: (v: Variable) => void; act: (id: string, action: string) => void }) {
  const assessment = state.latest_assessments.find(a => a.station_id === selected && a.variable === variable)
  const observation = state.recent_observations.findLast(o => o.station_id === selected && o.variable === variable)
  const incident = state.active_incidents.findLast(i => i.station_id === selected && i.variable === variable && i.status !== 'resolved')
  const health = state.sensor_health.find(h => h.station_id === selected && h.variable === variable)
  return <>
    <div className="page-head"><div><p className="eyebrow">SENSOR EVIDENCE</p><h1>Location Investigation</h1><p>Explain the current observation using causal and peer context.</p></div></div>
    <div className="station-chips" aria-label="Monitoring location">{state.stations.map(station => <button key={station.station_id} className={selected === station.station_id ? 'active' : ''} aria-pressed={selected === station.station_id} onClick={() => setSelected(station.station_id)}>{station.name}<small>{station.station_id}</small></button>)}</div>
    <div className="tabs" role="tablist">{variables.map(v => <button role="tab" aria-selected={v === variable} className={v === variable ? 'active' : ''} key={v} onClick={() => setVariable(v)}>{names[v]}</button>)}</div>
    <section className="panel assessment-overview"><div className="panel-head"><h3>Observation assessment</h3><span>{label(assessment?.assessment_status ?? 'unavailable')}</span></div>
      <div className="assessment-grid"><div className="assessment-decision"><FlatMeter label="Observation Trust" value={assessment?.trust_score} display={assessment?.trust_score == null ? undefined : `${assessment.trust_score}/100`} tone={assessment?.decision === 'likely_fault' ? 'danger' : assessment?.decision === 'needs_review' ? 'caution' : 'good'} /><span className={`pill ${assessment?.decision ?? 'unknown'}`}>{assessment ? label(assessment.decision) : 'Unknown'}</span></div>
        <div className="assessment-details"><FlatMeter label="Severity" value={severityLevel(assessment?.severity)} max={4} display={assessment ? `${label(assessment.severity)} · ${severityLevel(assessment.severity)}/4` : undefined} tone={assessment?.severity === 'critical' || assessment?.severity === 'high' ? 'danger' : assessment?.severity === 'medium' ? 'caution' : 'neutral'} /><div className="assessment-facts"><span>Evidence Confidence <b>{evidenceConfidence(assessment?.confidence, assessment?.assessment_status)}</b></span><span>Probable pattern <b>{assessment?.fault_type && assessment.fault_type !== 'unknown' ? label(assessment.fault_type) : 'Unknown'}</b></span></div></div></div>
      {assessment?.assessment_status === 'insufficient_context' && <p className="muted">Insufficient context: genuine live history is still accumulating. Trust remains N/A.</p>}
    </section>
    <section className="panel evidence-panel"><div className="panel-head"><h3>Why the system decided this</h3><span>Measured backend evidence</span></div><p>{assessment?.explanation || 'No complete assessment is available for this observation.'}</p><div className="evidence-grid">{assessment?.evidence.length ? assessment.evidence.map((e, i) => <div className="evidence" key={`${e.kind}-${i}`}><span className={`evidence-sign ${e.support < 0 ? 'negative' : 'positive'}`}>{e.support < 0 ? '−' : '+'}</span><div><strong>{e.label}</strong><p>{e.detail}</p></div></div>) : <p className="empty">No evidence available.</p>}</div></section>
    <div className="metric-grid"><div className="metric"><span>Observed</span><strong>{valueText(observation?.value, units[variable])}</strong><small>{observation?.is_test_overlay ? 'Test copy · ' : ''}{observation?.source_name ?? 'N/A'}</small></div><div className="metric"><span>Expected</span><strong>{valueText(assessment?.expected_value, units[variable])}</strong><small>Causal baseline</small></div><div className="metric"><span>Peer median</span><strong>{valueText(assessment?.peer_value, units[variable])}</strong><small>Nearby locations</small></div><div className="metric"><FlatMeter label="Sensor Health" value={health?.health_score} display={health?.health_score == null ? undefined : `${health.health_score}/100`} tone={health?.health_status === 'degrading' ? 'danger' : health?.health_status === 'watch' ? 'caution' : 'good'} /><small>{label(health?.health_status ?? 'unknown')}</small></div></div>
    <div className="two-col"><section className="panel"><ObservationChart state={state} variable={variable} selected={selected} investigation /><p className="muted">Source timestamp {shortTime(observation?.source_timestamp ?? null)} · Missing observations remain chart gaps. Expected and peer values come from backend assessments.</p></section><section className="panel"><div className="panel-head"><h3>Operator review</h3><span>{incident ? label(incident.status) : 'No active incident'}</span></div><p>{assessment?.resolution || incident?.recommendation || 'No action required for the selected variable.'}</p><div className="button-row"><button disabled={!incident} onClick={() => incident && act(incident.incident_id, 'acknowledge')}>Acknowledge</button><button disabled={!incident} onClick={() => incident && act(incident.incident_id, 'confirm_genuine')}>Confirm Genuine</button><button disabled={!incident} onClick={() => incident && act(incident.incident_id, 'confirm_fault')}>Confirm Fault</button></div><p className="muted">Human review is recorded separately from the model assessment.</p></section></div>
  </>
}

function Maintenance({ state, act }: { state: State; act: (id: string, action: string) => void }) {
  const [selectedId, setSelectedId] = useState('')
  const item = state.maintenance_items.find(i => i.incident_id === selectedId) ?? state.maintenance_items[0]
  const health = state.sensor_health.find(h => h.station_id === item?.station_id && h.variable === item.variable)
  return <>
    <div className="page-head"><div><p className="eyebrow">OPERATIONS</p><h1>Maintenance Centre</h1><p>Ranked active issues and operator history.</p></div><span className="timestamp">{state.maintenance_items.length} active issues</span></div>
    <section className="panel"><div className="panel-head"><h3>Priority queue</h3><span>Priority 0–100</span></div>{state.maintenance_items.length ? <div className="table-wrap"><table><thead><tr><th>Priority</th><th>Station / variable</th><th>Pattern</th><th>Severity</th><th>Sensor Health</th><th>Duration</th><th>Status</th></tr></thead><tbody>{state.maintenance_items.map(i => <tr key={i.incident_id} className={`clickable ${item?.incident_id === i.incident_id ? 'selected-row' : ''}`} onClick={() => setSelectedId(i.incident_id)}><td><strong>{i.maintenance_priority}</strong></td><td>{i.station_id}<small>{names[i.variable]}</small></td><td>{label(i.fault_type)}</td><td>{label(i.severity)}</td><td>{i.health_score ?? 'N/A'}</td><td>{i.duration_samples} samples</td><td>{label(i.status)}</td></tr>)}</tbody></table></div> : <p className="empty">No open maintenance issues.</p>}</section>
    <div className="two-col"><section className="panel"><div className="panel-head"><h3>Selected issue</h3><span>{item?.station_id ?? 'None'}</span></div>{item ? <><p><strong>{item.station_id} · {names[item.variable]}</strong></p><p>{item.recommendation}</p><p className="muted">Opened {shortTime(item.opened_at)} · Last seen {shortTime(item.last_seen_at)}</p><FlatMeter label="Sensor Health" value={health?.health_score} display={health?.health_score == null ? undefined : `${health.health_score}/100 · ${label(health.health_status)}`} tone={health?.health_status === 'degrading' ? 'danger' : health?.health_status === 'watch' ? 'caution' : 'good'} /><div className="trend" aria-label="Sensor Health recent trend">{health?.trend.map((v, i) => <span key={i} style={{ height: `${Math.max(5, v)}%` }} title={`${v}`} />)}</div><div className="button-row"><button onClick={() => act(item.incident_id, 'acknowledge')}>Acknowledge</button><button className="primary" onClick={() => { if (window.confirm('Record maintenance complete and resolve this workflow item?')) act(item.incident_id, 'maintenance_complete') }}>Maintenance Complete</button></div></> : <p className="empty">Select an issue when one appears.</p>}</section><section className="panel"><div className="panel-head"><h3>Operator action history</h3><span>Current run</span></div>{state.operator_actions.length ? state.operator_actions.slice(-10).reverse().map(a => <div className="history-row" key={a.action_id}><strong>{label(a.action)}</strong><small>{a.incident_id.slice(0, 8)} · {shortTime(a.timestamp)}</small></div>) : <p className="empty">No operator actions recorded.</p>}</section></div>
  </>
}

function Portal({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { state, connection, error, mutate, clearError } = useRun()
  const [page, setPage] = useState(user.role === 'authority' ? 'command' : 'dashboard')
  const [selected, setSelected] = useState('CHD-01')
  const [variable, setVariable] = useState<Variable>('temperature_c')
  const [focusedTaskId, setFocusedTaskId] = useState<string | null>(null)
  useEffect(() => { if (state?.stations.length && !state.stations.some(s => s.station_id === selected)) setSelected(state.stations[0].station_id) }, [state?.stations, selected])
  const command = (cmd: string, extras: object = {}) => { if (state) void mutate(`/runs/${state.run_id}/commands`, { method: 'POST', body: JSON.stringify({ command: cmd, ...extras }) }).catch(() => {}) }
  const act = (id: string, action: string) => { if (state) void mutate(`/runs/${state.run_id}/incidents/${id}/actions`, { method: 'POST', body: JSON.stringify({ action }) }).catch(() => {}) }
  const openNotification = (incidentId: string) => { setFocusedTaskId(incidentId); setPage('maintenance') }
  const authorityNav = [['command', 'Command Centre'], ['investigation', 'Investigation'], ['maintenance', 'Maintenance'], ['simulation', 'Simulation Lab'], ['admin', 'Stations & Employees'], ['emails', 'Email Alerts'], ['model', 'Model Information']]
  const employeeNav = [['dashboard', 'Dashboard'], ['tasks', 'Assigned Tasks'], ['details', 'Task Details'], ['history', 'Maintenance History']]
  return <div className="app portal"><aside className="sidebar"><button className="brand" onClick={() => setPage(user.role === 'authority' ? 'command' : 'dashboard')}><img src="/atmotrust.svg" alt="" /><span>AtmoTrust<small>Weather data assurance</small></span></button><nav aria-label="Main navigation">{(user.role === 'authority' ? authorityNav : employeeNav).map(([key, name]) => <Fragment key={key}>{key === 'admin' && <span className="nav-section-label">Administration</span>}<button className={`${page === key ? 'current' : ''} ${['admin', 'emails', 'model'].includes(key) ? 'secondary' : ''}`} onClick={() => setPage(key)}>{name}</button></Fragment>)}</nav><div className="sidebar-user"><strong>{user.display_name}</strong><span className="role-badge">{label(user.role)}</span><button onClick={onLogout}>Logout →</button></div></aside><div className="portal-body"><header className="portal-topbar"><span>{user.role === 'authority' ? 'Authority Portal' : 'Employee Portal'}</span><div>{user.role === 'authority' && <AuthorityBell stateVersion={state?.state_version ?? 0} onOpenIncident={openNotification} />}<strong>{user.display_name}</strong><span className="role-badge">{label(user.role)}</span><button onClick={onLogout}>Logout</button></div></header>
    <div className="status-strip"><div><span className={`status-dot ${state?.status ?? 'unknown'}`} /><strong>{state ? `${label(state.status)} · ${state.speed}×` : 'Backend starting'}</strong><span>{state ? `${label(state.source_mode)} · ${state.source_status.find(s => s.source_mode === state.source_mode)?.source_name}` : 'Waiting for snapshot'}</span><span className={connection === 'connected' ? 'connected' : 'stale'}>● {connection === 'connected' ? 'Updates connected' : 'Updates reconnecting · data may be stale'}</span><span>Source {shortTime(state?.source_timestamp ?? null)}</span></div><div className="strip-actions">{user.role === 'authority' ? <><button disabled={!state} onClick={() => command(state?.status === 'running' ? 'pause' : 'play')}>{state?.status === 'running' ? 'Pause' : 'Play'}</button><button disabled={!state} onClick={() => { if (window.confirm('Reset this run?')) command('reset') }}>Reset</button></> : <><span title="Authority access required"><button className="locked" aria-disabled="true" onClick={() => alert('Authority access required')}>🔒 Replay control</button></span><span title="Authority access required"><button className="locked" aria-disabled="true" onClick={() => alert('Authority access required')}>🔒 Reset</button></span></>}</div></div>
    {error && <div className="error" role="alert">{error}<button onClick={clearError} aria-label="Dismiss error">×</button></div>}
    <main>{!state ? <section className="panel loading"><h1>Connecting to AtmoTrust</h1><p>Waiting for the backend. The page will retry automatically.</p></section> : user.role === 'authority' ? <>{page === 'command' && <CommandCentre state={state} selected={selected} select={setSelected} navigate={setPage} />}{page === 'investigation' && <Investigation state={state} selected={selected} setSelected={setSelected} variable={variable} setVariable={setVariable} act={act} />}{page === 'maintenance' && <><Maintenance state={state} act={act} /><AuthorityTasks state={state} focusIncidentId={focusedTaskId} /></>}{page === 'simulation' && <SimulationLab state={state} command={command} mutate={mutate} />}{page === 'admin' && <StationsEmployees state={state} />}{page === 'emails' && <EmailAlerts state={state} />}{page === 'model' && <ModelInformation />}</> : <>{page === 'dashboard' && <><CommandCentre state={state} selected={selected} select={setSelected} navigate={() => setPage('tasks')} /><section className="panel locked-panel" title="Authority access required"><h3>🔒 Authority controls</h3><p>Replay, injection, station management, incident confirmation, email settings and model administration require authority access.</p><div className="button-row">{['Simulation Lab', 'Reset replay', 'Manage stations', 'Confirm fault'].map(name => <button key={name} className="locked" aria-disabled="true" onClick={() => alert('Authority access required')}>🔒 {name}</button>)}</div></section></>}{['tasks', 'details', 'history'].includes(page) && <EmployeeTasks state={state} page={page} />}</>}</main>
    <footer>AtmoTrust · {state?.source_status.find(s => s.source_mode === state.source_mode)?.provenance_type ?? 'Source pending'} · Scores are evidence indices, not probabilities. Logical locations are not physical AWS stations.</footer>
  </div></div>
}

export default function App() {
  const [path, setPath] = useState(location.pathname)
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(true)
  const navigate = useCallback((next: string) => { history.pushState({}, '', next); setPath(next.split('?')[0]); window.scrollTo(0, 0) }, [])
  useEffect(() => { const change = () => setPath(location.pathname); addEventListener('popstate', change); return () => removeEventListener('popstate', change) }, [])
  useEffect(() => { void request<User>('/auth/me').then(setUser).catch(() => setUser(null)).finally(() => setChecking(false)) }, [])
  const logout = async () => { await request('/auth/logout', { method: 'POST' }).catch(() => {}); setUser(null); navigate('/') }
  if (checking && (path === '/authority' || path === '/employee')) return <div className="loading">Checking session…</div>
  if (path === '/authority' || path === '/employee') {
    if (!user) { queueMicrotask(() => navigate('/login')); return null }
    if (path !== `/${user.role}`) { queueMicrotask(() => navigate(`/${user.role}`)); return null }
    return <Portal user={user} onLogout={() => void logout()} />
  }
  if (path === '/login') return <Login navigate={navigate} onLogin={next => { setUser(next); navigate(`/${next.role}`) }} />
  return <Landing navigate={navigate} />
}
