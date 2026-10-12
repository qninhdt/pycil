import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { I18nProvider } from '../../src/components/application/i18n-provider'
import { LibraryDestinationDialog } from '../../src/components/library/library-destination-dialog'
import { ServicesProvider } from '../../src/lib/services/provider'
import { createHttpServices } from '../../src/lib/services/http'
import { createMockServices } from '../../src/lib/services/mock'

const services = createHttpServices(async () => 'test-only-bearer')
const profile = { ...createMockServices().account.initialProfile!, id: 'test-account',
  library_node_id: 'library', personal_node_id: 'personal', published_node_id: 'published' }

export function Fixture() {
  const [open, setOpen] = useState(true)
  const [saved, setSaved] = useState('')
  return <ServicesProvider services={services} scope={profile.id}><I18nProvider>
    {open && <LibraryDestinationDialog open profile={profile} kind="DECK" action="Add to deck" onOpenChange={setOpen}
      onConfirm={async destination => {
        await services.library.updateDeckSenses(destination.id, { add: [49], remove: [] }, new AbortController().signal)
        setSaved(destination.id)
      }} />}
    <output>{saved}</output>
  </I18nProvider></ServicesProvider>
}

createRoot(document.getElementById('fixture')!).render(<Fixture />)
