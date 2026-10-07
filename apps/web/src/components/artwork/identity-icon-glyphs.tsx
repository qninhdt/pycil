import type { ReactNode } from 'react'

type Glyph = (mono: boolean) => ReactNode
const red = 'var(--art-red)', blue = 'var(--art-blue)', yellow = 'var(--art-yellow)'
const plane = (mono: boolean, color: string) => ({ fill: mono ? 'currentColor' : color, stroke: 'none' })
const ink = (mono: boolean, color: string) => mono ? 'currentColor' : color

const folder = (m: boolean) => m
  ? <path d="M5 12h14l5 5h19v24H5Z"/>
  : <><path d="M5 12h14l5 5h19v24H5Z"/><path d="M5 12h14l5 5H5Z" {...plane(m, yellow)}/></>
const cards = (m: boolean) => <><rect x="13" y="5" width="28" height="32" {...plane(m, blue)}/><rect x="5" y="13" width="28" height="32" fill="var(--art-paper)"/><path d="M33 35a10 10 0 0 1-10 10V35Z" {...plane(m, yellow)}/></>
const referenceBadge = (m: boolean) => <>
  <rect x="25" y="25" width="18" height="18" fill="var(--art-paper)" stroke="currentColor" strokeWidth={2.4}/>
  <path d="M29 39 37 31M31 31h6v6" stroke={ink(m, blue)} strokeWidth={2.4} strokeLinecap="square" strokeLinejoin="miter"/>
</>

// Color and mono are composed together, icon by icon, on the same 48-unit grid.
export const identityIcons = {
  dictionary: (m) => <><path d="M24 11C17 7 11 8 5 10v29c6-2 12-3 19 1 7-4 13-3 19-1V10c-6-2-12-3-19 1Z"/><path d="M24 11v29M9 17h10M29 17h10M9 24h10M29 24h10"/><path d="M29 11c5-2 9-2 14-1v15H29Z" {...plane(m, red)}/></>,
  vocabulary: (m) => <><rect x="6" y="11" width="29" height="31"/><rect x="13" y="5" width="29" height="31" {...plane(m, blue)}/><path d="m20 28 7-15 7 15m-12-5h10" stroke="var(--art-paper)"/></>,
  translate: (m) => <><path d="M3 37h42"/><rect x="4" y="8" width="18" height="23" {...plane(m, blue)}/><rect x="26" y="15" width="18" height="23" {...plane(m, yellow)}/><path d="m8 25 5-11 5 11m-8-4h6" stroke="var(--art-paper)"/><path d="M31 22h9m-5-4v9m-4 0h8m-7-5 6 7" stroke={m ? 'var(--art-paper)' : 'var(--art-ink)'}/></>,
  review: (m) => <><circle cx="24" cy="24" r="12" {...plane(m, red)}/><path d="m19 24 3.5 3.5 8-8" stroke="var(--art-paper)" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round"/><path d="M41 24A17 17 0 1 1 24 7" stroke="currentColor" strokeWidth={3} fill="none"/><polygon points="24,1 34,9 24,14" {...plane(m, blue)}/><rect x="34" y="32" width="8" height="8" rx="1" {...plane(m, yellow)}/></>,
  trophy: (m) => <><path d="M13 10h22v11a11 11 0 0 1-22 0Z" {...plane(m, yellow)}/><path d="M13 14H6v7a8 8 0 0 0 8 8m21-15h7v7a8 8 0 0 1-8 8M24 32v9M14 42h20"/></>,
  goal: (m) => <><path d="M11 5v38M5 43h12"/><path d="M11 8h29L30 18l10 10H11Z" {...plane(m, red)}/></>,
  microphone: (m) => <><rect x="18" y="5" width="12" height="25" rx="6" {...plane(m, red)}/><path d="M12 23v5a12 12 0 0 0 24 0v-5M24 40v5M17 45h14"/></>,
  headphones: (m) => <><path d="M8 27v-5a16 16 0 0 1 32 0v5"/><rect x="5" y="24" width="8" height="16" {...plane(m, blue)}/><rect x="35" y="24" width="8" height="16" {...plane(m, blue)}/></>,
  waveform: (m) => <><path d="M3 24h42M7 18v12m6-20v28m6-16v4m6-19v34m6-26v18m6-12v6m6-9v12"/><path d="M13 10v28" stroke={ink(m, red)}/><path d="M25 7v34" stroke={ink(m, blue)}/></>,
  notification: (m) => <><path d="M9 35h30l-5-7V19a10 10 0 0 0-20 0v9Z"/><path d="M14 19a10 10 0 0 1 20 0H14Z" {...plane(m, yellow)}/><rect x="21" y="39" width="6" height="4" {...plane(m, blue)}/></>,
  mail: (m) => m
    ? <><rect x="5" y="10" width="38" height="28"/><path d="M5 10 24 25 43 10M5 38l13-16m25 16L30 22"/></>
    : <><rect x="5" y="10" width="38" height="28"/><path d="M5 38l14-17m24 17L29 21"/><path d="M5 10h38L24 25Z" {...plane(m, blue)}/></>,
  share: (m) => <><path d="M13 24 36 10M13 24l23 14"/><circle cx="11" cy="24" r="6" {...plane(m, red)}/><rect x="33" y="4" width="12" height="12" {...plane(m, blue)}/><path d="m39 32 7 12H32Z" {...plane(m, yellow)}/></>,
  edit: (m) => <><path d="M7 10h25M7 10v34h34V23M15 31 32 14l6 6-17 17-8 2Z"/><path d="m13 39 8-2-6-6Z" {...plane(m, yellow)}/></>,
  filter: (m) => <><path d="M4 8h40L29 26v14l-10 4V26Z"/><path d="M4 8h40L35 19H13Z" {...plane(m, blue)}/></>,
  sort: (m) => <><path d="M5 10h23M5 18h18M5 26h13M5 34h8M37 8v31m-5-5 5 5 5-5"/><path d="M5 10h23" stroke={ink(m, red)}/></>,
  lock: (m) => <><path d="M13 20v-6a11 11 0 0 1 22 0v6"/><rect x="8" y="20" width="32" height="23" {...plane(m, blue)}/><path d="M24 29v7" stroke="var(--art-paper)"/></>,
  shield: (m) => <><path d="M8 8h32v16c0 9-7 15-16 21-9-6-16-12-16-21Z"/><path d="M8 8h32v11H8Z" {...plane(m, blue)}/></>,
  cloud: (m) => <><path d="M8 35a9 9 0 0 1-1-17 13 13 0 0 1 25-3 10 10 0 0 1 8 20Z"/><path d="M7 35h33" stroke={ink(m, blue)}/></>,
  sync: (m) => <><path d="M7 19a18 18 0 0 1 31-6M41 29a18 18 0 0 1-31 6"/><path d="m36 7 7 9-11-1Z" {...plane(m, red)}/><path d="m12 41-7-9 11 1Z" {...plane(m, blue)}/></>,
  history: (m) => <><path d="M24 5a19 19 0 1 0 19 19"/><path d="M24 5a19 19 0 0 1 19 19" stroke={ink(m, blue)}/><path d="M24 12v12l9 5"/></>,
  help: (m) => <><path d="M13 17a11 11 0 0 1 22 0c0 8-11 7-11 17" stroke={ink(m, yellow)}/><path d="M24 34v3"/><rect x="22" y="41" width="4" height="4" {...plane(m, yellow)}/></>,
  dashboard: (m) => <><path d="M5 5h38v38H5ZM24 5v38M5 24h38"/>{m
    ? <><rect x="5" y="5" width="19" height="19" fill="currentColor" stroke="none"/><path d="M43 43H24a19 19 0 0 1 19-19"/></>
    : <><rect x="5" y="5" width="19" height="19" {...plane(m, blue)}/><path d="M43 43H24a19 19 0 0 1 19-19Z" {...plane(m, red)}/></>}</>,
  folder,
  'folder-personal': (m) => <><path d="M5 12h14l5 5h19v24H5Z"/><path d="M5 12h14l5 5H5Z" {...plane(m, yellow)}/><path d="M21 27v-4a3 3 0 0 1 6 0v4"/><rect x="18" y="27" width="12" height="9" {...plane(m, blue)}/><circle cx="24" cy="31" r="1.5" fill="var(--art-paper)"/></>,
  'folder-published': (m) => <><path d="M5 12h14l5 5h19v24H5Z"/><path d="M5 12h14l5 5H5Z" {...plane(m, yellow)}/><circle cx="27" cy="29" r="6"/><path d="M21 29h12M27 23a9 9 0 0 1 0 12M27 23a9 9 0 0 0 0 12" stroke={ink(m, red)}/><rect x="25" y="27" width="4" height="4" {...plane(m, red)}/></>,
  flashcards: (m) => <><rect x="15" y="4" width="28" height="36" rx="1.5" {...plane(m, blue)}/><rect x="5" y="10" width="28" height="34" rx="1.5" fill="var(--art-paper)" stroke="currentColor" strokeWidth={2.5}/><path d="M10 19h18M10 25h12" stroke="currentColor" strokeWidth={2.5}/><rect x="21" y="30" width="8" height="8" rx="1" {...plane(m, yellow)}/><circle cx="11" cy="34" r="3" {...plane(m, red)}/></>,
  'learn-new': (m) => <><rect x="4" y="15" width="18" height="27" rx="1" {...plane(m, blue)}/><rect x="26" y="15" width="18" height="27" rx="1" fill="var(--art-paper)" stroke="currentColor" strokeWidth={2.5}/><path d="M22 17v23M30 22h10M30 28h10M30 34h6" stroke="currentColor" strokeWidth={2}/><circle cx="13" cy="28.5" r="4.5" {...plane(m, red)}/><polygon points="24,2 38,15 10,15" {...plane(m, yellow)}/><polygon points="24,2 38,15 10,15" fill="none" stroke="currentColor" strokeWidth={2}/></>,
  collection: cards,
  published: (m) => <><rect x="5" y="15" width="28" height="28"/><rect x="11" y="21" width="16" height="16" {...plane(m, blue)}/><path d="M25 7h17v17M42 7 25 24" stroke={ink(m, red)} strokeWidth={3.2}/><circle cx="39" cy="38" r="4" {...plane(m, yellow)}/></>,
  'folder-reference': (m) => <><path d="M5 12h14l5 5h19v24H5Z"/><path d="M5 12h14l5 5H5Z" {...plane(m, yellow)}/>{referenceBadge(m)}</>,
  'deck-reference': (m) => <><rect x="13" y="5" width="28" height="32" {...plane(m, blue)}/><rect x="5" y="13" width="28" height="32" fill="var(--art-paper)"/><path d="M5 13h28v32H5Z"/>{referenceBadge(m)}</>,
  document: (m) => <><path d="M9 5h22l8 8v30H9Z"/><path d="m31 5 8 8h-8Z" {...plane(m, red)}/><path d="M16 23h16M16 31h13"/></>,
  layers: (m) => <><path d="m5 33 19-9 19 9-19 9Z"/><path d="m5 23 19-9 19 9-19 9Z" fill={m ? 'var(--art-paper)' : yellow}/><path d="m5 13 19-9 19 9-19 9Z" {...plane(m, blue)}/></>,
  archive: (m) => <><rect x="8" y="16" width="32" height="27"/><rect x="5" y="9" width="38" height="9" {...plane(m, yellow)}/><path d="M18 26h12"/></>,
  'sign-out': (m) => <><path d="M7 6h18v36H7Z"/><path d="M7 6 21 10v28L7 42Z" {...plane(m, blue)}/><path d="M22 24h20m-6-6 6 6-6 6"/></>,
  person: (m) => <><circle cx="24" cy="14" r="8" {...plane(m, red)}/><path d="M7 43a17 17 0 0 1 34 0"/></>,
  group: (m) => <><circle cx="18" cy="14" r="7" {...plane(m, red)}/><circle cx="33" cy="17" r="6" {...plane(m, blue)}/><path d="M3 42a15 15 0 0 1 30 0m-1-16a13 13 0 0 1 13 16"/></>,
  workspace: (m) => <><rect x="5" y="5" width="38" height="38"/><path d="M5 22h38M22 22v21"/><rect x="5" y="5" width="17" height="17" {...plane(m, blue)}/></>,
  explore: (m) => <><circle cx="24" cy="24" r="19"/><path d="M33 15 28 28 15 33Z" fill={m ? 'currentColor' : red}/><path d="M33 15 20 20 15 33Z" fill="var(--art-paper)"/></>,
  home: (m) => <><path d="M5 22 24 6l19 16M10 19v24h28V19"/><path d="M24 6 5 22h38Z" {...plane(m, yellow)}/><path d="M20 43V29h8v14"/></>,
  search: (m) => <><path d="M31 31a15 15 0 1 1 4-11"/><path d="M20 5a15 15 0 0 1 15 15" stroke={ink(m, blue)}/><path d="M31 31 44 44"/></>,
  book: (m) => <><path d="M24 12C18 8 11 8 5 10v29c6-2 13-2 19 2 6-4 13-4 19-2V10c-6-2-13-2-19 2Z"/><path d="M24 12v29"/><path d="M5 10c6-2 13-2 19 2v29c-6-4-13-4-19-2Z" {...plane(m, red)}/></>,
  globe: (m) => <><circle cx="24" cy="24" r="19"/>{!m && <path d="M24 5a19 19 0 0 1 19 19H24Z" {...plane(m, yellow)}/>}<path d="M5 24h38M19 6a30 30 0 0 1 0 36"/></>,
  bookmark: (m) => <path d="M12 5h24v39L24 35 12 44Z" {...plane(m, blue)}/>,
  settings: (m) => <><path d={m ? 'M6 15h7m12 0h17M6 33h21m12 0h3' : 'M6 15h36M6 33h36'}/><rect x="13" y="9" width="12" height="12" {...plane(m, blue)}/><circle cx="33" cy="33" r="6" {...plane(m, red)}/></>,
  import: (m) => <><path d="M8 33v10h32V33M24 5v23"/><path d="m16 21 8 8 8-8Z" {...plane(m, blue)}/></>,
  export: (m) => <><path d="M8 22v21h32V22M24 29V7"/><path d="m16 14 8-8 8 8Z" {...plane(m, red)}/></>,
  calendar: (m) => <><rect x="6" y="9" width="36" height="34"/>{!m && <rect x="6" y="9" width="36" height="10" {...plane(m, yellow)}/>}<path d="M14 5v8m20-8v8M6 19h36"/><rect x="13" y="26" width="8" height="8" {...plane(m, red)}/></>,
  activity: (m) => <><path d="M4 43h40"/><rect x="8" y="28" width="8" height="15" {...plane(m, blue)}/><rect x="20" y="18" width="8" height="25" {...plane(m, red)}/><rect x="32" y="7" width="8" height="36" {...plane(m, yellow)}/></>,
  play: (m) => <><circle cx="24" cy="24" r="19"/><path d="m19 13 16 11-16 11Z" {...plane(m, red)}/></>,
  sound: (m) => <><path d="M4 18h9l12-10v32L13 30H4Z"/><path d="M13 18 25 8v32L13 30Z" {...plane(m, blue)}/><path d="M31 17a10 10 0 0 1 0 14m5-19a17 17 0 0 1 0 24"/></>,
  message: (m) => <><path d="M5 8h38v28H17L7 44v-8H5Z"/><rect x="13" y="18" width="18" height="5" {...plane(m, blue)}/></>,
  spark: (m) => <><path d="M21 19 24 4l3 15ZM29 21l15 3-15 3ZM27 29l-3 15-3-15ZM19 27 4 24l15-3Z" {...plane(m, yellow)}/><rect x="20" y="20" width="8" height="8"/></>,
} satisfies Record<string, Glyph>
