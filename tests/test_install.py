"""Exercise the driver's shell flow with mock downloads and installer, no Docker/network."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DriverInstallTests(unittest.TestCase):
    def run_driver(self, download_exit=0, install_exit=0):
        script = (ROOT / 'install-unraid.sh').read_text().split('"$image_base" -c \'\n', 1)[1].split("\n'\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            binary = work / 'bin'
            binary.mkdir()
            plugin = work / 'scan/plugins'
            plugin.mkdir(parents=True)
            (work / 'hplip').mkdir()
            script = script.replace('export HOME=/root', 'export HOME="$TEST_HOME"')
            script = script.replace('/usr/share/hplip/scan/plugins', str(plugin))
            script = script.replace('/usr/share/hplip', str(work / 'hplip'))
            script = script.replace('/var/lib/hp/hplip.state', str(work / 'hplip.state'))
            script = script.replace('/tmp/scanmail-plugin.', str(work / 'scanmail-plugin.'))
            commands = {
                'python3': '#!/bin/sh\nprintf "3.22.10\\n"\n',
                'wget': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_HOME/downloads"\n'
                        'if [ "$DOWNLOAD_EXIT" != 0 ]; then exit "$DOWNLOAD_EXIT"; fi\n'
                        'while [ "$1" != -O ]; do shift; done\nprintf data > "$2"\n',
                'hp-plugin': '#!/bin/sh\nprintf "%s\\n" "$*" > "$TEST_HOME/guide"\n'
                             'if [ "$INSTALL_EXIT" != 0 ]; then exit "$INSTALL_EXIT"; fi\n'
                             'touch "$TEST_HOME/hplip.state" "$TEST_HOME/scan/plugins/bb_marvell.so"\n',
            }
            for name, contents in commands.items():
                path = binary / name
                path.write_text(contents)
                path.chmod(0o700)
            environment = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                               TEST_HOME=str(work), SCANMAIL_PLUGIN_SOURCE='openprinting',
                               DOWNLOAD_EXIT=str(download_exit), INSTALL_EXIT=str(install_exit))
            result = subprocess.run(['sh', '-c', script], env=environment, capture_output=True)
            guide = (work / 'guide').read_text() if (work / 'guide').exists() else ''
            downloads = (work / 'downloads').read_text() if (work / 'downloads').exists() else ''
            return result.returncode, guide, downloads

    def test_mirror_fetches_version_and_signature_then_interactive_guide(self):
        code, guide, downloads = self.run_driver()
        self.assertEqual(code, 0)
        self.assertEqual(downloads.count('https://www.openprinting.org/'), 2)
        self.assertIn('hplip-3.22.10-plugin.run.asc', downloads)
        self.assertIn('--https-only', downloads)
        self.assertTrue(guide.startswith('-i -p '))
        self.assertNotIn('--yes', guide)

    def test_failed_download_never_executes_plugin(self):
        code, guide, _ = self.run_driver(download_exit=8)
        self.assertNotEqual(code, 0)
        self.assertEqual(guide, '')

    def test_failed_plugin_stops_setup(self):
        code, _, _ = self.run_driver(install_exit=1)
        self.assertNotEqual(code, 0)
