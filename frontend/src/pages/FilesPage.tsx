import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listFiles, uploadFile, type FileSummary } from '../api'
import { formatNumber, formatTime } from '../format'
import StatusBadge from '../components/StatusBadge'

const MAX_SIZE_MB = 50
const SUPPORTED_RE = /\.(jsonl|log|json)(\.gz)?$/i

export default function FilesPage() {
  const [files, setFiles] = useState<FileSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const refresh = useCallback(async () => {
    try {
      setFiles(await listFiles())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load files.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const doUpload = useCallback(
    async (file: File) => {
      if (!SUPPORTED_RE.test(file.name)) {
        setError('Only JSON-lines log files (.jsonl, .log, .json, optionally .gz) are supported.')
        return
      }
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        setError(`File is too large. Max size is ${MAX_SIZE_MB} MB.`)
        return
      }
      setUploading(true)
      setProgress(0)
      setError(null)
      try {
        const uploaded = await uploadFile(file, setProgress)
        navigate(`/files/${uploaded.id}`)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Upload failed.')
      } finally {
        setUploading(false)
      }
    },
    [navigate],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files?.[0]
      if (file) doUpload(file)
    },
    [doUpload],
  )

  return (
    <div className="space-y-6">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          dragOver
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/40'
            : 'border-gray-300 dark:border-gray-700'
        }`}
      >
        <p className="mb-2 font-medium">Upload log file</p>
        <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">
          Drag &amp; drop a .jsonl file here
        </p>
        <button
          type="button"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {uploading ? `Uploading… ${progress}%` : 'Browse'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".jsonl,.log,.json,.jsonl.gz,.log.gz,.json.gz"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) doUpload(file)
            e.target.value = ''
          }}
        />
        <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
          Max size: {MAX_SIZE_MB} MB · .jsonl, .log, .json (optionally .gz)
        </p>
        {uploading && (
          <div className="mx-auto mt-4 h-2 w-64 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800">
            <div
              className="h-full bg-blue-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-gray-200 bg-gray-100 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            <tr>
              <th className="px-4 py-3">File</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Events</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                  Loading…
                </td>
              </tr>
            ) : files.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                  No files yet. Upload a log file to get started.
                </td>
              </tr>
            ) : (
              files.map((f) => (
                <tr
                  key={f.id}
                  onClick={() => navigate(`/files/${f.id}`)}
                  className="cursor-pointer border-b border-gray-100 last:border-0 hover:bg-gray-50 dark:border-gray-800/60 dark:hover:bg-gray-900"
                >
                  <td className="max-w-[240px] truncate px-4 py-3 font-medium" title={f.original_filename}>
                    {f.original_filename}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{formatTime(f.created_at)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={f.status} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{formatNumber(f.parsed_events)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
