import { createRoot } from 'react-dom/client'
import { NextIntlClientProvider } from 'next-intl'
import messages from '../../../../src/messages/vi.json'
import { UiProvider } from '../../../../src/lib/preferences/ui-provider.client'
import { PatternBadge } from '../../../../src/features/vocabulary/pattern-badge.client'

createRoot(document.getElementById('fixture')!).render(
  <NextIntlClientProvider locale="vi" messages={messages}>
    <UiProvider><PatternBadge pattern="bank {one's} {clause}" lemma="bank" /></UiProvider>
  </NextIntlClientProvider>,
)
