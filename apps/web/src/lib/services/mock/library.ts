import type { MockDatabase } from '../mock'
import type { ContentsOptions, LibraryDetails, Meaning, MeaningOptions, MeaningPage } from '../../library-model'
import type { LibraryPage, StudySummary } from '../../home-api'
import { HomeApiError } from '../../home-api'

type SeedNode = { id: string; parent_id: string | null; name: string; type: string; description: string | null; updated_at?: string }

// All content and memberships live in the JSON. This module supplies repository behavior.
export function createMockLibrary(db: MockDatabase, now: () => Date) {
  const account = db.account
  const root = (id: string, name: string, parent_id: string | null): SeedNode => ({ id, name, parent_id, type: 'FOLDER', description: null })
  const storedNodes: SeedNode[] = db.library.nodes
  const nodes: SeedNode[] = [root(account.library_node_id, 'My Library', null), root(account.personal_node_id, 'Personal', account.library_node_id),
    root(account.published_node_id, 'Published', account.library_node_id), ...db.public_users.map(user => root(user.published_node_id, 'Published', null)), ...db.nodes, ...storedNodes]
  const byId = new Map(nodes.map(node => [node.id, node]))
  const memberships = db.library.membership as Record<string, number[]>
  const references = db.library.references as Record<string, string>
  const due = new Set(db.library.due_sense_ids), fresh = new Set(db.library.new_sense_ids)
  const lexical = [...db.dictionary.words, ...db.dictionary.pending_words].flatMap(word => word.senses.map(sense => ({ word, sense })))
  const bySenseId = new Map(lexical.map(entry => [entry.sense.id, entry]))
  const get = (id: string) => {
    const node = byId.get(id)
    if (!node) throw new HomeApiError(404, 'node_not_found')
    return node
  }
  function deckIds(id: string, strict = true): string[] {
    const seen = new Set<string>(), decks = new Set<string>(), queue = [id]
    while (queue.length) {
      const current = queue.pop()!
      if (seen.has(current)) continue
      seen.add(current)
      const node = get(current)
      if (node.type === 'DECK') decks.add(node.id)
      else if (node.type === 'REFERENCE') {
        const target = references[node.id]
        if (target && byId.has(target)) queue.push(target)
        else if (current === id && strict) throw new HomeApiError(404, 'reference_unavailable')
      } else for (const child of nodes) if (child.parent_id === current) queue.push(child.id)
    }
    return [...decks]
  }
  const senseIds = (id: string) => new Set(deckIds(id).flatMap(deck => memberships[deck] ?? []))
  function summary(id: string): StudySummary {
    const ids = senseIds(id)
    const newCount = [...ids].filter(id => fresh.has(id)).length
    const dueCount = [...ids].filter(id => due.has(id)).length
    return { node_id: id, as_of: now().toISOString(), total: ids.size, new: newCount, due: dueCount, studied: ids.size - newCount,
      not_due: ids.size - newCount - dueCount, reachable_decks: deckIds(id).length,
      last_studied_at: ids.size > newCount ? new Date(now().getTime() - 86400000).toISOString() : null }
  }
  function ancestors(id: string) {
    const result: SeedNode[] = [], seen = new Set<string>()
    let node: SeedNode | undefined = get(id)
    while (node?.parent_id && !seen.has(node.parent_id)) {
      seen.add(node.parent_id)
      node = byId.get(node.parent_id)
      if (node) result.unshift(node)
    }
    return result
  }
  function details(id: string): LibraryDetails {
    const node = get(id)
    const parents = ancestors(id)
    const target = node.type === 'REFERENCE' ? byId.get(references[id]) : null
    const available = node.type !== 'REFERENCE' || Boolean(target)
    const author = db.public_users.find(user => user.published_node_id === node.id || parents.some(parent => parent.id === user.published_node_id))
    const foreign = node.id === 'travel-source' || Boolean(author)
    return { id, name: node.name, type: node.type as LibraryDetails['type'], description: node.description,
      owner_id: author?.id ?? (foreign ? 'preview-sam' : account.id),
      space: foreign || id === account.published_node_id || parents.some(parent => parent.id === account.published_node_id || db.public_users.some(user => user.published_node_id === parent.id)) ? 'PUBLISHED' : id === account.library_node_id ? 'LIBRARY' : 'PERSONAL',
      role: id === account.library_node_id ? 'LIBRARY_ROOT' : id === account.personal_node_id ? 'PERSONAL_ROOT' : id === account.published_node_id ? 'PUBLISHED_ROOT' : 'NORMAL',
      created_at: db.library.created_at, updated_at: node.updated_at ?? db.library.updated_at,
      breadcrumbs: parents.map(parent => ({ id: parent.id, name: parent.name })), summary: available ? summary(id) : null,
      reference_available: node.type === 'REFERENCE' ? available : null,
      target: target ? { id: target.id, name: target.name, type: target.type as 'DECK' | 'FOLDER', owner_id: details(target.id).owner_id, space: details(target.id).space as 'PERSONAL' | 'PUBLISHED' } : null }
  }
  function page<T>(items: T[], options: { cursor?: string; limit?: number }, scope: string) {
    const limit = options.limit ?? 12
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new HomeApiError(422, 'invalid_page')
    let offset = 0
    if (options.cursor) {
      try {
        const cursor = JSON.parse(decodeURIComponent(options.cursor))
        if (cursor.scope !== scope || !Number.isSafeInteger(cursor.offset) || cursor.offset < 0 || cursor.offset > items.length) throw new Error()
        offset = cursor.offset
      } catch { throw new HomeApiError(422, 'invalid_cursor') }
    }
    return { items: items.slice(offset, offset + limit), next_cursor: offset + limit < items.length ? encodeURIComponent(JSON.stringify({ scope, offset: offset + limit })) : null }
  }
  function contents(id: string, options: ContentsOptions = {}): LibraryPage {
    const node = get(id)
    if (node.type === 'DECK') throw new HomeApiError(422, 'not_a_folder')
    const target = node.type === 'REFERENCE' ? details(id).target?.id : id
    if (!target) throw new HomeApiError(404, 'reference_unavailable')
    const query = options.q?.trim().toLowerCase() ?? ''
    if (query.length > 200) throw new HomeApiError(422, 'invalid_query')
    const matches = nodes.filter(child => query ? ancestors(child.id).some(parent => parent.id === target) && `${child.name} ${child.description ?? ''}`.toLowerCase().includes(query) : child.parent_id === target)
    const result = page(matches, options, `${id}:${query}`)
    return { nodes: result.items.map(child => {
      const detail = details(child.id)
      return { id: child.id, name: child.name, type: child.type as LibraryDetails['type'], description: child.description, owner_id: detail.owner_id, summary: detail.summary,
        reference_id: detail.target?.id ?? null, target_type: detail.target?.type ?? null }
    }), next_cursor: result.next_cursor }
  }
  function meanings(id: string, options: MeaningOptions = {}): MeaningPage {
    const ids = senseIds(id), decks = deckIds(id)
    const query = options.q?.trim().toLowerCase() ?? '', state = options.state ?? 'ALL', sort = options.sort ?? 'LEMMA_ASC'
    if (query.length > 200 || !['ALL', 'NEW', 'DUE', 'NOT_YET_DUE'].includes(state) || !['LEMMA_ASC', 'LAST_REVIEWED_DESC'].includes(sort)) throw new HomeApiError(422, 'invalid_query')
    const values = [...ids].map(id => bySenseId.get(id)).filter((entry): entry is NonNullable<typeof entry> => Boolean(entry)).map<Meaning>(({ word, sense }) => {
      const learningState = due.has(sense.id) ? 'DUE' : fresh.has(sense.id) ? 'NEW' : 'NOT_YET_DUE'
      return { sense_id: sense.id, lemma: word.lemma, pos: sense.pos.toLowerCase(), definition: sense.definition?.content ?? null, cefr_level: sense.cefr_level,
        examples: sense.examples.map(example => ({ text: example.content })),
        learning: { state: learningState, last_reviewed_at: learningState === 'NEW' ? null : new Date(now().getTime() - (sense.id % 6 + 1) * 86400000).toISOString(),
          due_at: learningState === 'NEW' ? null : new Date(now().getTime() + (learningState === 'DUE' ? -86400000 : 3 * 86400000)).toISOString() },
        sources: decks.filter(deck => memberships[deck]?.includes(sense.id)).map(deck => ({ id: deck, name: get(deck).name, owner_id: details(deck).owner_id, space: details(deck).space as 'PERSONAL' | 'PUBLISHED' })), sources_has_more: false }
    }).filter(sense => (state === 'ALL' || sense.learning?.state === state) && `${sense.lemma} ${sense.definition}`.toLowerCase().includes(query))
    values.sort((a, b) => sort === 'LAST_REVIEWED_DESC' ? (b.learning?.last_reviewed_at ?? '').localeCompare(a.learning?.last_reviewed_at ?? '') || a.sense_id - b.sense_id : a.lemma.localeCompare(b.lemma, 'en') || a.sense_id - b.sense_id)
    const result = page(values, options, `${id}:${query}:${state}:${sort}`)
    return { senses: result.items, next_cursor: result.next_cursor }
  }
  function updateDeckSenses(deckId: string, change: { add: number[]; remove: number[] }) {
    const node = get(deckId)
    if (node.type !== 'DECK' || details(deckId).owner_id !== account.id) throw new HomeApiError(422, 'invalid_destination')
    if (new Set(change.add).size !== change.add.length || new Set(change.remove).size !== change.remove.length || change.add.some(id => change.remove.includes(id))) throw new HomeApiError(422, 'invalid_selection')
    if (change.add.some(id => !bySenseId.has(id) || !db.dictionary.words.some(word => word.id === bySenseId.get(id)!.word.id))) throw new HomeApiError(404, 'sense_not_found')
    const ids = memberships[deckId] ??= []
    memberships[deckId] = [...new Set([...ids.filter(id => !change.remove.includes(id)), ...change.add])]
    for (const senseId of change.add) if (!due.has(senseId) && senseId > 48) fresh.add(senseId)
  }
  function discovery(options: ContentsOptions & { type?: 'DECK' | 'FOLDER'; ownerId?: string }) {
    const q = options.q?.trim().toLowerCase() ?? ''
    const matches = nodes.filter(node => {
      const detail = details(node.id)
      return detail.space === 'PUBLISHED' && detail.role === 'NORMAL' && detail.reference_available !== false &&
        (!options.type || node.type === options.type) && (!options.ownerId || detail.owner_id === options.ownerId) &&
        (!q || `${node.name} ${node.description ?? ''}`.toLowerCase().includes(q))
    })
    const result = page(matches, options, `discovery:${q}:${options.type ?? ''}:${options.ownerId ?? ''}`)
    return { nodes: result.items.map(node => ({ id: node.id, name: node.name, type: node.type as LibraryDetails['type'], description: node.description, owner_id: details(node.id).owner_id, summary: null, reference_id: details(node.id).target?.id ?? null, target_type: details(node.id).target?.type ?? null })), next_cursor: result.next_cursor }
  }
  function sources(id: string, senseId: number, cursor?: string) {
    if (!senseIds(id).has(senseId)) throw new HomeApiError(404, 'sense_not_found')
    const decks = deckIds(id).filter(deck => memberships[deck]?.includes(senseId)).map(deck => ({ id: deck, name: get(deck).name, owner_id: details(deck).owner_id, space: details(deck).space as 'PERSONAL' | 'PUBLISHED' }))
    const result = page(decks, { cursor, limit: 20 }, `sources:${id}:${senseId}`)
    return { decks: result.items, next_cursor: result.next_cursor }
  }
  function createReference(parentId: string, targetId: string, name: string) {
    const parent = get(parentId), target = get(targetId)
    if (parent.type !== 'FOLDER' || parentId === account.library_node_id || details(parentId).owner_id !== account.id || target.type === 'REFERENCE') throw new HomeApiError(422, 'invalid_reference_target')
    if (parentId === targetId || ancestors(parentId).some(node => node.id === targetId)) throw new HomeApiError(422, 'node_cycle')
    if (!name.trim() || name.length > 255) throw new HomeApiError(422, 'invalid_node')
    const id = `preview-reference-${Date.now()}-${nodes.length}`
    const node = { id, parent_id: parentId, name: name.trim(), type: 'REFERENCE', description: null }
    nodes.push(node); storedNodes.push(node); byId.set(id, node); references[id] = targetId
    return id
  }
  function createNode(parentId: string, type: 'FOLDER' | 'DECK', name: string, description: string | null, senseIds: number[] = []) {
    const parent = get(parentId)
    if (parent.type !== 'FOLDER' || parentId === account.library_node_id || details(parentId).owner_id !== account.id) throw new HomeApiError(422, 'invalid_destination')
    if (!name.trim() || name.trim().length > 255 || description !== null && description.length > 8000) throw new HomeApiError(422, 'invalid_node')
    if (type !== 'DECK' && senseIds.length) throw new HomeApiError(422, 'invalid_selection')
    if (new Set(senseIds).size !== senseIds.length || senseIds.some(id => !bySenseId.has(id) || !db.dictionary.words.some(word => word.id === bySenseId.get(id)!.word.id))) throw new HomeApiError(422, 'invalid_selection')
    const id = `preview-${type.toLowerCase()}-${Date.now()}-${nodes.length}`
    const node = { id, parent_id: parentId, name: name.trim(), type, description: description?.trim() || null, updated_at: now().toISOString() }
    nodes.push(node)
    storedNodes.push(node)
    byId.set(id, node)
    if (type === 'DECK') memberships[id] = [...senseIds]
    for (const senseId of senseIds) if (!due.has(senseId) && senseId > 48) fresh.add(senseId)
    return id
  }
  function createDeck(parentId: string, name: string, senseIds: number[]) { return createNode(parentId, 'DECK', name, null, senseIds) }
  function updateNode(id: string, change: { name: string; description: string | null }) {
    const node = get(id)
    if (details(id).role !== 'NORMAL' || details(id).owner_id !== account.id) throw new HomeApiError(403, 'node_not_editable')
    if (!change.name.trim() || change.name.trim().length > 255 || change.description !== null && change.description.length > 8000) throw new HomeApiError(422, 'invalid_node')
    node.name = change.name.trim(); node.description = change.description?.trim() || null; node.updated_at = now().toISOString()
  }
  function moveNode(id: string, parentId: string, publication?: { confirm: boolean; retainReference: boolean }) {
    const node = get(id), parent = get(parentId)
    if (details(id).role !== 'NORMAL' || details(id).owner_id !== account.id || parent.type !== 'FOLDER' || parentId === account.library_node_id ||
      details(parentId).owner_id !== account.id || id === parentId || ancestors(parentId).some(item => item.id === id)) throw new HomeApiError(422, 'invalid_destination')
    const oldParent = node.parent_id!, oldSpace = details(id).space
    if (oldSpace === 'PERSONAL' && details(parentId).space === 'PUBLISHED' && !publication?.confirm) throw new HomeApiError(409, 'publication_confirmation_required')
    if (publication?.retainReference && (oldSpace !== 'PERSONAL' || details(parentId).space !== 'PUBLISHED')) throw new HomeApiError(422, 'invalid_retained_reference')
    node.parent_id = parentId; node.updated_at = now().toISOString()
    if (publication?.retainReference) createReference(oldParent, references[id] ?? id, node.name)
  }
  function copyNode(id: string, parentId: string): string {
    const source = get(id), parent = get(parentId)
    if (details(id).role !== 'NORMAL' || details(id).owner_id !== account.id || parent.type !== 'FOLDER' || parentId === account.library_node_id ||
      details(parentId).owner_id !== account.id || details(id).space !== details(parentId).space || id === parentId || ancestors(parentId).some(item => item.id === id)) throw new HomeApiError(422, 'invalid_destination')
    const sourceNodes: SeedNode[] = [source], seen = new Set([id])
    for (let index = 0; index < sourceNodes.length; index++) for (const child of nodes) if (child.parent_id === sourceNodes[index].id && !seen.has(child.id)) { seen.add(child.id); sourceNodes.push(child) }
    const copies = new Map<string, string>()
    for (const original of sourceNodes) {
      const newParent = original.id === id ? parentId : copies.get(original.parent_id!)!
      const copyId = `preview-${original.type.toLowerCase()}-${Date.now()}-${nodes.length}`
      const copy = { ...original, id: copyId, parent_id: newParent, name: original.id === id ? `${original.name} copy` : original.name, updated_at: now().toISOString() }
      nodes.push(copy); storedNodes.push(copy); byId.set(copyId, copy); copies.set(original.id, copyId)
      if (original.type === 'DECK') memberships[copyId] = [...(memberships[original.id] ?? [])]
      if (original.type === 'REFERENCE' && references[original.id]) references[copyId] = references[original.id]
    }
    return copies.get(id)!
  }
  function deleteNode(id: string) {
    if (details(id).role !== 'NORMAL' || details(id).owner_id !== account.id) throw new HomeApiError(403, 'node_not_editable')
    const removed = new Set([id])
    for (let changed = true; changed;) {
      changed = false
      for (const node of nodes) if (node.parent_id && removed.has(node.parent_id) && !removed.has(node.id)) { removed.add(node.id); changed = true }
    }
    for (const node of [...nodes]) if (removed.has(node.id)) { byId.delete(node.id); delete memberships[node.id]; delete references[node.id] }
    for (const list of [nodes, storedNodes]) for (let index = list.length - 1; index >= 0; index--) if (removed.has(list[index].id)) list.splice(index, 1)
  }
  function setLearning(senseId: number, _rating: string) {
    fresh.delete(senseId); due.delete(senseId)
    db.library.new_sense_ids = db.library.new_sense_ids.filter(id => id !== senseId)
    db.library.due_sense_ids = db.library.due_sense_ids.filter(id => id !== senseId)
  }
  return { discovery, sources, createReference, details, contents, meanings, summary, updateDeckSenses, createDeck, createNode, updateNode, moveNode, copyNode, deleteNode, setLearning }
}
