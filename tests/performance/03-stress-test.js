import { shared } from './workload.js';
export { default, setup, handleSummary } from './workload.js';
export const options = {
  ...shared,
  scenarios: { stress: {
    executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s',
    preAllocatedVUs: 100, maxVUs: 300, gracefulStop: '10s',
    stages: [25, 50, 75, 100, 150].flatMap(target => [
      { target, duration: '30s' }, { target, duration: '5m' },
    ]).concat([{ target: 10, duration: '30s' }, { target: 10, duration: '3m' }]),
  } },
};
