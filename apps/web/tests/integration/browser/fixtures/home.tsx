import { NextIntlClientProvider } from 'next-intl'
import messages from '../../../../src/messages/en.json'
// Test-only browser entry. Never imported by an application route or auth provider.
import { useEffect,useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AppShellFrame as AppShell } from '../../../../src/components/shell/app-shell-frame.client'
import { HomeDashboard } from '../../../../src/features/home/home-page.client'
import { ScrollArea } from '../../../../src/components/ui/scroll-area'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import type { AccountProfile } from '../../../../src/lib/api/account'
import { createHttpServices } from '../../../../src/lib/api/services/http'
import { createMockServices } from '../../../../src/lib/api/services/mock'
import { ServicesProvider } from '../../../../src/lib/api/services/provider.client'

const getToken = async () => 'test-only-bearer'
const services = createHttpServices(getToken)
const profile: AccountProfile = {
  ...createMockServices().account.initialProfile!, id: 'test-account', display_name: 'Alex', handle: 'alex', plan: 'free',
  library_node_id: 'library-root', personal_node_id: 'personal-root', published_node_id: 'published-root',
}

export function Fixture() {
  const [account, setAccount] = useState<AccountProfile | null>(profile)
  useEffect(() => {
    const update = (event: Event) => setAccount((event as CustomEvent<AccountProfile | null>).detail)
    window.addEventListener('test-account-change', update)
    return () => window.removeEventListener('test-account-change', update)
  }, [])
  return <ServicesProvider key={account?.id ?? 'signed-out'} services={services} scope={account?.id ?? 'signed-out'}><NextIntlClientProvider locale="en" messages={messages}><TooltipProvider><AppShell skipToContentText="Skip to content">
    <p className="home-footnote">Test fixture · synthetic data</p>
    {account ? <HomeDashboard key={account.id} profile={account} /> : <p>Signed out of the test fixture.</p>}
    {new URLSearchParams(location.search).has('scroll') && <ScrollArea style={{ height: 160, width: 200 }}><div style={{ height: 1000 }}>Scrollbar test</div></ScrollArea>}
  </AppShell></TooltipProvider></NextIntlClientProvider></ServicesProvider>
}

createRoot(document.getElementById('fixture')!).render(<Fixture />)
