import { fetchProfile, parseAccountProfile, parsePublicProfile, parseUsageAllowance } from '../api'
import { HomeApiError, homeRequest, homeToken, parseActivity, parseGrade, parseLibrary, parsePreparation, parseReviewBatch, parseSchedule, parseSummary } from '../home-api'
import type { FrontendServices, DateWindow } from './contracts'
import { parseMeaningPage, parseNodeDetails, parseSources } from '../library-api'
import { createAssistantService } from '../assistant-api'
import { parseDictionaryWord, parseWordContext, parseWordGeneration, parseWordPreviews, parseWordSearch } from '../dictionary-model'

export function createHttpServices(getToken: () => Promise<string | null>): FrontendServices {
  async function request<T>(path: string, parse: (value: unknown) => T, signal: AbortSignal, body?: unknown, method?: 'POST' | 'PATCH' | 'DELETE', publicRead = false, headers?: Record<string, string>) {
    const boundedSignal = AbortSignal.any([signal, AbortSignal.timeout(path === 'study:prepare' ? 30000 : 12000)])
    return homeRequest(path, publicRead ? null : await homeToken(getToken, boundedSignal), parse, boundedSignal, body, method, headers)
  }
  const windowQuery = (window: DateWindow) => new URLSearchParams({ start_date: window.start, end_date: window.end }).toString()
  const nodeId = (value: unknown) => {
    if (!value || typeof value !== 'object' || !('id' in value) || typeof value.id !== 'string') throw new HomeApiError(502, 'invalid_response')
    return value.id
  }
  async function libraryPage(path: string, signal: AbortSignal, publicRead = false) {
    const page = await request(path, parseLibrary, signal, undefined, undefined, publicRead)
    const targets = new Map<string, Promise<ReturnType<typeof parseNodeDetails>>>()
    const nodes = await Promise.all(page.nodes.map(async node => {
      if (node.type !== 'REFERENCE' || !node.reference_id || node.target_type) return node
      try {
        if (!targets.has(node.reference_id)) targets.set(node.reference_id, request(`nodes/${encodeURIComponent(node.reference_id)}`, parseNodeDetails, signal, undefined, undefined, publicRead))
        const target = await targets.get(node.reference_id)!
        if (target.type === 'REFERENCE') throw new HomeApiError(502, 'invalid_response')
        return { ...node, target_type: target.type }
      } catch (error) {
        if (error instanceof HomeApiError && error.status === 404) return { ...node, reference_id: null, target_type: null, summary: null }
        throw error
      }
    }))
    return { ...page, nodes }
  }
  return {
    mode: 'live', notice: null,
    assistant: createAssistantService(getToken),
    account: { profile: async signal => {
      const boundedSignal = AbortSignal.any([signal, AbortSignal.timeout(12000)])
      return fetchProfile(await homeToken(getToken, boundedSignal), boundedSignal)
    }, publicProfile: (identifier, signal) => request(/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(identifier) ? `users/${encodeURIComponent(identifier)}` : `users:lookup?handle=${encodeURIComponent(identifier)}`, parsePublicProfile, signal, undefined, undefined, true),
    usage: signal => request('me/usage', parseUsageAllowance, signal),
    updateProfile: (patch, signal) => request('me/profile', parseAccountProfile, signal, patch, 'PATCH'),
    updateSettings: (patch, signal) => request('me/settings', parseAccountProfile, signal, patch, 'PATCH') },
    learning: {
      summary: (nodeId, signal) => request(`study/progress${nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : ''}`, parseSummary, signal),
      activity: (window, signal) => request(`study/activity?${windowQuery(window)}`, parseActivity, signal),
      schedule: (window, signal) => request(`study/review-schedule?${windowQuery(window)}`, parseSchedule, signal),
      prepare: (input, signal) => request('study:prepare', parsePreparation, signal, input),
      grade: (input, signal) => request('study:grade', parseGrade, signal, input),
      review: ({ results, key }, signal) => request('study:submitResults', parseReviewBatch, signal, { results }, 'POST', false, { 'Idempotency-Key': key }),
    },
    library: {
      discovery: (options, signal) => {
        const query = new URLSearchParams({ limit: String(options.limit ?? 12) })
        if (options.q?.trim()) query.set('q', options.q.trim())
        if (options.type) query.set('type', options.type)
        if (options.ownerId) query.set('owner_id', options.ownerId)
        if (options.cursor) query.set('cursor', options.cursor)
        return libraryPage(`discovery/nodes?${query}`, signal, true)
      },
      sources: (id, senseId, cursor, signal) => request(`nodes/${encodeURIComponent(id)}/senses/${senseId}/sources?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, parseSources, signal),
      createReference: (parentId, targetId, name, signal, confirmPublication = false) => request('nodes', nodeId, signal, { type: 'REFERENCE', name, parent_id: parentId, reference_id: targetId, confirm_publication: confirmPublication }),
      list: (parentId, signal) => libraryPage(`nodes?parent_id=${encodeURIComponent(parentId)}&include=summary&limit=4`, signal),
      publicContents: (parentId, cursor, signal) => libraryPage(`nodes?parent_id=${encodeURIComponent(parentId)}&limit=12${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, signal, true),
      publicNode: async (nodeId, signal) => {
        const node = await request(`nodes/${encodeURIComponent(nodeId)}`, parseNodeDetails, signal, undefined, undefined, true)
        if (node.type !== 'REFERENCE' || !node.reference_id || node.reference_available === false) return node
        const target = await request(`nodes/${encodeURIComponent(node.reference_id)}`, parseNodeDetails, signal, undefined, undefined, true)
        if (target.type === 'REFERENCE') throw new HomeApiError(502, 'invalid_response')
        return { ...node, target: { id: target.id, name: target.name, type: target.type, owner_id: target.owner_id, space: target.space } }
      },
      publicMeanings: (nodeId, cursor, signal) => request(`nodes/${encodeURIComponent(nodeId)}/senses?limit=12&sort=LEMMA_ASC&state=ALL&include=examples${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, parseMeaningPage, signal, undefined, undefined, true),
      details: async (id, signal) => {
        const node = await request(`nodes/${encodeURIComponent(id)}`, parseNodeDetails, signal)
        if (node.type === 'REFERENCE' && node.reference_available === false) return node
        const summary = await request(`study/progress?node_id=${encodeURIComponent(id)}`, parseSummary, signal)
        if (node.type === 'REFERENCE' && node.reference_id) {
          const target = await request(`nodes/${encodeURIComponent(node.reference_id)}`, parseNodeDetails, signal)
          if (target.type === 'REFERENCE') throw new Error('A reference must point to a deck or folder.')
          return { ...node, summary, target: { id: target.id, name: target.name, type: target.type, owner_id: target.owner_id, space: target.space } }
        }
        return { ...node, summary }
      },
      contents: (id, options, signal, publicRead = false) => {
        const query = new URLSearchParams({ limit: String(options.limit ?? 12) })
        if (!publicRead) query.set('include', 'summary')
        if (options.cursor) query.set('cursor', options.cursor)
        if (options.q?.trim()) { query.set('q', options.q.trim()); return libraryPage(`nodes/${encodeURIComponent(id)}:search?${query}`, signal, publicRead) }
        query.set('parent_id', id)
        return libraryPage(`nodes?${query}`, signal, publicRead)
      },
      meanings: (id, options, signal) => {
        const query = new URLSearchParams({ limit: String(options.limit ?? 12), include: 'examples,sources', state: options.state ?? 'ALL', sort: options.sort ?? 'LEMMA_ASC' })
        if (options.q?.trim()) query.set('q', options.q.trim())
        if (options.cursor) query.set('cursor', options.cursor)
        return request(`nodes/${encodeURIComponent(id)}/senses?${query}`, parseMeaningPage, signal)
      },
      updateDeckSenses: (deckId, change, signal) => request(`nodes/${encodeURIComponent(deckId)}:modifySenses`, () => undefined, signal, change, 'POST'),
      createDeck: (parentId, name, senseIds, signal, confirmPublication = false) => request('nodes', nodeId, signal, { type: 'DECK', name, parent_id: parentId, sense_ids: senseIds, confirm_publication: confirmPublication }),
      createNode: (input, signal) => request('nodes', nodeId, signal, { type: input.type, name: input.name, description: input.description, parent_id: input.parentId, confirm_publication: input.confirmPublication ?? false, ...(input.type === 'DECK' ? { sense_ids: [] } : {}) }),
      updateNode: (id, change, signal) => request(`nodes/${encodeURIComponent(id)}`, () => undefined, signal, change, 'PATCH'),
      moveNode: (id, parentId, signal, publication) => request(`nodes/${encodeURIComponent(id)}:move`, () => undefined, signal, { parent_id: parentId, confirm_publication: publication?.confirm ?? false, retain_personal_reference: publication?.retainReference ?? false }),
      copyNode: (id, parentId, signal, confirmPublication = false) => request(`nodes/${encodeURIComponent(id)}:copy`, nodeId, signal, { parent_id: parentId, confirm_publication: confirmPublication }),
      deleteNode: (id, signal) => request(`nodes/${encodeURIComponent(id)}`, () => undefined, signal, undefined, 'DELETE'),
    },
    dictionary: {
      search: (query, signal) => request(`words:search?query=${encodeURIComponent(query)}&include_reference=true`, parseWordSearch, signal, undefined, undefined, true),
      word: (id, signal) => request(`words/${id}`, parseDictionaryWord, signal, undefined, undefined, true),
      previews: (ids, signal) => request('words:batchPreview', parseWordPreviews, signal, { word_ids: ids }, 'POST', true),
      context: (id, signal) => request(`me/words/${id}`, parseWordContext, signal),
      prepare: (referenceId, target, signal) => request('words:generate', parseWordGeneration, signal, { reference_id: referenceId, target }),
      generation: (id, signal) => request(`word-tasks/${encodeURIComponent(id)}`, parseWordGeneration, signal),
    },
  }
}
