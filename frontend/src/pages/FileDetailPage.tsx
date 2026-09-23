import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { analyzeFile, deleteFile, getFile, type FileDetail } from '../api'
import { formatNumber, formatTimeRange } from '../format'
import StatusBadge from '../components/StatusBadge'
import IncidentCard from '../components/IncidentCard'

const LEVEL_ORDER = ['FATAL', 'ERROR', 'WARN', 'INFO', 'DEBUG']
const LEVEL_STYLES: Record<string, string> = {
  FATAL: 'text-red-600 dark:text-red-400',
  ERROR: 'text-red-600 dark:text-red-400',
  WARN: 'text-amber-600 dark:text-amber-400',
  INFO: 'text-blue-600 dark:text-blue-400',
  DEBUG: 'text-gray-500 dark:text-gray-400',
}

export default function FileDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [file, setFile] = useState<FileDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const load = useCallback(async () => {
    if (!id) return
    try {
      const detail = await getFile(id)
      setFile(detail)
      setError(null)
      if (detail.status !== 'ANALYZING') setAnalyzing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load file.')
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // Poll every 3s while analyzing.
  useEffect(() => {
    if (!analyzing) return
    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [analyzing, load])

  const onAnalyze = async () => {
    if (!id) return
    setAnalyzing(true)
    try {
      await analyzeFile(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start analysis.')
      setAnalyzing(false)
    }
  }

  const onDelete = async () => {
    if (!id) return
    try {
      await deleteFile(id)
      navigate('/')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete file.')
      setConfirmDelete(false)
    }
  }

  if (error && !file) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
        {error}{' '}
        <button className="underline" onClick={() => navigate('/')}>
          Back to files
        </button>
      </div>
    )
  }
  if (!file) {
    return <p className="text-gray-500">Loading…</p>
  }

  const hasAnalyzed = file.status === 'ANALYZED' || file.incidents.some((i) => i.analysis_status !== 'NOT_ANALYZED')

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <button
            onClick={() => navigate('/')}
            className="mb-1 text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            ← All files
          </button>
          <h2 className="truncate text-lg font-semibold" title={file.original_filename}>
            {file.original_filename}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {formatNumber(file.parsed_events)} events · {formatNumber(file.unparsed_lines)} unparsed ·{' '}
            {formatTimeRange(file.time_start, file.time_end)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onAnalyze}
            disabled={analyzing || file.status === 'FAILED'}
            className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {analyzing && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {analyzing ? 'Analyzing incidents…' : hasAnalyzed ? 'Re-analyze' : 'Analyze'}
          </button>
          <button
            onClick={() => setConfirmDelete(true)}
            className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            Delete
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}
      {file.status === 'FAILED' && file.error_message && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {file.error_message}
        </div>
      )}

      <div className="flex flex-wrap gap-4 rounded-lg border border-gray-200 px-4 py-3 text-sm dark:border-gray-800">
        <StatusBadge status={file.status} />
        {LEVEL_ORDER.filter((l) => file.level_counts[l] !== undefined).map((level) => (
          <span key={level} className={`font-medium tabular-nums ${LEVEL_STYLES[level] ?? ''}`}>
            {level} {formatNumber(file.level_counts[level])}
          </span>
        ))}
      </div>

      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Incidents ({file.incidents.length})
        </h3>
        {file.incidents.length === 0 ? (
          <p className="text-sm text-gray-500">No WARN/ERROR/FATAL events found in this file.</p>
        ) : (
          <ul className="space-y-2">
            {file.incidents.map((incident) => (
              <IncidentCard key={incident.id} incident={incident} />
            ))}
          </ul>
        )}
      </section>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl dark:bg-gray-900">
            <h4 className="mb-2 font-semibold">Delete this file?</h4>
            <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
              This removes the log file, its events, and its incidents. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={onDelete}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
