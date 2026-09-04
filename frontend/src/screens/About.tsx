import { useEffect, useState } from 'react'
import { api } from '../api'

const STEPS = [
  { n: 1, title: 'Diagnosis', body: 'Each failed payment is classified into a fixed failure class (expired card, insufficient funds, bank decline, mandate cancelled) using deterministic rules first and an LLM only for ambiguous free-text messages.' },
  { n: 2, title: 'Score', body: 'A tabular ML model predicts how recoverable the case is — calibrated probability, sub-millisecond, fully reproducible.' },
  { n: 3, title: 'Policy decision', body: 'A pure, deterministic rules module selects exactly one bounded intervention. The LLM never touches this step. Every decision records a human-readable reason.' },
  { n: 4, title: 'Intervention', body: 'The system simulates the chosen action: retry now, retry after cooldown, send a recovery message, escalate to a human, or stop.' },
  { n: 5, title: 'Audit', body: 'Every step is appended to an immutable audit trail. Batch metrics are computed from stored rows — nothing is hardcoded.' },
]

const NAV_GUIDE = [
  { label: 'Failure story', body: 'The documented failure — a hidden segment almost destroyed a successful batch. A deterministic rule fixed it.' },
  { label: 'Ledger', body: 'Batch results, segment breakdowns, and AI usage. Click any segment bar to open its case files.' },
  { label: 'Case files', body: 'Trace any case end-to-end: diagnosis → score → policy decision → message → audit. Use ↑/↓ to walk the docket.' },
  { label: 'Run batch', body: 'Process failed payments through the full pipeline. Toggle the hardened segment rule on or off to see the difference.' },
  { label: 'Try the rules', body: 'Sliders replay the policy engine in memory with different thresholds — no data is written.' },
]

type SeedStatus = 'unknown' | 'seeded' | 'seeding' | 'error'

export default function About({ onSeed, seeding, onNavigate }: {
  onSeed: () => void
  seeding: boolean
  onNavigate: (id: string) => void
}) {
  const [status, setStatus] = useState<SeedStatus>('unknown')

  useEffect(() => {
    let cancelled = false
    api.latestBatch()
      .then(() => { if (!cancelled) setStatus('seeded') })
      .catch(() => { if (!cancelled) setStatus('unknown') })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="mx-auto max-w-5xl px-5 md:px-9">
      {/* ---- hero (clean light surface, espresso accents) ---- */}
      <section className="hero-rise relative -mx-5 mt-[-1.75rem] overflow-hidden border-b border-line bg-paper px-5 py-20 md:-mx-9 md:px-9 md:py-28">
        <div aria-hidden className="hero-glow pointer-events-none absolute inset-0" />
        <div className="relative">
          <div className="kicker text-ochre">RENEW · recovery operations ledger</div>
          <h1 className="display mt-3 text-[44px] leading-[1.02] text-heading md:text-[64px]">
            Diagnose before you act.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-faded md:text-lg">
            RENEW turns failed subscription payments into measured recovery
            instead of blind retries. Every case flows through a controlled
            pipeline — diagnose, score, decide by rule, simulate the
            intervention, and record everything in an append-only audit
            trail. Decisions stay controlled, auditable, and reproducible.
          </p>
          <div className="mt-8 inline-block max-w-2xl border-l-2 border-ember bg-panel px-4 py-3">
            <div className="kicker text-ember">Where AI is used</div>
            <p className="mt-1 text-sm leading-relaxed text-ink">
              The LLM only <b>reads and writes words</b> — classifying
              ambiguous free-text failure reasons into a fixed enum, and
              drafting customer-facing message copy <i>after</i> the
              intervention has already been chosen.
            </p>
            <p className="mt-2 text-sm leading-relaxed text-faded">
              Every money-affecting decision — retry, cooldown, message,
              escalate, stop, and every rupee of budget — is made by a
              pure, deterministic, unit-tested rules module that never
              calls a model.
            </p>
          </div>
        </div>
      </section>

      {/* ---- spec-sheet pipeline (light) ---- */}
      <section className="mt-12">
        <div className="kicker mb-4">How a case is processed</div>
        <ol className="border-t border-line">
          {STEPS.map((s) => (
            <li key={s.n}
                className="grid grid-cols-[3rem_1fr] gap-6 border-b border-line py-4">
              <span className="tnum font-serif self-start text-2xl font-semibold text-ink">
                {String(s.n).padStart(2, '0')}
              </span>
              <div>
                <div className="font-medium">{s.title}</div>
                <p className="mt-1 text-sm leading-relaxed text-faded">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* ---- nav guide ---- */}
      <section className="mt-12">
        <div className="kicker mb-4">How to explore this app</div>
        <div className="border-t border-line">
          {NAV_GUIDE.map((g) => (
            <div key={g.label}
                 className="grid grid-cols-[12rem_1fr] gap-6 border-b border-line py-4">
              <span className="font-medium">{g.label}</span>
              <p className="text-sm leading-relaxed text-faded">{g.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- seed CTA ---- */}
      {status !== 'seeded' && (
        <section className="mt-10 border border-dashed border-line bg-panel px-6 py-8 text-center">
          <div className="kicker text-ochre">No demo data yet</div>
          <h3 className="font-serif mt-2 text-2xl font-semibold">
            Set up demo data
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-faded">
            Generates 2,000 synthetic cases, trains the scorer, and runs
            both before/after failure-story batches server-side. One click.
            No scripts to run by hand.
          </p>
          <button
            onClick={onSeed}
            disabled={seeding}
            className="mt-5 bg-ember px-7 py-3 font-medium tracking-wide text-paper
                       transition-colors hover:bg-ember-hover
                       disabled:cursor-wait disabled:opacity-60"
          >
            {seeding ? 'Setting up…' : 'Set up demo data'}
          </button>
          {seeding && (
            <p className="mt-3 text-xs text-faded">Generating cases, training model, running batches…</p>
          )}
        </section>
      )}
    </div>
  )
}
