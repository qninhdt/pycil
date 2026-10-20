// Pure workload contract, shared with the offline checks.
export function validateFixture(fixture, minimumExpiry) {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!/^[a-f0-9]{64}$/.test(fixture.dataset_hash) ||
      !Array.isArray(fixture.word_ids) || !fixture.word_ids.length || fixture.word_ids.length > 100 ||
      !fixture.word_ids.every(id => Number.isSafeInteger(id) && id > 0) ||
      new Set(fixture.word_ids).size !== fixture.word_ids.length ||
      !Array.isArray(fixture.users) || !fixture.users.length || fixture.users.length > 100 ||
      !fixture.users.every(user => uuid.test(user.account_id) && uuid.test(user.node_id) &&
        Number.isSafeInteger(user.total) && user.total > 0 &&
        typeof user.token === 'string' && /^[\w-]+\.[\w-]+\.[\w-]+$/.test(user.token) &&
        Number.isFinite(Date.parse(user.expires_at)) && Date.parse(user.expires_at) >= minimumExpiry) ||
      !Array.isArray(fixture.search_queries) || !fixture.search_queries.length ||
      !fixture.search_queries.every(query => typeof query === 'string' && query.length > 0 && query.length <= 100)) {
    throw new Error('Invalid fixture or token lifetime; use real owned nonempty scopes and fresh tokens');
  }
  return fixture;
}

export function requestSpec(sequence, userIndex, fixture, cohort) {
  if (cohort === 'mixed') {
    return requestSpec(Math.floor(sequence / 3), userIndex, fixture,
      ['db-read', 'search', 'app-read'][sequence % 3]);
  }
  if (cohort === 'search') {
    const query = fixture.search_queries[sequence % fixture.search_queries.length];
    return {
      path: `/v1/words:search?query=${encodeURIComponent(query)}&include_reference=true`,
      name: '/v1/words:search', kind: 'search',
    };
  }
  const user = fixture.users[userIndex % fixture.users.length];
  const slot = sequence % 10;
  if (cohort === 'app-read') {
    const routes = [
      [`/v1/nodes/${user.node_id}`, '/v1/nodes/:id', 'node'],
      [`/v1/nodes/${user.node_id}/senses?limit=50`, '/v1/nodes/:id/senses', 'senses'],
      ['/v1/nodes?include=summary', '/v1/nodes', 'nodes'],
      ['/v1/discovery/nodes?include=summary', '/v1/discovery/nodes', 'discovery'],
      [`/v1/users/${user.account_id}`, '/v1/users/:id', 'public-profile'],
      ['/v1/me/usage', '/v1/me/usage', 'usage'],
      ['/v1/study/activity', '/v1/study/activity', 'activity'],
      [`/v1/study/review-schedule?node_id=${user.node_id}`, '/v1/study/review-schedule', 'schedule'],
      ['/v1/assistant/models', '/v1/assistant/models', 'models'],
      ['/v1/assistant/conversations', '/v1/assistant/conversations', 'conversations'],
    ];
    const [path, name, kind] = routes[slot];
    return { path, name, kind, user };
  }
  if (slot < 6) {
    const id = fixture.word_ids[Math.floor(sequence / 10) % fixture.word_ids.length];
    return { path: `/v1/words/${id}`, name: '/v1/words/:id', kind: 'word', id };
  }
  return slot < 8
    ? { path: '/v1/me', name: '/v1/me', kind: 'me', user }
    : { path: `/v1/study/progress?node_id=${encodeURIComponent(user.node_id)}`,
      name: '/v1/study/progress', kind: 'progress', user };
}

export function validBody(spec, body) {
  if (!body || typeof body !== 'object') return false;
  if (spec.kind === 'word') {
    return body.id === spec.id && typeof body.lemma === 'string' &&
      body.generation_state === 'done' && Array.isArray(body.senses) && body.senses.length > 0;
  }
  if (spec.kind === 'me') return body.id === spec.user.account_id;
  if (spec.kind === 'progress') {
    return body.node_id === spec.user.node_id && body.total === spec.user.total;
  }
  if (spec.kind === 'node') return body.id === spec.user.node_id && body.owner_id === spec.user.account_id;
  if (spec.kind === 'senses') return Array.isArray(body.senses) && body.senses.length > 0 &&
    body.senses.every(sense => Number.isSafeInteger(sense.sense_id) && sense.sense_id > 0);
  if (spec.kind === 'nodes') return Array.isArray(body.nodes) && body.nodes.length > 0 &&
    body.nodes.every(node => node.owner_id === spec.user.account_id && node.summary?.node_id === node.id);
  if (spec.kind === 'discovery') return Array.isArray(body.nodes) &&
    body.nodes.every(node => node.space === 'published' && node.summary?.node_id === node.id);
  if (spec.kind === 'public-profile') return body.id === spec.user.account_id && typeof body.published_node_id === 'string';
  if (spec.kind === 'usage') return Number.isSafeInteger(body.used_units) &&
    body.remaining_units === Math.max(0, body.allowance_units - body.used_units);
  if (spec.kind === 'activity') return Array.isArray(body.days) && typeof body.timezone === 'string';
  if (spec.kind === 'schedule') return body.node_id === spec.user.node_id && Array.isArray(body.days);
  if (spec.kind === 'models') return Array.isArray(body) && body.length > 0 &&
    body.every(model => typeof model.id === 'string' && Array.isArray(model.efforts));
  if (spec.kind === 'conversations') return Array.isArray(body.conversations) &&
    body.conversations.every(conversation => typeof conversation.id === 'string');
  return Array.isArray(body.items) && body.items.length > 0 &&
    body.items.every(item => ['word', 'reference'].includes(item.kind));
}
