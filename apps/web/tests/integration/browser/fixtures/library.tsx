import { useAccount } from '@/components/application/providers'
import { createRoot } from 'react-dom/client'
import { useLibraryContents } from '../../../../src/hooks/use-library'
import { createHttpServices } from '../../../../src/lib/services/http'
import { ServicesProvider } from '../../../../src/lib/services/provider'

const services = createHttpServices(async () => 'test-only-bearer')
function Contents() {
  const result = useLibraryContents('public-node', {})
  return <><output aria-label="Query status">{result.status}</output><ul>{result.data?.nodes.map(node => <li key={node.id}>{node.name}</li>)}</ul></>
}
export function Fixture() {
  const account = useAccount()
  const scope = account.profile?.id ?? account.status
  return <ServicesProvider key={scope} services={services} scope={scope}><Contents /></ServicesProvider>
}
createRoot(document.getElementById('fixture')!).render(<Fixture />)
