import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import {
  BooksIcon,
  PlusIcon,
  WarningCircleIcon,
} from "@/lib/icons"

/**
 * The states a screen actually passes through. A token defect in a loading,
 * empty, or error state is invisible in a gallery of happy-path components,
 * which is the whole reason this file exists before any screen is built.
 */
const meta = {
  title: "Foundations/Primitive Inventory",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold tracking-[0.09em] text-muted-foreground uppercase">
        {label}
      </h3>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  )
}

export const Actions: Story = {
  render: () => (
    <div className="flex flex-col gap-8">
      <Row label="Variants">
        <Button>Start studying</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Delete deck</Button>
        <Button variant="link">Link</Button>
      </Row>
      <Row label="Sizes">
        <Button size="xs">Extra small</Button>
        <Button size="sm">Small</Button>
        <Button>Default</Button>
        <Button size="lg">Large</Button>
        <Button size="icon" aria-label="Add">
          <PlusIcon />
        </Button>
      </Row>
      <Row label="With icon, and the pending composition">
        <Button>
          <PlusIcon data-icon="inline-start" />
          New deck
        </Button>
        <Button disabled>
          <Spinner data-icon="inline-start" />
          Saving
        </Button>
        <Button variant="outline" disabled>
          Disabled
        </Button>
      </Row>
    </div>
  ),
}

export const Tags: Story = {
  render: () => (
    <div className="flex flex-col gap-8">
      <Row label="Badge variants">
        <Badge>Default</Badge>
        <Badge variant="secondary">Secondary</Badge>
        <Badge variant="outline">Outline</Badge>
        <Badge variant="destructive">Destructive</Badge>
      </Row>
      <Row label="Wash tags: the semantic pairs, never a raw hex">
        <span className="rounded-4xl bg-wash-success px-2 py-0.5 text-xs font-medium text-on-wash-success">
          Correct
        </span>
        <span className="rounded-4xl bg-wash-danger px-2 py-0.5 text-xs font-medium text-on-wash-danger">
          Incorrect
        </span>
        <span className="rounded-4xl bg-wash-warn px-2 py-0.5 text-xs font-medium text-on-wash-warn">
          Reconnecting
        </span>
        <span className="rounded-4xl bg-wash-info px-2 py-0.5 text-xs font-medium text-on-wash-info">
          Queued
        </span>
        <span className="rounded-4xl bg-wash-primary px-2 py-0.5 text-xs font-medium text-on-wash-primary">
          Selected
        </span>
      </Row>
    </div>
  ),
}

export const Surfaces: Story = {
  render: () => (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card className="card-hover">
        <CardHeader>
          <CardTitle>Academic Word List</CardTitle>
          <CardDescription>240 senses, 18 due today</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Full composition: header, content and footer. Hover raises the single
            shadow in the system, and nothing in dark mode.
          </p>
        </CardContent>
        <CardFooter>
          <Button size="sm">Study</Button>
        </CardFooter>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Loading</CardTitle>
          <CardDescription>Skeletons match the final shape</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </CardContent>
      </Card>
    </div>
  ),
}

export const Feedback: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <Alert>
        <AlertTitle>Session resumed</AlertTitle>
        <AlertDescription>
          Your previous round was still open, so it was restored.
        </AlertDescription>
      </Alert>
      <Alert variant="destructive">
        <WarningCircleIcon />
        <AlertTitle>Could not save the grade</AlertTitle>
        <AlertDescription>
          The answer was recorded locally and will retry.
        </AlertDescription>
      </Alert>
      <Row label="Spinner">
        <Spinner />
        <span className="text-sm text-muted-foreground">Loading senses</span>
      </Row>
    </div>
  ),
}

export const EmptyState: Story = {
  render: () => (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <BooksIcon />
        </EmptyMedia>
        <EmptyTitle>No decks yet</EmptyTitle>
        <EmptyDescription>
          A deck holds the senses you are learning. Create one to start.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button size="sm">
          <PlusIcon data-icon="inline-start" />
          New deck
        </Button>
      </EmptyContent>
    </Empty>
  ),
}

export const FormStates: Story = {
  render: () => (
    <FieldGroup className="max-w-sm">
      <Field>
        <FieldLabel htmlFor="deck-name">Deck name</FieldLabel>
        <Input id="deck-name" defaultValue="Academic Word List" />
        <FieldDescription>Shown in the library and in headers.</FieldDescription>
      </Field>
      <Field data-invalid>
        <FieldLabel htmlFor="deck-slug">Slug</FieldLabel>
        <Input id="deck-slug" aria-invalid defaultValue="academic word list" />
        <FieldDescription>
          Use lowercase letters, numbers and hyphens only.
        </FieldDescription>
      </Field>
      <Field data-disabled>
        <FieldLabel htmlFor="deck-owner">Owner</FieldLabel>
        <Input id="deck-owner" disabled defaultValue="you" />
      </Field>
    </FieldGroup>
  ),
}
