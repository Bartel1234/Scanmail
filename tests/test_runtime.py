"""Guard the two runtime prerequisites which caused HPLIP to crash on hardware."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'app' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


runtime = module('runtime')
identity = module('ensure_identity')


class RuntimeTests(unittest.TestCase):
    def test_missing_identity_fails_before_starting_driver(self):
        with patch.object(runtime.pwd, 'getpwuid', side_effect=KeyError), patch.object(runtime.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                runtime.start_bus()
            run.assert_not_called()

    def test_private_bus_overrides_inherited_host_address(self):
        with tempfile.TemporaryDirectory() as folder:
            address = f'unix:path={folder}/bus'
            with patch.dict(os.environ, {'DBUS_SYSTEM_BUS_ADDRESS': 'unix:path=/host/bus'}), \
                 patch.object(runtime.tempfile, 'mkdtemp', return_value=folder), \
                 patch.object(runtime.subprocess, 'run', return_value=Mock(stdout=address + ',guid=abc\n')) as run:
                self.assertEqual(runtime.start_bus(), address + ',guid=abc')
                self.assertEqual(os.environ['DBUS_SYSTEM_BUS_ADDRESS'], address + ',guid=abc')
                self.assertEqual(os.environ['DBUS_SESSION_BUS_ADDRESS'], address + ',guid=abc')
                self.assertIn('--session', run.call_args.args[0])
                self.assertIn('--address=' + address, run.call_args.args[0])

    def test_bus_failure_does_not_launch_http_server(self):
        with patch.object(runtime, 'start_bus', side_effect=subprocess.CalledProcessError(1, 'dbus-daemon')), \
             patch.object(runtime.os, 'execv') as execute:
            with self.assertRaises(SystemExit):
                runtime.main()
            execute.assert_not_called()

    def test_identity_repair_preserves_existing_accounts(self):
        with tempfile.TemporaryDirectory() as folder:
            passwd, group = Path(folder) / 'passwd', Path(folder) / 'group'
            passwd.write_text('root:x:0:0:root:/root:/bin/sh\n')
            group.write_text('root:x:0:\n')
            with patch.object(identity.pwd, 'getpwuid', side_effect=KeyError), \
                 patch.object(identity.grp, 'getgrgid', side_effect=KeyError):
                identity.ensure_identity(passwd_path=passwd, group_path=group)
            self.assertTrue(passwd.read_text().startswith('root:x:0:'))
            self.assertIn('scanmail:x:1000:1000:', passwd.read_text())
            self.assertIn('scanmail:x:1000:', group.read_text())
            previous = passwd.read_text(), group.read_text()
            with patch.object(identity.pwd, 'getpwuid'), patch.object(identity.grp, 'getgrgid'):
                identity.ensure_identity(passwd_path=passwd, group_path=group)
            self.assertEqual(previous, (passwd.read_text(), group.read_text()))

    def test_repair_build_failure_leaves_running_container_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / 'runtime.env').touch()
            docker = work / 'docker'
            log = work / 'calls'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n'
                              'case "$1" in inspect) echo sha256:test;; build) exit 1;; esac\n')
            docker.chmod(0o700)
            script = (ROOT / 'repair-unraid.sh').read_text().replace('/mnt/user/appdata/scanmail', str(work))
            (work / 'repair.sh').write_text(script)
            result = subprocess.run(['bash', str(work / 'repair.sh')], capture_output=True,
                                    env=dict(os.environ, PATH=str(work) + ':' + os.environ['PATH'], TEST_LOG=str(log)))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('stop ', log.read_text())
            self.assertNotIn('rename ', log.read_text())


if __name__ == '__main__':
    unittest.main()
