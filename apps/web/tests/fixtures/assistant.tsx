// Test-only authenticated shell; production authentication is never bypassed.
import { createRoot } from 'react-dom/client'
import { AppShell } from '../../src/components/application/app-shell'
import { TooltipProvider } from '../../src/components/ui/tooltip'
import { ServicesProvider } from '../../src/lib/services/provider'
import { createHttpServices } from '../../src/lib/services/http'

createRoot(document.getElementById('fixture')!).render(<ServicesProvider services={createHttpServices(async () => 'test-only-bearer')} scope="assistant-test"><TooltipProvider><AppShell><h1 className="text-5xl font-extrabold">Your workspace.</h1><p className="mt-5">Test fixture · synthetic account</p></AppShell></TooltipProvider></ServicesProvider>)
