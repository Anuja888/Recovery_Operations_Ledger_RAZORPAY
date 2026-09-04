import { useState } from 'react'
import { api } from './api'
import About from './screens/About'
import Dashboard from './screens/Dashboard'
import CaseExplorer from './screens/CaseExplorer'
import BatchRunner from './screens/BatchRunner'
import PolicySandbox from './screens/PolicySandbox'
import FailureStory from './screens/FailureStory'

type Screen = 'about' | 'failure' | 'dashboard' | 'cases' | 'runner' | 'sandbox'

const NAV: { id: Screen; index: string; label: string; hint: string }[] = [
  { id: 'about', index: '00', label: 'About', hint: 'what this is and how it works' },
  { id: 'failure', index: '01', label: 'Failure story', hint: 'what broke & how it was fixed' },
  { id: 'dashboard', index: '02', label: 'Ledger', hint: 'batch results & segments' },
  { id: 'cases', index: '03', label: 'Case files', hint: 'every decision, traced' },
  { id: 'runner', index: '04', label: 'Run batch', hint: 'process failed payments' },
  { id: 'sandbox', index: '05', label: 'Try the rules', hint: 'simulate policy changes' },
]

export default function App() {
  const [screen, setScreen] = useState<Screen>('about')
  const [batchId, setBatchId] = useState<string | null>(null)
  const [caseClassFilter, setCaseClassFilter] = useState<string | undefined>(undefined)
  const [navOpen, setNavOpen] = useState(false)
  const [seeded, setSeeded] = useState(false)

  async function seed() {
    setSeeded(true)
    try {
      // `api.seed()` already routes through the configured VITE_API_BASE
      // so the deployed Vercel frontend hits the real backend, not itself.
      await api.seed(true)
      window.location.reload()
    } catch (e) {
      setSeeded(false)
      alert('Setup failed: ' + (e as Error).message)
    }
  }

  function openCases(failureClass?: string) {
    setCaseClassFilter(failureClass)
    setScreen('cases')
  }

  return (
    <div className="flex min-h-screen">
      {/* ---- rail (dark espresso, warm white text) ---- */}
      <aside className={`${navOpen ? 'translate-x-0' : '-translate-x-full'} fixed z-20 flex h-screen w-60 shrink-0 flex-col bg-pine-deep text-[var(--color-rail-text)] transition-transform md:sticky md:top-0 md:translate-x-0`}>
        <div className="border-b border-[var(--color-rail-border)] px-5 py-5">
          <div className="font-serif text-2xl leading-none tracking-tight text-[var(--color-rail-text-strong)]">RENEW</div>
          <div className="mt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-rail-text-hint)]">recovery operations ledger</div>
        </div>

        <nav className="flex-1 py-3">
          {NAV.map((item) => {
            const active = screen === item.id
            return (
              <button
                key={item.id}
                onClick={() => { setScreen(item.id); setNavOpen(false) }}
                className={`block w-full border-l-2 px-5 py-3 text-left transition-colors ${
                  active
                    ? 'border-[var(--color-rail-active-border)] bg-[var(--color-rail-hover)] text-[var(--color-rail-text-strong)]'
                    : 'border-transparent text-[var(--color-rail-text-hint-active)] hover:bg-[var(--color-rail-hover)] hover:border-[var(--color-rail-hover-border)]'
                }`}
              >
                <span className={`tnum mr-2 text-xs ${active ? 'text-[var(--color-rail-number-active)]' : 'text-[var(--color-rail-number)]'}`}>
                  {item.index}
                </span>
                <span className="font-medium">{item.label}</span>
                <div className={`mt-0.5 text-[11px] ${active ? 'text-[var(--color-rail-text-hint-active)]' : 'text-[var(--color-rail-text-hint)]'}`}>{item.hint}</div>
              </button>
            )
          })}
        </nav>

        <div className="border-t border-[var(--color-rail-border)] px-5 py-4 text-[11px] leading-relaxed text-[var(--color-rail-text-hint)]">
          Deterministic policy decides.<br />
          The LLM only reads and writes words.<br />
          Everything is audited.
        </div>
      </aside>

      {navOpen && (
        <button
          aria-label="close menu"
          onClick={() => setNavOpen(false)}
          className="fixed inset-0 z-10 bg-black/40 md:hidden"
        />
      )}

      {/* ---- main sheet (light) ---- */}
      <div className="min-w-0 flex-1">
        <header className="flex items-center gap-3 border-b border-line bg-panel px-5 py-3 md:hidden">
          <button onClick={() => setNavOpen(true)}
                  className="rounded border border-line px-2 py-1 text-sm">☰</button>
          <span className="font-serif text-lg text-heading">RENEW</span>
        </header>

        <main className="mx-auto max-w-6xl px-5 py-7 md:px-9">
          {screen === 'about' && (
            <About onSeed={seed} seeding={seeded} onNavigate={(id) => setScreen(id as Screen)} />
          )}
          {screen === 'failure' && (
            <FailureStory />
          )}
          {screen === 'dashboard' && (
            <Dashboard batchId={batchId} onBatchChange={setBatchId} onOpenCases={openCases} onNavigate={(id) => setScreen(id as Screen)} />
          )}
          {screen === 'cases' && (
            <CaseExplorer initialFailureClass={caseClassFilter} />
          )}
          {screen === 'runner' && (
            <BatchRunner
              onDone={(id) => { setBatchId(id); setScreen('dashboard') }}
            />
          )}
          {screen === 'sandbox' && (
            <PolicySandbox />
          )}
        </main>
      </div>
    </div>
  )
}
