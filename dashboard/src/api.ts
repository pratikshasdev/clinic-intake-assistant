// Types mirror the view models returned by the FastAPI server (server/app/service.py).

export type ReviewStatus = 'pending' | 'approved' | 'rejected'

export interface Coding {
  system: string | null
  code: string | null
  display: string | null
}

export interface Item {
  resource_type: 'Condition' | 'AllergyIntolerance' | 'MedicationStatement'
  id: string
  kind: 'condition' | 'allergy' | 'medication'
  label: string
  code: Coding | null
  detail: string
  source_quote: string | null
  quote_found: boolean | null
  review_status: ReviewStatus
}

export interface ObservationView {
  id: string
  label: string
  value: string
  code: Coding | null
}

export interface Arrival {
  encounter_id: string
  status: string
  arrived_at: string | null
  reason: string | null
  visit_summary: string | null
  extractor: string | null
  patient: {
    id: string
    name: string
    birth_date: string | null
    age: number | null
    gender: string | null
    phone: string | null
  }
  counts: Record<ReviewStatus, number>
  items: Item[]
  observations: ObservationView[]
  resources?: Array<Record<string, unknown>>
}

export interface DemoPatient {
  key: string
  name: string
  reason: string
}

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // keep the status text
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean; fhir_server: string; extractor: string }>('/api/health'),
  arrivals: () => request<Arrival[]>('/api/arrivals'),
  arrival: (id: string) => request<Arrival>(`/api/arrivals/${id}`),
  review: (item: Item, decision: 'approve' | 'reject') =>
    request<Item>(`/api/items/${item.resource_type}/${item.id}/review`, {
      method: 'POST',
      body: JSON.stringify({ decision, reviewer: 'Front desk' }),
    }),
  approveAll: (encounterId: string) =>
    request<Arrival>(`/api/arrivals/${encounterId}/approve-all`, {
      method: 'POST',
      body: JSON.stringify({ decision: 'approve', reviewer: 'Front desk' }),
    }),
  demoPatients: () => request<DemoPatient[]>('/api/demo/patients'),
  submitDemo: (key: string) => request<{ encounter_id: string }>(`/api/demo/patients/${key}`, { method: 'POST' }),
}
