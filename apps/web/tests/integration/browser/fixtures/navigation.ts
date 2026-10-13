export const navigationPlatform = `import {useSyncExternalStore} from 'react';
const event='fixture-navigation';
for(const method of ['pushState','replaceState']){const original=history[method].bind(history);history[method]=(...args)=>{original(...args);window.dispatchEvent(new Event(event))}};
function subscribe(listener){window.addEventListener(event,listener);window.addEventListener('popstate',listener);return()=>{window.removeEventListener(event,listener);window.removeEventListener('popstate',listener)}};
export function usePathname(){return useSyncExternalStore(subscribe,()=>location.pathname,()=>'/app')};
export function useSearchParams(){return new URLSearchParams(useSyncExternalStore(subscribe,()=>location.search,()=>''))};
export function useRouter(){return {push:href=>{location.href=href},replace:href=>history.replaceState(null,'',href),refresh:()=>window.dispatchEvent(new Event(event))}}`
