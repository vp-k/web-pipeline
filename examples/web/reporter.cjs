const fs = require('node:fs');
const path = require('node:path');
class Report {
  onBegin(config, suite) { this.suite = suite; this.errors = []; }
  onError(error) { this.errors.push(error.message || String(error)); }
  onEnd(result) {
    const root = process.env.PIPELINE_EVIDENCE_DIR;
    const tests = this.suite.allTests().map(test => {
      const last = test.results.at(-1);
      const status = test.results.some(r => !['passed','skipped'].includes(r.status)) ? 'failed' : !last ? 'error' : last.status === 'passed' ? 'passed' :
        last.status === 'skipped' ? 'skipped' : last.status === 'failed' ? 'failed' : 'error';
      return {id:test.id, group:(test.title.match(/^\[([^\]]+)\]/) || [,'ungrouped'])[1],
        status, duration_ms:test.results.reduce((sum, r) => sum + Math.max(0, r.duration), 0)};
    });
    const report = {schema_version:'1.0', run_id:path.basename(root),
      check_id:process.env.PIPELINE_CHECK_ID || 'web-tests',
      completed:!['timedout','interrupted'].includes(result.status), errors:this.errors, tests};
    fs.mkdirSync(path.join(root, 'artifacts'), {recursive:true});
    fs.writeFileSync(path.join(root, 'artifacts/web-tests.json'), JSON.stringify(report, null, 2), {flag:'wx'});
  }
}
module.exports = Report;
