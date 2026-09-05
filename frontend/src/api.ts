/** Thin typed client for the RENEW backend. */

// `VITE_API_BASE` (or the alias `VITE_API_BASE_URL`) is the origin of the
// deployed FastAPI backend, e.g. "https://renew-api.onrender.com". It
// MUST NOT end with a slash. The path components (/batches,
// /failure-story, ...) are appended as-is.
//
// In local development leave it unset — the Vite dev server proxies
// "/api/*" to the FastAPI server and we hit same-origin URLs.
const _rawBase = (import.meta.env.VITE_API_BASE_URL
                  ?? import.meta.env.VITE_API_BASE
                  ?? '').replace(/\/$/, '')
const BASE = _rawBase ? _rawBase + '/api' : '/api'

// Surface a single, actionable error in the browser console when the
// production build is missing the API base. Without this, every API
// call silently returns a Vercel 404 (or HTML, depending on the
// rewrite), which surfaces as a misleading JSON parse error in the UI.
if (typeof window !== 'undefined' && !_rawBase && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
  // eslint-disable-next-line no-console
  console.error(
    '[RENEW] VITE_API_BASE_URL is not set. All API calls will fail. ' +
    'Set it in your Vercel project environment to the FastAPI backend origin ' +
    '(e.g. https://renew-api.onrender.com) and redeploy.',
  )
}

export interface BatchRun {
  id: string
  started_at: string
  finished_at: string | null
  total_cases: number
  total_at_risk_amount: number
  total_recovered_amount: number
  total_cost: number
  net_recovered: number
  recovery_rate: number
  baseline_recovery_rate: number
  false_positive_cost: number
  cases_blocked_by_stopping_rules: number
  requested_cases?: number | null
  cases_topped_up?: number | null
}

export interface SegmentRow {
  segment: string
  cases: number
  recovered_cases: number
  recovered_amount: number
  cost: number
  net_recovered: number
  recovery_rate: number
}

export interface AIUsageResponse {
  diagnoses_by_rule: number
  diagnoses_by_llm: number
  escalations_from_low_confidence: number
  messages_drafted_by_llm: number
  money_decisions_made_by_ai: number
}

export interface SandboxResponse {
  total_cases: number
  total_at_risk_amount: number
  total_recovered_amount: number
  total_cost: number
  net_recovered: number
  recovery_rate: number
  baseline_recovery_rate: number
  false_positive_cost: number
  cases_blocked_by_stopping_rules: number
  is_simulation: boolean
  sample_size_used: number
}

export interface CaseSummary {
  id: string
  subscription_id: string
  amount: number
  status: string
  prior_failure_count: number
  created_at: string
  failure_class?: string | null
}

export interface AuditEntry {
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export interface CaseDetail extends CaseSummary {
  merchant_id: string
  currency: string
  failure_code: string | null
  failure_message: string | null
  customer_tenure_months: number
  payment_method: string
  merchant_category: string
  diagnosis: {
    failure_class: string
    confidence: number
    source: string
    rationale: string
  } | null
  score: {
    recoverability: number
    model_version: string
    top_features: Record<string, number>
  } | null
  policy_decision: {
    intervention: string
    reason: string
    budget_consumed: number | null
  } | null
  message: string | null
  audit_trail: AuditEntry[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${text}`)
  }
  return res.json()
}

export const api = {
  batches: () => get<BatchRun[]>('/batches'),
  latestBatch: () => get<BatchRun[]>('/batches/latest').then((r) => r[0]).catch(() => undefined),

  seed: async (force = false) => {
    const res = await fetch(`${BASE}/admin/seed?force=${force}`, { method: 'POST' })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  batch: (id: string) => get<BatchRun>(`/batches/${id}`),
  segments: (id: string) => get<SegmentRow[]>(`/batches/${id}/segments`),
  aiUsage: (id: string) => get<AIUsageResponse>(`/batches/${id}/ai-usage`),

  cases: (status?: string, failureClass?: string) => {
    const q = new URLSearchParams()
    if (status) q.set('status', status)
    if (failureClass) q.set('failure_class', failureClass)
    const qs = q.toString() ? `?${q}` : ''
    return get<CaseSummary[]>(`/cases${qs}`)
  },

  caseDetail: (id: string) => get<CaseDetail>(`/cases/${id}`),

  runBatch: async (
    nCases: number,
    segmentSendThreshold: number | null,
  ): Promise<BatchRun> => {
    const res = await fetch(`${BASE}/batches/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        n_cases: nCases,
        segment_send_threshold: segmentSendThreshold,
      }),
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  sandboxSimulate: async (params: {
    segmentSendThreshold: number | null
    budgetCap: number
    messageEstimatedCost: number
    sampleSize: number
  }): Promise<SandboxResponse> => {
    const res = await fetch(`${BASE}/sandbox/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        segment_send_threshold: params.segmentSendThreshold,
        budget_cap: params.budgetCap,
        message_estimated_cost: params.messageEstimatedCost,
        sample_size: params.sampleSize,
      }),
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  failureStory: () => get<{
    before: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
    after: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
    narrative: Record<string, string>
    latest?: {
      before: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
      after: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
    } | null
  }>('/failure-story').catch((e) => { throw e }),

  rerunFailureStory: async (): Promise<{
    before: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
    after: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
    narrative: Record<string, string>
    latest?: {
      before: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
      after: { batch: Record<string, unknown>; segment: Record<string, unknown> | null }
    } | null
  }> => {
    const res = await fetch(`${BASE}/failure-story/rerun`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
}
