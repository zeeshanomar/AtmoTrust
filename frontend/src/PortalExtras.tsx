import { useEffect, useRef, useState } from 'react'
import type { AuthorityNotification, State, Task, User } from './types'
import { evidenceConfidence, FlatMeter, severityLevel } from './Meters'

const API = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}/api/v1${path}`, { ...init, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

type Assignment = { user_id: string; station_id: string; display_name: string; pole_id: string }
type Delivery = { id: string; incident_id: string; station_id: string; recipient: string | null; reason: string; severity: string; subject: string; body: string; status: string; safe_error: string | null; created_at: string }
const label = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())

type NotificationList = { items: AuthorityNotification[]; unread_count: number }

export function AuthorityBell({ stateVersion, onOpenIncident }: { stateVersion: number; onOpenIncident: (incidentId: string) => void }) {
  const [notifications, setNotifications] = useState<NotificationList>({ items: [], unread_count: 0 })
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const timer = useRef<number | null>(null)
  const lastFetch = useRef(0)
  const requestNumber = useRef(0)
  const reload = async () => {
    lastFetch.current = Date.now()
    const number = ++requestNumber.current
    const next = await request<NotificationList>('/authority/notifications')
    if (number === requestNumber.current) setNotifications(next)
  }
  useEffect(() => {
    if (timer.current != null) return
    timer.current = window.setTimeout(() => { timer.current = null; void reload().catch(cause => setError(String(cause))) }, Math.max(0, 500 - (Date.now() - lastFetch.current)))
  }, [stateVersion])
  useEffect(() => () => { if (timer.current != null) window.clearTimeout(timer.current) }, [])
  const markRead = async (notification: AuthorityNotification) => {
    await request(`/authority/notifications/${notification.id}/read`, { method: 'PATCH' })
    await reload()
  }
  const openItem = async (notification: AuthorityNotification) => {
    try { if (!notification.read_at) await markRead(notification) } catch (cause) { setError(String(cause)) }
    setOpen(false)
    onOpenIncident(notification.incident_id)
  }
  const markAll = async () => {
    try { setNotifications(await request<NotificationList>('/authority/notifications/read-all', { method: 'POST' })); setError('') } catch (cause) { setError(String(cause)) }
  }
  return <div className="notification-wrap"><button className="notification-toggle" aria-label={`Authority notifications, ${notifications.unread_count} unread`} aria-expanded={open} onClick={() => setOpen(value => !value)}>🔔<span aria-hidden="true">Notifications</span>{notifications.unread_count > 0 && <b className="notification-badge">{notifications.unread_count > 99 ? '99+' : notifications.unread_count}</b>}</button>
    {open && <div className="notification-panel" role="region" aria-label="Authority notifications"><div className="notification-header"><strong>Employee updates</strong><button className="link" disabled={!notifications.unread_count} onClick={() => void markAll()}>Mark all read</button></div>{error && <p className="warning" role="alert">{error}</p>}<div className="notification-list">{notifications.items.length ? notifications.items.map(item => <div className={`notification-item ${item.read_at ? 'read' : 'unread'}`} key={item.id}><button className="notification-open" onClick={() => void openItem(item)}><strong>{item.title}</strong><span>{item.body}</span><small>{new Date(item.created_at).toLocaleString()} · Open maintenance →</small></button>{!item.read_at && <button className="link notification-read" onClick={() => void markRead(item).catch(cause => setError(String(cause)))}>Mark read</button>}</div>) : <p className="empty">No employee updates yet.</p>}</div></div>}
  </div>
}

export function StationsEmployees({ state }: { state: State }) {
  const [users, setUsers] = useState<User[]>([])
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [selected, setSelected] = useState(state.stations[0]?.station_id ?? '')
  const station = state.stations.find(item => item.station_id === selected)
  const [name, setName] = useState(station?.name ?? '')
  const [pole, setPole] = useState(station?.pole_id ?? '')
  const [email, setEmail] = useState(station?.maintenance_email ?? '')
  const [criticality, setCriticality] = useState(station?.criticality ?? .5)
  const [message, setMessage] = useState('')
  const reload = async () => { const [nextUsers, nextAssignments] = await Promise.all([request<User[]>('/admin/users'), request<Assignment[]>('/admin/assignments')]); setUsers(nextUsers); setAssignments(nextAssignments) }
  useEffect(() => { void reload().catch(error => setMessage(String(error))) }, [])
  useEffect(() => { setName(station?.name ?? ''); setPole(station?.pole_id ?? ''); setEmail(station?.maintenance_email ?? ''); setCriticality(station?.criticality ?? .5) }, [selected, station?.name, station?.pole_id, station?.maintenance_email, station?.criticality])
  const submit = async (fn: () => Promise<unknown>) => { try { await fn(); setMessage('Saved.'); await reload() } catch (error) { setMessage(String(error)) } }
  return <><div className="page-head"><div><p className="eyebrow">NETWORK ADMINISTRATION</p><h1>Stations & Employees</h1><p>Edit pole details, create employees and control station assignments.</p></div></div>{message && <p className="info" role="status">{message}</p>}
    <div className="two-col"><section className="panel"><h3>Station / pole metadata</h3><label>Station<select value={selected} onChange={e => setSelected(e.target.value)}>{state.stations.map(item => <option key={item.station_id} value={item.station_id}>{item.name} · {item.station_id}</option>)}</select></label><div className="form-grid"><label>Name<input value={name} onChange={e => setName(e.target.value)} /></label><label>Pole / asset ID<input value={pole} onChange={e => setPole(e.target.value)} /></label><label>Maintenance email<input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Optional until SMTP is configured" /></label><label>Criticality (0–1)<input type="number" min="0" max="1" step=".1" value={criticality} onChange={e => setCriticality(Number(e.target.value))} /></label></div><button className="primary" onClick={() => void submit(() => request(`/admin/stations/${selected}`, { method: 'PUT', body: JSON.stringify({ name, pole_id: pole, maintenance_email: email || null, criticality }) }))}>Save station</button></section>
      <section className="panel"><h3>Create employee</h3><div className="form-grid"><label>Username<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="off" /></label><label>Display name<input value={displayName} onChange={e => setDisplayName(e.target.value)} /></label><label>Temporary password (12+ characters)<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" /></label></div><button className="primary" disabled={!username || !displayName || password.length < 12} onClick={() => void submit(async () => { await request('/admin/employees', { method: 'POST', body: JSON.stringify({ username, display_name: displayName, password }) }); setPassword(''); setUsername(''); setDisplayName('') })}>Create employee</button><p className="muted">Share the new password privately. It is not displayed again.</p></section></div>
    <section className="panel"><div className="panel-head"><h3>Employee assignments</h3><span>{users.filter(user => user.role === 'employee').length} employees</span></div>{users.filter(user => user.role === 'employee').map(user => <div className="employee-row" key={user.id}><div><strong>{user.display_name}</strong><small>{user.username} · {user.active ? 'Active' : 'Disabled'}</small><button onClick={() => void submit(() => request(`/admin/employees/${user.id}?active=${user.active ? 'false' : 'true'}`, { method: 'PATCH' }))}>{user.active ? 'Disable account' : 'Enable account'}</button></div><div className="assignment-list">{state.stations.map(item => { const checked = assignments.some(row => row.user_id === user.id && row.station_id === item.station_id); return <label key={item.station_id}><input type="checkbox" checked={checked} onChange={e => void submit(() => request('/admin/assignments', { method: 'POST', body: JSON.stringify({ user_id: user.id, station_id: item.station_id, assigned: e.target.checked }) }))} />{item.name} · {item.pole_id}</label> })}</div></div>)}</section></>
}

export function EmailAlerts({ state }: { state: State }) {
  const [rows, setRows] = useState<Delivery[]>([])
  const [message, setMessage] = useState('')
  useEffect(() => { const refresh = () => void request<Delivery[]>('/admin/emails').then(setRows).catch(error => setMessage(String(error))); refresh(); const timer = window.setInterval(refresh, 3000); return () => window.clearInterval(timer) }, [state.state_version])
  const resend = async (id: string) => { try { const delivery = await request<Delivery>(`/admin/emails/${id}/resend`, { method: 'POST' }); setRows(await request<Delivery[]>('/admin/emails')); setMessage(`Alert ${delivery.status}.`) } catch (error) { setMessage(String(error)) } }
  return <><div className="page-head"><div><p className="eyebrow">DELIVERY HISTORY</p><h1>Email Alerts</h1><p>One alert when an incident opens; another only for a severity increase or manual resend.</p></div></div>{message && <p className="info" role="status">{message}</p>}<section className="panel"><h3>Delivery records and development outbox</h3>{rows.length ? rows.map(row => <details className="email-row" key={row.id}><summary><span className={`pill ${row.status}`}>{label(row.status)}</span><strong>{row.subject}</strong><small>{row.recipient || 'No recipient'} · {new Date(row.created_at).toLocaleString()}</small></summary><p>{row.safe_error}</p><pre>{row.body}</pre><button onClick={() => void resend(row.incident_id)}>Resend alert</button></details>) : <p className="empty">No alerts have been created yet. Configure a station contact to receive or queue alerts.</p>}</section></>
}

export function ModelInformation() {
  const [model, setModel] = useState<Record<string, unknown> | null>(null)
  useEffect(() => { void request<Record<string, unknown>>('/admin/model').then(setModel).catch(() => setModel({ status: 'Analysis unavailable' })) }, [])
  const metrics = model?.held_out_metrics as Record<string, unknown> | undefined
  return <><div className="page-head"><div><p className="eyebrow">MODEL TRANSPARENCY</p><h1>Model Information</h1><p>Saved offline training artifacts used for inference during the live application.</p></div></div><section className="panel"><h3>{String(model?.model_type ?? model?.status ?? 'Loading…')}</h3><div className="detail-grid"><span>Version <b>{String(model?.model_version ?? 'N/A')}</b></span><span>Trained <b>{String(model?.trained_at ?? 'N/A')}</b></span><span>Dataset <b>{String(model?.dataset_id ?? 'N/A')}</b></span><span>Provenance <b>{String(model?.provenance_type ?? 'N/A')}</b></span><span>Selected model <b>{String(model?.chosen_model ?? 'N/A')}</b></span><span>Held-out macro-F1 <b>{String(metrics?.macro_f1 ?? 'N/A')}</b></span><span>Fault recall <b>{String(metrics?.strict_fault_recall ?? 'N/A')}</b></span><span>False-alarm rate <b>{String(metrics?.false_alarm_rate ?? 'N/A')}</b></span></div><h4>Feature order</h4><p>{Array.isArray(model?.feature_order) ? (model.feature_order as string[]).join(' · ') : 'Unavailable'}</p><h4>Training and validation</h4><pre>{JSON.stringify(model?.chronological_split_boundaries ?? {}, null, 2)}</pre><h4>Limitations</h4><p>{String(model?.limitations ?? 'Analysis unavailable')}</p><p className="muted">{String(model?.label_origin ?? '')}</p></section></>
}

export function EmployeeTasks({ state, page }: { state: State; page: string }) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [selectedId, setSelectedId] = useState(new URLSearchParams(location.search).get('task') || '')
  const [notes, setNotes] = useState<{ id: string; body: string; author: string; created_at: string }[]>([])
  const [draft, setDraft] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => { void request<Task[]>('/tasks').then(setTasks).catch(error => setMessage(String(error))) }, [state.state_version])
  const task = tasks.find(item => item.incident_id === selectedId) ?? tasks[0]
  useEffect(() => { if (task) void request<typeof notes>(`/tasks/${task.incident_id}/notes`).then(setNotes).catch(() => setNotes([])) }, [task?.incident_id, state.state_version])
  const change = async (status: string) => { if (!task) return; try { await request(`/tasks/${task.incident_id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); setTasks(await request<Task[]>('/tasks')); setMessage(`Task marked ${status}.`) } catch (error) { setMessage(String(error)) } }
  const addNote = async () => { if (!task || !draft.trim()) return; try { setNotes(await request<typeof notes>(`/tasks/${task.incident_id}/notes`, { method: 'POST', body: JSON.stringify({ body: draft.trim() }) })); setDraft(''); setMessage('Note saved.') } catch (error) { setMessage(String(error)) } }
  const visible = page === 'history' ? tasks.filter(item => item.status === 'Maintained') : tasks.filter(item => item.status !== 'Maintained')
  return <>
    <div className="page-head"><div><p className="eyebrow">FIELD MAINTENANCE</p><h1>{page === 'history' ? 'Maintenance History' : page === 'details' ? 'Task Details' : 'Assigned Tasks'}</h1><p>Only tasks assigned to your station/pole are available.</p></div></div>
    {message && <p className="info" role="status">{message}</p>}
    {page !== 'details' && <section className="panel"><h3>{page === 'history' ? 'Completed work' : 'Current assignments'}</h3>{visible.length ? visible.map(item => <button className="task-row" key={item.incident_id} onClick={() => setSelectedId(item.incident_id)}><strong>{item.station_name} · {item.pole_id}</strong><span>{label(item.variable)} · {label(item.fault_type)} · {label(item.severity)}</span><b>{item.status}</b></button>) : <p className="empty">No tasks in this view.</p>}</section>}
    {task && page !== 'history' && <section className="panel task-detail"><div className="panel-head"><h3>{task.station_name} · {task.pole_id}</h3><span className="pill review">{task.status}</span></div><p><strong>{label(task.variable)} · probable {label(task.fault_type)} · {label(task.severity)}</strong></p><p>{task.explanation || 'Measured evidence is pending.'}</p><h4>Recommended resolution</h4><p>{task.resolution || 'Inspect the station and telemetry.'}</p><div className="task-meter-grid"><FlatMeter label="Observation Trust" value={task.trust_score} display={task.trust_score == null ? undefined : `${task.trust_score}/100`} tone={task.trust_score != null && task.trust_score <= 34 ? 'danger' : 'caution'} /><FlatMeter label="Severity" value={severityLevel(task.severity)} max={4} display={`${label(task.severity)} · ${severityLevel(task.severity)}/4`} tone={task.severity === 'high' || task.severity === 'critical' ? 'danger' : 'caution'} /></div><div className="detail-grid"><span>Evidence Confidence <b>{evidenceConfidence(task.confidence, task.assessment_status)}</b></span><span>Incident <b>{task.incident_id.slice(0, 8)}</b></span><span>Updated <b>{new Date(task.updated_at).toLocaleString()}</b></span></div><div className="button-row">{(task.status === 'Assigned' || task.status === 'Reopened') && <button className="primary" onClick={() => void change('Maintenance In Progress')}>Start Maintenance</button>}{task.status === 'Maintenance In Progress' && <button className="primary" onClick={() => void change('Maintained')}>Mark Maintained</button>}</div><h4>Maintenance notes</h4>{notes.map(note => <p className="note" key={note.id}><strong>{note.author}</strong> · {new Date(note.created_at).toLocaleString()}<br />{note.body}</p>)}<label>Add note<textarea value={draft} onChange={e => setDraft(e.target.value)} maxLength={2000} rows={3} /></label><button disabled={!draft.trim()} onClick={() => void addNote()}>Save note</button></section>}
  </>
}

export function AuthorityTasks({ state, focusIncidentId }: { state: State; focusIncidentId: string | null }) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [selectedId, setSelectedId] = useState(focusIncidentId ?? '')
  const [notes, setNotes] = useState<{ id: string; body: string; author: string; created_at: string }[]>([])
  const [message, setMessage] = useState('')
  useEffect(() => { void request<Task[]>('/tasks').then(rows => { setTasks(rows); setMessage('') }).catch(error => setMessage(String(error))) }, [state.state_version])
  useEffect(() => { void Promise.all([request<User[]>('/admin/users'), request<Assignment[]>('/admin/assignments')]).then(([nextUsers, nextAssignments]) => { setUsers(nextUsers); setAssignments(nextAssignments); setMessage('') }).catch(error => setMessage(String(error))) }, [state.state_version])
  useEffect(() => { if (focusIncidentId) setSelectedId(focusIncidentId) }, [focusIncidentId])
  const selected = tasks.find(task => task.incident_id === selectedId) ?? tasks[0]
  useEffect(() => { if (selected) void request<typeof notes>(`/tasks/${selected.incident_id}/notes`).then(rows => { setNotes(rows); setMessage('') }).catch(error => { setNotes([]); setMessage(String(error)) }) }, [selected?.incident_id, state.state_version])
  useEffect(() => { if (focusIncidentId && selected?.incident_id === focusIncidentId) { const timer = window.setTimeout(() => document.getElementById('authority-task-detail')?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 100); return () => window.clearTimeout(timer) } }, [focusIncidentId, selected?.incident_id])
  const update = async (id: string, status: string) => { try { await request(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); setTasks(await request<Task[]>('/tasks')); setMessage(`Task ${status.toLowerCase()}.`) } catch (error) { setMessage(String(error)) } }
  const assign = async (id: string, userId: string) => { try { await request(`/admin/tasks/${id}/assignee`, { method: 'PATCH', body: JSON.stringify({ user_id: userId }) }); setTasks(await request<Task[]>('/tasks')); setMessage('Task assignee saved.') } catch (error) { setMessage(String(error)) } }
  return <section className="panel"><div className="panel-head"><h3>Maintenance task records</h3><span>Assigned · In progress · Maintained · Reopened</span></div>{message && <p className="info" role="status">{message}</p>}{tasks.length ? <div className="table-wrap"><table><thead><tr><th>Location / pole</th><th>Fault</th><th>Status</th><th>Employee</th><th>Action</th></tr></thead><tbody>{tasks.map(task => <tr key={task.incident_id} className={`clickable ${selected?.incident_id === task.incident_id ? 'selected-row' : ''}`} onClick={() => setSelectedId(task.incident_id)}><td>{task.station_name}<small>{task.pole_id}</small></td><td>{label(task.fault_type)}<small>{label(task.severity)}</small></td><td>{task.status}</td><td><select aria-label={`Assignee for ${task.station_name} ${label(task.variable)}`} value={task.assignee_id ?? ''} onChange={e => void assign(task.incident_id, e.target.value)}><option value="" disabled>Unassigned</option>{users.filter(user => user.role === 'employee' && user.active && assignments.some(row => row.user_id === user.id && row.station_id === task.station_id)).map(user => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></td><td>{task.status === 'Maintained' ? <button onClick={() => void update(task.incident_id, 'Reopened')}>Reopen</button> : task.status === 'Reopened' ? <button onClick={() => void update(task.incident_id, 'Assigned')}>Assign</button> : <button onClick={() => void update(task.incident_id, 'Maintained')}>Mark Maintained</button>}</td></tr>)}</tbody></table></div> : <p className="empty">No task records yet.</p>}
    {selected && <div className="authority-task-detail" id="authority-task-detail"><h4>{selected.station_name} · {selected.pole_id} · {label(selected.variable)}</h4><p><strong>{selected.status}</strong> · probable {label(selected.fault_type)} · {label(selected.severity)} · incident {selected.incident_id.slice(0, 8)}</p><p>{selected.explanation}</p><h4>Maintenance notes</h4>{notes.length ? notes.map(note => <p className="note" key={note.id}><strong>{note.author}</strong> · {new Date(note.created_at).toLocaleString()}<br />{note.body}</p>) : <p className="muted">No notes yet.</p>}</div>}
  </section>
}
