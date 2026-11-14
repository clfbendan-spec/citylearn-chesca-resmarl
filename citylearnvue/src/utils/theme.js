// Canvas libraries require resolved colors rather than CSS var() expressions.
export function themeColor(token) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${token}`).trim()
}
