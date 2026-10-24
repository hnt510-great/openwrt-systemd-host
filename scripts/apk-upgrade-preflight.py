#!/usr/bin/env python3
"""Bind a prepared signed release to a fresh, read-only router upgrade check."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess

TREE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('apk_migrations', TREE / 'scripts/apk-migrations.py')
MIGRATIONS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MIGRATIONS)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def policy(destination):
    """The canonical production config applies even to low-level CLI callers."""
    config = json.loads((TREE / 'configs/lan-apk-feeds.json').read_text())
    if Path(config['destination']).resolve() != Path(destination).resolve():
        return None
    result = config.get('upgrade_preflight')
    if not result or not result.get('ssh_target'):
        raise ValueError('Production publication requires upgrade_preflight.ssh_target')
    return result


def require_coordinator(destination, prepared=False):
    if policy(destination) and not prepared:
        raise ValueError('Production feeds require the coordinated staged upgrade preflight; '
                         'use scripts/publish-changed-feeds.sh')


def installed_records(data):
    result = {}
    for record in data.split('\n\n'):
        info, folder, files = {}, '', []
        for line in record.splitlines():
            if len(line) < 2 or line[1] != ':':
                continue
            key, value = line[0], line[2:]
            if key == 'F':
                folder = value
            elif key == 'R':
                files.append(folder + '/' + value)
            elif key in 'PVCDo':
                info[key] = value
        if 'P' in info:
            info['files'] = files
            result[info['P']] = info
    return result


def validate_transition(baseline, packages, abi, migrations=None):
    records = installed_records(baseline['installed'])
    current = baseline['abi']
    candidates = {p['name']: p for p in packages
                  if 'kernel=' + abi in p.get('depends', [])}
    payloads = {p['name']: p for p in packages if p.get('origin') == 'kernel-generations'}
    logical = {n for n in records if n.startswith('kmod-') and '-owrt-' not in n and n != 'kmod'}
    if current != abi:
        missing = sorted(logical - candidates.keys())
        if missing:
            raise ValueError('Upgrade preflight: installed modules have no target ABI tracker: ' + ', '.join(missing))
        for name in sorted(logical):
            pins = [d.split('=', 1) for d in candidates[name].get('depends', [])
                    if d.startswith(name + '-') and '-owrt-' in d and '=' in d]
            if (len(pins) != 1 or pins[0][0] not in payloads or
                    payloads[pins[0][0]]['version'] != pins[0][1]):
                raise ValueError('Upgrade preflight: missing target generation payload: ' + name)
    migrations = migrations if migrations is not None else MIGRATIONS.rules(TREE / 'configs/apk-migrations.json')
    for old, rule in migrations.items():
        if old not in records or old not in candidates:
            continue
        for target in rule['to']:
            if target not in candidates or target not in candidates[old].get('depends', []):
                raise ValueError('Upgrade preflight: compatibility dependency missing: ' + old + ' -> ' + target)
        owners = [records[old]]
        for dep in records[old].get('D', '').split():
            name = re.split(r'[<>=~]', dep, 1)[0]
            if name.startswith(old + '-') and '-owrt-' in name and name in records:
                owners.append(records[name])
        for owner in owners:
            for name in owner['files']:
                bookkeeping = (name == 'usr/lib/apk/packages/' + old + '.list' or
                    re.fullmatch(r'usr/lib/openwrt-kernel/[^/]+/kmods/' + re.escape(old) + r'\.json', name))
                if not bookkeeping:
                    raise ValueError('Upgrade preflight: empty compatibility rule would discard a real file: ' + name)


BASELINE = r'''
import fcntl,hashlib,json,os,pathlib
def h(b): return hashlib.sha256(b).hexdigest()
root=pathlib.Path('/')
with open('/lib/apk/db/lock','rb') as lock:
 fcntl.flock(lock,fcntl.LOCK_SH)
 paths={'world':'/etc/apk/world','installed':'/lib/apk/db/installed',
        'protected':'/etc/openwrt-kernel/protected','state':'/etc/openwrt-kernel/state.json'}
 data={k:pathlib.Path(p).read_bytes() for k,p in paths.items()}
 state=json.loads(data['state']); release=os.uname().release
 abis={g['abi'] for g in state['generations'].values() if g.get('release')==release}
 if len(abis)!=1 or state.get('pending') or state.get('phase')!='ready':
  raise SystemExit('Router kernel baseline is ambiguous or has an unfinished trial')
 hashes={k:h(v) for k,v in data.items()}
 for p in [pathlib.Path('/etc/apk/repositories'),*pathlib.Path('/etc/apk/repositories.d').glob('*'),
           *pathlib.Path('/lib/apk/repositories.d').glob('*'),
           *pathlib.Path('/etc/apk/keys').glob('*')]:
  if p.is_file(): hashes[str(p)]=h(p.read_bytes())
 hashes['apk']=h(pathlib.Path('/usr/bin/apk').read_bytes())
 result={'schema':1,'abi':abis.pop(),'release':release,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
         'hashes':hashes,'world':data['world'].decode(),'installed':data['installed'].decode()}
 print(json.dumps(result))
'''

SIMULATE = r'''
import hashlib,json,pathlib,subprocess,sys,tempfile,urllib.request
request=json.load(sys.stdin)
with tempfile.TemporaryDirectory(prefix='apk-release-check-') as folder:
 root=pathlib.Path(folder); cache=root/'cache'; cache.mkdir(); repos=[]
 for i,entry in enumerate(request['indexes']):
  with urllib.request.urlopen(entry['url'],timeout=30) as stream: data=stream.read()
  if hashlib.sha256(data).hexdigest()!=entry['sha256']: raise SystemExit('Candidate index changed')
  repo=root/str(i); repo.mkdir(); index=repo/'packages.adb'; index.write_bytes(data)
  repos+=['--repository',str(index)]
 command=['apk','--no-logfile','--cache-dir',str(cache),*repos]
 if request.get('replace_managed'):
  origin=request['origin'].rstrip('/'); lines=[]
  sources=[pathlib.Path('/etc/apk/repositories'),*pathlib.Path('/etc/apk/repositories.d').glob('*.list'),
           *pathlib.Path('/lib/apk/repositories.d').glob('*.list')]
  for source in sources:
   if not source.is_file(): continue
   for line in source.read_text().splitlines():
    if not any(t.startswith((origin+'/abi/',origin+'/kernel-upgrades/')) for t in line.split()): lines.append(line)
  config=root/'repositories.list'; config.write_text('\n'.join(lines)+'\n')
  command+=['--repositories-file',str(config)]
 update=subprocess.run(command+['update'],capture_output=True,text=True)
 if update.returncode: print(json.dumps({'returncode':update.returncode,'stdout':update.stdout,'stderr':update.stderr})); sys.exit(0)
 helptext=subprocess.run(['apk','upgrade','--help'],capture_output=True,text=True).stdout
 args=['upgrade','--simulate']; plan=root/'plan.json'
 if '--plan-json' in helptext: args+=['--plan-json',str(plan)]
 result=subprocess.run(command+args,capture_output=True,text=True)
 report={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
 if plan.exists(): report['plan']=json.loads(plan.read_text())
 print(json.dumps(report))
'''


def remote(target, code, request=None):
    if not re.fullmatch(r'[A-Za-z0-9_.@:-]+', target) or target.startswith('-'):
        raise ValueError('Invalid preflight SSH target')
    command = 'sudo -n python3 -c ' + shlex.quote(code)
    try:
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                                 target, command], input=json.dumps(request) if request else None,
                                text=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise ValueError('Router upgrade preflight timed out; release was not promoted') from error
    if result.returncode:
        raise ValueError('Router upgrade preflight failed: ' + result.stderr[-4096:])
    return json.loads(result.stdout)


def capture(target):
    return remote(target, BASELINE)


def same_baseline(before, after):
    return all(before[k] == after[k] for k in ('abi', 'release', 'boot_id', 'hashes'))


def snapshot_hashes(snapshot):
    root = Path(snapshot)
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*')) if p.is_file()}


def prepared_record(result):
    path = Path(result['snapshot']).resolve()
    return {'snapshot': str(path), 'files': snapshot_hashes(path)}


def check_prepared(result, record):
    if prepared_record(result) != record:
        raise ValueError('Prepared release changed after upgrade validation')


def preflight(destination, origin, userspace, kernel):
    selected_policy = policy(destination)
    stages = {'userspace': prepared_record(userspace), 'kernel': prepared_record(kernel)}
    receipt = {'schema': 1, 'status': 'passed', 'stages': stages, 'baseline': None,
               'policy_sha256': digest(TREE / 'configs/lan-apk-feeds.json'),
               'migrations_sha256': digest(TREE / 'configs/apk-migrations.json')}
    if selected_policy:
        target = selected_policy['ssh_target']
        before = capture(target)
        manifest = json.loads((Path(kernel['snapshot']) / 'manifest.json').read_text())
        latest = max(manifest['images'], key=lambda n: int(n.rsplit('-g', 1)[1]))
        abi = manifest['images'][latest]
        validate_transition(before, [e['info'] for e in manifest['packages'].values()], abi)
        indexes = []
        roots = [Path(kernel['snapshot'])]
        # Match the existing client's first transaction: normal feeds follow
        # the running ABI. The target ABI userspace view is validated on disk.
        if abi == before['abi']:
            roots.append(Path(userspace['snapshot']))
        for root in roots:
            for index in sorted(root.rglob('packages.adb')):
                relative = index.relative_to(Path(destination) / 'public').as_posix()
                indexes.append({'url': origin.rstrip('/') + '/' + relative,
                                'sha256': digest(index)})
        simulation = remote(target, SIMULATE, {'indexes': indexes})
        receipt['simulation'] = simulation
        if simulation['returncode']:
            raise ValueError('Router rejects prepared release: ' + simulation['stderr'][-8192:])
        if abi != before['abi']:
            target_indexes = list(indexes)
            for index in sorted(Path(userspace['snapshot']).rglob('packages.adb')):
                relative = index.relative_to(Path(destination) / 'public').as_posix()
                target_indexes.append({'url': origin.rstrip('/') + '/' + relative,
                                       'sha256': digest(index)})
            target_simulation = remote(target, SIMULATE, {'indexes': target_indexes,
                                       'replace_managed': True, 'origin': origin})
            receipt['target_abi_simulation'] = target_simulation
            if target_simulation['returncode']:
                raise ValueError('Router rejects target ABI userspace view: ' +
                                 target_simulation['stderr'][-8192:])
        if not same_baseline(before, capture(target)):
            raise ValueError('Router baseline changed during upgrade validation')
        receipt['baseline'] = {k: v for k, v in before.items() if k not in ('world', 'installed')}
    for name, result in (('userspace', userspace), ('kernel', kernel)):
        check_prepared(result, stages[name])
    return receipt


def authorize(destination, result, receipt, kind):
    if not receipt or receipt.get('schema') != 1 or receipt.get('status') != 'passed':
        raise ValueError('Missing successful upgrade preflight receipt')
    if policy(destination) and not receipt.get('baseline'):
        raise ValueError('Production release lacks a router baseline')
    if (receipt['policy_sha256'] != digest(TREE / 'configs/lan-apk-feeds.json') or
            receipt['migrations_sha256'] != digest(TREE / 'configs/apk-migrations.json')):
        raise ValueError('Upgrade policy changed after validation')
    check_prepared(result, receipt['stages'][kind])


def check_alias(result):
    alias = Path(result['alias'])
    previous = result['previous']
    current = str(alias.resolve()) if alias.exists() else None
    if current != previous:
        raise ValueError('Active release changed during preparation')
