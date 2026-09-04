import { useEffect, useRef, useState } from 'react'
import { api, BatchRun } from '../api'

const inr = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN')

const STAGES = [
  'Pulling unprocessed case files…',
  'Diagnosing failures (rules first, LLM only for ambiguous text)…',
  'Scoring recoverability…',
  'Consulting the deterministic policy engine…',
  'Drafting messages & simulating interventions…',
  'Writing audit trail & settling metrics…',
]

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`relative h-5 w-9 border transition-colors ${
        on ? 'border-ember bg-ember' : 'border-line bg-panel'
      }`}
      aria-pressed={on}
    >
      <span className={`absolute top-0.5 h-3.5 w-3.5 transition-all ${
        on ? 'left-[18px] bg-paper' : 'left-0.5 bg-line'}`} />
    </button>
  )
}

function fmtClock(s: number) {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export default function BatchRunner({ onDone }: { onDone: (batchId: string) => void }) {
  const [nCases, setNCases] = useState(300)
  const [applyFix, setApplyFix] = useState(false)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [result, setResult] = useState<BatchRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (timer.current) clearInterval(timer.current) }, [])

  async function run() {
    setRunning(true)
    setError(null)
    setResult(null)
    setElapsed(0)

    timer.current = setInterval(() => {
      setElapsed((s) => s + 1)
    }, 1000)

    try {
      const batch = await api.runBatch(nCases, applyFix ? 0.85 : null)
      setResult(batch)
    } catch (e) {
      setError(String(e))
    } finally {
      if (timer.current) clearInterval(timer.current)
      setRunning(false)
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="border-b-2 border-line pb-4">
        <h1 className="font-serif text-[28px] leading-tight text-heading">Run a recovery batch</h1>
        <p className="mt-1 text-sm text-faded">
          Each case is diagnosed, scored, decided by rule — and audited.
          Nothing here touches real money.
        </p>
      </div>

      <div className="border border-line bg-panel p-5">
        <div className="flex items-center justify-between gap-6">
          <div>
            <div className="kicker">Cases to process</div>
            <div className="mt-1 flex items-center">
              <button onClick={() => setNCases((n) => Math.max(1, n - 25))}
                      disabled={running}
                      className="h-8 w-8 border border-line bg-paper text-lg leading-none
                                 hover:border-heading disabled:opacity-40">−</button>
              <input
                type="number" min={1} max={600} value={nCases}
                onChange={(e) => setNCases(Number(e.target.value))}
                disabled={running}
                className="tnum mx-2 w-24 border border-line bg-paper px-2 py-1 text-center
                           text-lg outline-none focus:border-ember"
              />
              <button onClick={() => setNCases((n) => Math.min(600, n + 25))}
                      disabled={running}
                      className="h-8 w-8 border border-line bg-paper text-lg leading-none
                                 hover:border-heading disabled:opacity-40">+</button>
            </div>
          </div>

          <div className="max-w-[15rem] text-right">
            <div className="kicker">Hardened segment rule</div>
            <div className="mt-2 flex items-center justify-end gap-2">
              <span className="text-xs text-faded">
                {applyFix ? 'score ≥ 0.85 to message' : 'original v1 policy'}
              </span>
              <Toggle on={applyFix} onChange={setApplyFix} />
            </div>
          </div>
        </div>

        <p className="mt-4 border-l-2 border-line pl-3 text-[11px] leading-relaxed text-faded">
          The toggle applies the fix from docs/what-broke.md: cases in
          insufficient_funds with ≥3 prior failures must score very high before
          any outreach money is spent.
        </p>

        <button
          onClick={run}
          disabled={running}
          className="mt-5 w-full bg-ember py-2.5 font-medium tracking-wide text-paper
                     transition-colors hover:bg-ember-hover disabled:cursor-wait disabled:opacity-60"
        >
          {running ? `RUNNING — ${fmtClock(elapsed)}` : `Process ${Math.min(Math.max(nCases, 1), 600)} cases`}
        </button>

        {running && (
          <div className="mt-4 grid grid-cols-[5rem_1fr] gap-x-4 gap-y-2">
            <div className="tnum self-start text-3xl font-semibold text-ember">{fmtClock(elapsed)}</div>
            <ol className="space-y-1.5">
              {STAGES.map((s, i) => (
                <li key={s} className={`flex items-center gap-2 text-xs transition-opacity ${
                  i === STAGES.length - 1 ? 'opacity-100' : 'opacity-70'}`}>
                  <span className={`tnum flex h-4 w-4 items-center justify-center border text-[9px]
                    ${i === STAGES.length - 1 ? 'animate-pulse border-ember text-ember' : 'border-ember bg-ember text-paper'}`}>
                    {i < STAGES.length - 1 ? '✓' : i + 1}
                  </span>
                  <span className={i === STAGES.length - 1 ? 'text-ink' : 'text-faded'}>{s}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {error && (
          <p className="mt-4 border-l-2 border-clay pl-3 text-sm text-clay">{error}</p>
        )}
      </div>

      {result && (
        <div className="border border-ember bg-panel">
          <div className="flex items-baseline justify-between border-b border-line px-4 py-2">
            <span className="kicker">Batch settled</span>
            <span className="tnum text-xs text-faded">{result.id.slice(0, 12)}…</span>
          </div>
          {(result.requested_cases ?? result.total_cases) !== result.total_cases && (
            <div className="border-b border-line-soft px-4 py-2 text-xs text-ochre">
              {result.total_cases} of {result.requested_cases} processed
              {result.cases_topped_up
                ? ` — pool topped up automatically (+${result.cases_topped_up} synthetic cases)`
                : ''}
            </div>
          )}
          <table className="ledger tnum text-sm">
            <tbody>
              {([
                ['cases processed', String(result.total_cases)],
                ['at-risk amount', inr(Number(result.total_at_risk_amount))],
                ['recovered', inr(Number(result.total_recovered_amount))],
                ['outreach cost', inr(Number(result.total_cost))],
                ['net recovered', inr(Number(result.net_recovered))],
                ['recovery rate', `${(result.recovery_rate * 100).toFixed(1)}% vs baseline ${(result.baseline_recovery_rate * 100).toFixed(1)}%`],
                ['stopped by rules', String(result.cases_blocked_by_stopping_rules)],
              ] as const).map(([k, v]) => (
                <tr key={k}>
                  <td className="font-sans text-faded">{k}</td>
                  <td className={`text-right ${
                    k === 'net recovered' ? 'font-semibold text-pine' : ''}`}>
                    {v}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={() => onDone(result.id)}
                  className="w-full border-t border-line py-2 text-sm font-medium text-heading
                             transition-colors hover:bg-[#F5F1EA]">
            Open this batch in the ledger →
          </button>
        </div>
      )}
    </div>
  )
}
