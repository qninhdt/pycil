"use client"

import { useState, useTransition } from "react"
import { useRouter } from "next/navigation"

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { deleteAccount } from "@/lib/actions/account"
import { WarningIcon } from "@/lib/icons"

/**
 * The literal the API validates. Sent by the action, typed here.
 *
 * Requiring it to be typed is not theatre: this is the one irreversible action in the
 * product, and a button that deletes an account on a single click is a button that
 * deletes an account by accident. The server checks the same string, so a client that
 * skipped this gate would still be refused.
 */
const CONFIRMATION = "DELETE"

/**
 * Deleting the account.
 *
 * The consequence list is specific because "this cannot be undone" tells the learner
 * nothing about what they are losing. What actually goes is enumerated from what the
 * server erases: decks and folders, every review record and schedule, assistant
 * threads, and word generation history.
 *
 * What survives is worth stating too. The dictionary is shared content, so the words
 * themselves are not deleted — only this account's relationship to them.
 */
export function DeleteAccountDialog() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState("")
  const [problem, setProblem] = useState<string | null>(null)
  const [isDeleting, startDeleting] = useTransition()

  const armed = typed === CONFIRMATION

  function submit() {
    if (!armed) return

    startDeleting(async () => {
      setProblem(null)
      // Only a failure can return: the action redirects on success, and a redirect
      // throws, so there is no success branch to handle here.
      const result = await deleteAccount()
      if (result.success) router.push("/login")
      else setProblem(result.error)
    })
  }

  return (
    <>
      <Button variant="destructive" onClick={() => setOpen(true)}>
        Delete account
      </Button>

      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          // The typed confirmation is cleared on dismiss, so reopening the dialog does
          // not present an already-armed delete button.
          if (!next) {
            setTyped("")
            setProblem(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia>
              <WarningIcon className="text-destructive" />
            </AlertDialogMedia>
            <AlertDialogTitle>Delete your account?</AlertDialogTitle>
            <AlertDialogDescription>
              This is permanent. Deleted with it: every folder and deck you own, all of
              your review history and schedules, your assistant conversations, and your
              word generation history. The dictionary itself is shared, so the words stay
              for everyone else.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <Field className="px-4">
            <FieldLabel htmlFor="confirm-delete">
              Type {CONFIRMATION} to confirm
            </FieldLabel>
            <Input
              id="confirm-delete"
              value={typed}
              autoComplete="off"
              onChange={(event) => setTyped(event.target.value)}
            />
            <FieldDescription>
              Export your data first if you want a copy. There is no recovery after this.
            </FieldDescription>
            {problem ? <FieldDescription>{problem}</FieldDescription> : null}
          </Field>

          <AlertDialogFooter>
            <AlertDialogCancel>Keep my account</AlertDialogCancel>
            {/* Not an `AlertDialogAction`: that primitive closes the dialog on click, and
                a failed deletion has to leave the dialog open to state why. */}
            <Button variant="destructive" onClick={submit} disabled={!armed || isDeleting}>
              {isDeleting ? <Spinner data-icon="inline-start" /> : null}
              Delete permanently
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
