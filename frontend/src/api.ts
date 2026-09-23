export interface FileSummary {
  id: string
  original_filename: string
  file_size: number
  status: string
  total_lines: number
  parsed_events: number
  unparsed_lines: number
  time_start: string | null
  time_end: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface IncidentEvidenceLine {
  line_number: number
  timestamp: string
  level: string
  message: string
}

export interface Incident {
  id: string
  service: string
  level: string
  fingerprint: string
  sample_message: string
  event_count: number
  first_seen: string
  last_seen: string
  analysis_status: string
  title: string | null
  category: string | null
  severity: string | null
  summary: string | null
  likely_cause: string | null
  evidence_lines: number[] | null
  evidence: IncidentEvidenceLine[]
  analysis_error: string | null
  model_name: string | null
  analyzed_at: string | null
}

export interface FileDetail {
  id: string
  original_filename: string
  file_size: number
  status: string
  total_lines: number
  parsed_events: number
  unparsed_lines: number
  unparsed_samples: number[] | null
  time_start: string | null
  time_end: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  level_counts: Record<string, number>
  service_counts: Record<string, number>
  incidents: Incident[]
}

const API_BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '') + '/api'

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep default
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export function listFiles(): Promise<FileSummary[]> {
  return fetch(`${API_BASE}/files`).then((r) => handle<FileSummary[]>(r))
}

export function getFile(id: string): Promise<FileDetail> {
  return fetch(`${API_BASE}/files/${id}`).then((r) => handle<FileDetail>(r))
}

export function uploadFile(file: File, onProgress: (pct: number) => void): Promise<FileSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/files/upload`)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        let detail = `Upload failed (${xhr.status})`
        try {
          const body = JSON.parse(xhr.responseText)
          if (body && typeof body.detail === 'string') detail = body.detail
        } catch {
          // keep default
        }
        reject(new Error(detail))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

export function analyzeFile(id: string): Promise<void> {
  return fetch(`${API_BASE}/files/${id}/analyze`, { method: 'POST' }).then((r) => handle<void>(r))
}

export function deleteFile(id: string): Promise<void> {
  return fetch(`${API_BASE}/files/${id}`, { method: 'DELETE' }).then((r) => handle<void>(r))
}
