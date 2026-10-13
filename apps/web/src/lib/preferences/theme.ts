export type Theme = 'light' | 'dark'
export const themeCookie = 'pycil-theme'

export function resolveTheme(value: string | undefined): Theme {
  return value === 'dark' ? 'dark' : 'light'
}
