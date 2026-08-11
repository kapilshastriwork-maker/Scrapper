import { useCallback, useEffect, useState } from 'react'
import { getCollectorResults, getCollectors, runCollector } from '../api/client'
import type { Collector } from '../types'
import { formatRelativeTime } from '../utils/format'

type SuccessRate = { valid: number; total: number }

const STATUS_STYLES: Record<
  string,
  { label: string; badge: string }
> = {
  success: { label: 'Success', badge: 'bg-emerald-500/15 text-emerald-400' },
  degraded: { label: 'Degraded', badge: 'bg-amber-500/15 text-amber-400' },
  failed: { label: 'Failed', badge: 'bg-rose-500/15 text-rose-400' },
}

function statusBadge(lastStatus: string | null) {
  if (lastStatus === null) {
    return { label: 'Never run', badge: 'bg-slate-500/15 text-slate-400' }
  }
  return (
    STATUS_STYLES[lastStatus] ?? {
      label: lastStatus,
      badge: 'bg-slate-500/15 text-slate-400',
    }
  )
}

function rateColor(rate: number | null): string {
  if (rate === null) return 'bg-slate-600'
  if (rate >= 0.75) return 'bg-emerald-500'
  if (rate > 0) return 'bg-amber-500'
  return 'bg-rose-500'
}

function computeHealth(
  lastStatus: string | null,
  rate: SuccessRate | null,
): { label: string; text: string; dot: string } {
  if (rate === null) {
    if (lastStatus === null) {
      return { label: 'Unknown', text: 'text-slate-400', dot: 'bg-slate-500' }
    }
    if (lastStatus === 'success') {
      return { label: 'Healthy', text: 'text-emerald-400', dot: 'bg-emerald-400' }
    }
    if (lastStatus === 'degraded') {
      return { label: 'Degraded', text: 'text-amber-400', dot: 'bg-amber-400' }
    }
    if (lastStatus === 'failed') {
      return { label: 'Failing', text: 'text-rose-400', dot: 'bg-rose-500' }
    }
    return { label: 'Unknown', text: 'text-slate-400', dot: 'bg-slate-500' }
  }

  const fraction = rate.total > 0 ? rate.valid / rate.total : 0
  if (rate.total === 0) {
    return { label: 'Unknown', text: 'text-slate-400', dot: 'bg-slate-500' }
  }
  if (fraction >= 0.75) {
    return { label: 'Healthy', text: 'text-emerald-400', dot: 'bg-emerald-400' }
  }
  if (fraction > 0) {
    return { label: 'Degraded', text: 'text-amber-400', dot: 'bg-amber-400' }
  }
  return { label: 'Failing', text: 'text-rose-400', dot: 'bg-rose-500' }
}

function HealthRow({
  collector,
  rate,
  running,
  error,
  onRun,
}: {
  collector: Collector
  rate: SuccessRate | null
  running: boolean
  error: string | null
  onRun: () => void
}) {
  const status = statusBadge(collector.last_status)
  const health = computeHealth(collector.last_status, rate)
  const percent =
    rate !== null && rate.total > 0
      ? Math.round((rate.valid / rate.total) * 100)
      : null

  return (
    <tr className="border-b border-slate-800 last:border-0">
      <td className="px-4 py-3 text-sm font-medium text-slate-100">
        {collector.name}
      </td>
      <td className="px-4 py-3">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${status.badge}`}
        >
          {status.label}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center gap-1.5 text-sm ${health.text}`}>
          <span className={`h-2 w-2 rounded-full ${health.dot}`} />
          {health.label}
        </span>
      </td>
      <td className="px-4 py-3">
        {rate === null || rate.total === 0 ? (
          <span className="text-xs text-slate-500">No data</span>
        ) : (
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full ${rateColor(percent)}`}
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="text-xs text-slate-400">
              {percent}% ({rate.valid}/{rate.total})
            </span>
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500">
        {formatRelativeTime(collector.last_run_at)}
      </td>
      <td className="px-4 py-3">
        {error && <p className="mb-1 text-xs text-rose-400">{error}</p>}
        <button
          type="button"
          onClick={onRun}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-700/60 px-3 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {running && (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-transparent" />
          )}
          {running ? 'Running…' : 'Run'}
        </button>
      </td>
    </tr>
  )
}

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex gap-6 rounded-lg bg-slate-900/60 px-4 py-4">
          <div className="h-4 w-24 rounded bg-slate-800" />
          <div className="h-4 w-20 rounded bg-slate-800" />
          <div className="h-4 w-16 rounded bg-slate-800" />
          <div className="h-4 w-32 rounded bg-slate-800" />
          <div className="h-4 w-20 rounded bg-slate-800" />
        </div>
      ))}
    </div>
  )
}

function CollectorHealth() {
  const [collectors, setCollectors] = useState<Collector[] | null>(null)
  const [rates, setRates] = useState<Record<string, SuccessRate | null>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runningIds, setRunningIds] = useState<Record<string, boolean>>({})
  const [runAll, setRunAll] = useState(false)
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const collectorList = await getCollectors()
      setCollectors(collectorList)
      const settled = await Promise.allSettled(
        collectorList.map((collector) => getCollectorResults(collector.id)),
      )
      const next: Record<string, SuccessRate | null> = {}
      collectorList.forEach((collector, index) => {
        const results =
          settled[index].status === 'fulfilled' ? settled[index].value : []
        next[collector.id] =
          results.length > 0
            ? {
                valid: results.filter((r) => r.is_valid).length,
                total: results.length,
              }
            : null
      })
      setRates(next)
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

  const refreshOne = useCallback(
    async (collectorId: string) => {
      const settled = await Promise.allSettled([getCollectorResults(collectorId)])
      if (settled[0].status === 'fulfilled') {
        const results = settled[0].value
        setRates((prev) => ({
          ...prev,
          [collectorId]:
            results.length > 0
              ? {
                  valid: results.filter((r) => r.is_valid).length,
                  total: results.length,
                }
              : null,
        }))
      }
      setCollectors(await getCollectors())
    },
    [],
  )

  const runOne = useCallback(
    async (collectorId: string) => {
      setRunningIds((prev) => ({ ...prev, [collectorId]: true }))
      setRowErrors((prev) => ({ ...prev, [collectorId]: '' }))
      try {
        await runCollector(collectorId)
        await refreshOne(collectorId)
      } catch (err) {
        setRowErrors((prev) => ({
          ...prev,
          [collectorId]:
            err instanceof Error ? `Run failed: ${err.message}` : 'Run failed',
        }))
      } finally {
        setRunningIds((prev) => ({ ...prev, [collectorId]: false }))
      }
    },
    [refreshOne],
  )

  const handleRunAll = useCallback(async () => {
    if (collectors === null) return
    setRunAll(true)
    let index = 0
    for (const collector of collectors) {
      index += 1
      await runOne(collector.id)
    }
    setRunAll(false)
  }, [collectors, runOne])

  const runningCount =
    collectors === null ? 0 : collectors.filter((c) => runningIds[c.id]).length

  return (
    <section>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">
            Collector Health
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Status of each collector and its recent runs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={load}
            className="rounded-lg bg-slate-700/60 px-3 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={handleRunAll}
            disabled={runAll || loading}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-600/80 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {runAll && (
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/70 border-t-transparent" />
            )}
            {runAll
              ? `Running ${runningCount}/${collectors?.length ?? 4}…`
              : 'Run All Now'}
          </button>
        </div>
      </div>

      {loading ? (
        <TableSkeleton />
      ) : error ? (
        <div className="rounded-xl border border-rose-900/50 bg-rose-950/30 p-6">
          <h2 className="text-lg font-semibold text-rose-300">Failed to load</h2>
          <p className="mt-1 text-sm text-rose-200/80">
            {error} Make sure the backend is running on http://localhost:8000.
          </p>
          <button
            type="button"
            onClick={load}
            className="mt-4 rounded-lg bg-rose-500/20 px-3 py-1.5 text-sm font-medium text-rose-200 transition-colors hover:bg-rose-500/30"
          >
            Retry
          </button>
        </div>
      ) : collectors === null || collectors.length === 0 ? (
        <div className="flex min-h-72 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/50">
          <p className="text-sm text-slate-500">No collectors configured.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3 font-medium">Collector</th>
                <th className="px-4 py-3 font-medium">Last status</th>
                <th className="px-4 py-3 font-medium">Health</th>
                <th className="px-4 py-3 font-medium">Success rate</th>
                <th className="px-4 py-3 font-medium">Last run</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {collectors.map((collector) => (
                <HealthRow
                  key={collector.id}
                  collector={collector}
                  rate={rates[collector.id] ?? null}
                  running={runningIds[collector.id] ?? false}
                  error={rowErrors[collector.id] ?? null}
                  onRun={() => runOne(collector.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default CollectorHealth
