import { shared } from './workload.js';
export { default, setup, handleSummary } from './workload.js';
export const options = {
  ...shared,
  scenarios: { spike: {
    executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s',
    preAllocatedVUs: 150, maxVUs: 300, gracefulStop: '10s',
    stages: [
      { target: 10, duration: '2m' }, { target: 100, duration: '1s' },
      { target: 100, duration: '8m' }, { target: 10, duration: '1s' },
      { target: 10, duration: '6m' },
    ],
  } },
};
