import { NextIntlClientProvider } from 'next-intl'
import messages from '../../../../src/messages/en.json'
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { LibraryDestinationDialog } from '../../../../src/features/library/library-destination-dialog.client'
import { createHttpServices } from '../../../../src/lib/api/services/http'
import { createMockServices } from '../../../../src/lib/api/services/mock'
import { ServicesProvider } from '../../../../src/lib/api/services/provider.client'

const services = createHttpServices(async () => 'test-only-bearer')
const profile = { ...createMockServices().account.initialProfile!, id: 'test-account',
  library_node_id: 'library', personal_node_id: 'personal', published_node_id: 'published' }

export function Fixture() {
  const [open, setOpen] = useState(true)
  const [saved, setSaved] = useState('')
  return <ServicesProvider services={services} scope={profile.id}><NextIntlClientProvider locale="en" messages={messages}>
    {open && <LibraryDestinationDialog open profile={profile} kind="deck" action="Add to deck" onOpenChange={setOpen}
      onConfirm={async destination => {
        await services.library.updateDeckSenses(destination.id, { add: [49], remove: [] }, new AbortController().signal)
        setSaved(destination.id)
      }} />}
    <output>{saved}</output>
  </NextIntlClientProvider></ServicesProvider>
}

createRoot(document.getElementById('fixture')!).render(<Fixture />)
