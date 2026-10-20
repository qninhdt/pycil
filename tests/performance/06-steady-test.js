import { shared } from './workload.js';
export { default, setup, handleSummary } from './workload.js';

export const options = {
  ...shared,
  scenarios: {
    steady: {
      executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s',
      preAllocatedVUs: 150, maxVUs: 300, gracefulStop: '10s',
      stages: [{ target: 200, duration: '15s' }, { target: 200, duration: '3m' }],
    },
    recovery: {
      executor: 'constant-arrival-rate', startTime: '195s', duration: '75s',
      rate: 10, timeUnit: '1s', preAllocatedVUs: 20, maxVUs: 30, gracefulStop: '10s',
    },
  },
  thresholds: {
    ...shared.thresholds,
    'http_req_duration{phase:business,scenario:steady}': ['p(95)<300', 'p(99)<800']
      .map(threshold => ({ threshold, abortOnFail: true, delayAbortEval: '75s' })),
  },
};
