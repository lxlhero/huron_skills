#!/usr/bin/env python3
"""Convert a sealed verified bundle to a private environment mount. Never builds images."""
import argparse, gzip, hashlib, importlib.util, json, os, pathlib, re, shutil, subprocess, sys, tempfile
P = pathlib.Path

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return mod

def read(p): return json.loads(P(p).read_text())
def write(p, v): P(p).write_text(json.dumps(v, indent=2, ensure_ascii=False)+'\n')
def sha(p):
    h=hashlib.sha256()
    with P(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def run(args): return subprocess.check_output(args, text=True)

def audit_env(env, prefix):
    for p in env.rglob('*'):
        if p.is_symlink():
            target=os.readlink(p)
            if target.startswith(prefix+'/'):
                resolved=env/target[len(prefix)+1:]
            else: resolved=(p.parent/target).resolve()
            if not resolved.is_relative_to(env.resolve()) or not resolved.exists():
                raise ValueError('external/broken environment symlink: '+str(p.relative_to(env)))
        if p.is_file() and p.suffix=='.egg-link': raise ValueError('editable egg-link: '+p.name)
        if p.is_file() and p.name=='direct_url.json' and read(p).get('dir_info',{}).get('editable'):
            raise ValueError('editable package must be resolved in private build environment: '+str(p))
        if p.is_file() and p.suffix=='.pth':
            # Reviewed namespace initializer: resolves only this env's sitedir/sphinxcontrib.
            if sha(p) in {'6ef09bbd30e129409336dac26eee8755ef13b180b81b8fa14645de1dd109eade', 'b8e1b828090bfec4b25656d04cd0948d3e70221ea8281ac0e12569eef48ae2a6', '2638ce9e2500e572a5e0de7faed6661eb569d1b696fcba07b0dd223da5f5d224'}:
                continue
            for line in p.read_text(errors='replace').splitlines():
                if line.strip().startswith('/') or '__editable__' in line or (line.strip().startswith(('import ', 'import\t')) ):
                    raise ValueError('review/remove external or executable .pth in private env first: '+str(p))


def normalize_private_links(env, prefix):
    root=env.resolve(); rewrites=[]
    # Convert only links to this environment's stable container prefix.
    for p in env.rglob('*'):
        if p.is_symlink():
            target=os.readlink(p)
            if target.startswith(prefix+'/'):
                translated=env/target[len(prefix)+1:]
                replacement=os.path.relpath(translated,p.parent)
                rewrites.append({'path':str(p.relative_to(env)),'original_target':target,'target':replacement})
                p.unlink();p.symlink_to(replacement)
    for p in env.rglob('*'):
        if p.is_symlink():
            try:p.resolve(strict=True).relative_to(root)
            except (ValueError,OSError,RuntimeError) as exc:raise ValueError('external/broken private env symlink: '+str(p)) from exc
    return rewrites

def audit_relative_pth(env):
    root=env.resolve()
    for p in env.rglob('*.pth'):
        for line in p.read_text(errors='strict').splitlines():
            text=line.strip()
            if not text or text.startswith('#') or text.startswith('import '):continue
            target=(p.parent/text).resolve()
            try:target.relative_to(root)
            except ValueError as exc:raise ValueError('external relative .pth: '+str(p)) from exc

def main():
    a=argparse.ArgumentParser(description=__doc__)
    for x in ['bundle','verification','conda-root','base-image-archive','output','generator','validator','env-relative']:a.add_argument('--'+x,required=True)
    a.add_argument('--base-image-id', default='sha256:ff79591fe576640163af45e25898e0e545f2ddd2f36e9933554cc347ca44faf8')
    a.add_argument('--container-conda-root',default='/data/lwj/test/swe/python_conda_batch')
    a.add_argument('--expected-source-seal',required=True,help='SHA256 of bundle_manifest.json bound by coordinator to strict verification')
    args=a.parse_args(); source=P(args.bundle).resolve(); dest=P(args.output).resolve()
    if dest.exists() or dest.is_relative_to(source):raise ValueError('output must be new and outside input')
    gen=load(args.generator,'pack_generator'); val=load(args.validator,'pack_validator')
    task=read(source/'task.json'); iid=read(source/'bundle_manifest.json')['instance_id']
    if dest.name!=iid:raise ValueError('output basename must equal instance_id')
    if sha(source/'bundle_manifest.json')!=args.expected_source_seal:raise ValueError('source seal mismatch')
    proof=read(args.verification)
    if proof.get('task_id')!=iid or proof.get('mode')!='redgreen' or proof.get('ok') is not True or not val.strict_testonly_red(proof.get('testonly',{})) or not val.strict_gold_ok(proof.get('gold',{})):
        raise ValueError('strict redgreen proof required')
    command=task['strict_eval_command_sha256']
    for mode in ['testonly','gold']:
        if proof[mode].get('observed_test_command_sha256') != command:
            # Current validators use test_command_sha256 for the observed marker.
            if proof[mode].get('test_command_sha256') != command:raise ValueError('proof command hash mismatch')
    if not val.quality_gate_result(source,task)['ok']:raise ValueError('quality gate failed')
    val.validate_existing_command_proof(source,command)
    if val.verify_repo_identity(source,task,None)['status']!='passed':raise ValueError('embedded identity/seal failed')
    rel=P(args.env_relative)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe env-relative')
    env=(P(args.conda_root)/rel).resolve(); prefix=str(P(args.container_conda_root)/rel)
    if not re.fullmatch(r'/[A-Za-z0-9_./+-]+',prefix):raise ValueError('unsafe prefix')
    required_id='sha256:ff79591fe576640163af45e25898e0e545f2ddd2f36e9933554cc347ca44faf8'
    if args.base_image_id != required_id:raise ValueError('only user-required base image is allowed')
    if args.container_conda_root != '/data/lwj/test/swe/python_conda_batch':raise ValueError('unexpected container conda root')
    if len(rel.parts)!=2 or rel.parts[0]!='envs':raise ValueError('env-relative must be envs/name')
    base_archive=P(args.base_image_archive)
    if base_archive.is_symlink() or not base_archive.is_file():raise ValueError('base archive must be a regular file')
    import tarfile
    with tarfile.open(base_archive,'r:*') as saved:
        names=[m.name for m in saved.getmembers()]
        if len(names)!=len(set(names)):raise ValueError('duplicate archive members')
        m=saved.getmember('manifest.json')
        if not m.isfile() or m.size>1024*1024:raise ValueError('invalid image manifest')
        images=json.load(saved.extractfile(m))
        if len(images)!=1:raise ValueError('expected one base image')
        config=saved.getmember(images[0]['Config'])
        if not config.isfile() or config.size>16*1024*1024:raise ValueError('invalid config')
        data=saved.extractfile(config).read()
        if 'sha256:'+hashlib.sha256(data).hexdigest()!=required_id:raise ValueError('base archive image ID mismatch')
        base=json.loads(data)
        if base.get('os')!='linux' or base.get('architecture')!='amd64':raise ValueError('requires Linux amd64')
    image_id=required_id
    shutil.copytree(source,dest,symlinks=True,ignore=lambda directory,names: ['validation'] if P(directory).resolve()==source and 'validation' in names else [])
    runtime=dest/'runtime';runtime.mkdir(exist_ok=True)
    private_env=runtime/'conda'/rel
    private_env.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(env,private_env,symlinks=True)
    removals=[]
    if True:
        # Only the task's own mypy editable hook may be removed. Its code is /work/testbed.
        if task.get('repo') == 'python/mypy' or read(source/'runtime_manifest.json').get('repository') == 'python/mypy':
            import ast
            for finder in private_env.rglob('__editable___mypy_*_finder.py'):
                tree=ast.parse(finder.read_text()); mapping=None
                for node in tree.body:
                    if isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) and node.target.id=='MAPPING':mapping=ast.literal_eval(node.value)
                if mapping != {'mypy':'/repo/mypy','mypyc':'/repo/mypyc'}:raise ValueError('unreviewed mypy editable mapping')
                pths=list(finder.parent.glob('__editable__.mypy-*.pth'))
                for hook in pths:
                    if hook.read_text().strip() != 'import '+finder.stem+'; '+finder.stem+'.install()':raise ValueError('unreviewed editable hook')
                    removals.append({'path':str(hook.relative_to(private_env)),'sha256':sha(hook)});hook.unlink()
                removals.append({'path':str(finder.relative_to(private_env)),'sha256':sha(finder)});finder.unlink()
            for metadata in private_env.rglob('mypy-*.dist-info/direct_url.json'):
                if read(metadata) != {'dir_info':{'editable':True},'url':'file:///repo'}:raise ValueError('unreviewed mypy editable metadata')
                removals.append({'path':str(metadata.relative_to(private_env)),'sha256':sha(metadata)});metadata.unlink()
        link_rewrites=normalize_private_links(private_env,prefix)
        audit_env(private_env,prefix)
        audit_relative_pth(private_env)
    archive=runtime/'image.tar.gz'
    if archive.exists():raise ValueError('output archive already exists')
    try:os.link(base_archive,archive)
    except OSError:shutil.copyfile(base_archive,archive)
    rm=read(dest/'runtime_manifest.json')
    rm['selfcontained_image']={'schema':'openswe-selfcontained-image-v1','archive':'runtime/image.tar.gz','archive_sha256':sha(archive),'image_id':image_id,'environment_prefix':prefix,'os':'linux','architecture':'amd64','base_image_id':required_id,'archive_bytes':archive.stat().st_size}
    rm['candidate_status']='pending_validation';rm['image']=image_id
    rm['image_tag']='swe-python-conda-runner:base-multilang-20260909'
    rm['project_editable_hooks_removed']=removals
    rm['environment_link_rewrites']=link_rewrites
    rm['validation']={'quality_gate':'pending_gate','strict_mounted_redgreen':'pending_gate'}
    rm.pop('external_cache_identity',None)
    rm['environment']['copied_into_bundle']=True;rm['environment']['delivery']='bundle_local_mount'
    rm['bundle_conda_root']='runtime/conda'
    write(dest/'runtime_manifest.json',rm)
    kit_files={'verify_mounted.py':sha(args.validator)}
    helper=P(args.validator).parent/'source_origin_helper.py'
    if helper.is_file():kit_files[helper.name]=sha(helper)
    if rm.get('repository')=='python/mypy' and helper.name not in kit_files:raise ValueError('missing source-origin kit helper')
    write(runtime/'conversion.json',{'schema':'openswe-image-conversion-v1','source_bundle_manifest_sha256':args.expected_source_seal,'source_verification_sha256':sha(args.verification),'generator_sha256':sha(args.generator),'converter_sha256':sha(__file__),'validator_sha256':sha(args.validator),'validation_kit_files':kit_files,'status':'candidate_pending_bundle_local_redgreen','accepted':False,'harvest_eligible':False})
    (dest/'validate_redgreen.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
BUNDLE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${OPENSWE_VALIDATION_KIT:?Set path to shared kit containing verify_mounted.py}"
python3 - "$BUNDLE/runtime/conversion.json" "$OPENSWE_VALIDATION_KIT" <<'PYKIT'
import hashlib, json, pathlib, sys
conversion = json.loads(pathlib.Path(sys.argv[1]).read_text())
kit = pathlib.Path(sys.argv[2])
for name, digest in conversion['validation_kit_files'].items():
    if pathlib.Path(name).name != name:
        raise SystemExit('invalid kit filename')
    if hashlib.sha256((kit / name).read_bytes()).hexdigest() != digest:
        raise SystemExit('shared kit checksum mismatch: ' + name)
PYKIT
exec python3 "$OPENSWE_VALIDATION_KIT/verify_mounted.py" one --bundle-root "$(dirname -- "$BUNDLE")" --task-id "$(basename -- "$BUNDLE")" --mode redgreen --require-bundle-local-env --no-regenerate-scripts --network none "$@"
''');(dest/'validate_redgreen.sh').chmod(0o755)
    provenance=dest/'repair_provenance.json'
    if provenance.exists():
        p=read(provenance);p['candidate_status']='pending_validation'
        if 'self_package' in p:
            p['self_package'].update(runtime_manifest_sha256=sha(dest/'runtime_manifest.json'),validate_redgreen_sha256=sha(dest/'validate_redgreen.sh'),status='pending_validation',strict_redgreen_proof='pending_gate')
        write(provenance,p)
    for document in ['task.json','metadata.json']:
        q=read(dest/document);q.update(candidate_status='pending_validation',accepted=False,harvest_eligible=False)
        for key in ['image','image_name','base_image','mounted_base_image','docker_image','runtime_image']:
            if key in q:q[key]='swe-python-conda-runner:base-multilang-20260909'
        q['mounted_base_image']='swe-python-conda-runner:base-multilang-20260909'
        write(dest/document,q)
    (dest/'README.md').write_text('# '+iid+'\n\nBase image: `swe-python-conda-runner:base-multilang-20260909`.\n\nThe Python environment is in `runtime/conda/'+str(rel)+'` and is mounted read-only; it is not baked into the base image. The complete base image archive is `runtime/image.tar.gz`. Source, patches, data, and the environment are local to this folder.\n\nSet `OPENSWE_VALIDATION_KIT` to the shared directory containing the hash-bound `verify_mounted.py` and `source_origin_helper.py`, then run `bash ./validate_redgreen.sh`. Set external `--results-dir` and `--run-root` paths for disposable execution output. The runtime verifies the archive and embedded Git identity, uses no network, and never searches a shared conda cache.\n')
    entries=gen._selfpack_delivery_entries(dest)
    m=read(dest/'bundle_manifest.json');m.update(files=entries,candidate_status='pending_validation',quality_proof='pending_gate',strict_redgreen_proof='pending_gate',seal_kind='candidate_payload',delivery_seal='not_created_by_generator',candidate_payload_sha256=hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    write(dest/'bundle_manifest.json',m);(dest/'bundle_manifest.sha256').write_text(sha(dest/'bundle_manifest.json')+'  bundle_manifest.json\n')
    val.validate_existing_command_proof(dest,command)
    identity=val.verify_repo_identity(dest,task,None)
    if identity['status']!='passed':raise ValueError('converted embedded identity/seal rejected: '+json.dumps(identity))
    print(json.dumps({'bundle':str(dest),'image_id':image_id,'status':'candidate_pending_bundle_local_redgreen'}))

if __name__=='__main__':main()
