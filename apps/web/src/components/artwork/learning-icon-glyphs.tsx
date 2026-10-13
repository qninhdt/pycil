import type { ReactNode } from 'react'
import type { AnswerFormat } from '@/lib/api'
import type { QuestionType } from '@/lib/home-api'

type Name = Exclude<QuestionType, 'sentence_rewrite'> | AnswerFormat
type Glyph = (mono: boolean) => ReactNode
const red = 'var(--art-red)', blue = 'var(--art-blue)', yellow = 'var(--art-yellow)'
const plane = (mono: boolean, color: string) => ({ fill: mono ? 'currentColor' : color, stroke: 'none' })

// Word tile, definition bars, context line, and speech frames retain their positions in both tones.
export const learningIcons: Record<Name, Glyph> = {
  definition_to_word: (m) => <><path d="M4 12h18M4 23h18M4 34h14M22 23h9"/><rect x="34" y="15" width="10" height="16" {...plane(m, blue)}/></>,
  word_to_definition: (m) => <><rect x="4" y="15" width="10" height="16" {...plane(m, blue)}/><path d="M17 23h9M28 12h16M28 23h16M28 34h12"/></>,
  context_to_word: (m) => <><path d="M4 8h28v27H4ZM10 16h15M10 25h11M32 22h6"/><rect x="38" y="18" width="8" height="13" {...plane(m, yellow)}/></>,
  cloze_to_word: (m) => <><path d="M4 15h15m10 0h15M4 34h40"/><rect x="19" y="10" width="10" height="10" {...plane(m, blue)}/></>,
  dialogue_completion: (m) => <><path d="M4 5h27v17H15l-7 6v-6H4ZM18 26h26v16H31l-7 5v-5h-6Z"/><path d="M10 12h15M10 17h11"/><rect x="24" y="33" width="14" height="4" {...plane(m, red)}/></>,
  word_to_usage: (m) => <><rect x="4" y="4" width="11" height="11" {...plane(m, blue)}/><path d="M20 10h24M4 25h40M4 35h40"/><path d="M18 25h11" stroke={m ? 'currentColor' : blue}/></>,
  meaning_in_context: (m) => <><path d="M4 13h40M4 24h10m20 0h10M4 35h40"/><circle cx="24" cy="24" r="10" stroke={m ? 'currentColor' : red}/></>,
  single_choice: (m) => <><circle cx="10" cy="11" r="5"/><circle cx="10" cy="24" r="5"/><circle cx="10" cy="37" r="5"/><circle cx="10" cy="11" r="2.5" fill={m ? 'currentColor' : red} stroke="none"/><path d="M21 11h23M21 24h23M21 37h16"/></>,
  single_word: (m) => <><rect x="4" y="10" width="40" height="31"/><rect x="10" y="18" width="10" height="13" {...plane(m, blue)}/><path d="M25 17v15"/></>,
  short_answer: (m) => <><rect x="6" y="4" width="36" height="40"/><path d="M13 14h22M13 23h22M13 32h15"/><rect x="32" y="35" width="5" height="5" {...plane(m, yellow)}/></>,
}
