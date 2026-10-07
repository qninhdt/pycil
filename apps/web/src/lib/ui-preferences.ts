import { timeOfDayStarts } from './time-of-day'

export const navigationCollapsedKey = 'pycil-navigation-collapsed'

// Runs in <head> before the first paint; React reads the same attributes later.
export const initialUiScript = `(()=>{
  const root=document.documentElement;
  const hour=new Date().getHours();
  const starts=${JSON.stringify(timeOfDayStarts)};
  root.dataset.timeOfDay=hour<starts.morning||hour>=starts.night?'night':hour<starts.afternoon?'morning':'afternoon';
  try{
    if(localStorage.getItem('bauhaus-theme')==='dark')root.classList.add('dark');
    root.dataset.navigationCollapsed=localStorage.getItem(${JSON.stringify(navigationCollapsedKey)})==='true'?'true':'false';
  }catch{root.dataset.navigationCollapsed='false'}
})()`
