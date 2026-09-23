import { Route, Routes } from 'react-router-dom'
import FilesPage from './pages/FilesPage'
import FileDetailPage from './pages/FileDetailPage'

export default function App() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Log Incident Analyzer</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Upload JSON-lines logs, group errors into incidents, and get plain-language summaries.
        </p>
      </header>
      <Routes>
        <Route path="/" element={<FilesPage />} />
        <Route path="/files/:id" element={<FileDetailPage />} />
      </Routes>
    </div>
  )
}
