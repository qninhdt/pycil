import { NextIntlClientProvider } from 'next-intl'
import messages from '../../../../src/messages/en.json'
// Test-only authenticated shell; production authentication is never bypassed.
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AppShellFrame as AppShell } from '../../../../src/components/shell/app-shell-frame.client'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import { useAssistantView } from '../../../../src/features/assistant/current-view.client'
import { createHttpServices } from '../../../../src/lib/api/services/http'
import { ServicesProvider } from '../../../../src/lib/api/services/provider.client'

export function FixtureView() {
  const [word, setWord] = useState(false)
  useAssistantView(word ? undefined : '01900000-0000-7000-8000-000000000001', word ? 1 : undefined)
  return <><h1 className="text-5xl font-extrabold">Your workspace.</h1><p className="mt-5">Test fixture · synthetic account</p><button onClick={() => setWord(value => !value)}>Switch current view</button></>
}

createRoot(document.getElementById('fixture')!).render(<ServicesProvider services={createHttpServices(async () => 'test-only-bearer')} scope="assistant-test"><NextIntlClientProvider locale="en" messages={messages}><TooltipProvider><AppShell skipToContentText="Skip to content"><FixtureView /></AppShell></TooltipProvider></NextIntlClientProvider></ServicesProvider>)
