import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import { requestSpec, validBody, validateFixture } from './contract.js';

const base = (__ENV.API_BASE_URL || '').replace(/\/$/, '');
const cohort = __ENV.COHORT || 'db-read';
const fixture = new SharedArray('private fixture', () => [
  validateFixture(JSON.parse(open(__ENV.FIXTURE_FILE)), Number(__ENV.MINIMUM_EXPIRY)),
])[0];
if (!/^https:\/\//.test(base) || !['db-read', 'search', 'app-read', 'mixed'].includes(cohort) ||
    !['edge', 'origin'].includes(__ENV.TEST_PATH) || !__ENV.VERSION || !__ENV.RUN_ID) {
  throw new Error('Validated HTTPS target, cohort and release/run metadata are required');
}

export const shared = {
  tags: { env: 'vps-docker', version: __ENV.VERSION, run_id: __ENV.RUN_ID,
    dataset: fixture.dataset_hash, workload: cohort, path: __ENV.TEST_PATH },
  // Raw URLs and error messages can contain private IDs; keep bounded route names only.
  systemTags: ['status', 'method', 'name', 'scenario', 'expected_response', 'error_code'],
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  setupTimeout: '2m',
  thresholds: {
    'http_req_failed{phase:business}': [
      'rate<0.01', { threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '30s' },
    ],
    'http_req_duration{phase:business}': ['p(95)<300', 'p(99)<800'],
    ...Object.fromEntries([...new Set(Array.from({ length: 30 }, (_, i) =>
      requestSpec(i, 0, fixture, cohort).name))].map(name =>
      [`http_req_duration{phase:business,name:${name}}`, ['p(95)<300', 'p(99)<800']])),
    'checks{phase:business}': ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
  ...(__ENV.ORIGIN_IP ? { hosts: { [base.match(/^https:\/\/([^/]+)/)[1]]: __ENV.ORIGIN_IP } } : {}),
};

function read(spec, phase) {
  const response = http.get(base + spec.path, {
    timeout: '5s', redirects: 0,
    headers: spec.user ? { Authorization: `Bearer ${spec.user.token}` } : {},
    tags: { name: spec.name, phase },
  });
  if (response.status !== 200) {
    console.error(JSON.stringify({ route: spec.name, status: response.status,
      error_code: response.error_code, server: response.headers.Server,
      cf_ray: response.headers['Cf-Ray'], request_id: response.headers['X-Request-Id'] }));
  }
  let body;
  try { body = response.json(); } catch { body = null; }
  const valid = check(response, {
    'business HTTP 200': r => r.status === 200,
    'expected business data': () => validBody(spec, body),
  }, { phase });
  if (phase === 'preflight' && !valid) {
    exec.test.abort(`Fixture/contract check failed at ${spec.name}, status=${response.status}`);
  }
  if ([401, 403].includes(response.status)) {
    exec.test.abort(`Authentication or edge policy rejected ${spec.name}; not a capacity result`);
  }
  return body;
}

export function setup() {
  for (const user of fixture.users) {
    read({ path: '/v1/me', name: '/v1/me', kind: 'me', user }, 'preflight');
    const node = http.get(`${base}/v1/nodes/${user.node_id}`, {
      headers: { Authorization: `Bearer ${user.token}` }, timeout: '5s', redirects: 0,
      tags: { name: '/v1/nodes/:id', phase: 'preflight' },
    });
    let body;
    try { body = node.json(); } catch { body = null; }
    if (node.status !== 200 || body?.owner_id !== user.account_id) {
      exec.test.abort('Fixture scope is not owned by the test identity');
    }
    read({ path: `/v1/study/progress?node_id=${user.node_id}`,
      name: '/v1/study/progress', kind: 'progress', user }, 'preflight');
  }
  for (const id of fixture.word_ids) {
    read({ path: `/v1/words/${id}`, name: '/v1/words/:id', kind: 'word', id }, 'preflight');
  }
  for (let i = 0; i < fixture.search_queries.length; i++) {
    read(requestSpec(i, 0, fixture, 'search'), 'preflight');
  }
  if (['app-read', 'mixed'].includes(cohort)) {
    for (let user = 0; user < fixture.users.length; user++) {
      for (let slot = 0; slot < (cohort === 'mixed' ? 30 : 10); slot++) {
        read(requestSpec(slot, user, fixture, cohort), 'preflight');
      }
    }
  }
}

export default function businessRead() {
  if (fixture.users.some(user => Date.parse(user.expires_at) < Date.now() + 60000)) {
    exec.test.abort('Token approaching expiry; stop before authentication changes the workload');
  }
  read(requestSpec(exec.scenario.iterationInTest, exec.vu.idInTest - 1, fixture, cohort), 'business');
}

export function handleSummary(data) {
  const metrics = Object.fromEntries(Object.entries(data.metrics)
    .filter(([name]) => name.includes('phase:business') || ['iterations', 'dropped_iterations'].includes(name)));
  return {
    '/output/summary.json': JSON.stringify(data, null, 2),
    stdout: JSON.stringify(metrics, null, 2) + '\n',
  };
}
