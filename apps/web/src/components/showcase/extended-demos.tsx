import { useState, type ComponentType } from 'react'
import { useForm } from 'react-hook-form'
import { REGEXP_ONLY_DIGITS } from 'input-otp'
import { ArrowRight, FileText, Minus, Plus, Send, X } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'
import { DirectionProvider } from '@/components/ui/direction'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { InputOTP, InputOTPGroup, InputOTPSeparator, InputOTPSlot } from '@/components/ui/input-otp'
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from '@/components/ui/item'
import { Menubar, MenubarCheckboxItem, MenubarContent, MenubarGroup, MenubarItem, MenubarMenu, MenubarSeparator, MenubarTrigger } from '@/components/ui/menubar'
import { NativeSelect, NativeSelectOption, NativeSelectOptGroup } from '@/components/ui/native-select'
import { NavigationMenu, NavigationMenuContent, NavigationMenuItem, NavigationMenuLink, NavigationMenuList, NavigationMenuTrigger } from '@/components/ui/navigation-menu'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Attachment, AttachmentAction, AttachmentActions, AttachmentContent, AttachmentDescription, AttachmentMedia, AttachmentTitle } from '@/components/ui/attachment'
import { Bubble, BubbleContent, BubbleReactions } from '@/components/ui/bubble'
import { Marker, MarkerContent, MarkerIcon } from '@/components/ui/marker'
import { Message, MessageAvatar, MessageContent, MessageFooter, MessageHeader } from '@/components/ui/message'
import { MessageScroller, MessageScrollerButton, MessageScrollerContent, MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport } from '@/components/ui/message-scroller'
import { Questionnaire, QuestionnaireActions, QuestionnaireChoice, QuestionnaireChoices, QuestionnaireDescription, QuestionnaireError, QuestionnaireInput, QuestionnaireItem, QuestionnaireNext, QuestionnairePrevious, QuestionnaireProgress, QuestionnaireSkip, QuestionnaireSubmit, QuestionnaireTitle } from '@/components/ui/questionnaire'
import { Background, Motif } from '@/components/artwork/artwork'

function GroupedActionsDemo() {
  const [zoom, setZoom] = useState(100)
  return <div className="flex flex-col gap-5">
    <ButtonGroup aria-label="Preview zoom">
      <Button variant="outline" size="icon" aria-label="Zoom out" disabled={zoom <= 50} onClick={() => setZoom(zoom - 10)}><Minus /></Button>
      <ButtonGroupText aria-live="polite">{zoom}%</ButtonGroupText>
      <Button variant="outline" size="icon" aria-label="Zoom in" disabled={zoom >= 150} onClick={() => setZoom(zoom + 10)}><Plus /></Button>
    </ButtonGroup>
    <ButtonGroup aria-label="Split action">
      <Button onClick={() => toast.info('Preview saved locally; no server request')}>Save preview</Button>
      <Button variant="outline" onClick={() => setZoom(100)}>Reset zoom</Button>
    </ButtonGroup>
    <p className="text-xs text-muted-foreground leading-relaxed mt-4.5">Connected actions, clear boundaries. Zoom is a local value preview.</p>
  </div>
}

function HoverDetailsDemo() {
  const [open, setOpen] = useState(false)
  return <div className="flex flex-col gap-5">
    <HoverCard open={open} onOpenChange={setOpen} openDelay={200}>
      <HoverCardTrigger asChild><Button variant="outline" aria-expanded={open} onClick={() => setOpen(!open)}>About the workshop</Button></HoverCardTrigger>
      <HoverCardContent>
        <Motif name="arch-window" className="h-24" />
        <p className="font-semibold">Built with intention.</p>
        <p className="text-xs text-muted-foreground leading-relaxed mt-4.5">Hand-authored artwork and accessible primitives, not random decoration.</p>
      </HoverCardContent>
    </HoverCard>
    <p className="text-xs text-muted-foreground leading-relaxed mt-4.5">Hover, focus, or tap to preview supporting information.</p>
  </div>
}

function ItemDemo() {
  const [saved, setSaved] = useState(false)
  return <ItemGroup>
    <Item variant="outline" role="listitem">
      <ItemMedia variant="icon"><FileText /></ItemMedia>
      <ItemContent><ItemTitle>Notes from the workshop</ItemTitle><ItemDescription>A compact list row with its own action.</ItemDescription></ItemContent>
      <ItemActions><Button variant="outline" size="sm" aria-pressed={saved} onClick={() => setSaved(!saved)}>{saved ? 'Saved' : 'Save note'}</Button></ItemActions>
    </Item>
    <Item variant="muted" role="listitem"><ItemContent><ItemTitle>Quiet supporting detail</ItemTitle><ItemDescription>Use the same structure for settings, results and file lists.</ItemDescription></ItemContent></Item>
  </ItemGroup>
}

function OTPDemo() {
  const [code, setCode] = useState('')
  const [format, setFormat] = useState('visual')
  return <FieldGroup>
    <Field>
      <FieldLabel htmlFor="demo-otp">Verification code</FieldLabel>
      <InputOTP id="demo-otp" maxLength={6} pattern={REGEXP_ONLY_DIGITS} value={code} onChange={setCode}>
        <InputOTPGroup>{[0, 1, 2].map(index => <InputOTPSlot key={index} index={index} />)}</InputOTPGroup>
        <InputOTPSeparator />
        <InputOTPGroup>{[3, 4, 5].map(index => <InputOTPSlot key={index} index={index} />)}</InputOTPGroup>
      </InputOTP>
      <FieldDescription aria-live="polite">{code.length === 6 ? 'Six digits entered. This preview does not verify an account.' : `${code.length} of 6 digits entered.`}</FieldDescription>
    </Field>
    <Field>
      <FieldLabel htmlFor="demo-native-select">Native format</FieldLabel>
      <NativeSelect id="demo-native-select" value={format} onChange={event => setFormat(event.target.value)}>
        <NativeSelectOptGroup label="Collection formats"><NativeSelectOption value="visual">Visual</NativeSelectOption><NativeSelectOption value="text">Text</NativeSelectOption></NativeSelectOptGroup>
        <NativeSelectOption value="audio">Audio</NativeSelectOption>
      </NativeSelect>
      <FieldDescription>Selected format: {format}</FieldDescription>
    </Field>
  </FieldGroup>
}

function MenubarDemo() {
  const [grid, setGrid] = useState(true)
  const [created, setCreated] = useState(0)
  return <div className="flex flex-col gap-5">
    <Menubar aria-label="Workshop menu">
      <MenubarMenu><MenubarTrigger>File</MenubarTrigger><MenubarContent><MenubarGroup>
        <MenubarItem onSelect={() => setCreated(created + 1)}>New study</MenubarItem>
        <MenubarItem onSelect={() => setCreated(0)}>Reset studies</MenubarItem>
      </MenubarGroup><MenubarSeparator /><MenubarGroup><MenubarItem disabled>Publish (not connected)</MenubarItem></MenubarGroup></MenubarContent></MenubarMenu>
      <MenubarMenu><MenubarTrigger>View</MenubarTrigger><MenubarContent><MenubarGroup><MenubarCheckboxItem checked={grid} onCheckedChange={setGrid}>Construction grid</MenubarCheckboxItem></MenubarGroup></MenubarContent></MenubarMenu>
    </Menubar>
    <p className="text-xs text-muted-foreground leading-relaxed mt-4.5" aria-live="polite">{created} local studies · Construction grid {grid ? 'on' : 'off'}</p>
  </div>
}

function NavigationMenuDemo() {
  return <div className="flex flex-col gap-5">
    <NavigationMenu viewport={false} aria-label="Workshop sections">
      <NavigationMenuList>
        <NavigationMenuItem><NavigationMenuTrigger>Resources</NavigationMenuTrigger><NavigationMenuContent>
          <div className="flex w-52 flex-col gap-1">
            <NavigationMenuLink href="#catalog">Return to the catalog</NavigationMenuLink>
            <NavigationMenuLink href="#main-content">Read the introduction</NavigationMenuLink>
          </div>
        </NavigationMenuContent></NavigationMenuItem>
        <NavigationMenuItem><NavigationMenuLink href="#main-content">Introduction <ArrowRight /></NavigationMenuLink></NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
    <p className="text-xs text-muted-foreground leading-relaxed mt-4.5">Keyboard-friendly site navigation, distinct from an application command menu.</p>
  </div>
}

function AspectDemo() {
  const [ratio, setRatio] = useState('wide')
  const ratios = { wide: 16 / 9, square: 1, editorial: 4 / 3 }
  return <div className="flex flex-col gap-5">
    <ToggleGroup type="single" value={ratio} onValueChange={value => { if (value) setRatio(value) }} aria-label="Artwork aspect ratio">
      <ToggleGroupItem value="wide">16:9</ToggleGroupItem><ToggleGroupItem value="square">1:1</ToggleGroupItem><ToggleGroupItem value="editorial">4:3</ToggleGroupItem>
    </ToggleGroup>
    <AspectRatio ratio={ratios[ratio as keyof typeof ratios]} className="overflow-hidden border border-border"><Background name="archway-poster" /></AspectRatio>
  </div>
}

function DirectionDemo() {
  const [direction, setDirection] = useState<'ltr' | 'rtl'>('ltr')
  return <div className="flex flex-col gap-5">
    <ToggleGroup type="single" value={direction} onValueChange={value => { if (value === 'ltr' || value === 'rtl') setDirection(value) }} aria-label="Reading direction">
      <ToggleGroupItem value="ltr">Left to right</ToggleGroupItem><ToggleGroupItem value="rtl">Right to left</ToggleGroupItem>
    </ToggleGroup>
    <DirectionProvider direction={direction}>
      <div dir={direction} data-testid="direction-preview">
        <Tabs defaultValue="overview">
          <TabsList><TabsTrigger value="overview">{direction === 'rtl' ? 'نظرة عامة' : 'Overview'}</TabsTrigger><TabsTrigger value="details">{direction === 'rtl' ? 'التفاصيل' : 'Details'}</TabsTrigger></TabsList>
          <TabsContent value="overview"><p className="text-xs text-muted-foreground leading-relaxed mt-4.5" lang={direction === 'rtl' ? 'ar' : 'en'}>{direction === 'rtl' ? 'مساحة للأفكار الجديدة.' : 'Make space for new ideas.'}</p></TabsContent>
          <TabsContent value="details"><p className="text-xs text-muted-foreground leading-relaxed mt-4.5">The primitive and DOM directions stay in sync.</p></TabsContent>
        </Tabs>
      </div>
    </DirectionProvider>
  </div>
}

function ValidatedFormDemo() {
  const { register, handleSubmit, reset, formState: { errors } } = useForm<{ title: string }>({ defaultValues: { title: '' } })
  const [saved, setSaved] = useState('')
  return <form noValidate onSubmit={handleSubmit(data => setSaved(data.title))}>
    <FieldGroup>
      <Field data-invalid={!!errors.title}>
        <FieldLabel htmlFor="validated-title">Study title</FieldLabel>
        <Input id="validated-title" aria-invalid={!!errors.title} aria-describedby="validated-help validated-error"
          {...register('title', { required: 'Enter a study title.', minLength: { value: 3, message: 'Use at least 3 characters.' }, validate: value => value.trim().length >= 3 || 'Use at least 3 non-space characters.' })} />
        <FieldDescription id="validated-help">Field + React Hook Form. No credentials or network requests.</FieldDescription>
        <FieldError id="validated-error">{errors.title?.message}</FieldError>
      </Field>
      <div className="flex flex-wrap items-center gap-2.5"><Button type="submit">Validate study</Button><Button type="button" variant="outline" onClick={() => { reset(); setSaved('') }}>Reset form</Button></div>
      <p className="text-xs text-muted-foreground leading-relaxed mt-4.5" role="status">{saved ? `Validated locally: ${saved}` : 'Enter a title and try submitting an invalid value.'}</p>
    </FieldGroup>
  </form>
}

const questions = [
  { name: 'medium', required: true, choices: [{ value: 'visual' }, { value: 'audio' }] },
  { name: 'note' },
] as const

function QuestionnaireDemo() {
  const [answer, setAnswer] = useState('')
  return <div className="flex flex-col gap-5">
    <Questionnaire items={questions} onSubmit={event => {
      event.preventDefault()
      const data = new FormData(event.currentTarget)
      setAnswer(`Selected ${data.get('medium')}; note: ${data.get('note') || 'skipped'}. Saved in this preview only.`)
    }}>
      <QuestionnaireProgress />
      <QuestionnaireItem name="medium" required>
        <QuestionnaireTitle>How do you like to explore?</QuestionnaireTitle>
        <QuestionnaireDescription>Choose one medium to continue.</QuestionnaireDescription>
        <QuestionnaireChoices><QuestionnaireChoice value="visual">Visual studies</QuestionnaireChoice><QuestionnaireChoice value="audio">Audio studies</QuestionnaireChoice></QuestionnaireChoices>
        <QuestionnaireError />
      </QuestionnaireItem>
      <QuestionnaireItem name="note"><QuestionnaireTitle>A note for your next study?</QuestionnaireTitle><QuestionnaireInput aria-label="Study note" placeholder="An optional thought…" /></QuestionnaireItem>
      <QuestionnaireActions><QuestionnairePrevious /><QuestionnaireSkip /><QuestionnaireNext>Continue</QuestionnaireNext><QuestionnaireSubmit>Finish questionnaire</QuestionnaireSubmit></QuestionnaireActions>
    </Questionnaire>
    <p className="text-xs text-muted-foreground leading-relaxed mt-4.5" role="status">{answer || 'A multi-step local preview. Nothing is sent to an assistant.'}</p>
  </div>
}

function MessagesDemo() {
  const [messages, setMessages] = useState([{ id: 'intro', text: 'A conversation can have structure without losing its warmth.' }])
  const [draft, setDraft] = useState('')
  const [attachment, setAttachment] = useState(true)
  return <div className="flex flex-col gap-5">
    <div className="h-[260px] border border-border">
      <MessageScrollerProvider autoScroll>
        <MessageScroller><MessageScrollerViewport aria-label="Preview conversation"><MessageScrollerContent className="p-4">
          <MessageScrollerItem messageId="marker"><Marker variant="separator"><MarkerIcon><FileText /></MarkerIcon><MarkerContent>Local preview</MarkerContent></Marker></MessageScrollerItem>
          {messages.map((message, index) => <MessageScrollerItem key={message.id} messageId={message.id} scrollAnchor={index > 0}>
            <Message align={index ? 'end' : 'start'}><MessageAvatar aria-hidden="true">{index ? 'Y' : 'W'}</MessageAvatar><MessageContent><MessageHeader>{index ? 'You' : 'Workshop'}</MessageHeader><Bubble align={index ? 'end' : 'start'} variant={index ? 'secondary' : 'default'}><BubbleContent>{message.text}</BubbleContent></Bubble><MessageFooter>Preview only</MessageFooter></MessageContent></Message>
          </MessageScrollerItem>)}
        </MessageScrollerContent></MessageScrollerViewport><MessageScrollerButton /></MessageScroller>
      </MessageScrollerProvider>
    </div>
    {attachment && <Attachment><AttachmentMedia><FileText /></AttachmentMedia><AttachmentContent><AttachmentTitle>study-notes.txt</AttachmentTitle><AttachmentDescription>Sample attachment · not uploaded</AttachmentDescription></AttachmentContent><AttachmentActions><AttachmentAction aria-label="Remove sample attachment" onClick={() => setAttachment(false)}><X /></AttachmentAction></AttachmentActions></Attachment>}
    <form onSubmit={event => {
      event.preventDefault()
      if (!draft.trim()) return
      setMessages(current => [...current, { id: crypto.randomUUID(), text: draft.trim() }].slice(-20))
      setDraft('')
    }}><FieldGroup><Field><FieldLabel htmlFor="message-draft">Preview message</FieldLabel><InputGroup>
      <InputGroupInput id="message-draft" value={draft} onChange={event => setDraft(event.target.value)} placeholder="Add a local message…" maxLength={500} />
      <InputGroupAddon align="inline-end"><InputGroupButton type="submit" aria-label="Send preview message" disabled={!draft.trim()}><Send /></InputGroupButton></InputGroupAddon>
    </InputGroup></Field></FieldGroup></form>
    {!attachment && <Button variant="outline" size="sm" onClick={() => setAttachment(true)}>Restore sample attachment</Button>}
  </div>
}

function BubbleVariantsDemo() {
  return <div className="flex flex-col gap-4">
    <Marker variant="separator"><MarkerContent>Conversation surfaces</MarkerContent></Marker>
    <Bubble><BubbleContent>Assistant response on midnight ink.</BubbleContent></Bubble>
    <Bubble variant="secondary" align="end"><BubbleContent>Your note uses the blue construction line.</BubbleContent></Bubble>
    <Bubble variant="tinted"><BubbleContent>Yellow marks a useful aside.</BubbleContent></Bubble>
    <Bubble variant="outline"><BubbleContent>Outlined supporting detail.</BubbleContent><BubbleReactions aria-label="Reaction preview">Useful</BubbleReactions></Bubble>
    <Bubble variant="ghost"><BubbleContent>Unframed system text.</BubbleContent></Bubble>
    <Bubble variant="destructive"><BubbleContent>Something needs your attention.</BubbleContent></Bubble>
  </div>
}

function AttachmentStatesDemo() {
  return <div className="flex flex-wrap gap-3">
    {(['idle', 'uploading', 'processing', 'done', 'error'] as const).map(state =>
      <Attachment key={state} state={state}>
        <AttachmentMedia><FileText /></AttachmentMedia>
        <AttachmentContent><AttachmentTitle>study-notes.txt</AttachmentTitle><AttachmentDescription>{state === 'error' ? 'Could not add file' : state}</AttachmentDescription></AttachmentContent>
      </Attachment>
    )}
  </div>
}

export const extendedComponentDemos: { title: string; components: string; code: string; render: ComponentType; wide?: boolean }[] = [
  { title: 'Grouped actions', components: 'Button Group · Button', code: '<ButtonGroup><Button variant="outline">Save</Button><Button variant="outline">Reset</Button></ButtonGroup>', render: GroupedActionsDemo },
  { title: 'Hover details', components: 'Hover Card · Motif', code: '<HoverCard><HoverCardTrigger asChild><Button>Details</Button></HoverCardTrigger><HoverCardContent>Supporting context</HoverCardContent></HoverCard>', render: HoverDetailsDemo },
  { title: 'List items', components: 'Item · Item Group', code: '<ItemGroup><Item variant="outline"><ItemContent><ItemTitle>Notes</ItemTitle><ItemDescription>Supporting detail</ItemDescription></ItemContent><ItemActions><Button>Save</Button></ItemActions></Item></ItemGroup>', render: ItemDemo },
  { title: 'OTP & native selection', components: 'Input OTP · Native Select', code: '<InputOTP maxLength={6}><InputOTPGroup>{[0,1,2,3,4,5].map(index => <InputOTPSlot key={index} index={index} />)}</InputOTPGroup></InputOTP>\n<NativeSelect><NativeSelectOption value="visual">Visual</NativeSelectOption></NativeSelect>', render: OTPDemo },
  { title: 'Application menubar', components: 'Menubar · Checkbox Item', code: '<Menubar><MenubarMenu><MenubarTrigger>File</MenubarTrigger><MenubarContent><MenubarGroup><MenubarItem>New study</MenubarItem></MenubarGroup></MenubarContent></MenubarMenu></Menubar>', render: MenubarDemo },
  { title: 'Site navigation', components: 'Navigation Menu', code: '<NavigationMenu><NavigationMenuList><NavigationMenuItem><NavigationMenuTrigger>Resources</NavigationMenuTrigger><NavigationMenuContent><NavigationMenuLink href="/">Home</NavigationMenuLink></NavigationMenuContent></NavigationMenuItem></NavigationMenuList></NavigationMenu>', render: NavigationMenuDemo },
  { title: 'Aspect ratios', components: 'Aspect Ratio · Toggle Group · Background', code: '<AspectRatio ratio={16 / 9}><Background name="archway-poster" /></AspectRatio>', render: AspectDemo },
  { title: 'Reading direction', components: 'Direction · Tabs', code: '<DirectionProvider direction="rtl"><div dir="rtl">Your localized interface</div></DirectionProvider>', render: DirectionDemo },
  { title: 'Validated forms', components: 'Field · React Hook Form · Input', code: 'const { register, handleSubmit } = useForm()\n<form onSubmit={handleSubmit(onSubmit)}><Field><FieldLabel htmlFor="title">Title</FieldLabel><Input id="title" {...register("title", { required: true })} /><FieldError>{error}</FieldError></Field><Button type="submit">Save</Button></form>', render: ValidatedFormDemo },
  { title: 'Questionnaire', components: 'Questionnaire · Multi-step form', code: '<Questionnaire items={[{ name: "medium", required: true }]} onSubmit={onSubmit}><QuestionnaireItem name="medium" required><QuestionnaireTitle>Choose a medium</QuestionnaireTitle><QuestionnaireChoices><QuestionnaireChoice value="visual">Visual</QuestionnaireChoice></QuestionnaireChoices><QuestionnaireError /></QuestionnaireItem><QuestionnaireActions><QuestionnaireSubmit>Finish</QuestionnaireSubmit></QuestionnaireActions></Questionnaire>', render: QuestionnaireDemo },
  { title: 'Conversation surfaces', components: 'Bubble · Bubble Reactions · Marker', code: '<Bubble variant="secondary"><BubbleContent>Your note</BubbleContent></Bubble>', render: BubbleVariantsDemo },
  { title: 'Attachment states', components: 'Attachment · Attachment Media · Attachment Content', code: '<Attachment state="error"><AttachmentMedia><FileText /></AttachmentMedia><AttachmentContent><AttachmentTitle>study-notes.txt</AttachmentTitle><AttachmentDescription>Could not add file</AttachmentDescription></AttachmentContent></Attachment>', render: AttachmentStatesDemo },
  { title: 'Messages & attachments', components: 'Message · Bubble · Marker · Attachment · Message Scroller', code: '<MessageScrollerProvider autoScroll><MessageScroller><MessageScrollerViewport><MessageScrollerContent><MessageScrollerItem messageId="intro"><Message><MessageContent><Bubble><BubbleContent>Your message</BubbleContent></Bubble></MessageContent></Message></MessageScrollerItem></MessageScrollerContent></MessageScrollerViewport><MessageScrollerButton /></MessageScroller></MessageScrollerProvider>', render: MessagesDemo, wide: true },
]
