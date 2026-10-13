import { useEffect, useRef, useState, type ComponentType } from 'react'
import { MarkedText } from '@/components/content/marked-text'
import { Button } from '@/components/ui/button'

type ChatTurn = {
  speaker: string
  text: string | null
}

type DemoOption = {
  id: string
  text: string
  isCorrect: boolean
  explanation: string
}

function InteractiveDialogueBox({
  title,
  partnerSpeaker,
  partnerInitial,
  userSpeaker,
  conversation,
  options,
  badgeText,
}: {
  title: string
  partnerSpeaker: string
  partnerInitial: string
  userSpeaker: string
  conversation: ChatTurn[]
  options: DemoOption[]
  badgeText: string
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const missingRef = useRef<HTMLDivElement>(null)
  const selectedOption = options.find(o => o.id === selectedId)

  useEffect(() => {
    if (missingRef.current) {
      missingRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [selectedId])

  return (
    <div className="flex flex-col gap-4 w-full">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-mono font-bold uppercase tracking-wider text-muted-foreground">
          {title}
        </span>
        <span className="px-2 py-0.5 text-[11px] font-mono font-bold bg-art-blue/10 text-art-blue border border-art-blue/30 rounded-xs">
          {badgeText}
        </span>
      </div>

      {/* Messenger / WhatsApp Chat Window */}
      <div className="border-2 border-foreground bg-background shadow-xs overflow-hidden">
        {/* Chat Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-foreground bg-muted/30">
          <div className="flex items-center gap-3">
            <div className="relative">
              <span className="size-8 rounded-full bg-art-yellow border border-foreground text-foreground flex items-center justify-center text-xs font-black shrink-0">
                {partnerInitial}
              </span>
              <span className="absolute bottom-0 right-0 size-2.5 rounded-full bg-emerald-500 border border-background" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-extrabold text-foreground leading-none">{partnerSpeaker}</span>
              <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-mono font-medium leading-tight mt-1">
                Online
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground max-sm:hidden">
              Replying as <strong className="text-foreground">{userSpeaker}</strong>
            </span>
            {selectedId && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => setSelectedId(null)}
              >
                Reset
              </Button>
            )}
          </div>
        </div>

        {/* Scrollable Message Thread with Themed Scrollbar */}
        <div
          tabIndex={0}
          aria-label={`${title} messages`}
          className="p-4 sm:p-5 flex flex-col gap-3.5 bg-[color-mix(in_srgb,var(--muted)_25%,var(--background))] max-h-[290px] overflow-y-auto overscroll-contain focus-dialogue-scrollbar focus:outline-none"
        >
          {conversation.map((turn, index) => {
            const isUserSpeaker = turn.speaker === userSpeaker
            const isMissingSlot = turn.text === null
            const timeMinute = 15 + index * 2
            const timeStr = `10:${timeMinute < 10 ? '0' + timeMinute : timeMinute} AM`

            if (isMissingSlot) {
              return (
                <div
                  key={index}
                  ref={missingRef}
                  className="flex flex-col items-end self-end max-w-[85%] sm:max-w-[75%]"
                >
                  <span className="text-[11px] font-extrabold text-muted-foreground/80 mb-1 mr-1">
                    {userSpeaker} (You)
                  </span>
                  {selectedOption ? (
                    <div className="px-4 py-2.5 rounded-2xl rounded-tr-xs bg-art-blue text-white shadow-xs font-medium text-sm sm:text-[15px] leading-relaxed [&_mark]:bg-white/25 [&_mark]:text-white [&_mark]:border-b-2 [&_mark]:border-white [&_mark]:shadow-xs">
                      <MarkedText text={selectedOption.text} />
                      <div className="text-[10px] text-white/80 font-mono text-right mt-1.5 flex items-center justify-end gap-1">
                        <span>{timeStr}</span>
                        <span className="font-bold">✓✓</span>
                      </div>
                    </div>
                  ) : (
                    <div className="px-4 py-2.5 rounded-2xl rounded-tr-xs border-2 border-dashed border-art-blue bg-art-blue/10 text-art-blue font-medium text-sm flex items-center gap-2.5 transition-all">
                      <span className="flex gap-1 items-center" aria-hidden="true">
                        <span className="size-1.5 rounded-full bg-art-blue animate-bounce [animation-delay:-0.3s]" />
                        <span className="size-1.5 rounded-full bg-art-blue animate-bounce [animation-delay:-0.15s]" />
                        <span className="size-1.5 rounded-full bg-art-blue animate-bounce" />
                      </span>
                      <span className="italic">Choose your reply below…</span>
                    </div>
                  )}
                </div>
              )
            }

            if (isUserSpeaker) {
              return (
                <div
                  key={index}
                  className="flex flex-col items-end self-end max-w-[85%] sm:max-w-[75%]"
                >
                  <span className="text-[11px] font-extrabold text-muted-foreground/80 mb-1 mr-1">
                    {userSpeaker}
                  </span>
                  <div className="px-4 py-2.5 rounded-2xl rounded-tr-xs bg-art-blue text-white shadow-xs font-medium text-sm sm:text-[15px] leading-relaxed [&_mark]:bg-white/25 [&_mark]:text-white [&_mark]:border-b-2 [&_mark]:border-white [&_mark]:shadow-xs">
                    <p className="m-0 font-medium">
                      <MarkedText text={turn.text ?? ''} />
                    </p>
                    <div className="text-[10px] text-white/80 font-mono text-right mt-1.5 flex items-center justify-end gap-1">
                      <span>{timeStr}</span>
                      <span className="font-bold">✓✓</span>
                    </div>
                  </div>
                </div>
              )
            }

            return (
              <div
                key={index}
                className="flex flex-col items-start self-start max-w-[85%] sm:max-w-[75%]"
              >
                <span className="text-[11px] font-extrabold text-muted-foreground/80 mb-1 ml-1">
                  {turn.speaker}
                </span>
                <div className="px-4 py-2.5 rounded-2xl rounded-tl-xs bg-background border border-foreground/20 text-foreground text-sm sm:text-[15px] leading-relaxed shadow-xs">
                  <p className="m-0 font-medium">
                    <MarkedText text={turn.text ?? ''} />
                  </p>
                  <span className="text-[10px] text-muted-foreground/70 font-mono block text-right mt-1.5">
                    {timeStr}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Interactive Options Section */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-mono text-muted-foreground">
          {selectedId ? 'Click another option to test different replies:' : 'Select a response to complete the dialogue:'}
        </span>
        <div className="grid grid-cols-1 gap-2.5">
          {options.map((option, index) => {
            const isSelected = selectedId === option.id
            return (
              <button
                key={option.id}
                type="button"
                aria-pressed={isSelected}
                onClick={() => setSelectedId(option.id)}
                className={`min-h-[52px] flex items-center gap-3 px-3.5 py-2.5 border text-left leading-snug transition-colors duration-150 cursor-pointer ${
                  isSelected
                    ? 'border-art-blue bg-[color-mix(in_srgb,var(--art-blue)_15%,var(--background))] ring-1 ring-art-blue'
                    : 'border-foreground/30 bg-background hover:bg-accent'
                }`}
              >
                <span
                  className={`grid place-items-center size-6.5 flex-none border text-xs font-mono font-bold tabular-nums transition-colors ${
                    isSelected
                      ? 'bg-art-blue text-white border-art-blue'
                      : 'border-foreground/30 bg-muted/40 text-foreground'
                  }`}
                >
                  {index + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <span className="font-semibold text-sm text-foreground leading-normal block">
                    <MarkedText text={option.text} />
                  </span>
                  {isSelected && (
                    <span
                      className={`text-[11px] mt-1 block font-mono ${
                        option.isCorrect ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-art-red font-medium'
                      }`}
                    >
                      {option.isCorrect ? '✓ ' : '✕ '}
                      {option.explanation}
                    </span>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** 1. Showcase Demo: Target in Options */
export function DialogueTargetInOptionsDemo() {
  const conversation: ChatTurn[] = [
    {
      speaker: 'Anna',
      text: 'Both department directors submitted completely contradictory timelines for the upcoming Q3 product release.',
    },
    {
      speaker: 'Ben',
      text: null, // Hidden turn: Learner replies as Ben using the marked target word
    },
    {
      speaker: 'Anna',
      text: 'Exactly. Resolving those tensions now prevents costly renegotiations during sprint delivery.',
    },
    {
      speaker: 'Ben',
      text: "I'll draft a unified alignment proposal and share it with both leads before 3 PM.",
    },
    {
      speaker: 'Anna',
      text: "Perfect. Let's make sure the engineering leads review it as well.",
    },
  ]

  const options: DemoOption[] = [
    {
      id: 'opt-1',
      text: 'We should [reconcile] the conflicting points before committing to the release milestones.',
      isCorrect: true,
      explanation: 'Correct: uses “reconcile” in the intended sense of making incompatible items consistent.',
    },
    {
      id: 'opt-2',
      text: 'We should [reconcile] by ignoring their feedback and shipping without consulting them.',
      isCorrect: false,
      explanation: 'Incorrect: contradicts the core meaning of reaching mutual compatibility.',
    },
    {
      id: 'opt-3',
      text: 'I will [reconcile] our team budget rather than addressing the product requirements.',
      isCorrect: false,
      explanation: 'Incorrect: applies the term to an unrelated financial topic instead of the schedule.',
    },
    {
      id: 'opt-4',
      text: "Let's [reconcile] all future communications and cancel the project immediately.",
      isCorrect: false,
      explanation: 'Incorrect: confuses reconciling with terminating collaboration.',
    },
  ]

  return (
    <InteractiveDialogueBox
      title="Options Placement"
      partnerSpeaker="Anna"
      partnerInitial="A"
      userSpeaker="Ben"
      conversation={conversation}
      options={options}
      badgeText="Target marked in every option"
    />
  )
}

/** 2. Showcase Demo: Target in Dialogue */
export function DialogueTargetInDialogueDemo() {
  const conversation: ChatTurn[] = [
    {
      speaker: 'Dr. Aris',
      text: 'The preliminary clinical trials demonstrated unusual variance in drug absorption rates across different age cohorts.',
    },
    {
      speaker: 'Dr. Chen',
      text: 'Our laboratory was able to [corroborate] the initial findings with independent hospital pathology records.',
    },
    {
      speaker: 'Dr. Aris',
      text: null, // Hidden turn: Learner replies as Dr. Aris showing understanding of "corroborate"
    },
    {
      speaker: 'Dr. Chen',
      text: 'Precisely. The secondary trial verified the statistical validity within 48 hours.',
    },
    {
      speaker: 'Dr. Aris',
      text: 'That gives our regulatory submission solid empirical backing. Let’s finalize the documentation.',
    },
  ]

  const options: DemoOption[] = [
    {
      id: 'diag-1',
      text: 'That was a crucial step—verifying experimental results with supporting evidence ensures rigor.',
      isCorrect: true,
      explanation: 'Correct: shows understanding of “corroborate” as confirming evidence.',
    },
    {
      id: 'diag-2',
      text: 'Why would your team contradict and disprove the trial results so prematurely?',
      isCorrect: false,
      explanation: 'Incorrect: treats “corroborate” as meaning contradict or refute.',
    },
    {
      id: 'diag-3',
      text: 'Fabricating the hospital pathology data beforehand makes the entire paper suspect.',
      isCorrect: false,
      explanation: 'Incorrect: introduces an irrelevant claim of falsification.',
    },
    {
      id: 'diag-4',
      text: 'Postponing the clinical trial indefinitely until next year was the safest path.',
      isCorrect: false,
      explanation: 'Incorrect: fails to address the corroborating evidence provided by the lab.',
    },
  ]

  return (
    <InteractiveDialogueBox
      title="Dialogue Placement"
      partnerSpeaker="Dr. Chen"
      partnerInitial="C"
      userSpeaker="Dr. Aris"
      conversation={conversation}
      options={options}
      badgeText="Target marked in conversation"
    />
  )
}

export const dialogueDemos: {
  title: string
  components: string
  code: string
  render: ComponentType
  wide?: boolean
}[] = [
  {
    title: 'Dialogue · Target in options',
    components: 'Dialogue Completion · Multi-Turn Thread · Options Placement · MarkedText',
    code: '<Prompt item={{ question: { question_type: "dialogue_completion", target_placement: "options" } }} />',
    render: DialogueTargetInOptionsDemo,
    wide: true,
  },
  {
    title: 'Dialogue · Target in dialogue',
    components: 'Dialogue Completion · Multi-Turn Thread · Dialogue Placement · MarkedText',
    code: '<Prompt item={{ question: { question_type: "dialogue_completion", target_placement: "dialogue" } }} />',
    render: DialogueTargetInDialogueDemo,
    wide: true,
  },
]
