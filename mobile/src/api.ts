import type { Questionnaire } from './fhir'

// On a phone, localhost is the phone itself. Set EXPO_PUBLIC_API_URL to your
// computer's address on the same Wi-Fi, for example http://192.168.1.20:8000.
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export type SubmitResult = {
  encounter_id: string
  patient_id: string
  returning_patient: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30000)
  try {
    const res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      const detail = typeof body?.detail === 'string' ? body.detail : `The clinic's server answered ${res.status}.`
      throw new Error(detail)
    }
    return (await res.json()) as T
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw new Error('The clinic took too long to answer. Please try again.')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  questionnaire: () => request<Questionnaire>('/api/questionnaire'),
  submit: (questionnaireResponse: unknown) =>
    request<SubmitResult>('/api/intake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(questionnaireResponse),
    }),
}
