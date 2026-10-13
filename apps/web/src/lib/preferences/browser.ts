import { timeOfDayStarts } from '../time-of-day'

export const navigationCollapsedKey = 'pycil-navigation-collapsed'
export const aiOpenKey = 'pycil-ai-open'

// Runs in <head> before the first paint; React reads the same attributes later.
export const initialUiScript = `(()=>{
  const root=document.documentElement;
  const hour=new Date().getHours();
  const starts=${JSON.stringify(timeOfDayStarts)};
  root.dataset.timeOfDay=hour<starts.morning||hour>=starts.night?'night':hour<starts.afternoon?'morning':'afternoon';
  try{
    root.dataset.navigationCollapsed=localStorage.getItem(${JSON.stringify(navigationCollapsedKey)})==='true'?'true':'false';
    root.dataset.aiOpen=localStorage.getItem(${JSON.stringify(aiOpenKey)})==='true'?'true':'false';
  }catch{root.dataset.navigationCollapsed='false';root.dataset.aiOpen='false'}
})()`
