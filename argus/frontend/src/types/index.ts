export interface Collector {
  id: string
  name: string
  site_url: string
  last_snapshot_id: string | null
  last_status: string | null
  last_run_at: string | null
  created_at: string
}

export interface ScrapeResult {
  id: number
  collector_id: string
  title: string | null
  price: number | null
  original_price: number | null
  discount_percentage: string | null
  stock_status: string | null
  url: string | null
  scraped_at: string
  is_valid: boolean
}

export interface HealEvent {
  id: number
  collector_id: string
  collector_name: string | null
  detected_at: string
  issue_description: string
  heal_prompt: string
  status: string
  diff_summary: string | null
  error_message: string | null
  resolved_at: string | null
}

export interface RunCollectorResponse {
  collector_id: string
  issues: string[]
  heal_event_status: string | null
  result: ScrapeResult
}

export type HealEventStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'heal_already_in_progress'
  | 'heal_request_failed'
  | string
