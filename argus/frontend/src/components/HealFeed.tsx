import { useCallback, useEffect, useState } from 'react'
import {
  approveHealEvent,
  getHealEvents,
  rejectHealEvent,
} from '../api/client'
import type { HealEvent } from '../types'
import { formatRelativeTime } from '../utils/format'

const STATUS_STYLES: Record<
  string,
  { label: string; badge: string; dot: string }
> = {
  pending: {
    label: 'Pending Review',
    badge: 'bg-amber-500/15 text-amber-400',
    dot: 'bg-amber-400',
  },
  approved: {
    label: 'Approved',
    badge: 'bg-emerald-500/15 text-emerald-400',
    dot: 'bg-emerald-400',
  },
  rejected: {
    label: 'Rejected',
    badge: 'bg-slate-500/15 text-slate-400',
    dot: 'bg-slate-500',
  },
  heal_already_in_progress: {
    label: 'Blocked (heal already running)',
    badge: 'bg-sky-500/15 text-sky-400',
    dot: 'bg-sky-400',
  },
  heal_request_failed: {
    label: 'Heal Request Failed',
    badge: 'bg-rose-500/15 text-rose-400',
    dot: 'bg-rose-500',
  },
}

function statusStyle(status: string) {
  return (
    STATUS_STYLES[status] ?? {
      label: status,
      badge: 'bg-slate-500/15 text-slate-400',
      dot: 'bg-slate-500',
    }
  )
}

function HealEventEntry({
  event,
  expanded,
  busy,
  actionError,
  onToggle,
  onApprove,
  onReject,
}: {
  event: HealEvent
  expanded: boolean
  busy: boolean
  actionError: string | null
  onToggle: () => void
  onApprove: () => void
  onReject: () => void
}) {
  const style = statusStyle(event.status)

  return (
    <li className="relative pl-6">
      <span
        className={`absolute -left-[4px] top-1.5 h-2.5 w-2.5 rounded-full ${style.dot}`}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-slate-100">
          {event.collector_name ?? event.collector_id}
        </h3>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style.badge}`}
        >
          {style.label}
        </span>
        <time className="text-xs text-slate-500">
          {formatRelativeTime(event.detected_at)}
        </time>
      </div>

      <p className="mt-2 text-sm text-slate-300">{event.issue_description}</p>

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={onToggle}
          className="text-xs font-medium text-sky-400 transition-colors hover:text-sky-300"
        >
          {expanded ? 'Hide prompt' : 'Show prompt'}
        </button>

        {event.status === 'pending' && (
          <>
            <button
              type="button"
              onClick={onApprove}
              disabled={busy}
              className="rounded-lg bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-400 transition-colors hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? 'Updating…' : 'Approve'}
            </button>
            <button
              type="button"
              onClick={onReject}
              disabled={busy}
              className="rounded-lg bg-rose-500/15 px-3 py-1 text-xs font-medium text-rose-400 transition-colors hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? 'Updating…' : 'Reject'}
            </button>
          </>
        )}
      </div>

      {actionError && (
        <p className="mt-2 text-xs text-rose-400">{actionError}</p>
      )}

      {expanded && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <p className="text-xs text-slate-500">
            Heal prompt ({event.heal_prompt.length} chars)
          </p>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-300">
            {event.heal_prompt}
          </pre>
          {event.error_message && (
            <>
              <p className="mt-4 text-xs text-slate-500">Error</p>
              <pre className="mt-1 whitespace-pre-wrap font-mono text-xs leading-relaxed text-rose-300">
                {event.error_message}
              </pre>
            </>
          )}
        </div>
      )}
    </li>
  )
}

function FeedSkeleton() {
  return (
    <div className="animate-pulse space-y-8">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="pl-6">
          <div className="h-4 w-32 rounded bg-slate-800" />
          <div className="mt-3 h-3 w-2/3 rounded bg-slate-800" />
          <div className="mt-2 h-3 w-1/3 rounded bg-slate-800" />
        </div>
      ))}
    </div>
  )
}

function HealFeed() {
  const [events, setEvents] = useState<HealEvent[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  const [actionBusy, setActionBusy] = useState<number | null>(null)
  const [actionError, setActionError] = useState<{
    id: number
    message: string
  } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setEvents(await getHealEvents())
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Couldn't load heal events — is the backend running?",
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleAction = useCallback(
    async (eventId: number, action: 'approve' | 'reject') => {
      setActionBusy(eventId)
      setActionError(null)
      try {
        if (action === 'approve') {
          await approveHealEvent(eventId)
        } else {
          await rejectHealEvent(eventId)
        }
        setEvents(await getHealEvents())
      } catch (err) {
        setActionError({
          id: eventId,
          message: err instanceof Error ? err.message : 'Action failed',
        })
      } finally {
        setActionBusy(null)
      }
    },
    [],
  )

  return (
    <section>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">Heal Feed</h2>
          <p className="mt-1 text-sm text-slate-400">
            A timeline of detected issues and heal events.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="rounded-lg bg-slate-700/60 px-3 py-1.5 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700"
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <FeedSkeleton />
      ) : error ? (
        <div className="rounded-xl border border-rose-900/50 bg-rose-950/30 p-6">
          <h2 className="text-lg font-semibold text-rose-300">
            Failed to load
          </h2>
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
      ) : events === null || events.length === 0 ? (
        <div className="flex min-h-72 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/50">
          <p className="text-sm text-slate-500">
            No heal events yet — detected issues and their heal events will
            appear here.
          </p>
        </div>
      ) : (
        <ol className="relative ml-2 space-y-8 border-l-2 border-slate-800">
          {events.map((event) => (
            <HealEventEntry
              key={event.id}
              event={event}
              expanded={expanded[event.id] ?? false}
              busy={actionBusy === event.id}
              actionError={
                actionError !== null && actionError.id === event.id
                  ? actionError.message
                  : null
              }
              onToggle={() =>
                setExpanded((prev) => ({ ...prev, [event.id]: !prev[event.id] }))
              }
              onApprove={() => handleAction(event.id, 'approve')}
              onReject={() => handleAction(event.id, 'reject')}
            />
          ))}
        </ol>
      )}
    </section>
  )
}

export default HealFeed
