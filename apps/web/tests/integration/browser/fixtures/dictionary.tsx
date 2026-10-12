import { createRoot } from 'react-dom/client'
import { I18nProvider } from '../../../../src/components/application/i18n-provider'
import { DictionaryPage } from '../../../../src/components/dictionary/dictionary-page'
import { TooltipProvider } from '../../../../src/components/ui/tooltip'
import { createHttpServices } from '../../../../src/lib/services/http'
import { ServicesProvider } from '../../../../src/lib/services/provider'
import { profile } from './api-fixtures'

export function Fixture() {
  return <ServicesProvider services={createHttpServices(async () => 'test-only-bearer')} scope={profile.id}><I18nProvider><TooltipProvider><DictionaryPage initialQuery="bank" /></TooltipProvider></I18nProvider></ServicesProvider>
}
createRoot(document.getElementById('fixture')!).render(<Fixture />)
