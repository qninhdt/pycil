# Pycil — Product Specification

Pycil helps vocabulary learners organize meanings they want to study, practice them,
and return when a review is due. Learners can keep personal material private, publish
selected material, and learn from other people's published libraries without losing
their own progress or control over their organization.

## Register

Product specification. This document defines the intended user experience and the
agreed behavior of features. It is not an announcement that every feature is available.

## Users and jobs to be done

| User | Context | Primary need |
| --- | --- | --- |
| Independent learner | Collects vocabulary across reading, work, and daily life | Organize relevant meanings and know what to review next |
| Returning learner | Has limited time for a learning visit | Start an appropriately sized session without manually choosing every item |
| Content author | Creates decks and groups them into topics | Publish a coherent browsing experience while keeping personal material private |
| Learner using an author's content | Wants useful material without rebuilding it | Save a reference, study it, and keep personal progress independent of the author |
| Visitor | Has not signed in or is evaluating public material | Browse published vocabulary without seeing anyone's private learning information |

## Problem and product purpose

Vocabulary lists easily become disconnected from practice. Repeated copies of a word
can create confusing progress, a large collection can make choosing the next session
hard, and sharing can blur the boundary between private notes and public material.

Pycil should make four questions easy to answer:

1. What belongs in my Library?
2. What is new or due in the material I want to study?
3. What did I actually practice, and when?
4. What can I safely publish or reuse from someone else?

Success means that a learner can organize material, start a focused session, submit
results reliably, and understand their next review without interpreting an unexplained
score. An author can publish deliberately without exposing unrelated private content.

## Brand personality and tone

Pycil should feel clear, calm, useful, and respectful of the learner's time. Its language
should distinguish facts from suggestions and explain what a choice will do before it
changes content or access.

- Say "due for review," not "you have failed to keep up."
- Say "no eligible questions are available," not "you know everything."
- Describe a lapse without blame. Forgetting is a normal part of learning.
- Never imply that a studied item is permanently mastered or that a streak proves ability.
- Explain empty states and blocked actions with a useful next step.

### Anti-references

The product should not resemble a competitive popularity feed, a guilt-driven streak
game, an unexplained mastery dashboard, or a sharing system where a private child can
unexpectedly become visible through a public parent.

## Design principles

1. **Organization is not progress.** Moving or linking content does not reset learning.
2. **Publication is deliberate.** Public and personal material have a clear location boundary.
3. **One meaning, one personal progress.** Repeated appearances never multiply learning credit.
4. **Saving and studying are distinct.** Direct public practice does not add content to Library.
5. **Show facts, not invented certainty.** Due dates and accepted activity are useful; arbitrary mastery claims are not.
6. **Respect the selected scope.** A Due-only session must not silently become a New session.
7. **Failures must be honest.** An incomplete calculation must not look like a complete result.
8. **The learner remains in control.** Assistant changes require approval.

## Vocabulary and shared concepts

| Term | User-facing meaning |
| --- | --- |
| Word | A vocabulary entry that can have several distinct meanings |
| Sense | One particular meaning of a word; the unit of personal learning progress |
| Deck | A named set of senses selected for study |
| Folder | A container for folders, decks, and references |
| Reference | A saved placement that opens an existing folder or deck, rather than a separate copy |
| Library | The learner's organized material, including Personal and Published |
| Personal | The private part of the learner's Library |
| Published | The publicly browsable part of the author's Library |
| Scope | The material included when opening, counting, searching, or studying a chosen location |
| Tracked material | Readable material reachable from the learner's Library and included in Home learning counts |

A word such as "bank" may have a financial sense and a river-side sense. Studying one
does not automatically mark the other as studied. Studying the same financial sense in
two decks does not create two independent learning histories.

## 1. Account, preferences, and privacy

### Behavior

- A signed-in learner has one Library containing Personal and Published.
- Preferences cover interface language, reporting timezone, translation language,
  question types, answer formats, questions per sense, session size, and explanations.
- Visitors can browse published content. Personal progress and learning actions require sign-in.
- A public profile contains public identity information and the author's Published tree,
  not their Personal tree, account settings, activity, or private preferences.
- When a plan does not support a selected answer format, the learning experience uses
  supported formats where possible and explains when the remaining selection is infeasible.
- A plan change must not erase vocabulary organization or personal learning progress.
- A learner may set a unique lowercase handle and a short bio. Both appear publicly;
  their joined date is visible, but country and private learning statistics are not.

### Acceptance criteria

- A new learner can identify Personal and Published without creating either manually.
- Visiting another author never reveals that author's personal due counts or settings.
- A preference combination that cannot produce a session is explained, not silently ignored.

## 2. Library organization

### Behavior

- Personal and Published are permanent system containers. Users cannot delete, move,
  or convert them into ordinary content.
- Ordinary folders, decks, and references live within Personal or Published, not beside them.
- New content goes into Personal unless the user deliberately chooses another destination.
- An owned item can be renamed, described, moved, or deleted. Other people's content is read-only.
- Moving a folder moves its contents with it. A folder cannot be moved inside itself or a descendant.
- A deck may be empty. An empty folder or Published space is a valid state.
- Deleting a folder removes its contents from active browsing and tracking. There is no
  restore/trash feature in this product scope.
- Removing a deck, a reference, or an individual sense from a deck does not erase
  previously recorded learning progress or activity.

### Acceptance criteria

- Given a sense appears in two decks, removing it from one preserves its progress in the other.
- Given an item is moved within Personal, its contents and progress remain unchanged.
- An invalid move leaves the original organization intact.
- An empty Published space never falls back to showing Personal content.

## 3. References and shared material

### Behavior

- A reference points to a folder or deck the learner can read. It cannot point to another reference.
- Personal references may point to the learner's own personal content or readable published content.
- Published references may point only to published content. Publishing a reference does
  not publish the material it points to.
- Adding a reference to another author's published content brings its readable senses
  into the learner's Library scope. Future content changes are reflected when it is opened again.
- A reference has its own placement and label. It is not an editable copy of the target.
- The target of an existing reference is not silently changed during an ordinary edit;
  the user creates a new reference to choose a different target.
- References must not create repeated vocabulary items in a scope's counts or session.
- If content is unpublished or deleted, the reference no longer opens that content.
  Its owner can see an unavailable state and remove or replace the reference.
- A visitor must not see private target names or other private details through an unavailable reference.

### Acceptance criteria

- Saving two references to the same deck counts each sense once in a combined scope.
- A direct reference back to its containing ancestor is rejected.
- Interconnected references do not produce endless navigation loading or duplicate learning items.
- An unavailable reference does not grant continued access merely because it was previously saved.

## 4. Publishing and unpublishing

### Behavior

- Publish moves an owned item into Published, including its contents when it is a folder.
- The user confirms the move and understands which content will become public.
- The user may keep a reference at the previous Personal location. This preserves
  organization without producing a second deck or a second learning progress.
- Publishing a nested item does not publish its previous private ancestors.
- A folder containing references to external private material cannot be published as-is.
  Pycil explains that those references must be removed, moved, or point to published material.
- Unpublish moves the content back into Personal. It does not require approval from people
  who saved references to it.
- Other people lose future access after unpublishing. Content already viewed or retained
  on their device cannot be made unseen.
- Existing learners keep the progress and activity they previously recorded.

### Acceptance criteria

- A cancelled publication confirmation leaves the content in Personal.
- A published deck remains the same deck, with the same owner's progress.
- A visitor's navigation begins at Published and does not disclose a private ancestor.
- Unpublishing makes other people's references unavailable without erasing their past learning.

## 5. Discovery and search

### Search and discovery

- Dictionary search finds words and their separate meanings.
- Library search finds named content and descriptions within the learner's Library,
  including readable content reached through references.
- Searching a selected folder or reference is restricted to that scope.
- Discovery finds published content independently of what the learner has saved.
- An author profile provides a real Published tree that visitors can browse by folder.
- Search never exposes private content or private ancestors.
- Search results do not become tracked material merely because they were viewed.

### Acceptance criteria

- Viewing or directly studying a foreign deck leaves tracked membership unchanged.
- Adding its reference may change Home counts and reveals existing personal progress.
- A Library search excludes content that has become unreadable.

## 6. Browse and edit a deck

### Behavior

- Decks show separate senses with their lexical information and, for signed-in learners,
  the learner's own learning state.
- Users can browse all senses or filter New, Due, and Not yet due.
- Within the chosen scope, users can search word text and sort by word or applied-review
  recency. Source decks are shown without exposing unreadable or private material.
- Large decks are browsable in pages; paging does not change membership.
- An owner can edit the name, description, destination, and final selected senses.
- Save applies the complete final selection together. A failed save does not keep only
  the rename, only part of the senses, or an unintended move.
- Senses not visible on the current browsing page are preserved unless deliberately removed.
- Duplicate selection of the same sense does not create duplicate membership.
- Visitors can browse and learn but cannot edit another author's deck.

### Acceptance criteria

- Renaming a 1,000-sense deck does not remove senses beyond the first visible page.
- A failed content selection leaves the previous saved deck intact.
- Moving a deck into Published during editing requires publication confirmation.

## 7. Home and scope summaries

### Learning states

| State | Meaning |
| --- | --- |
| New | No learning result has yet established personal progress for this sense |
| Due | The sense has been studied and its scheduled review time has arrived or passed |
| Not yet due | The sense has been studied and its next scheduled review is in the future |

"Studied" means recorded practice in Pycil, not proof that a learner already knew a word
outside Pycil. A review becomes Due when its scheduled time arrives, not only afterward.

### Behavior

- Home summarizes readable material reachable from the learner's Library, across both
  Personal and Published. There is no required separate "Studying" folder.
- A folder, deck, or reference can show the same kind of summary for its own scope.
- Summaries count unique senses. Parent totals are not the sum of overlapping child totals.
- Total = New + Studied; Studied = Due + Not yet due.
- A public deck's personalized summary describes the current learner, not the author.
- Studying public content directly is allowed without adding it to Library. That progress
  is retained, but the content does not enter proactive Home counts until referenced from Library.
- Changing Library membership can change the summary denominator without meaning that
  the learner has lost knowledge.
- The product does not present a mastery percentage, mastered/unmastered classification,
  or weakest-word recommendation list.

### Acceptance criteria

- A previously studied sense outside Library does not contribute to Home's Due count.
- Adding a reference reveals existing personal progress rather than starting again.
- A summary never counts the same sense twice because it has several placements.

## 8. Prepare a learning session

### Scope and selection

The learner chooses Library, a folder, a deck, or a readable reference as the scope.
The learner then chooses one of these modes:

| Mode | Selection rule |
| --- | --- |
| Due | Only currently due senses, with the oldest due work first |
| New | Only senses without established personal progress |
| Auto | Due first, then New, then Not yet due if space remains |

- Auto is the default when the learner does not choose a specific selection mode.
- Due never fills unused places with New or Not yet due senses. New never fills with studied senses.
- Maximum senses is an upper limit, not a promise to deliver that many.
- The default is up to 10 senses, with 3 questions per sense.
- The learner can choose 1–7 questions per sense; the session must not exceed 100 questions.
  An invalid combination is explained rather than silently reduced.
- Only senses with enough suitable questions are included. A due count can therefore be
  larger than the number of senses available for a session.
- If no eligible material exists, show a truthful empty state. Opening a session does
  not itself count as learning activity or change a review date.
- Sessions are local learning experiences. Continuing an unfinished session on another
  device is not promised; a same-device resume is possible only while its local work is retained.

### Acceptance criteria

- Requesting up to 10 Due senses when only 4 are eligible produces 4, not 4 Due plus 6 New.
- Auto uses New only after eligible Due material has been considered.
- An empty selection explains whether no matching material or no suitable questions are available.
- A scope that is too large produces a clear failure, not a misleading zero-item session.

## 9. Questions, ratings, and completion

### Behavior

- Question types cover definitions, context, cloze, meaning, usage, and dialogue.
- Supported answer experiences include multiple choice, a single word, and short written answers.
  Availability depends on question suitability, preferences, and plan.
- Explanations can be shown according to the learner's preference.
- Answer feedback and personal recall ratings have different meanings. Feedback alone
  does not submit learning progress.
- The recall choices are Again, Hard, Good, and Easy. The learner's completed work is
  summarized into one final rating per sense for a submission.
- Results for a new or due sense update its next review. An Again rating also updates
  the next review when the sense was not yet due.
- Early Hard, Good, or Easy practice counts as activity but leaves the existing review schedule unchanged.
- Learning progress is personal; it never updates the author's or another learner's progress.

### Reliable submission

- A submission contains up to 100 distinct senses, with one final rating for each.
- A submitted set of results is accepted together or not at all.
- A network interruption may leave acceptance uncertain. The experience must distinguish
  that state from confirmed success and allow retrying the same work.
- Retrying the same submission does not repeat learning credit, move the schedule again,
  or count as new activity, even if later learning has already occurred.
- Changing an already submitted set of results is not treated as a retry of the old work.
- A genuinely new practice submission is distinct from retrying an earlier one.
- If a source deck becomes unavailable after a session was prepared, the learner may
  still submit the already prepared work. This does not reopen the source deck.

### Acceptance criteria

- An early Good practice leaves the due date unchanged but contributes to activity.
- An Again result is counted even when the learner forgot the answer.
- If one result in a submission cannot be accepted, none of that submission appears as completed.
- A retry after an uncertain network outcome records the work only once.

## 10. Activity, streaks, and upcoming reviews

### Activity

- One accepted sense result is one learning event. Intensity reflects accepted events,
  not page views, unique words, or the number of sessions opened.
- Applied learning and early practice both count. Again also counts.
- Preparing, browsing, or requesting answer feedback without submitting results does not count.
- Retries do not count again. Removing or unpublishing content does not erase past activity.
- An event belongs to the date when Pycil accepts it, using the learner's timezone at
  that moment. Work submitted after midnight belongs to the new acceptance date.
- Changing timezone does not relabel dates already recorded.

### Streaks

- An active date has at least one accepted learning or practice event.
- Current streak is the consecutive run ending today, or ending yesterday if today has
  no activity. Otherwise it is zero.
- Longest streak considers all recorded active dates, not just the year currently displayed.
- A calendar view includes inactive dates explicitly; absence is not a loading state.

### Upcoming reviews

- The schedule groups currently future reviews by date in the learner's reporting timezone.
- Overdue work appears in Due counts, not as a future prediction.
- The schedule changes as the learner reviews or changes their Library.
- It is a view of current scheduled work, not a forecast of success or future learning.

### Acceptance criteria

- Yesterday's activity preserves the current streak while today is still inactive.
- A deleted deck leaves the learner's already recorded activity and longest streak intact.
- A timezone change affects future reporting without moving old recorded activity dates.

## 11. Dictionary and content availability

- Dictionary results distinguish a saved word from a selectable entry that still needs preparation.
- Distinct meanings remain selectable; choosing a word does not imply choosing every sense.
- Requesting unavailable content shows waiting, in-progress, ready, or failed preparation states.
- Preparation of vocabulary material is distinct from preparing a learner's study session.
- Repeated requests for the same material should not appear to create duplicate words.
- Failed preparation gives a useful retry path; a failure is not presented as a ready question bank.
- Dictionary browsing alone does not add material to Library or establish learning progress.
- Saved meanings can show personal progress and containing Library decks. A previously
  studied meaning retains its progress even when no Library deck currently contains it.

## 12. Assistant

- The assistant can help find vocabulary, browse readable material, inspect owned deck
  selections, explain current progress, and propose Library changes.
- Creating, editing, moving, publishing, or deleting content requires approval before execution.
- The user can approve or reject a proposal. A rejected action must not be executed by a substitute action.
- Approval does not override ownership or access. A change that became unavailable may still fail.
- Publication consent remains necessary even when the change was proposed in conversation.
- Conversations can be reopened with their messages and pending approvals while retained.
- Supported images, models, and effort choices are limited to those offered in the interface.
- The assistant must not claim a change succeeded before receiving confirmation.
- It must not invent progress, subscription changes, learning results, or access to private material.

### Acceptance criteria

- Rejecting a proposed deck edit preserves the deck.
- Reopening a retained conversation shows an outstanding approval rather than repeating it as a new action.
- Approving a change to an item that is no longer editable produces an honest failure.

## Offer and plan behavior

Pycil distinguishes Free and Pro. The offer includes a periodic assistant allowance;
Pro also enables advanced written-answer grading. Supported choices and remaining
allowance must be visible rather than discovered only after a failed action.

A period is anchored to the user's account cycle rather than assumed to start on the
first calendar day. Reading the allowance does not consume it. Upgrading does not reset
usage; downgrading does not delete progress or selected preferences. A started assistant
turn may consume the work it actually performs even if the conversation is interrupted.

This specification does not set currency prices, payment methods, promotional offers,
or automatic purchasing behavior. Those require separate product decisions.

## Product limits and failure experience

| Limit | Agreed behavior |
| --- | --- |
| Senses per deck | Up to 1,000 |
| Immediate children per folder | Up to 500 |
| Active owned items | Up to 2,000, counting Personal and Published but not Library itself |
| Total selections across owned decks | Up to 100,000; the same sense in two decks uses two selections |
| Organization depth | Up to 20 steps from Library; Personal and Published occupy the first step |
| Prepared questions | Up to 100 per session |

References count as owned placements; another author's original content does not count
as owned content. A large referenced scope can nevertheless be too large to study or
summarize in one operation. The user must be offered a smaller scope, not partial results
presented as complete. Referenced content may grow after it was saved.

Existing material above a new limit is preserved. Users may reduce or repair it, while
changes that grow the over-limit dimension are rejected. The product must not delete
material automatically to make a quota appear satisfied.

Errors should identify the action that did not complete and an appropriate next step:
sign in, reduce the scope, correct the selection, confirm publication, remove an
unavailable reference, or retry an uncertain submission. Loading, empty, unavailable,
and failed states must not be conflated.

## Accessibility and inclusion

- Primary actions, browsing, answer selection, and approval must be usable with a keyboard.
- Controls need meaningful labels, visible focus, and a reading order that matches the task.
- New, Due, Not yet due, activity intensity, and failures must not rely on color alone.
- Meaningful vocabulary distinctions and long descriptions must remain understandable
  on narrow screens and with enlarged text.
- Confirmation messages must explain the consequences rather than relying on an icon.
- Localization must not change privacy, learning state, or the meaning of a protected container.
- Learners should not be punished in wording for choosing smaller sessions, practicing early,
  missing a day, or changing the material they want to study.

## Boundaries

This product scope does not include collaborative editing, teams, invitations, private
sharing links, per-item visibility overrides, public favorite rankings, social likes,
weak-word recommendations, mastery scores, a raw review-history feature, or guaranteed
cross-device continuation of unfinished learning sessions.

Star/Pin, sense difficult/bookmark marks, node/word tags, translated content, country,
Import, audio/TTS, courses and recommendations are deferred from this release. A saved
translation-language preference does not imply translations are available.

Pycil does not claim to measure all vocabulary a learner knows outside the product, to
predict future recall perfectly, or to make previously viewed public content disappear
from other people's devices after unpublishing.
