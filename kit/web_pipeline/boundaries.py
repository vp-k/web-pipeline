"""Language-neutral boundary policy and source-bound dependency graph evidence."""
from __future__ import annotations

import fnmatch
import json

from .common import (PipelineError, atomic_json, canonical_hash, hash_file, safe_path,
                     source_files, validate_schema)

INPUT = 'artifacts/boundary-input.json'
GRAPH = 'artifacts/boundary-graph.json'
PROFILES = {'Policy', 'Baseline', 'Fast', 'Full', 'Release'}
RUNTIMES = {'browser': {'browser', 'shared'}, 'server': {'server', 'shared'}, 'shared': {'shared'}}


def matches(path, patterns):
    # Same case-sensitive, slash-spanning fnmatch semantics as risk.path_rules.
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owner(model, path):
    found = [c for c in model['components'] if matches(path, c['paths'])]
    if len(found) != 1:
        raise PipelineError(f'Boundary source needs exactly one component: {path}')
    return found[0]


def validate_config(root, config, kit=False):
    model = config.get('boundaries')
    if model is None:
        return
    validate_schema(root, 'boundaries', model)
    components = {c['id']: c for c in model['components']}
    if len(components) != len(model['components']):
        raise PipelineError('Duplicate boundary component ID')
    patterns = list(model['source_patterns'])
    for component in components.values():
        patterns += component['paths']
        for target in component['depends_on']:
            if target not in components or target == component['id']:
                raise PipelineError('Boundary dependencies must name other declared components')
            if components[target]['runtime'] not in RUNTIMES[component['runtime']]:
                raise PipelineError('Boundary dependency permission violates runtime separation')
    contracts = model['contracts']
    if len({c['id'] for c in contracts}) != len(contracts):
        raise PipelineError('Duplicate boundary contract ID')
    checks = {model['dependency_check']: PROFILES}
    for contract in contracts:
        patterns += contract['paths']
        parties = [contract['provider'], *contract['consumers']]
        if len(set(parties)) != len(parties) or not set(parties) <= set(components):
            raise PipelineError('Contract provider/consumers must name distinct components')
        if components[contract['provider']]['runtime'] != 'server':
            raise PipelineError('API contract provider must be a server component')
        for check in contract['checks'].values():
            if check == model['dependency_check']:
                raise PipelineError('Import graph evidence is not an API contract or integration test')
            checks.setdefault(check, set()).update({'Full', 'Release'})
    for pattern in patterns:
        safe_path(root, pattern)
        if pattern != pattern.replace('\\', '/') or pattern.startswith('./') or not pattern.strip():
            raise PipelineError('Boundary patterns must use canonical repository-relative paths')
    definitions = {c['id']: c for c in config['verification']['commands']}
    for check, profiles in checks.items():
        command = definitions.get(check)
        if not command or not profiles <= set(command['profiles']) or (not kit and not command['enabled']):
            raise PipelineError(f'Required boundary/contract command unavailable: {check}')
    if definitions[model['dependency_check']]['cwd'] != '.':
        raise PipelineError('Boundary dependency adapter must execute at project root')


def inventory(root, config):
    model = config['boundaries']
    patterns = model['source_patterns'] + [p for c in model['components'] for p in c['paths']]
    files = {rel: hash_file(path) for rel, path in source_files(root, config) if matches(rel, patterns)}
    if not files:
        raise PipelineError('Boundary source inventory is empty; configure actual source paths')
    owners = {rel: owner(model, rel)['id'] for rel in files}
    if set(owners.values()) != {c['id'] for c in model['components']}:
        raise PipelineError('Declared boundary component has no source files')
    for contract in model['contracts']:
        if not any(matches(rel, contract['paths']) for rel in files):
            raise PipelineError(f'Contract source is absent from boundary inventory: {contract["id"]}')
    return files


def prepare_input(root, config, run_dir, snapshot):
    data = {'schema_version': '1.0', 'files': inventory(root, config),
            'model_digest': canonical_hash(config['boundaries']), 'tree_digest': snapshot['tree_digest']}
    atomic_json(safe_path(run_dir, INPUT), data)
    return data


def validate_graph(root, config, run_dir, snapshot, require_current=True):
    model = config['boundaries']
    try:
        request = json.loads(safe_path(run_dir, INPUT, True).read_text(encoding='utf-8-sig'))
        graph = json.loads(safe_path(run_dir, GRAPH, True).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise PipelineError(f'Invalid boundary JSON evidence: {exc}') from exc
    validate_schema(root, 'boundary-graph', graph)
    if not isinstance(request, dict) or request.get('schema_version') != '1.0':
        raise PipelineError('Invalid boundary input inventory')
    if request.get('model_digest') != canonical_hash(model) or request.get('tree_digest') != snapshot['tree_digest']:
        raise PipelineError('Boundary input does not bind the model/source snapshot')
    if graph['files'] != request.get('files'):
        raise PipelineError('Boundary adapter coverage/hashes do not match the complete input inventory')
    if require_current and request['files'] != inventory(root, config):
        raise PipelineError('Boundary source inventory is stale')
    if graph['unresolved']:
        raise PipelineError('Boundary adapter has unresolved analysis: ' + '; '.join(graph['unresolved']))
    owners = {rel: owner(model, rel) for rel in graph['files']}
    violations = []
    for edge in graph['edges']:
        if edge['from'] not in owners:
            raise PipelineError('Boundary edge source is outside the analyzed inventory')
        source = owners[edge['from']]
        if 'to' in edge:
            if edge['to'] not in owners:
                raise PipelineError(f'Boundary edge target is unclassified/unscanned: {edge["to"]}')
            target = owners[edge['to']]
            if (target['runtime'] not in RUNTIMES[source['runtime']] or
                (target['id'] != source['id'] and target['id'] not in source['depends_on'])):
                violations.append(f'{edge["from"]} -> {edge["to"]}: forbidden component dependency')
        elif source['runtime'] != 'server':
            package = edge['external']
            if package.startswith('node:') or matches(package, model['server_only_packages']):
                violations.append(f'{edge["from"]} -> {package}: server-only dependency')
    return violations


def required_checks(config, profile):
    model = config.get('boundaries')
    if model is None:
        return set()
    wanted = {model['dependency_check']}
    if profile in {'Full', 'Release'}:
        for contract in model['contracts']:
            wanted.update(contract['checks'].values())
    return wanted


def affected_components(config, paths, seeds=()):
    """One impact closure for classification and verification selection."""
    model = config.get('boundaries')
    scoped = config.get('verification', {}).get('scopes', {})
    components = list(scoped.get('components', []))
    affected = set(seeds)
    for component in components:
        if any(matches(path, component['paths']) for path in paths):
            affected.add(component['id'])
    if model:
        components += model['components']
        patterns = model.get('source_patterns', []) + [p for c in model['components'] for p in c['paths']]
        affected.update(owner(model, path)['id'] for path in paths if matches(path, patterns))
        for contract in model['contracts']:
            if any(matches(path, contract['paths']) for path in paths):
                affected.update([contract['provider'], *contract['consumers']])
    while True:
        expanded = affected | {c['id'] for c in components if set(c['depends_on']) & affected}
        if expanded == affected:
            return affected
        affected = expanded


def classify_paths(config, paths):
    model = config.get('boundaries')
    if model is None:
        return set()
    domains = set()
    mapping = {'browser': {'frontend'}, 'server': {'backend'}, 'shared': set()}
    components = {c['id']: c for c in model['components']}
    affected = affected_components(config, paths)
    for contract in model['contracts']:
        if any(matches(p, contract['paths']) for p in paths):
            domains.add('api')
    for component in affected:
        if component in components:
            domains.update(mapping[components[component]['runtime']])
    return domains
