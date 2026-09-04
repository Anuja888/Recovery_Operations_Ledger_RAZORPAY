import { useEffect, useMemo, useState } from 'react'
import { api, CaseDetail, CaseSummary } from '../api'

const inr = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN')

type Row = CaseSummary & { failure_class?: string }

const STATUS_TONE: Record<string, string> = {
  resolved: 'text-pine border-pine',
  intervened: 'text-ochre border-ochre',
  stopped: 'text-clay border-clay',
  diagnosed: 'text-faded border-line',
  scored: 'text-faded border-line',
  new: 'text-faded border-line',
}

function TimelineStep({ n, title, children }: {
  n: number; title: string; children: React.ReactNode
}) {
  return (
    <li className="relative pb-5 pl-9">
      <span className="absolute left-[11px] top-6 h-full w-px bg-line" />
      <span className="tnum absolute left-0 top-0 flex h-6 w-6 items-center justify-center
                       border border-heading bg-panel text-xs">
        {n}
      </span>
      <div className="kicker pt-1">{title}</div>
      <div className="mt-1.5 text-sm leading-relaxed">{children}</div>
    </li>
  )
}

function DetailPane({ detail }: { detail: CaseDetail }) {
  const d = detail
  const [copied, setCopied] = useState(false)

  function copyId() {
    navigator.clipboard?.writeText(d.id).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    })
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-serif text-lg text-heading">Case file</h2>
          <button onClick={copyId}
                  className="kicker border border-line px-2 py-1 hover:border-heading">
            {copied ? 'copied ✓' : 'copy id'}
          </button>
        </div>
        <div className="tnum mt-1 text-xs text-faded">
          {d.id.slice(0, 12)}… · {inr(Number(d.amount))} ·{' '}
          tenure {d.customer_tenure_months} mo · {d.payment_method}
        </div>
        <div className="mt-1 text-xs text-faded">
          raw failure: <em>{d.failure_code ?? d.failure_message ?? '—'}</em>
        </div>
      </div>

      <ol className="scroll-slim flex-1 overflow-y-auto px-4 py-4">
        <TimelineStep n={1} title="Diagnosis">
          {d.diagnosis ? (
            <>
              <b>{d.diagnosis.failure_class.replaceAll('_', ' ')}</b>
              {' '}· confidence {(d.diagnosis.confidence * 100).toFixed(0)}%
              {' '}· via{' '}
              <span className={`border px-1 py-0.5 text-[10px] ${
                d.diagnosis.source === 'llm' ? 'border-ochre text-ochre'
                : d.diagnosis.source === 'mock' ? 'border-line text-faded'
                : 'border-ember text-ember'
              }`}>
                {d.diagnosis.source === 'llm' ? 'LLM'
                 : d.diagnosis.source === 'mock' ? 'Mock'
                 : 'Rule'}
              </span>
              <div className="mt-1 text-xs text-faded">{d.diagnosis.rationale}</div>
            </>
          ) : 'not diagnosed'}
        </TimelineStep>

        <TimelineStep n={2} title="Recoverability score">
          {d.score ? (
            <>
              <span className="tnum inline-block min-w-14 border border-line bg-paper px-1 text-center font-semibold">
                {(d.score.recoverability * 100).toFixed(1)}%
              </span>{' '}
              <span className="text-xs text-faded">model {d.score.model_version}</span>
            </>
          ) : (
            <span className="text-ochre">withheld — low-confidence diagnosis, human review required</span>
          )}
        </TimelineStep>

        <TimelineStep n={3} title="Policy decision (deterministic)">
          {d.policy_decision ? (
            <>
              <div className="flex items-center gap-2">
                <span>intervention =</span>
                <b className={
                  d.policy_decision.intervention === 'stop' ? ' text-clay'
                  : d.policy_decision.intervention === 'send_message' ? ' text-ochre'
                  : ' text-ink'
                }> {d.policy_decision.intervention.replaceAll('_', ' ')}</b>
                {d.policy_decision.budget_consumed
                  ? ` · spent ${inr(Number(d.policy_decision.budget_consumed))}` : ''}
                <span className="ml-auto border border-line bg-paper px-1 py-0.5 text-[10px] text-faded"
                      title="policy_engine.decide() never calls a model.">
                  🔒 Deterministic — no AI call
                </span>
              </div>
              <blockquote className="mt-1 border-l-2 border-line pl-3 text-xs italic text-faded">
                "{d.policy_decision.reason}"
              </blockquote>
            </>
          ) : 'no decision recorded'}
        </TimelineStep>

        {d.message && (
          <TimelineStep n={4} title="Recovery message (LLM-drafted wording, action already decided)">
            <div className="border border-line bg-paper p-3 text-[13px] leading-relaxed">
              {d.message}
            </div>
          </TimelineStep>
        )}

        <TimelineStep n={d.message ? 5 : 4} title={`Audit trail — ${d.audit_trail.length} events`}>
          <ul className="tnum space-y-1 text-[11px] text-faded">
            {d.audit_trail.map((e, i) => (
              <li key={i} className="flex justify-between gap-3 border-b border-line-soft pb-1">
                <span>{e.event_type}</span>
                <span>{new Date(e.created_at).toLocaleTimeString()}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-faded">append-only — nothing here can be edited or removed</p>
        </TimelineStep>
      </ol>
    </div>
  )
}

type SortKey = 'amount' | 'status' | 'prior_failure_count' | 'subscription_id'

export default function CaseExplorer({ initialFailureClass }: {
  initialFailureClass?: string
}) {
  const [rows, setRows] = useState<Row[]>([])
  const [status, setStatus] = useState('')
  const [failureClass, setFailureClass] = useState(initialFailureClass ?? '')
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('prior_failure_count')
  const [asc, setAsc] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setFailureClass(initialFailureClass ?? '')
  }, [initialFailureClass])

  useEffect(() => {
    api.cases(status || undefined, failureClass || undefined)
      .then((list) => setRows(list as Row[]))
      .catch((e) => setError(String(e)))
  }, [status, failureClass])

  function select(id: string) {
    setSelectedId(id)
    api.caseDetail(id).then(setDetail).catch((e) => setError(String(e)))
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return
      e.preventDefault()
      const idx = rows.findIndex((r) => r.id === selectedId)
      const next = e.key === 'ArrowDown'
        ? Math.min(rows.length - 1, idx + 1)
        : Math.max(0, idx <= 0 ? 0 : idx - 1)
      if (rows[next]) select(rows[next].id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, selectedId])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = q
      ? rows.filter((r) => r.subscription_id.toLowerCase().includes(q) || r.id.includes(q))
      : rows
    return [...filtered].sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey]
      const cmp = typeof va === 'string'
        ? String(va).localeCompare(String(vb))
        : Number(va) - Number(vb)
      return asc ? cmp : -cmp
    })
  }, [rows, query, sortKey, asc])

  function header(key: SortKey, label: string) {
    const active = sortKey === key
    return (
      <th onClick={() => { setSortKey(key); setAsc(active ? !asc : false) }}>
        <span className={active ? 'text-ember' : ''}>
          {label}{active ? (asc ? ' ↑' : ' ↓') : ''}
        </span>
      </th>
    )
  }

  return (
    <div className="space-y-4">
      <div className="border-b-2 border-line pb-4">
        <h1 className="font-serif text-[28px] leading-tight text-heading">Case files</h1>
        <p className="mt-1 text-sm text-faded">
          Every intervention, in order, with the reason the rule engine gave.
          Use ↑ / ↓ to walk the docket.
        </p>
      </div>

      {error && (
        <p className="border-l-2 border-clay bg-panel px-3 py-2 text-sm text-clay">{error}</p>
      )}

      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="search subscription id…"
              className="tnum w-52 border border-line bg-panel px-2 py-1.5 text-sm outline-none focus:border-ember"
            />
            <select value={status} onChange={(e) => setStatus(e.target.value)}
                    className="border border-line bg-panel px-2 py-1.5 text-sm">
              <option value="">any status</option>
              {['new', 'diagnosed', 'scored', 'intervened', 'resolved', 'stopped'].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <select value={failureClass}
                    onChange={(e) => setFailureClass(e.target.value)}
                    className="border border-line bg-panel px-2 py-1.5 text-sm">
              <option value="">any failure class</option>
              {['expired_card', 'insufficient_funds', 'bank_decline',
                'mandate_cancelled', 'unknown'].map((f) => <option key={f}>{f}</option>)}
            </select>
            <span className="kicker">{visible.length} shown</span>
          </div>

          <div className="scroll-slim max-h-[62vh] overflow-auto border border-line bg-panel">
            <table className="ledger text-sm">
              <thead className="kicker sticky top-0 z-10 bg-panel text-faded">
                <tr>
                  {header('subscription_id', 'subscription')}
                  {header('amount', 'amount')}
                  {header('status', 'status')}
                  {header('prior_failure_count', 'fails')}
                  <th>class</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => {
                  const active = c.id === selectedId
                  return (
                    <tr key={c.id} onClick={() => select(c.id)}
                        className={`cursor-pointer ${active ? 'bg-[#EDE8D8]' : ''}`}>
                      <td className={`py-2 font-mono text-xs ${
                        active ? 'border-l-2 border-l-ember pl-2' : ''}`}>
                        {c.subscription_id}
                      </td>
                      <td>{inr(Number(c.amount))}</td>
                      <td>
                        <span className={`border px-1.5 py-0.5 text-[11px] ${
                          STATUS_TONE[c.status] ?? 'text-faded border-line'}`}>
                          {c.status}
                        </span>
                      </td>
                      <td>{c.prior_failure_count}</td>
                      <td className="text-xs text-faded">{c.failure_class ?? '—'}</td>
                    </tr>
                  )
                })}
                {!visible.length && !error && (
                  <tr><td colSpan={5} className="py-6 text-center text-sm text-faded">
                    No case files match.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="sticky top-6 max-h-[75vh] border border-line bg-panel">
          {detail ? (
            <DetailPane detail={detail} />
          ) : (
            <div className="px-5 py-10 text-center text-sm text-faded">
              Select a case file to read its trail:
              diagnosis → score → policy decision → message → audit.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
