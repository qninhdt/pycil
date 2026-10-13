import { useState, type ReactNode } from 'react'
import { Check, Code2, Copy } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'

export function CopyButton({ text, label = 'Copy usage' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const [manualCopy, setManualCopy] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Usage copied to clipboard')
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      setManualCopy(true)
    }
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button size="icon-sm" variant="ghost" aria-label={label} onClick={copy}>
            {copied ? <Check /> : <Copy />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{copied ? 'Copied' : label}</TooltipContent>
      </Tooltip>
      <Dialog open={manualCopy} onOpenChange={setManualCopy}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy usage manually</DialogTitle>
            <DialogDescription>Clipboard access is unavailable. Select and copy the example below.</DialogDescription>
          </DialogHeader>
          <Textarea aria-label="Usage example" readOnly value={text} rows={6} onFocus={event => event.target.select()} />
        </DialogContent>
      </Dialog>
    </>
  )
}

export function Specimen({ title, components, code, children, wide = false }: {
  title: string
  components: string
  code: string
  children: ReactNode
  wide?: boolean
}) {
  const [showCode, setShowCode] = useState(false)
  return (
    <article className={`specimen border border-border bg-card min-w-0 scroll-mt-24 [&.wide]:col-span-full max-md:[&.wide]:col-auto${wide ? ' wide' : ''}`} id={title.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')}>
      <header className="flex items-center justify-between gap-3.5 px-5 py-3.5 border-b border-border [&_h3]:text-sm [&_h3]:font-bold [&_h3]:m-0 [&_small]:text-muted-foreground [&_small]:text-[10px] [&_small]:block [&_small]:mt-0.5 max-md:px-4 max-md:py-3">
        <div><h3>{title}</h3><small>{components}</small></div>
        <div className="flex gap-1">
          <Button variant="ghost" size="icon-sm" aria-label={`Toggle ${title} code`}
            aria-expanded={showCode} onClick={() => setShowCode(!showCode)}><Code2 /></Button>
          <CopyButton text={code} />
        </div>
      </header>
      <div className="px-5.5 py-6.5 min-h-[140px] max-md:px-4.5 max-md:py-5.5">{children}</div>
      {showCode && <pre className="specimen-code border-t border-border bg-muted p-5 m-0 text-xs leading-loose whitespace-pre-wrap break-words"><code>{code}</code></pre>}
    </article>
  )
}

export function SectionIntro({ title, description, children }: {
  title: string
  description: string
  children?: ReactNode
}) {
  return <div className="flex justify-between items-end gap-6 mt-9 mb-5.5 [&_h2]:text-[28px] [&_h2]:font-bold [&_h2]:tracking-[-.03em] [&_h2]:m-0 [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 [&_p]:leading-relaxed max-md:mt-6 max-md:gap-2.5 max-md:[&_h2]:text-[25px]"><div><h2>{title}</h2><p>{description}</p></div>{children}</div>
}
