import { useEffect, useState } from 'react'
import { useSession } from './Auth'

export type Scenario = 'HIBRIDO' | 'SINTETICO_IA'
export type Population = 'incluidos' | 'todos'

export const scenarioLabels: Record<Scenario, string> = { HIBRIDO: 'Híbrido', SINTETICO_IA: 'Sintético IA' }
export const populationLabels: Record<Population, string> = { incluidos: 'Pacientes elegibles', todos: 'Todos los pacientes' }

export async function readOperation<T>(response: Response): Promise<T> {
  const body = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail
    const message = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail[0]?.msg?.replace(/^Value error, /, '') : undefined
    throw new Error(message || 'No se pudo completar la operación.')
  }
  return body as T
}

export function useOperationQuery<T>(url: string | null) {
  const { request } = useSession()
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState<{ url: string; version: number; data: T | null; error: string }>()

  useEffect(() => {
    if (!url) return
    const controller = new AbortController()
    request(url, { signal: controller.signal }).then(readOperation<T>)
      .then(data => { if (!controller.signal.aborted) setResult({ url, version, data, error: '' }) })
      .catch(error => { if (!controller.signal.aborted) setResult({ url, version, data: null, error: error.message }) })
    return () => controller.abort()
  }, [url, request, version])

  const current = result?.url === url && result.version === version ? result : undefined
  return { data: current?.data ?? null, error: current?.error ?? '', loading: Boolean(url && !current),
    refresh: () => setVersion(value => value + 1) }
}

export function localToday() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function formValue(form: FormData, name: string): string | null {
  return String(form.get(name) ?? '').trim() || null
}

export function formBoolean(form: FormData, name: string) {
  const value = formValue(form, name)
  return value === null ? null : value === 'true'
}

export function displayDateTime(value: string | null) {
  return value ? value.slice(0, 16).replace('T', ' ') : '—'
}
