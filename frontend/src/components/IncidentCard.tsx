import { useState } from 'react'
import type { Incident } from '../api'
import { formatNumber, formatTime, formatTimeRange } from '../format'

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  low: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
}

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'CRIT',
  high: 'HIGH',
  medium: 'MED',
  low: 'LOW',
}

export default function IncidentCard({ incident }: { incident: Incident }) {
  const [open, setOpen] = useState(false)
  const analyzed = incident.analysis_status === 'COMPLETED'
  const failed = incident.analysis_status === 'FAILED'

  return (
    <li className="rounded-lg border border-gray-200 dark:border-gray-800">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-900"
      >
        <span className="text-gray-400">{open ? '▾' : '▸'}</span>
        <span className="w-12 shrink-0 text-xs font-semibold">
          {analyzed && incident.severity ? (
            <span
              className={`inline-block rounded px-1.5 py-0.5 ${SEVERITY_STYLES[incident.severity] ?? ''}`}
            >
              {SEVERITY_LABEL[incident.severity] ?? incident.severity.toUpperCase()}
            </span>
          ) : (
            <span className="text-gray-400">—</span>
          )}
        </span>
        <span className="w-24 shrink-0 truncate text-xs text-gray-500 dark:text-gray-400">
          {analyzed ? incident.category : '—'}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium" title={incident.sample_message}>
          {analyzed ? incident.title : incident.sample_message}
        </span>
        <span className="shrink-0 text-sm tabular-nums text-gray-500 dark:text-gray-400">
          {formatNumber(incident.event_count)}
        </span>
        <span className="hidden shrink-0 text-xs text-gray-400 sm:inline">
          {formatTime(incident.first_seen)}
        </span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-gray-200 px-4 py-3 text-sm dark:border-gray-800">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
            <span>
              Service: <span className="font-medium text-gray-700 dark:text-gray-200">{incident.service}</span>
            </span>
            <span>
              Level: <span className="font-medium text-gray-700 dark:text-gray-200">{incident.level}</span>
            </span>
            <span>
              Events: <span className="font-medium text-gray-700 dark:text-gray-200">{formatNumber(incident.event_count)}</span>
            </span>
            <span>
              Time: <span className="font-medium text-gray-700 dark:text-gray-200">{formatTimeRange(incident.first_seen, incident.last_seen)}</span>
            </span>
          </div>

          {analyzed ? (
            <>
              <div>
                <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Summary
                </h5>
                <p className="whitespace-pre-wrap">{incident.summary}</p>
              </div>
              <div>
                <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Likely cause
                </h5>
                <p className="whitespace-pre-wrap">{incident.likely_cause}</p>
              </div>
              {incident.evidence.length > 0 && (
                <div>
                  <h5 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Evidence lines
                  </h5>
                  <ul className="space-y-1 overflow-x-auto rounded-md bg-gray-100 p-2 font-mono text-xs dark:bg-gray-900">
                    {incident.evidence.map((line) => (
                      <li key={line.line_number} className="whitespace-pre-wrap break-all">
                        <span className="text-gray-400">L{line.line_number}</span>{' '}
                        <span className={line.level === 'ERROR' || line.level === 'FATAL' ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'}>
                          {line.level}
                        </span>{' '}
                        {line.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : failed ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              <span className="font-semibold">Analysis failed:</span> {incident.analysis_error}
            </div>
          ) : (
            <p className="text-gray-500 dark:text-gray-400">
              Not analyzed yet. Run <span className="font-medium">Analyze</span> to get a summary and likely cause.
            </p>
          )}
        </div>
      )}
    </li>
  )
}
