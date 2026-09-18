#!/usr/bin/env node
'use strict';

// Reference JS/TS dependency adapter. It never executes application source.
// Use a framework/compiler-specific adapter for SFCs, virtual modules and bridges.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire, isBuiltin } = require('node:module');

function analyze(root, input, ts, configPath) {
  const files = Object.create(null), edges = [], unresolved = [];
  let options = { allowJs: true, resolveJsonModule: true,
    module: ts.ModuleKind.NodeNext, moduleResolution: ts.ModuleResolutionKind.NodeNext };
  if (configPath) {
    const file = path.resolve(root, configPath);
    const loaded = ts.readConfigFile(file, ts.sys.readFile);
    if (loaded.error) throw new Error(ts.flattenDiagnosticMessageText(loaded.error.messageText, '\n'));
    const parsed = ts.parseJsonConfigFileContent(loaded.config, ts.sys, path.dirname(file));
    const errors = parsed.errors.filter(e => e.code !== 18003); // roots come from engine inventory
    if (errors.length) throw new Error(errors.map(e => ts.flattenDiagnosticMessageText(e.messageText, '\n')).join('; '));
    options = parsed.options;
  }
  const realRoot = fs.realpathSync(root);
  const relative = file => path.relative(realRoot, fs.realpathSync(file)).split(path.sep).join('/');
  for (const rel of Object.keys(input.files).sort()) {
    const file = path.resolve(root, rel);
    if (relative(file) !== rel) throw new Error(`Non-canonical or linked source: ${rel}`);
    const bytes = fs.readFileSync(file);
    files[rel] = crypto.createHash('sha256').update(bytes).digest('hex');
    if (files[rel] !== input.files[rel]) throw new Error(`Source changed: ${rel}`);
    if (/\.json$/i.test(rel)) { JSON.parse(bytes.toString('utf8')); continue; }
    if (!/\.(?:[cm]?[jt]s|[jt]sx)$/i.test(rel)) {
      unresolved.push(`${rel}: unsupported file type; supply a language/framework adapter`); continue;
    }
    const source = ts.createSourceFile(file, bytes.toString('utf8'), ts.ScriptTarget.Latest, true);
    for (const error of source.parseDiagnostics) {
      unresolved.push(`${rel}: ${ts.flattenDiagnosticMessageText(error.messageText, '\n')}`);
    }
    function dependency(expression) {
      if (!expression || !(ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression))) {
        unresolved.push(`${rel}: computed module specifier`); return;
      }
      const spec = expression.text;
      if (isBuiltin(spec)) {
        edges.push({ from: rel, external: `node:${spec.replace(/^node:/, '')}` }); return;
      }
      const resolved = ts.resolveModuleName(spec, file, options, ts.sys).resolvedModule;
      if (!resolved) { unresolved.push(`${rel}: unresolved import ${spec}`); return; }
      const target = relative(resolved.resolvedFileName);
      if (target.startsWith('../') || path.isAbsolute(target)) {
        unresolved.push(`${rel}: dependency escapes project: ${spec}`); return;
      }
      if (target.split('/').includes('node_modules')) {
        // Preserve both requested and actual package names: aliases must not hide
        // a configured server-only package behind an innocent-looking specifier.
        edges.push({ from: rel, external: spec });
        const parts = target.split('/');
        const i = parts.lastIndexOf('node_modules') + 1;
        const actual = parts[i].startsWith('@') ? parts.slice(i, i + 2).join('/') : parts[i];
        if (actual !== spec) edges.push({ from: rel, external: actual });
      } else {
        edges.push({ from: rel, to: target });
      }
    }
    function walk(node) {
      if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
        if (node.moduleSpecifier) dependency(node.moduleSpecifier);
      } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
        dependency(node.moduleReference.expression);
      } else if (ts.isImportTypeNode(node)) {
        dependency(ts.isLiteralTypeNode(node.argument) ? node.argument.literal : null);
      } else if (ts.isCallExpression(node)) {
        const callee = node.expression;
        const text = callee.getText(source);
        if (callee.kind === ts.SyntaxKind.ImportKeyword || ['require', 'require.resolve', 'module.require'].includes(text)) {
          dependency(node.arguments[0]);
        } else if (['eval', 'Function'].includes(text) || /(?:^|\.)createRequire$/.test(text) || /import\.meta\.(?:glob|globEager)/.test(text)) {
          unresolved.push(`${rel}: opaque loader/evaluation requires a dedicated adapter`);
        }
      } else if (ts.isElementAccessExpression(node) && ['module', 'require', 'import.meta'].includes(node.expression.getText(source))) {
        unresolved.push(`${rel}: computed loader access requires a dedicated adapter`);
      } else if (ts.isNewExpression(node) && node.expression.getText(source) === 'Function') {
        unresolved.push(`${rel}: dynamic Function evaluation is not analyzable`);
      } else if (ts.isIdentifier(node) && node.text === 'require') {
        const parent = node.parent;
        const direct = ts.isCallExpression(parent) && parent.expression === node;
        const property = ts.isPropertyAccessExpression(parent) &&
          ['require.resolve', 'module.require'].includes(parent.getText(source)) &&
          ts.isCallExpression(parent.parent) && parent.parent.expression === parent;
        const mainGuard = ts.isPropertyAccessExpression(parent) && parent.getText(source) === 'require.main';
        if (!direct && !property && !mainGuard) unresolved.push(`${rel}: aliased/opaque require`);
      }
      ts.forEachChild(node, walk);
    }
    walk(source);
  }
  return { schema_version: '1.0', files, edges, unresolved };
}

function main() {
  const root = process.cwd();
  const evidence = process.env.PIPELINE_EVIDENCE_DIR;
  if (!evidence) throw new Error('Run through the pipeline; PIPELINE_EVIDENCE_DIR is required');
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 2 || args[0] !== '--tsconfig')) throw new Error('Usage: boundary-graph.cjs [--tsconfig <path>]');
  const projectRequire = createRequire(path.join(root, 'package.json'));
  const ts = projectRequire('typescript');
  const major = Number(ts.versionMajorMinor.split('.')[0]);
  if (major < 5 || major >= 7) throw new Error('This adapter supports project TypeScript >=5 <7; use a compatible adapter');
  const input = JSON.parse(fs.readFileSync(path.join(evidence, 'artifacts/boundary-input.json'), 'utf8'));
  const graph = analyze(root, input, ts, args[1]);
  const output = path.join(evidence, 'artifacts/boundary-graph.json');
  fs.writeFileSync(output, JSON.stringify(graph, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ analyzed_files: Object.keys(graph.files).length, edges: graph.edges.length,
    unresolved: graph.unresolved }));
  return graph.unresolved.length ? 1 : 0;
}

module.exports = { analyze };
if (require.main === module) {
  try { process.exitCode = main(); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
