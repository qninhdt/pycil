import { shared } from './workload.js';
export { default, setup, handleSummary } from './workload.js';

const rates = [50, 100, 200, 400];
const scenarios = {};
const thresholds = { ...shared.thresholds };
for (const [index, rate] of rates.entries()) {
  const name = `rate_${rate}`;
  scenarios[name] = {
    executor: 'ramping-arrival-rate', startTime: `${index * 135}s`,
    startRate: index ? rates[index - 1] : 10, timeUnit: '1s',
    preAllocatedVUs: 150, maxVUs: 300, gracefulStop: '10s',
    stages: [{ target: rate, duration: '15s' }, { target: rate, duration: '2m' }],
  };
  // Native per-scenario thresholds stop overload after the ramp and a minute of samples.
  thresholds[`http_req_duration{phase:business,scenario:${name}}`] = ['p(95)<300', 'p(99)<800']
    .map(threshold => ({ threshold, abortOnFail: true, delayAbortEval: `${index * 135 + 75}s` }));
  thresholds[`http_req_failed{phase:business,scenario:${name}}`] = [
    { threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: `${index * 135 + 75}s` },
  ];
}
scenarios.recovery = {
  executor: 'constant-arrival-rate', startTime: '540s', duration: '75s',
  rate: 10, timeUnit: '1s', preAllocatedVUs: 20, maxVUs: 30, gracefulStop: '10s',
};
export const options = { ...shared, scenarios, thresholds };
