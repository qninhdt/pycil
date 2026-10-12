// Test-only authenticated shell; production authentication is never bypassed.
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AppShell } from '../../../../src/components/application/app-shell'
import { I18nProvider } from '../../../../src/components/application/i18n-provider'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import { useAssistantView } from '../../../../src/hooks/use-assistant-view'
import { createHttpServices } from '../../../../src/lib/services/http'
import { ServicesProvider } from '../../../../src/lib/services/provider'

export function FixtureView() {
  const [word, setWord] = useState(false)
  useAssistantView(word ? undefined : '01900000-0000-7000-8000-000000000001', word ? 1 : undefined)
  return <><h1 className="text-5xl font-extrabold">Your workspace.</h1><p className="mt-5">Test fixture · synthetic account</p><button onClick={() => setWord(value => !value)}>Switch current view</button></>
}

createRoot(document.getElementById('fixture')!).render(<ServicesProvider services={createHttpServices(async () => 'test-only-bearer')} scope="assistant-test"><I18nProvider><TooltipProvider><AppShell><FixtureView /></AppShell></TooltipProvider></I18nProvider></ServicesProvider>)
