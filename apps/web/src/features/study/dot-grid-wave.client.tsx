'use client'

import { useEffect, useRef, useState } from 'react'
import { useLocale } from 'next-intl'
import { PREPARING_PHRASES } from './preparing-phrases'

export function DotGridWave({ className = '' }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const locale = useLocale()
  const [phraseIndex, setPhraseIndex] = useState(0)

  useEffect(() => {
    // Pick a random phrase on mount
    setPhraseIndex(Math.floor(Math.random() * PREPARING_PHRASES.length))

    // Rotate phrase every 3.5s if preparation takes time
    const interval = setInterval(() => {
      setPhraseIndex(prev => (prev + 1) % PREPARING_PHRASES.length)
    }, 3500)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationFrameId: number
    let startTime = performance.now()

    let cols = 28
    let rows = 18
    const dpr = typeof window !== 'undefined' ? Math.min(window.devicePixelRatio || 1, 2) : 1

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      cols = rect.width < 340 ? 18 : rect.width < 460 ? 22 : 28
      rows = rect.height < 240 ? 12 : rect.height < 340 ? 15 : 18
    }
    resize()
    window.addEventListener('resize', resize)

    const render = (now: number) => {
      const elapsed = (now - startTime) / 1000
      const width = canvas.width
      const height = canvas.height

      ctx.clearRect(0, 0, width, height)

      const spacingX = width / (cols + 1)
      const spacingY = height / (rows + 1)

      // Bauhaus Primary Blue with cyan luminance
      // Wave travels diagonally from top-left to bottom-right with radial influence
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const x = (c + 1) * spacingX
          const y = (r + 1) * spacingY

          // Diagonal wave formula
          const wave = Math.sin(c * 0.28 + r * 0.28 - elapsed * 2.8)
          // Secondary cross ripple
          const ripple = Math.cos(c * 0.15 - r * 0.2 + elapsed * 1.6)
          const combined = (wave + ripple * 0.5) / 1.5

          // Normalized factor between 0.15 and 1.0
          const factor = Math.max(0.12, Math.min(1, (combined + 1) / 2))

          const radius = (1.2 + factor * 2.6) * dpr
          const alpha = 0.15 + factor * 0.85

          ctx.beginPath()
          ctx.arc(x, y, radius, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(52, 152, 219, ${alpha.toFixed(3)})`
          ctx.fill()
        }
      }

      animationFrameId = requestAnimationFrame(render)
    }

    animationFrameId = requestAnimationFrame(render)

    return () => {
      cancelAnimationFrame(animationFrameId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  const currentPhrase =
    locale === 'vi'
      ? PREPARING_PHRASES[phraseIndex].vi
      : PREPARING_PHRASES[phraseIndex].en

  return (
    <div className={`flex flex-col items-center justify-center gap-6 w-full max-w-[520px] mx-auto p-4 ${className}`}>
      {/* Interactive Dot Grid Canvas */}
      <div className="relative w-full aspect-[4/3] max-w-[420px] overflow-hidden border border-foreground/20 bg-background/80 shadow-xs">
        <canvas ref={canvasRef} className="w-full h-full block" />
        <div className="pointer-events-none absolute inset-0 bg-radial from-transparent via-transparent to-background/60" />
      </div>

      {/* Text with tw-shimmer effect */}
      <div className="flex flex-col items-center gap-1.5 text-center px-4">
        <span className="text-[11px] font-mono font-bold tracking-widest uppercase text-art-blue/80">
          PYCIL // STUDY ENGINE
        </span>
        <p
          key={phraseIndex}
          className="shimmer text-foreground/50 text-base sm:text-lg font-semibold tracking-tight animate-in fade-in duration-300 min-h-[1.75em] flex items-center justify-center"
        >
          {currentPhrase}
        </p>
      </div>
    </div>
  )
}
