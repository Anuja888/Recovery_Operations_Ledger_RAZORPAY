import { useEffect, useState } from 'react'
import { api, SandboxResponse } from '../api'

const inr = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN')
const pct = (v: number) => (v * 100).toFixed(1) + '%'

function Figure({ label, value, money = false, suffix = '', tone = 'ink', note }: {
  label: string; value: number; money?: boolean; suffix?: string
  tone?: 'ink' | 'pine' | 'clay' | 'ochre'; note?: string
}) {
  const [display, setDisplay] = useState(0)
  useEffect(() => {
    let raf = 0
    const t0 = performance.now()
    const dur = 400
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur)
      setDisplay(value * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])

  const toneCls =
    tone === 'pine' ? 'text-pine'
    : tone === 'clay' ? 'text-clay'
    : tone === 'ochre' ? 'text-ochre'
    : ''
  return (
    <div className="border-b border-line px-4 py-4">
      <div className="kicker">{label}</div>
      <div className={`tnum mt-2 text-[26px] leading-none font-semibold ${toneCls}`}>
        {money ? inr(display) : display.toFixed(1) + suffix}
      </div>
      {note && <div className="mt-2 text-xs text-faded">{note}</div>}
    </div>
  )
}

export default function PolicySandbox() {
  const [threshold, setThreshold] = useState(0.85)
  const [budgetCap, setBudgetCap] = useState(5000)
  const [messageCost, setMessageCost] = useState(300)
  const [sampleSize, setSampleSize] = useState(300)
  const [result, setResult] = useState<SandboxResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  let debounce: ReturnType<typeof setTimeout> | null = null
  function scheduleSimulate() {
    setLoading(true)
    setError(null)
    if (debounce) clearTimeout(debounce)
    debounce = setTimeout(async () => {
      try {
        const res = await api.sandboxSimulate({
          segmentSendThreshold: threshold,
          budgetCap: budgetCap,
          messageEstimatedCost: messageCost,
          sampleSize: sampleSize,
        })
        setResult(res)
      } catch (e) {
        setError(String(e))
      } finally {
        setLoading(false)
      }
    }, 300)
  }

  useEffect(() => {
    scheduleSimulate()
    return () => { if (debounce) clearTimeout(debounce) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => () => { if (debounce) clearTimeout(debounce) }, [])

  function resetDefaults() {
    setThreshold(0.85)
    setBudgetCap(5000)
    setMessageCost(300)
    setSampleSize(300)
    scheduleSimulate()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="border-b-2 border-line pb-4">
        <h1 className="font-serif text-[28px] leading-tight text-heading">Try the rules</h1>
        <p className="mt-1 text-sm text-faded">
          This calls the exact same decision function that runs in production.
          Nothing here is faked or precomputed.
        </p>
      </div>

      {error && (
        <p className="border-l-2 border-clay bg-panel px-3 py-2 text-sm text-clay">{error}</p>
      )}

      <div className="border border-line bg-panel p-5">
        <div className="space-y-5">
          <div>
            <div className="flex items-baseline justify-between">
              <label className="kicker">Segment send threshold</label>
              <span className="tnum text-sm">{threshold.toFixed(2)}</span>
            </div>
            <input
              type="range" min={0.5} max={1.0} step={0.01}
              value={threshold}
              onChange={(e) => { setThreshold(Number(e.target.value)); scheduleSimulate() }}
              className="mt-2 w-full accent-ember"
            />
            <p className="mt-1 text-[11px] text-faded">
              Cases in insufficient_funds with ≥3 prior failures must score at
              least this high before any outreach money is spent.
            </p>
          </div>

          <div>
            <div className="flex items-baseline justify-between">
              <label className="kicker">Batch budget cap</label>
              <span className="tnum text-sm">{inr(budgetCap)}</span>
            </div>
            <input
              type="range" min={0} max={20000} step={100}
              value={budgetCap}
              onChange={(e) => { setBudgetCap(Number(e.target.value)); scheduleSimulate() }}
              className="mt-2 w-full accent-ember"
            />
          </div>

          <div>
            <div className="flex items-baseline justify-between">
              <label className="kicker">Message estimated cost</label>
              <span className="tnum text-sm">{inr(messageCost)}</span>
            </div>
            <input
              type="range" min={50} max={1000} step={10}
              value={messageCost}
              onChange={(e) => { setMessageCost(Number(e.target.value)); scheduleSimulate() }}
              className="mt-2 w-full accent-ember"
            />
          </div>

          <div>
            <div className="flex items-baseline justify-between">
              <label className="kicker">Sample size</label>
              <span className="tnum text-sm">{sampleSize} cases</span>
            </div>
            <input
              type="range" min={50} max={600} step={10}
              value={sampleSize}
              onChange={(e) => { setSampleSize(Number(e.target.value)); scheduleSimulate() }}
              className="mt-2 w-full accent-ember"
            />
          </div>
        </div>

        <button
          onClick={resetDefaults}
          className="mt-5 border border-line bg-paper px-3 py-1.5 text-xs hover:border-heading"
        >
          Reset to production defaults
        </button>

        {loading && (
          <p className="mt-3 text-xs text-faded">Simulating…</p>
        )}
      </div>

      {result && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="border border-ochre bg-paper px-1.5 py-0.5 text-[10px] text-ochre">
              SIMULATED — no data written
            </span>
            <span className="kicker">{result.sample_size_used} cases processed</span>
          </div>

          <div className="grid grid-cols-2 gap-x-6 bg-panel md:grid-cols-3">
            <Figure label="At risk" value={result.total_at_risk_amount} money
                    note={`${result.total_cases} cases`} />
            <Figure label="Recovered" value={result.total_recovered_amount} money tone="pine" />
            <Figure label="Net recovered" value={result.net_recovered} money
                    tone={result.net_recovered >= 0 ? 'pine' : 'clay'}
                    note={`after ${inr(result.total_cost)} outreach cost`} />
            <Figure label="Recovery rate" value={result.recovery_rate * 100} suffix="%"
                    note={`baseline ${pct(result.baseline_recovery_rate)}`} />
            <Figure label="False-positive cost" value={result.false_positive_cost} money tone="clay"
                    note={`${result.cases_blocked_by_stopping_rules} stopped by rules`} />
            <Figure label="Spent" value={result.total_cost} money />
          </div>
        </div>
      )}
    </div>
  )
}
