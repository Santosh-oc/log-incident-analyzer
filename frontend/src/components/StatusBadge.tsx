const STATUS_STYLES: Record<string, string> = {
  UPLOADED: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
  PARSED: 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
  ANALYZING: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300',
  ANALYZED: 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
  FAILED: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
}

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.UPLOADED
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  )
}
