import { NextIntlClientProvider } from 'next-intl'
import messages from '../../../../src/messages/en.json'
import { createRoot } from 'react-dom/client'
import { WordPickerDialog } from '../../../../src/features/vocabulary/word-picker-dialog.client'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import { createHttpServices } from '../../../../src/lib/api/services/http'
import { ServicesProvider } from '../../../../src/lib/api/services/provider.client'
import { profile } from './api-fixtures'

function Fixture() {
  return <ServicesProvider services={createHttpServices(async () => 'test-only-bearer')} scope={profile.id}><NextIntlClientProvider locale="en" messages={messages}><TooltipProvider><WordPickerDialog open onOpenChange={() => {}} deckId="http-deck" /></TooltipProvider></NextIntlClientProvider></ServicesProvider>
}
createRoot(document.getElementById('fixture')!).render(<Fixture />)
