"""Cold image source-origin proof. Call only after bundle seal and image-ID checks."""
from __future__ import annotations
import json
import re
import subprocess
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Any

MODULES = ('mypy', 'mypy.main', 'mypyc')
MARKER = 'OPENSWE_SOURCE_ORIGIN_JSON='
PROBE = '''import importlib, json
from pathlib import Path
root = Path('/work/testbed').resolve()
origins = {}
for name in ('mypy', 'mypy.main', 'mypyc'):
    module = importlib.import_module(name)
    source = getattr(module, '__file__', None)
    if not source:
        raise RuntimeError('OPENSWE_INFRA_FAILURE: missing module origin: ' + name)
    path = Path(source).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise RuntimeError('OPENSWE_INFRA_FAILURE: wrong module origin: ' + name + ': ' + str(path))
    if not path.is_file():
        raise RuntimeError('OPENSWE_INFRA_FAILURE: nonexistent module origin: ' + name)
    origins[name] = str(path)
print('OPENSWE_SOURCE_ORIGIN_JSON=' + json.dumps(origins, sort_keys=True))
'''


def prove_mypy_source_origin(bundle_dir: Path, image_id: str, environment_prefix: str,
                             timeout_seconds: int = 120, conda_root: Path | None = None) -> dict[str, Any]:
    """Copy sealed repo via stdin; no host volumes, external conda or network.

    This pre-patch environment proof never counts as a behavior test/attempt.
    Failures return structured infrastructure evidence rather than raising.
    """
    result: dict[str, Any] = {
        'schema': 'openswe-source-origin-proof-v1', 'status': 'failed',
        'failure_class': 'infrastructure', 'counts_as_swe_attempt': False,
        'counts_as_behavior_failure': False, 'test_executed': False,
        'image_id': image_id, 'modules': list(MODULES),
        'external_mounts_used': False, 'network': 'none',
    }
    name = 'openswe-origin-' + uuid.uuid4().hex
    launched = False
    try:
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
            raise ValueError('source proof requires an immutable image ID')
        prefix = Path(environment_prefix)
        if (not prefix.is_absolute() or '..' in prefix.parts or
                not re.fullmatch(r'/[A-Za-z0-9_./+-]+', environment_prefix)):
            raise ValueError('invalid environment prefix')
        repo = Path(bundle_dir) / 'repo'
        if repo.is_symlink() or not repo.is_dir():
            raise ValueError('missing regular embedded repo directory')
        # Caller has verified the recursive seal; reject external links anyway.
        resolved = repo.resolve()
        for entry in repo.rglob('*'):
            if entry.is_symlink():
                entry.resolve(strict=True).relative_to(resolved)
        shell = ('set -eu\nmkdir -p /work/testbed\n'
                 'tar -xf - -C /work/testbed\ncd /work/testbed\n'
                 'export PYTHONPATH="/work/testbed/src:/work/testbed/Lib:/work/testbed:${PYTHONPATH:-}"\n'
                 'exec "$OPENSWE_ORIGIN_PY" -c "$OPENSWE_ORIGIN_PROBE"\n')
        command = ['docker', 'run', '--rm', '-i', '--pull', 'never', '--network', 'none',
                   '--name', name, '-e', 'PYTHONNOUSERSITE=1',
                   '-e', 'OPENSWE_ORIGIN_PY=' + environment_prefix.rstrip('/') + '/bin/python',
                   '-e', 'OPENSWE_ORIGIN_PROBE=' + PROBE,
                   '--entrypoint', 'bash', image_id, '-c', shell]
        if conda_root is not None:
            conda_root.resolve().relative_to(bundle_dir.resolve())
            command[2:2] = ['-v', str(conda_root.resolve()) + ':/data/lwj/test/swe/python_conda_batch:ro']
            result['bundle_local_environment_mounted'] = True
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode='w') as tar:
                tar.add(repo, arcname='.', recursive=True)
            archive.seek(0)
            launched = True
            completed = subprocess.run(command, stdin=archive, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True,
                                       timeout=timeout_seconds, check=False)
        result['returncode'] = completed.returncode
        result['stdout_tail'] = completed.stdout[-8000:]
        if completed.returncode:
            raise ValueError('cold source-origin subprocess failed')
        lines = [line[len(MARKER):] for line in completed.stdout.splitlines() if line.startswith(MARKER)]
        if len(lines) != 1:
            raise ValueError('missing or ambiguous source-origin marker')
        origins = json.loads(lines[0])
        if not isinstance(origins, dict) or set(origins) != set(MODULES):
            raise ValueError('source-origin module set mismatch')
        for path in origins.values():
            if not isinstance(path, str) or '..' in Path(path).parts:
                raise ValueError('invalid source-origin path')
            Path(path).relative_to('/work/testbed')
        result.update(status='passed', failure_class='none', origins=origins)
    except Exception as exc:
        result['error'] = str(exc)
        result['timeout'] = isinstance(exc, subprocess.TimeoutExpired)
    finally:
        if launched:
            try:
                subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30, check=False)
            except Exception as exc:
                result.update(status='failed', failure_class='infrastructure',
                              cleanup_error=str(exc))
    return result
