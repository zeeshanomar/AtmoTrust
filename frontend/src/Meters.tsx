type Tone = 'good' | 'caution' | 'danger' | 'neutral'

export function evidenceConfidence(value: number | null | undefined, status: string | null | undefined): string {
  if (status !== 'complete' || value == null || !Number.isFinite(value)) return 'N/A'
  const band = value < 0.4 ? 'Weak' : value < 0.7 ? 'Moderate' : 'Strong'
  return `${band} · ${value.toFixed(2)}`
}

const severityLevels: Record<string, number> = { none: 0, low: 1, medium: 2, high: 3, critical: 4 }

export function severityLevel(severity: string | null | undefined): number | null {
  return severity != null && severity in severityLevels ? severityLevels[severity] : null
}

export function FlatMeter({ label, value, max = 100, display, tone = 'neutral' }: { label: string; value: number | null | undefined; max?: number; display?: string; tone?: Tone }) {
  const available = value != null && Number.isFinite(value)
  const bounded = available ? Math.max(0, Math.min(max, value)) : 0
  const text = available ? display ?? `${value}/${max}` : 'N/A'
  return <div className={`flat-meter ${tone}`} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={available ? bounded : undefined} aria-valuetext={text}>
    <div className="meter-heading"><span>{label}</span><strong>{text}</strong></div>
    <div className="meter-track"><span style={{ width: `${available ? bounded / max * 100 : 0}%` }} /></div>
  </div>
}
