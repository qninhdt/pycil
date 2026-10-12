// Test-only browser entry. Never imported by an application route or auth provider.
import { useEffect,useState } from 'react'
import { createRoot } from 'react-dom/client'
import { AppShell } from '../../../../src/components/application/app-shell'
import { I18nProvider } from '../../../../src/components/application/i18n-provider'
import { HomeDashboard } from '../../../../src/components/home/home-page'
import { ScrollArea } from '../../../../src/components/ui/scroll-area'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import type { AccountProfile } from '../../../../src/lib/api'
import { createHttpServices } from '../../../../src/lib/services/http'
import { createMockServices } from '../../../../src/lib/services/mock'
import { ServicesProvider } from '../../../../src/lib/services/provider'

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
  return <ServicesProvider key={account?.id ?? 'signed-out'} services={services} scope={account?.id ?? 'signed-out'}><I18nProvider><TooltipProvider><AppShell>
    <p className="home-footnote">Test fixture · synthetic data</p>
    {account ? <HomeDashboard key={account.id} profile={account} /> : <p>Signed out of the test fixture.</p>}
    {new URLSearchParams(location.search).has('scroll') && <ScrollArea style={{ height: 160, width: 200 }}><div style={{ height: 1000 }}>Scrollbar test</div></ScrollArea>}
  </AppShell></TooltipProvider></I18nProvider></ServicesProvider>
}

createRoot(document.getElementById('fixture')!).render(<Fixture />)
