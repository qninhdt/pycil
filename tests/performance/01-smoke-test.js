import { shared } from './workload.js';
export { default, setup, handleSummary } from './workload.js';
export const options = {
  ...shared,
  scenarios: { smoke: {
    executor: 'constant-arrival-rate', rate: 1, timeUnit: '1s', duration: '2m',
    preAllocatedVUs: 2, maxVUs: 5, gracefulStop: '10s',
  } },
  thresholds: {
    ...shared.thresholds,
    'http_req_failed{phase:business}': ['rate==0'],
    'checks{phase:business}': ['rate==1'],
  },
};
