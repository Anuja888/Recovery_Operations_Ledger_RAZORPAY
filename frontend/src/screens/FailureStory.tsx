import { useEffect, useState } from 'react'
import { api } from '../api'

const inr = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN')
const inrExact = (v: number) => {
  const n = Math.round(v * 100) / 100
  return '₹' + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const pct = (v: number) => (v * 100).toFixed(1) + '%'

type BatchRow = Record<string, unknown>
type SegmentRow = Record<string, unknown> | null
type Narrative = Record<string, string>
type Side = { batch: BatchRow; segment: SegmentRow }
type Story = {
  before: Side
  after: Side
  narrative: Narrative
  latest?: { before: Side; after: Side } | null
}

function segMetrics(s: SegmentRow) {
  return {
    cases: typeof s?.cases === 'number' ? s.cases : 0,
    recoveredCases: typeof s?.recovered_cases === 'number' ? s.recovered_cases : 0,
    recoveredAmount: typeof s?.recovered_amount === 'number' ? s.recovered_amount : 0,
    cost: typeof s?.cost === 'number' ? s.cost : 0,
    net: typeof s?.net_recovered === 'number' ? s.net_recovered : 0,
    rate: typeof s?.recovery_rate === 'number' ? s.recovery_rate : 0,
  }
}

function StoryCard({ title, batch, segment, tone, label }: {
  title: string; batch: BatchRow; segment: SegmentRow;
  tone: 'rust' | 'ink' | 'faded'; label?: string
}) {
  const cases = typeof batch.total_cases === 'number' ? batch.total_cases : 0
  const net = typeof batch.net_recovered === 'number' ? batch.net_recovered : 0
  const seg = segMetrics(segment)
  const toneText = tone === 'rust' ? 'text-rust' : tone === 'ink' ? 'text-ink' : 'text-faded'

  return (
    <div className="flex-1 border border-line bg-panel">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <div className="kicker text-heading">{title}</div>
            {label && <div className="mt-0.5 text-[10px] uppercase tracking-widest text-faded">{label}</div>}
          </div>
          <div className="text-right">
            <div className="kicker text-heading">Batch net</div>
            <div className="tnum mt-0.5 font-serif text-xl text-ink">
              {inr(net)}
            </div>
          </div>
        </div>
        <div className="tnum mt-1 text-xs text-faded">{cases} cases processed</div>
      </div>
      <div className="p-4">
        {segment ? (
          <div className="space-y-3">
            <div>
              <div className="kicker text-heading">Failure segment · insufficient_funds | pfc ≥ 3</div>
              <div className="tnum mt-1 font-serif text-2xl font-semibold">
                {seg.cases} cases · {seg.recoveredCases} recovered
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 border-t border-line pt-3">
              <div>
                <div className="kicker text-heading">Outreach cost</div>
                <div className={`tnum mt-1 font-serif text-xl font-semibold ${toneText}`}>{inrExact(seg.cost)}</div>
              </div>
              <div>
                <div className="kicker text-heading">Recovered</div>
                <div className={`tnum mt-1 font-serif text-xl font-semibold ${tone === 'rust' ? 'text-ink' : 'text-ink'}`}>
                  {inrExact(seg.recoveredAmount)}
                </div>
              </div>
              <div>
                <div className="kicker text-heading">Net</div>
                <div className={`tnum mt-1 font-serif text-xl font-semibold ${toneText}`}>{inrExact(seg.net)}</div>
              </div>
              <div>
                <div className="kicker text-heading">Recovery rate</div>
                <div className={`tnum mt-1 font-serif text-xl font-semibold ${toneText}`}>{pct(seg.rate)}</div>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-faded">Segment data not available.</p>
        )}
      </div>
    </div>
  )
}

function SectionDivider({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="flex items-center gap-3 border-t border-line pt-5">
      <div className="kicker whitespace-nowrap text-heading">{label}</div>
      <div className="h-px flex-1 bg-line" />
      {hint && <div className="text-[10px] uppercase tracking-widest text-faded">{hint}</div>}
    </div>
  )
}

export default function FailureStory() {
  const [story, setStory] = useState<Story | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const s = await api.failureStory()
      setStory(s as Story)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function rerun() {
    setLoading(true)
    setError(null)
    try {
      const s = await api.rerunFailureStory()
      // Only update the latest field; canonical numbers are pinned server-side
      // and re-loaded from the response, so the top section never changes.
      setStory(prev => prev ? { ...prev, latest: s.latest ?? null } : (s as Story))
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  if (!story && !error) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="border-b-2 border-line pb-4">
          <h1 className="font-serif text-[28px] leading-tight text-heading">Failure story</h1>
          <p className="mt-1 text-sm text-faded">
            How a hidden segment almost destroyed a successful batch.
          </p>
        </div>
        <div className="border border-dashed border-line bg-panel px-6 py-16 text-center">
          <p className="font-serif text-xl">No failure story yet.</p>
          <p className="mt-2 text-sm text-faded">
            Run <code className="tnum border border-line bg-paper px-1">scripts/failure_demo.py</code> to generate the before/after data.
          </p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="border-b-2 border-line pb-4">
          <h1 className="font-serif text-[28px] leading-tight text-heading">Failure story</h1>
        </div>
        <p className="border-l-2 border-clay bg-panel px-3 py-2 text-sm text-clay">{error}</p>
      </div>
    )
  }

  const beforeSeg = segMetrics(story!.before.segment)
  const afterSeg = segMetrics(story!.after.segment)
  const delta = afterSeg.cost - beforeSeg.recoveredAmount
  const headline = beforeSeg.cost > 0
    ? `This segment spent ${inrExact(beforeSeg.cost)} on outreach and recovered only ${inrExact(beforeSeg.recoveredAmount)} — net ${inrExact(beforeSeg.net)}. The fix below stops the bleed.`
    : `This segment no longer triggers outreach under the hardened rule.`

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="border-b-2 border-line pb-4">
        <h1 className="font-serif text-[28px] leading-tight text-heading">Failure story</h1>
        <p className="mt-1 text-sm text-faded">
          How a hidden segment almost destroyed a successful batch.
        </p>
      </div>

      {error && (
        <p className="border-l-2 border-clay bg-panel px-3 py-2 text-sm text-clay">{error}</p>
      )}

      <div className="border-2 border-heading bg-paper px-5 py-4">
        <div className="kicker text-heading">Headline</div>
        <p className="mt-1 font-serif text-xl leading-snug">{headline}</p>
        {delta > 0 && (
          <p className="tnum mt-2 text-sm text-faded">
            Stopping this segment saves {inrExact(delta)} per batch ({inrExact(beforeSeg.cost)} outreach − {inrExact(beforeSeg.recoveredAmount)} recovered).
          </p>
        )}
      </div>

      <SectionDivider label="Canonical · pinned at seed" hint="does not change on rerun" />

      <div className="flex flex-col gap-4 md:flex-row">
        <StoryCard title="Before — v1 policy" batch={story!.before.batch}
                   segment={story!.before.segment} tone="rust" label="canonical" />
        <StoryCard title="After — hardened rule" batch={story!.after.batch}
                   segment={story!.after.segment} tone="ink" label="canonical" />
      </div>

      <div className="space-y-4 border border-line bg-panel p-5">
        <div>
          <div className="kicker text-heading">What happened</div>
          <p className="mt-1.5 text-sm leading-relaxed">{story!.narrative.what_happened}</p>
        </div>
        <div className="border-t border-line pt-4">
          <div className="kicker text-heading">How it was found</div>
          <p className="mt-1.5 text-sm leading-relaxed">{story!.narrative.how_found}</p>
        </div>
        <div className="border-t border-line pt-4">
          <div className="kicker text-heading">What changed</div>
          <p className="mt-1.5 text-sm leading-relaxed">{story!.narrative.what_changed}</p>
        </div>
      </div>

      <button
        onClick={rerun}
        disabled={loading}
        className="w-full bg-ember py-2.5 font-medium tracking-wide text-paper
                   transition-colors hover:bg-ember-hover disabled:cursor-wait disabled:opacity-60"
      >
        {loading ? 'RUNNING…' : 'Re-run live (does not change the canonical above)'}
      </button>

      {story!.latest && (
        <>
          <SectionDivider label="Latest live sample" hint="updated by re-run" />
          <div className="flex flex-col gap-4 md:flex-row">
            <StoryCard title="Before — v1 policy" batch={story!.latest.before.batch}
                       segment={story!.latest.before.segment} tone="faded" label="live sample" />
            <StoryCard title="After — hardened rule" batch={story!.latest.after.batch}
                       segment={story!.latest.after.segment} tone="faded" label="live sample" />
          </div>
        </>
      )}
    </div>
  )
}
