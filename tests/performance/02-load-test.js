import { shared } from './workload.js';
export { default, setup, handleSummary } from './workload.js';
export const options = {
  ...shared,
  scenarios: { load: {
    executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s',
    preAllocatedVUs: 50, maxVUs: 150, gracefulStop: '10s',
    stages: [
      { target: 10, duration: '2m' }, { target: 50, duration: '1m' },
      { target: 50, duration: '10m' }, { target: 75, duration: '1m' },
      { target: 75, duration: '5m' }, { target: 10, duration: '1m' },
      { target: 10, duration: '2m' },
    ],
  } },
};
