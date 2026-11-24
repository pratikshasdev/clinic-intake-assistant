import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type Arrival, type DemoPatient, type Item } from './api'

const POLL_MS = 5000

const SECTIONS: Array<{ kind: Item['kind']; title: string }> = [
  { kind: 'allergy', title: 'Allergies' },
  { kind: 'medication', title: 'Medications' },
  { kind: 'condition', title: 'Conditions' },
]

const SYSTEM_NAMES: Record<string, string> = {
  'http://snomed.info/sct': 'SNOMED',
  'http://www.nlm.nih.gov/research/umls/rxnorm': 'RxNorm',
  'http://loinc.org': 'LOINC',
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return `${hours} h ago`
}

export default function App() {
  const [arrivals, setArrivals] = useState<Arrival[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Arrival | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<{ fhir_server: string; extractor: string } | null>(null)
  const [demoPatients, setDemoPatients] = useState<DemoPatient[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [showFhir, setShowFhir] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const list = await api.arrivals()
      setArrivals(list)
      setError(null)
      setSelectedId((current) => current ?? list[0]?.encounter_id ?? null)
    } catch (e) {
      setError(`Can't reach the API: ${(e as Error).message}`)
    }
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined)
    api.demoPatients().then(setDemoPatients).catch(() => undefined)
    refresh()
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  // Reload the selected arrival whenever the list changes, so review counts stay in step.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    api.arrival(selectedId).then(setDetail).catch((e) => setError((e as Error).message))
  }, [selectedId, arrivals])

  const review = async (item: Item, decision: 'approve' | 'reject') => {
    setBusy(item.id)
    try {
      const updated = await api.review(item, decision)
      setDetail((d) => d && { ...d, items: d.items.map((i) => (i.id === updated.id && i.resource_type === updated.resource_type ? updated : i)) })
      refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const approveAll = async () => {
    if (!detail) return
    setBusy('all')
    try {
      setDetail(await api.approveAll(detail.encounter_id))
      refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const addDemo = async (key: string) => {
    setBusy('demo')
    try {
      const created = await api.submitDemo(key)
      setSelectedId(created.encounter_id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const pendingTotal = useMemo(() => arrivals.reduce((n, a) => n + a.counts.pending, 0), [arrivals])

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Today's arrivals</h1>
          <p className="muted">
            {arrivals.length} {arrivals.length === 1 ? 'patient' : 'patients'} · {pendingTotal} items waiting for review
          </p>
        </div>
        <div className="topbar-actions">
          {demoPatients.length > 0 && (
            <select
              aria-label="Add a demo patient"
              value=""
              disabled={busy === 'demo'}
              onChange={(e) => e.target.value && addDemo(e.target.value)}
            >
              <option value="">{busy === 'demo' ? 'Adding…' : '+ Add demo patient'}</option>
              {demoPatients.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="layout">
        <nav className="list" aria-label="Arrivals">
          {arrivals.length === 0 && (
            <div className="empty">
              <p>No one has checked in yet.</p>
              <p className="muted">Submit the intake from the patient app, or add a demo patient.</p>
            </div>
          )}
          {arrivals.map((a) => (
            <button
              key={a.encounter_id}
              className={`list-row ${a.encounter_id === selectedId ? 'selected' : ''}`}
              onClick={() => setSelectedId(a.encounter_id)}
            >
              <span className="row-main">
                <strong>{a.patient.name}</strong>
                <span className="muted">
                  {a.patient.age != null ? `${a.patient.age} y` : ''} · {timeAgo(a.arrived_at)}
                </span>
              </span>
              <span className="row-reason">{a.visit_summary ?? a.reason}</span>
              {a.counts.pending > 0 ? (
                <span className="badge pending">{a.counts.pending} to review</span>
              ) : (
                <span className="badge done">Reviewed</span>
              )}
            </button>
          ))}
        </nav>

        <section className="detail">
          {!detail && arrivals.length > 0 && <p className="muted">Pick a patient on the left.</p>}
          {detail && (
            <>
              <div className="patient-header">
                <div>
                  <h2>{detail.patient.name}</h2>
                  <p className="muted">
                    {[
                      detail.patient.birth_date && `Born ${detail.patient.birth_date}`,
                      detail.patient.age != null && `${detail.patient.age} y`,
                      detail.patient.gender,
                      detail.patient.phone,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>
                <button className="primary" disabled={detail.counts.pending === 0 || busy === 'all'} onClick={approveAll}>
                  {busy === 'all' ? 'Approving…' : detail.counts.pending === 0 ? 'All reviewed' : `Approve all ${detail.counts.pending}`}
                </button>
              </div>

              <div className="card">
                <h3>Reason for visit</h3>
                {detail.visit_summary && <p className="summary">{detail.visit_summary}</p>}
                <p className="quote">“{detail.reason}”</p>
                {detail.observations.length > 0 && (
                  <div className="chips">
                    {detail.observations.map((o) => (
                      <span key={o.id} className="chip" title={o.code ? `LOINC ${o.code.code}` : undefined}>
                        {shortLabel(o.label)}: <strong>{o.value}</strong>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {SECTIONS.map(({ kind, title }) => {
                const items = detail.items.filter((i) => i.kind === kind)
                return (
                  <div className="card" key={kind}>
                    <h3>
                      {title} <span className="muted small">extracted by AI from the patient's words</span>
                    </h3>
                    {items.length === 0 && <p className="muted">None reported.</p>}
                    {items.map((item) => (
                      <ItemRow key={`${item.resource_type}/${item.id}`} item={item} busy={busy === item.id} onReview={review} />
                    ))}
                  </div>
                )
              })}

              <div className="footer-meta">
                <span className="muted small">
                  Extractor: {detail.extractor ?? 'unknown'} · FHIR server: {health?.fhir_server ?? '…'}
                </span>
                <button className="link" onClick={() => setShowFhir((v) => !v)}>
                  {showFhir ? 'Hide FHIR resources' : `View ${detail.resources?.length ?? ''} FHIR resources`}
                </button>
              </div>
              {showFhir && <pre className="fhir">{JSON.stringify(detail.resources, null, 2)}</pre>}
            </>
          )}
        </section>
      </main>
    </div>
  )
}

function shortLabel(label: string): string {
  if (label.startsWith('Pain severity')) return 'Pain'
  if (label.startsWith('Tobacco')) return 'Smoking'
  return label
}

function ItemRow({
  item,
  busy,
  onReview,
}: {
  item: Item
  busy: boolean
  onReview: (item: Item, decision: 'approve' | 'reject') => void
}) {
  const system = item.code?.system ? SYSTEM_NAMES[item.code.system] ?? item.code.system : null
  return (
    <div className={`item ${item.review_status}`}>
      <div className="item-main">
        <div className="item-title">
          <strong>{item.label}</strong>
          {item.detail && <span className="muted"> · {item.detail}</span>}
        </div>
        <div className="item-meta">
          {item.code ? (
            <span className="code" title={item.code.display ?? undefined}>
              {system} {item.code.code}
            </span>
          ) : (
            <span className="code uncoded" title="Not in the clinic's code list. Staff can code it later.">
              Not coded
            </span>
          )}
          {item.source_quote && (
            <span className={`source ${item.quote_found === false ? 'warn' : ''}`}>
              {item.quote_found === false ? 'Not found in the answer: ' : ''}“{item.source_quote}”
            </span>
          )}
        </div>
      </div>
      <div className="item-actions">
        {item.review_status === 'pending' ? (
          <>
            <button disabled={busy} onClick={() => onReview(item, 'approve')} className="approve">
              Approve
            </button>
            <button disabled={busy} onClick={() => onReview(item, 'reject')} className="reject">
              Reject
            </button>
          </>
        ) : (
          <span className={`status ${item.review_status}`}>{item.review_status === 'approved' ? 'Approved' : 'Rejected'}</span>
        )}
      </div>
    </div>
  )
}
