import type {
  Collector,
  HealEvent,
  RunCollectorResponse,
  ScrapeResult,
} from '../types'

const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else {
        detail = JSON.stringify(body)
      }
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(detail, response.status)
  }

  return response.json() as Promise<T>
}

export function getCollectors(): Promise<Collector[]> {
  return request('/collectors')
}

export function getCollectorResults(collectorId: string): Promise<ScrapeResult[]> {
  return request(`/collectors/${encodeURIComponent(collectorId)}/results`)
}

export function runCollector(collectorId: string): Promise<RunCollectorResponse> {
  return request(`/collectors/${encodeURIComponent(collectorId)}/run`, {
    method: 'POST',
  })
}

export function getHealEvents(): Promise<HealEvent[]> {
  return request('/heal-events')
}

export function approveHealEvent(id: number): Promise<HealEvent> {
  return request(`/heal-events/${id}/approve`, { method: 'POST' })
}

export function rejectHealEvent(id: number): Promise<HealEvent> {
  return request(`/heal-events/${id}/reject`, { method: 'POST' })
}
