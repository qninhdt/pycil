import type { Browser,BrowserContext,ConsoleMessage,Page } from '@playwright/test';

export function trackBrowserErrors(browser: Browser, context: BrowserContext) {
  const errors: string[] = [], consoleErrors: string[] = []
  const contexts = new Set<BrowserContext>()
  const pages = new Map<Page, { error: (error: Error) => void; console: (message: ConsoleMessage) => void }>()
  const observePage = (page: Page) => {
    if (pages.has(page)) return
    const handlers = {
      error: (error: Error) => { errors.push(error.stack ?? error.message) },
      console: (message: ConsoleMessage) => { if (message.type() === 'error') consoleErrors.push(message.text()) },
    }
    pages.set(page, handlers)
    page.on('pageerror', handlers.error)
    page.on('console', handlers.console)
  }
  const observeContext = (value: BrowserContext) => {
    if (contexts.has(value)) return
    contexts.add(value)
    value.pages().forEach(observePage)
    value.on('page', observePage)
  }
  const original = browser.newContext
  browser.newContext = async options => {
    const value = await original.call(browser, options)
    observeContext(value)
    return value
  }
  observeContext(context)
  return { errors, consoleErrors, dispose() {
    browser.newContext = original
    for (const value of contexts) value.off('page', observePage)
    for (const [page, handlers] of pages) {
      page.off('pageerror', handlers.error)
      page.off('console', handlers.console)
    }
  } }
}
