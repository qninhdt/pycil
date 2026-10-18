export type SearchValues = Record<string, string | string[] | undefined>

export function searchParams(values: SearchValues): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (Array.isArray(value)) for (const item of value) params.append(key, item)
    else if (value !== undefined) params.set(key, value)
  }
  return params
}

export function paginationHref(pathname: string, params: URLSearchParams, cursors: string[]) {
  const next = new URLSearchParams(params)
  next.delete('cursor')
  for (const cursor of cursors) next.append('cursor', cursor)
  return `${pathname}${next.size ? `?${next}` : ''}`
}

export function updateUrl(changes: Record<string, string | string[] | null>, replace = false) {
  const url = new URL(window.location.href)
  for (const [key, value] of Object.entries(changes)) {
    url.searchParams.delete(key)
    if (Array.isArray(value)) for (const item of value) url.searchParams.append(key, item)
    else if (value !== null && value !== '') url.searchParams.set(key, value)
  }
  if (url.href === window.location.href) return
  // Next.js adds its own fields; passing its router marker skips URL synchronization.
  const state = replace && window.history.state?.pycilWorkspaceEntry
    ? { pycilWorkspaceEntry: window.history.state.pycilWorkspaceEntry } : null
  window.history[replace ? 'replaceState' : 'pushState'](state, '', `${url.pathname}${url.search}${url.hash}`)
}
