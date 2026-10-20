import assert from 'node:assert/strict';
import test from 'node:test';
import { requestSpec, validBody, validateFixture } from '../contract.js';

const fixture = {
  dataset_hash: 'a'.repeat(64), word_ids: [12, 23], search_queries: ['hello', 'hel'],
  users: [{ account_id: '00000000-0000-4000-8000-000000000001',
    node_id: '00000000-0000-4000-8000-000000000002', total: 4,
    token: 'header.payload.signature', expires_at: '2099-01-01T00:00:00Z' }],
};

test('one request per iteration preserves 60/20/20 and rotates words', () => {
  const kinds = Array.from({ length: 20 }, (_, i) => requestSpec(i, 0, fixture, 'db-read').kind);
  assert.equal(kinds.filter(k => k === 'word').length, 12);
  assert.equal(kinds.filter(k => k === 'me').length, 4);
  assert.equal(kinds.filter(k => k === 'progress').length, 4);
  assert.equal(requestSpec(10, 0, fixture, 'db-read').id, 23);
  assert.equal(requestSpec(20, 0, fixture, 'db-read').id, 12);
});

test('rejects expired, empty, duplicated or invented-ID fixtures before load', () => {
  assert.equal(validateFixture(fixture, Date.now()), fixture);
  for (const change of [{ word_ids: [] }, { word_ids: [-1] }, { word_ids: [12, 12] },
    { users: [] }, { dataset_hash: 'unknown' }, { search_queries: [] }]) {
    assert.throws(() => validateFixture({ ...fixture, ...change }, Date.now()));
  }
  assert.throws(() => validateFixture(fixture, Date.parse('2100-01-01')));
});

test('HTTP 200 is insufficient: reject wrong identities, scopes and incomplete words', () => {
  const me = requestSpec(6, 0, fixture, 'db-read');
  assert.equal(validBody(me, { id: fixture.users[0].account_id }), true);
  assert.equal(validBody(me, { id: 'another-user' }), false);
  const progress = requestSpec(8, 0, fixture, 'db-read');
  assert.equal(validBody(progress, { node_id: fixture.users[0].node_id, total: 4 }), true);
  assert.equal(validBody(progress, { node_id: fixture.users[0].node_id, total: 0 }), false);
  const word = requestSpec(0, 0, fixture, 'db-read');
  assert.equal(validBody(word, { id: 12, lemma: 'hello', generation_state: 'pending', senses: [] }), false);
  assert.equal(validBody(word, null), false);
});

test('only search cohort calls search and URL-encodes its input', () => {
  const spec = requestSpec(0, 0, { ...fixture, search_queries: ['hello world&x=y'] }, 'search');
  assert.equal(spec.name, '/v1/words:search');
  assert.match(spec.path, /query=hello%20world%26x%3Dy&include_reference=true$/);
  assert.equal(spec.user, undefined);
  assert.equal(validBody(spec, { items: [] }), false);
});

test('application read checks reject another owner, missing summaries and private discovery', () => {
  const spec = i => requestSpec(i, 0, fixture, 'app-read');
  assert.equal(new Set(Array.from({ length: 10 }, (_, i) => spec(i).name)).size, 10);
  const node = { id: fixture.users[0].node_id, owner_id: fixture.users[0].account_id,
    summary: { node_id: fixture.users[0].node_id } };
  assert.equal(validBody(spec(0), node), true);
  assert.equal(validBody(spec(0), { ...node, owner_id: 'another-user' }), false);
  assert.equal(validBody(spec(2), { nodes: [node] }), true);
  assert.equal(validBody(spec(2), { nodes: [{ ...node, summary: null }] }), false);
  assert.equal(validBody(spec(3), { nodes: [{ ...node, space: 'personal' }] }), false);
  assert.equal(validBody(spec(3), { nodes: [{ ...node, space: 'published' }] }), true);
  assert.equal(validBody(spec(5), { used_units: 5, remaining_units: 95, allowance_units: 100 }), true);
  assert.equal(validBody(spec(5), { used_units: 5, remaining_units: 100, allowance_units: 100 }), false);
  assert.equal(validBody(spec(5), { used_units: 105, remaining_units: 0, allowance_units: 100 }), true);
});


test('mixed workload covers every read family and rotates fixture words and queries', () => {
  const specs = Array.from({ length: 60 }, (_, i) => requestSpec(i, 0, fixture, 'mixed'));
  assert.equal(specs.filter(s => s.kind === 'search').length, 20);
  assert.equal(specs.filter(s => s.kind === 'word').length, 12);
  assert.equal(specs.filter(s => s.kind === 'me').length, 4);
  assert.equal(specs.filter(s => s.kind === 'progress').length, 4);
  assert.equal(new Set(specs.filter(s => !['search', 'word', 'me', 'progress'].includes(s.kind))
    .map(s => s.name)).size, 10);
  assert.equal(requestSpec(30, 0, fixture, 'mixed').id, 23);
  assert.match(requestSpec(4, 0, fixture, 'mixed').path, /query=hel&/);
});
