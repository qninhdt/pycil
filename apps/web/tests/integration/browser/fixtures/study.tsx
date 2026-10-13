import { NextIntlClientProvider } from 'next-intl'
import messages from '../../../../src/messages/en.json'
import { createRoot } from 'react-dom/client'
import { QuizFocus } from '../../../../src/features/study/quiz-focus.client'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import { createHttpServices } from '../../../../src/lib/api/services/http'
import { ServicesProvider } from '../../../../src/lib/api/services/provider.client'
import { profile } from './api-fixtures'

export function Fixture() {
  return <ServicesProvider services={createHttpServices(async () => 'test-only-bearer')} scope={profile.id}><NextIntlClientProvider locale="en" messages={messages}><TooltipProvider><QuizFocus /></TooltipProvider></NextIntlClientProvider></ServicesProvider>
}
createRoot(document.getElementById('fixture')!).render(<Fixture />)
