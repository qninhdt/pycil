'use client'

import { useTimeOfDay } from '@/hooks/use-time-of-day'

export function DaylightArt({ mobile = false }: { mobile?: boolean }) {
  const period = useTimeOfDay()
  return <svg className={`shell-brand-detail ${mobile ? 'right-0 left-auto' : 'left-[159px]'} absolute bottom-0 -z-10 h-[88px] w-24 transition-opacity duration-200 motion-reduce:transition-none`} viewBox="0 0 96 88" aria-hidden="true" data-time-of-day={period}>
    <g className={`shell-brand-period ${period === 'morning' ? 'inline' : 'hidden'}`} data-period="morning">
      <path className="shell-brand-arc" d="M96 16v72H24A72 72 0 0 1 96 16Z" fill="var(--art-red)" />
      <path className="shell-brand-axes" d="M0 70.5h96M84.5 0v88" fill="none" stroke="var(--foreground)" strokeWidth="1" />
    </g>
    <g className={`shell-brand-period ${period === 'afternoon' ? 'inline' : 'hidden'}`} data-period="afternoon">
      <circle className="shell-brand-disc" cx="60" cy="44" r="36" fill="var(--art-yellow)" />
      <path className="shell-brand-axes" d="M0 44.5h96M60.5 0v88" fill="none" stroke="var(--foreground)" strokeWidth="1" />
    </g>
    <g className={`shell-brand-period ${period === 'night' ? 'inline' : 'hidden'}`} data-period="night">
      {/* Intersecting r=36 and r=32 arcs form a true cutout, without a painted-over seam. */}
      <path className="shell-brand-crescent" d="M52.1227 8.8724A36 36 0 1 0 93.8734 56.1899A32 32 0 0 1 52.1227 8.8724Z" fill="var(--art-blue)" />
      <path className="shell-brand-axes" d="M0 72.5h96M24.5 0v88" fill="none" stroke="var(--foreground)" strokeWidth="1" />
    </g>
  </svg>
}
