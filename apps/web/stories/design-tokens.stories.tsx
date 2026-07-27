import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { LAYERS } from "@/lib/design/layers"
import { MASTERY_BANDS } from "@/lib/design/mastery"

/**
 * The token layer rendered as itself. Switching the toolbar theme here is the
 * check that catches a dark wash lighter than its surface or a mastery ramp
 * that inverts, neither of which a contrast ratio can express.
 */
const meta = {
  title: "Foundations/Tokens",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-b py-8 last:border-b-0">
      <div className="flex flex-col gap-1">
        <h2 className="text-[1.0625rem] font-semibold tracking-[-0.01em]">{title}</h2>
        {note ? <p className="text-muted-foreground max-w-[65ch] text-[0.8125rem]">{note}</p> : null}
      </div>
      {children}
    </section>
  )
}

const SURFACES = [
  { name: "background", className: "bg-background text-foreground" },
  { name: "card", className: "bg-card text-card-foreground" },
  { name: "muted", className: "bg-muted text-muted-foreground" },
  { name: "primary", className: "bg-primary text-primary-foreground" },
  { name: "secondary", className: "bg-secondary text-secondary-foreground" },
  { name: "destructive", className: "bg-destructive text-destructive-foreground" },
]

const WASHES = [
  { name: "primary", className: "bg-wash-primary text-on-wash-primary" },
  { name: "success", className: "bg-wash-success text-on-wash-success" },
  { name: "danger", className: "bg-wash-danger text-on-wash-danger" },
  { name: "warn", className: "bg-wash-warn text-on-wash-warn" },
  { name: "info", className: "bg-wash-info text-on-wash-info" },
]

const RADII = ["rounded-sm", "rounded-md", "rounded-lg", "rounded-xl", "rounded-2xl", "rounded-3xl", "rounded-4xl"]

export const Palette: Story = {
  render: () => (
    <div className="flex flex-col">
      <Section title="Surfaces" note="Each pair is a background and the only foreground allowed on it.">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {SURFACES.map(({ name, className }) => (
            <div key={name} className={`${className} flex h-24 flex-col justify-end rounded-xl border p-3`}>
              <span className="font-mono text-xs">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Washes"
        note="Tag and banner backgrounds only. In dark mode each must read as darker than the surface behind it, never as a glowing slab."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {WASHES.map(({ name, className }) => (
            <div key={name} className={`${className} flex h-20 flex-col justify-end rounded-xl p-3`}>
              <span className="font-mono text-xs">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Mastery ramp"
        note="One ordered dimension. More colour means more learned, and that reading must survive the theme flip."
      >
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-5 gap-3">
            {MASTERY_BANDS.map((band) => (
              <div key={band.stage} className="flex flex-col gap-2" data-stage={band.stage}>
                <div className="stage-fill h-16 rounded-xl" />
                <span className="font-mono text-xs">{band.stage}</span>
                <span className="text-muted-foreground text-xs">{band.name}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-1" aria-hidden>
            {MASTERY_BANDS.map((band) => (
              <span key={band.stage} data-stage={band.stage} className="stage-fill h-2 w-8 rounded-4xl" />
            ))}
          </div>
        </div>
      </Section>

      <Section title="Radius" note="All seven levels the primitives consume, capped at the 12px container ceiling.">
        <div className="flex flex-wrap gap-3">
          {RADII.map((r) => (
            <div key={r} className={`bg-muted flex size-24 items-end justify-center border p-2 ${r}`}>
              <span className="font-mono text-[0.6875rem]">{r}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Typography" note="Two families plus a mono. Serif carries dictionary content only.">
        <div className="flex flex-col gap-4">
          <p className="font-serif text-[2rem] leading-[1.15] font-semibold tracking-[-0.02em]">eloquent</p>
          <p className="text-muted-foreground font-mono text-xs">
            /ˈel.ə.kwənt/ · θɪŋ · ðɪs · ˈvɪʒ.ən · tʃɜːtʃ
          </p>
          <p className="font-serif max-w-[65ch] text-[1.0625rem] leading-[1.65]">
            Fluent or persuasive in speaking or writing; clearly expressing or indicating something.
          </p>
          <p className="max-w-[65ch] text-[0.9375rem] leading-[1.6]">
            Interface copy is set in the sans family. This paragraph is chrome, not content, so it never takes the
            serif.
          </p>
          <p className="font-mono text-[1.75rem] leading-none font-medium [font-variant-numeric:tabular-nums]">
            1,284
          </p>
        </div>
      </Section>

      <Section title="Stacking order" note="Named layers, so no call site invents a z-index that lands above a dialog.">
        <ul className="flex flex-col gap-1">
          {Object.entries(LAYERS).map(([name, value]) => (
            <li key={name} className="flex gap-4 font-mono text-xs">
              <span className="text-muted-foreground w-32">{name}</span>
              <span>{value}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Elevation" note="One hover shadow in light mode; dark mode gets depth from surface steps.">
        <div className="card-hover bg-card w-64 rounded-xl border p-4">
          <p className="text-[0.8125rem]">Hover this card.</p>
        </div>
      </Section>
    </div>
  ),
}

/** IPA rendering, isolated so a tofu box is unmissable. */
export const PhoneticCoverage: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground max-w-[65ch] text-[0.8125rem]">
        Every row must render as glyphs. Theta, the tie bar and the voicing diacritic are absent from the Google subset
        of Geist Mono and resolve through the fallback tail of <code className="font-mono">--font-mono</code>.
      </p>
      <dl className="flex flex-col gap-2">
        {[
          ["dataset sample", "ˈel.ə.kwənt"],
          ["dental fricatives", "θɪŋ · bəʊθ · ˈmeθ.əd · ðɪs"],
          ["affricates", "tʃɜːtʃ · t͡ʃ · dʒʌdʒ"],
          ["vowels", "ɑːɒɔːɜːʊuːiːeɪaɪɔɪaʊəʊ"],
          ["diacritics", "ˈbʌt̬.ər · ˌbætl̩ · ɡlɒtəl ʔ"],
        ].map(([label, value]) => (
          <div key={label} className="flex flex-col gap-1 border-b pb-2">
            <dt className="text-muted-foreground text-[0.6875rem] font-semibold tracking-[0.09em] uppercase">
              {label}
            </dt>
            <dd className="font-mono text-base">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  ),
}
