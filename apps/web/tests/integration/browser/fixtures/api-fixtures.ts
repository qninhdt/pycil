import { parseAccountProfile } from '../../../../src/lib/api'
import database from '../../../../src/lib/services/mock/database.json' with { type: 'json' }

// Synthetic native DTOs; component tests never invoke preview domain services.
export const profile = parseAccountProfile({ ...structuredClone(database.account), id: 'http-account', plan: 'PRO' })
export const accountPlatform = `const profile=${JSON.stringify(profile)}; export function useAccount(){return {status:'ready',signedIn:true,profile,name:'HTTP learner',error:null,retry:()=>{},signOut:async()=>{}}}; export function useTheme(){return {theme:'light',toggleTheme:()=>{}}}`
export const navigationPlatform = `export function usePathname(){return '/app'}; export function useSearchParams(){return new URLSearchParams(location.search)}; export function useRouter(){return {push:href=>{location.href=href},replace:href=>history.replaceState(null,'',href)}}`
