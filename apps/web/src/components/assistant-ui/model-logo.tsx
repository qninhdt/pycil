import { cn } from '@/lib/utils'

export type ModelProvider = 'openai' | 'google' | 'anthropic' | 'deepseek' | 'meta' | 'default'

export function resolveModelProvider(modelId: string, modelName?: string): ModelProvider {
  const target = `${modelId} ${modelName ?? ''}`.toLowerCase()
  if (target.includes('openai') || target.includes('gpt') || target.includes('luna') || target.includes('vision-model') || target.includes('preview-vision')) {
    return 'openai'
  }
  if (target.includes('google') || target.includes('gemini') || target.includes('gemma')) {
    return 'google'
  }
  if (target.includes('anthropic') || target.includes('claude') || target.includes('text-model') || target.includes('preview-text')) {
    return 'anthropic'
  }
  if (target.includes('deepseek')) {
    return 'deepseek'
  }
  if (target.includes('meta') || target.includes('llama')) {
    return 'meta'
  }
  return 'default'
}

const logoConfig: Record<ModelProvider, { src: string; isMonochrome: boolean; label: string }> = {
  openai: { src: '/models/openai.svg', isMonochrome: true, label: 'OpenAI' },
  google: { src: '/models/gemini.svg', isMonochrome: false, label: 'Google Gemini' },
  anthropic: { src: '/models/claude.svg', isMonochrome: false, label: 'Anthropic Claude' },
  deepseek: { src: '/models/deepseek.svg', isMonochrome: false, label: 'DeepSeek' },
  meta: { src: '/models/meta.svg', isMonochrome: false, label: 'Meta' },
  default: { src: '/models/openai.svg', isMonochrome: true, label: 'AI Model' },
}

export function ModelLogo({
  modelId,
  modelName,
  className,
}: {
  modelId: string
  modelName?: string
  className?: string
}) {
  const provider = resolveModelProvider(modelId, modelName)
  const config = logoConfig[provider]

  return (
    <span className={cn('ai-model-logo-wrap', className)} aria-hidden="true">
      <img
        src={config.src}
        alt={config.label}
        className={cn('ai-model-logo', config.isMonochrome && 'ai-model-logo--monochrome')}
      />
    </span>
  )
}
