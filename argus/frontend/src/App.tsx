import { useState } from 'react'
import type { ComponentType } from 'react'
import CollectorHealth from './components/CollectorHealth'
import HealFeed from './components/HealFeed'
import ProductGrid from './components/ProductGrid'

const TABS = [
  { id: 'products', label: 'Products' },
  { id: 'heal-feed', label: 'Heal Feed' },
  { id: 'collector-health', label: 'Collector Health' },
] as const

type TabId = (typeof TABS)[number]['id']

const TAB_COMPONENTS: Record<TabId, ComponentType> = {
  products: ProductGrid,
  'heal-feed': HealFeed,
  'collector-health': CollectorHealth,
}

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? 'rounded-lg bg-slate-700/60 px-4 py-2 text-sm font-medium text-slate-100 shadow-sm ring-1 ring-slate-600/50'
          : 'rounded-lg px-4 py-2 text-sm font-medium text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-200'
      }
    >
      {label}
    </button>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('products')
  const ActiveView = TAB_COMPONENTS[activeTab]

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <header className="border-b border-slate-800 bg-slate-900/60">
        <div className="mx-auto flex max-w-6xl items-baseline gap-3 px-6 py-5">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Argus
          </h1>
          <p className="text-sm text-slate-400">
            Self-Healing Price Intelligence
          </p>
        </div>
      </header>

      <nav className="mx-auto max-w-6xl px-6 pt-6">
        <div className="flex gap-2">
          {TABS.map((tab) => (
            <TabButton
              key={tab.id}
              label={tab.label}
              active={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
            />
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <ActiveView />
      </main>
    </div>
  )
}

export default App
