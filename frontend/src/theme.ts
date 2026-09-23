// DKubeX theme contract: the platform stores the user's preference in
// localStorage under "dkubex-ui-theme" ("dark" | "light" | "system", default
// dark). The platform toggle is the only theme control — never a second key.
const THEME_KEY = 'dkubex-ui-theme'

export function getResolvedTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem(THEME_KEY) || 'dark'
  if (stored === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return stored === 'light' ? 'light' : 'dark'
}

export function applyTheme(value: string | null): void {
  const theme = value ? (value === 'light' ? 'light' : 'dark') : getResolvedTheme()
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

export function initTheme(): void {
  applyTheme(null)
  // The user can toggle the theme from the DKubeX shell while the app is open.
  window.addEventListener('storage', (e) => {
    if (e.key === THEME_KEY) applyTheme(e.newValue)
  })
}
