import { parseAccountProfile } from '../../../../src/lib/api/account'
import database from '../../../../src/lib/api/services/mock/database.json' with { type: 'json' }

// Synthetic native DTOs; component tests never invoke preview domain services.
export const profile = parseAccountProfile({ ...structuredClone(database.account), id: 'http-account', plan: 'pro' })
export const accountPlatform = `const profile=${JSON.stringify(profile)}; export function useAccount(){return {status:'ready',signedIn:true,canMutate:true,profile,name:'HTTP learner',error:null,retry:()=>{},signOut:async()=>{}}}; export function useTheme(){return {theme:'light',toggleTheme:()=>{}}}`
export { navigationPlatform } from './navigation'
