"""Run the entire shell updater against a stateful Docker fake, including rollback."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ['DOCKER_STATE'])
state = json.loads(path.read_text())
a = sys.argv[1:]
state['calls'].append(a)
containers = state['containers']
code, output = 0, ''
if a[0] == 'inspect':
    name = a[-1]
    if name not in containers:
        code = 1
    elif 'RestartPolicy' in ' '.join(a):
        output = 'unless-stopped'
    else:
        output = containers[name]['image']
elif a[:2] == ['image', 'inspect']:
    output = 'sha256:new'
elif a[0] == 'build':
    if os.environ['FAIL_PHASE'] == 'build': code = 1
elif a[0] == 'run':
    if '--name' in a:
        name = a[a.index('--name')+1]
        containers[name] = {'image':'sha256:new','running':True}
        output = name
        if name == 'scanmail' and os.environ['FAIL_PHASE'] == 'run': code = 1
    elif os.environ['FAIL_PHASE'] == 'preflight':
        code = 1
elif a[0] == 'exec':
    if a[1] == 'scanmail' and os.environ['FAIL_PHASE'] == 'health': code = 1
    if a[1].startswith('scanmail-smoke-') and os.environ['FAIL_PHASE'] == 'smoke': code = 1
elif a[0] == 'stop':
    containers[a[1]]['running'] = False
elif a[0] == 'rename':
    if a[1] not in containers or a[2] in containers:
        code = 1
    else:
        containers[a[2]] = containers.pop(a[1])
elif a[0] == 'rm':
    containers.pop(a[-1], None)
elif a[0] == 'start':
    containers[a[1]]['running'] = True
elif a[:2] == ['image','save']:
    output = 'fake image archive'
path.write_text(json.dumps(state))
if output: print(output)
sys.exit(code)
'''


class UpdateTests(unittest.TestCase):
    def run_update(self, phase):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / 'runtime.env').write_text('SCANMAIL_PASSWORD_HASH=not-logged\n')
            state = work / 'state.json'
            state.write_text(json.dumps({'containers':{'scanmail':{'image':'sha256:old','running':True}},'calls':[]}))
            docker = work / 'docker'; docker.write_text(FAKE); docker.chmod(0o700)
            sleep = work / 'sleep'; sleep.write_text('#!/bin/sh\nexit 0\n'); sleep.chmod(0o700)
            result = subprocess.run(['bash', str(ROOT / 'update-unraid.sh')], capture_output=True, text=True,
                                    env=dict(os.environ, PATH=str(work)+':'+os.environ['PATH'],
                                             SCANMAIL_DATA_DIR=str(work), SCANMAIL_ARCHIVE_DIR=str(work/'images'),
                                             DOCKER_STATE=str(state), FAIL_PHASE=phase), timeout=20)
            return result, json.loads(state.read_text())

    def test_success_disables_backup_autostart_and_preserves_parent(self):
        result, state = self.run_update('none')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['containers']['scanmail']['image'], 'sha256:new')
        backups = [key for key in state['containers'] if key.startswith('scanmail-backup-')]
        self.assertEqual(len(backups), 1)
        self.assertFalse(state['containers'][backups[0]]['running'])
        self.assertIn(['update','--restart=no',backups[0]], state['calls'])
        self.assertNotIn('not-logged', result.stdout + result.stderr)

    def test_build_preflight_and_smoke_failure_never_stop_old_app(self):
        for phase in ('build', 'preflight', 'smoke'):
            with self.subTest(phase=phase):
                result, state = self.run_update(phase)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(state['containers']['scanmail'], {'image':'sha256:old','running':True})
                self.assertFalse(any(call[0] == 'stop' for call in state['calls']))

    def test_failed_run_or_health_check_restores_original_container(self):
        for phase in ('run', 'health'):
            with self.subTest(phase=phase):
                result, state = self.run_update(phase)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(state['containers']['scanmail'], {'image':'sha256:old','running':True})
                self.assertIn(['update','--restart=unless-stopped','scanmail'], state['calls'])
                self.assertIn(['start','scanmail'], state['calls'])
