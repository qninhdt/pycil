'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import { resolveTheme, themeCookie, type Theme } from './theme'

const ThemeContext = createContext({ theme: 'light' as Theme, toggleTheme: () => {} })

export function ThemeProvider({ initialTheme, children }: { initialTheme: Theme; children: React.ReactNode }) {
  const [theme, setTheme] = useState(initialTheme)
  useEffect(() => {
    const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(themeCookie)
    if (channel) channel.onmessage = event => {
      const next = resolveTheme(event.data)
      document.documentElement.classList.toggle('dark', next === 'dark')
      setTheme(next)
    }
    return () => channel?.close()
  }, [])
  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light'
    document.cookie = `${themeCookie}=${next}; Path=/; Max-Age=31536000; SameSite=Lax`
    document.documentElement.classList.toggle('dark', next === 'dark')
    setTheme(next)
    if (typeof BroadcastChannel !== 'undefined') {
      const channel = new BroadcastChannel(themeCookie)
      channel.postMessage(next)
      channel.close()
    }
  }
  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
