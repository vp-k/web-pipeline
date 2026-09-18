const path = require('node:path');
const evidence = process.env.PIPELINE_EVIDENCE_DIR;
if (!evidence) throw new Error('Run using the pipeline or example orchestrator');
module.exports = {
  testDir: './tests', testMatch: '*.spec.cjs', workers:1, retries:0, timeout:30000,
  outputDir:path.join(evidence, 'artifacts/playwright'),
  reporter:[['list'], [path.join(__dirname, 'reporter.cjs')]],
  use:{headless:true, trace:'retain-on-failure'}
};
