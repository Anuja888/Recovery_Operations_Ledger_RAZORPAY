import { useEffect, useMemo, useState } from 'react'
import { api, BatchRun, SegmentRow, AIUsageResponse } from '../api'
import { useCountUp } from '../useCountUp'

const inr = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN')
const pct = (v: number) => (v * 100).toFixed(1) + '%'

function Figure({ label, value, money = false, suffix = '', tone = 'ink', note }: {
  label: string; value: number; money?: boolean; suffix?: string
  tone?: 'ink' | 'pine' | 'clay' | 'ochre'; note?: string
}) {
  const animated = useCountUp(value)
  const toneCls =
    tone === 'pine' ? 'text-pine'
    : tone === 'clay' ? 'text-clay'
    : tone === 'ochre' ? 'text-ochre'
    : ''
  return (
    <div className="border-b border-line px-4 py-4">
      <div className="kicker">{label}</div>
      <div className={`tnum mt-2 text-[26px] leading-none font-semibold ${toneCls}`}>
        {money ? inr(animated) : animated.toFixed(1) + suffix}
      </div>
      {note && <div className="mt-2 text-xs text-faded">{note}</div>}
    </div>
  )
}

type SortKey = 'segment' | 'cases' | 'recovery_rate' | 'cost' | 'net_recovered'

export default function Dashboard({
  batchId, onBatchChange, onOpenCases, onNavigate,
}: {
  batchId: string | null
  onBatchChange: (id: string) => void
  onOpenCases: (failureClass?: string) => void
  onNavigate?: (id: string) => void
}) {
  const [batches, setBatches] = useState<BatchRun[]>([])
  const [batch, setBatch] = useState<BatchRun | null>(null)
  const [segments, setSegments] = useState<SegmentRow[]>([])
  const [aiUsage, setAiUsage] = useState<AIUsageResponse | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('net_recovered')
  const [asc, setAsc] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.batches()
      .then((list) => {
        setBatches(list)
        const chosen =
          (batchId && list.find((b) => b.id === batchId)) || list[0]
        if (chosen) {
          setBatch(chosen)
          onBatchChange(chosen.id)
        }
      })
      .catch((e) => setError(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!batchId || batchId === batch?.id) return
    const b = batches.find((x) => x.id === batchId)
    if (b) setBatch(b)
    else api.batch(batchId).then(setBatch).catch((e) => setError(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId])

  useEffect(() => {
    if (!batch) return
    api.segments(batch.id).then(setSegments).catch((e) => setError(String(e)))
    api.aiUsage(batch.id).then(setAiUsage).catch((e) => setError(String(e)))
  }, [batch])

  const sorted = useMemo(() => {
    const rows = [...segments]
    rows.sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey]
      const cmp = typeof va === 'string'
        ? String(va).localeCompare(String(vb))
        : Number(va) - Number(vb)
      return asc ? cmp : -cmp
    })
    return rows
  }, [segments, sortKey, asc])

  function header(key: SortKey, label: string, right = false) {
    const active = sortKey === key
    return (
      <th className={right ? 'text-right' : ''}
          onClick={() => { setSortKey(key); setAsc(active ? !asc : false) }}>
        <span className={active ? 'text-ember' : ''}>
          {label}{active ? (asc ? ' ↑' : ' ↓') : ''}
        </span>
      </th>
    )
  }

  if (!batch && !error)
    return (
      <div className="border border-dashed border-line bg-panel px-6 py-16 text-center">
        <p className="font-serif text-xl">The ledger is empty.</p>
        <p className="mt-2 text-sm text-faded">
          Run a batch to fill it — every decision will be recorded here.
        </p>
        {onNavigate && (
          <button onClick={() => onNavigate('runner')}
                  className="mt-4 border border-ember bg-ember px-4 py-2 text-sm font-medium text-paper
                             transition-colors hover:bg-ember-hover">
            Run a batch →
          </button>
        )}
      </div>
    )

  const delta = batch ? batch.recovery_rate - batch.baseline_recovery_rate : 0

  const byClass = segments.filter(
    (s) => s.segment.startsWith('class:') && !s.segment.includes('|'),
  )
  const maxRate = Math.max(0.01, ...byClass.map((s) => s.recovery_rate))

  return (
    <div className="space-y-7">
      {error && (
        <p className="border-l-2 border-clay bg-panel px-3 py-2 text-sm text-clay">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4 border-b-2 border-line pb-4">
        <div>
          <h1 className="font-serif text-[28px] leading-tight text-heading">Recovery ledger</h1>
          <p className="mt-1 text-sm text-faded">
            Measured against the retry-everything baseline, rupee for rupee.
          </p>
        </div>
        <label className="text-right">
          <span className="kicker block">Batch run</span>
          <select
            value={batch?.id ?? ''}
            onChange={(e) => onBatchChange(e.target.value)}
            className="tnum mt-1 border border-line bg-panel px-2 py-1.5 text-sm"
          >
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {(b.started_at ?? '').slice(0, 16).replace('T', ' ')} ·{' '}
                {b.total_cases} cases · net {inr(Number(b.net_recovered))}
              </option>
            ))}
          </select>
        </label>
      </div>

      {batch && batch.total_cases === 0 && (
        <div className="border border-ochre bg-panel px-5 py-6">
          <div className="kicker text-ochre">Empty batch</div>
          <p className="mt-1 text-sm">
            This batch run processed <b>0 cases</b> — at the time it ran the
            pool had no fresh &lsquo;new&rsquo; cases to consume. The figures
            below are zero, not a bug.
          </p>
          <p className="mt-2 text-xs text-faded">
            The pool now auto-tops itself up. Switch to a populated batch
            above, or run a new batch from the &ldquo;Run batch&rdquo; tab.
          </p>
        </div>
      )}

      {batch && (
        <>
          <div className="grid grid-cols-2 gap-x-6 bg-panel md:grid-cols-3">
            <Figure label="At risk" value={Number(batch.total_at_risk_amount)} money
                    note={`${batch.total_cases} failed payments`} />
            <Figure label="Recovered" value={Number(batch.total_recovered_amount)}
                    money tone="pine" />
            <Figure label="Net recovered" value={Number(batch.net_recovered)} money
                    tone={Number(batch.net_recovered) >= 0 ? 'pine' : 'clay'}
                    note={`after ${inr(Number(batch.total_cost))} outreach cost`} />
            <Figure label="Recovery rate" value={batch.recovery_rate * 100} suffix="%"
                    note={`baseline would keep only ${pct(batch.baseline_recovery_rate)}`} />
            <Figure label="Uplift vs baseline" value={delta * 100} suffix=" pp"
                    tone="ink"
                    note={delta >= 0 ? 'policy beats blind retries' : 'worse than doing nothing'} />
            <Figure label="Spent on lost causes"
                    value={Number(batch.false_positive_cost)} money tone="clay"
                    note={`${batch.cases_blocked_by_stopping_rules} cases stopped by rules`} />
          </div>

          <section>
            <h2 className="kicker mb-3">
              Segments — click a bar to open its case files
            </h2>

            {aiUsage && (
              <div className="mb-4 border-l-2 border-line bg-paper px-3 py-2 text-xs text-faded md:text-sm">
                <span className="font-medium text-ink">AI judgment</span>
                {' — '}
                touched {aiUsage.diagnoses_by_llm}/{batch.total_cases} diagnoses
                (rule handled the rest)
                {' · '}
                drafted {aiUsage.messages_drafted_by_llm} recovery messages
                {' · '}
                decided ₹{aiUsage.money_decisions_made_by_ai.toLocaleString('en-IN')} of the money
              </div>
            )}
            <div className="space-y-1.5">
              {byClass.map((s) => {
                const fc = s.segment.replace('class:', '')
                return (
                  <button key={s.segment} onClick={() => onOpenCases(fc)}
                          className="group flex w-full items-center gap-3 text-left">
                    <span className="w-36 shrink-0 truncate text-sm group-hover:text-ember">
                      {fc.replaceAll('_', ' ')}
                    </span>
                    <span className="relative h-5 flex-1 bg-[var(--color-bar-track)]">
                      <span className="absolute inset-y-0 left-0 bg-[var(--color-bar-fill)] transition-all"
                            style={{ width: `${(s.recovery_rate / maxRate) * 100}%` }} />
                      <span className="tnum absolute inset-y-0 right-2 flex items-center text-xs">
                        {pct(s.recovery_rate)}
                      </span>
                    </span>
                    <span className={`tnum w-28 shrink-0 text-right text-sm ${
                      s.net_recovered < 0 ? 'font-semibold text-clay' : 'text-faded'}`}>
                      net {inr(s.net_recovered)}
                    </span>
                  </button>
                )
              })}
            </div>
          </section>

          <section>
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="kicker">Full segment breakdown</h2>
              <span className="text-xs text-faded">click headers to sort</span>
            </div>
            <div className="scroll-slim overflow-x-auto border border-line bg-panel">
              <table className="ledger text-sm">
                <thead className="kicker">
                  <tr>
                    {header('segment', 'segment')}
                    {header('cases', 'cases', true)}
                    <th className="text-right">recovered</th>
                    {header('recovery_rate', 'rate', true)}
                    {header('cost', 'cost', true)}
                    {header('net_recovered', 'net recovered', true)}
                  </tr>
                </thead>
                <tbody className="tnum">
                  {sorted.map((s) => {
                    const risky = s.segment.includes('pfc>=3')
                    return (
                      <tr key={s.segment}
                          onClick={() =>
                            onOpenCases(
                              s.segment.startsWith('class:') && !s.segment.includes('|')
                                ? s.segment.replace('class:', '')
                                : undefined,
                            )
                          }
                          className="cursor-pointer">
                        <td className="font-sans">
                          {risky && (
                            <span className="mr-2 inline-block h-2 w-2 bg-clay align-middle"
                                  title="documented failure segment" />
                          )}
                          {s.segment.replace('class:', '').replaceAll('_', ' ').replaceAll('|', ' · ')}
                        </td>
                        <td className="text-right">{s.cases}</td>
                        <td className="text-right">{inr(s.recovered_amount)}</td>
                        <td className="text-right">{pct(s.recovery_rate)}</td>
                        <td className="text-right">{inr(s.cost)}</td>
                        <td className={`text-right font-semibold ${
                          s.net_recovered < 0 ? 'text-clay' : 'text-pine'}`}>
                          {inr(s.net_recovered)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-faded">
              Every figure is read from the stored BatchRun and Diagnosis rows —
              nothing on this page is hardcoded.
            </p>
          </section>
        </>
      )}
    </div>
  )
}
