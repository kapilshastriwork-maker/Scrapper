import { useCallback, useEffect, useState } from 'react'
import { getCollectorResults, getCollectors, runCollector } from '../api/client'
import type { Collector, ScrapeResult } from '../types'
import { formatPrice, formatRelativeTime } from '../utils/format'

function isInStock(stock: string | null): boolean {
  if (!stock) return false
  const value = stock.toLowerCase()
  return value.includes('stock') || value.includes('available')
}

function ProductCard({
  collector,
  result,
  running,
  cardError,
  onRefresh,
}: {
  collector: Collector
  result: ScrapeResult | null
  running: boolean
  cardError: string | null
  onRefresh: () => void
}) {
  const inStock = result !== null && isInStock(result.stock_status)
  const showOriginal =
    result !== null &&
    result.original_price !== null &&
    result.original_price !== result.price

  return (
    <article className="flex flex-col rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          {collector.name}
        </h3>
        {result !== null && !result.is_valid && (
          <span className="rounded bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
            Data flagged
          </span>
        )}
      </div>

      {result === null ? (
        <p className="mt-4 text-sm text-slate-500">No data yet</p>
      ) : (
        <>
          <p className="mt-3 line-clamp-2 text-base font-medium text-slate-100">
            {result.title ?? '(missing title)'}
          </p>
          <p className="mt-2 flex items-baseline gap-2">
            <span className="text-xl font-bold text-white">
              {formatPrice(result.price)}
            </span>
            {showOriginal && (
              <span className="text-sm text-slate-500 line-through">
                {formatPrice(result.original_price)}
              </span>
            )}
          </p>
          <div className="mt-3 flex items-center justify-between gap-2">
            <span
              className={
                inStock
                  ? 'rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-400'
                  : 'rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-400'
              }
            >
              {result.stock_status?.trim() || 'unknown stock'}
            </span>
          </div>
          <p className="mt-4 text-xs text-slate-500">
            Last scraped {formatRelativeTime(result.scraped_at)}
          </p>
        </>
      )}

      <div className="mt-auto pt-4">
        {cardError && <p className="mb-2 text-xs text-rose-400">{cardError}</p>}
        <button
          type="button"
          onClick={onRefresh}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-700/60 px-3 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {running && (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-transparent" />
          )}
          {running ? 'Scraping…' : 'Refresh'}
        </button>
      </div>
    </article>
  )
}

function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="h-3 w-24 rounded bg-slate-800" />
      <div className="mt-4 h-4 w-3/4 rounded bg-slate-800" />
      <div className="mt-3 h-6 w-28 rounded bg-slate-800" />
      <div className="mt-3 h-4 w-20 rounded bg-slate-800" />
      <div className="mt-6 h-4 w-28 rounded bg-slate-800" />
    </div>
  )
}

function ProductGrid() {
  const [collectors, setCollectors] = useState<Collector[] | null>(null)
  const [results, setResults] = useState<Record<string, ScrapeResult | null>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState<Record<string, boolean>>({})
  const [cardErrors, setCardErrors] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const collectorList = await getCollectors()
      setCollectors(collectorList)
      const settled = await Promise.allSettled(
        collectorList.map((collector) => getCollectorResults(collector.id)),
      )
      const next: Record<string, ScrapeResult | null> = {}
      collectorList.forEach((collector, index) => {
        next[collector.id] =
          settled[index].status === 'fulfilled'
            ? (settled[index].value[0] ?? null)
            : null
      })
      setResults(next)
    } catch (err) {
      setError(
        err instanceof Error
          ? `Couldn't load collectors: ${err.message}`
          : "Couldn't load collectors — is the backend running?",
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleRefresh = useCallback(
    async (collectorId: string) => {
      setRunning((prev) => ({ ...prev, [collectorId]: true }))
      setCardErrors((prev) => ({ ...prev, [collectorId]: '' }))
      try {
        await runCollector(collectorId)
        const latest = await getCollectorResults(collectorId)
        setResults((prev) => ({ ...prev, [collectorId]: latest[0] ?? null }))
      } catch (err) {
        setCardErrors((prev) => ({
          ...prev,
          [collectorId]:
            err instanceof Error
              ? `Refresh failed: ${err.message}`
              : 'Refresh failed',
        }))
      } finally {
        setRunning((prev) => ({ ...prev, [collectorId]: false }))
      }
    },
    [],
  )

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    )
  }

  if (error || collectors === null) {
    return (
      <div className="rounded-xl border border-rose-900/50 bg-rose-950/30 p-6">
        <h2 className="text-lg font-semibold text-rose-300">Failed to load</h2>
        <p className="mt-1 text-sm text-rose-200/80">
          {error ?? 'Unknown error'} Make sure the backend is running on
          http://localhost:8000.
        </p>
        <button
          type="button"
          onClick={load}
          className="mt-4 rounded-lg bg-rose-500/20 px-3 py-1.5 text-sm font-medium text-rose-200 transition-colors hover:bg-rose-500/30"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {collectors.map((collector) => (
        <ProductCard
          key={collector.id}
          collector={collector}
          result={results[collector.id] ?? null}
          running={running[collector.id] ?? false}
          cardError={cardErrors[collector.id] ?? null}
          onRefresh={() => handleRefresh(collector.id)}
        />
      ))}
    </div>
  )
}

export default ProductGrid
