"""Supply HPLIP with a real Unix identity and a private, container-local D-Bus."""
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile


def start_bus():
    try:
        pwd.getpwuid(os.getuid())
    except KeyError:
        raise RuntimeError('Containerens bruger mangler. Kør det opdaterede reparationsscript.') from None
    directory = tempfile.mkdtemp(prefix='scanmail-bus-')
    address = f'unix:path={directory}/bus'
    # A session daemon provides an isolated bus with a policy for this UID.
    # HPLIP requests DBUS_BUS_SYSTEM, so point that lookup at our own socket.
    result = subprocess.run([
        'dbus-daemon', '--session', '--fork', '--nopidfile',
        '--print-address=1', f'--address={address}',
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=10)
    actual = result.stdout.strip()
    if actual != address and not actual.startswith(address + ',guid='):
        raise RuntimeError('Den private D-Bus returnerede en ugyldig adresse.')
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = actual
    os.environ['DBUS_SESSION_BUS_ADDRESS'] = actual
    return actual


def main():
    try:
        start_bus()
    except (OSError, RuntimeError, subprocess.SubprocessError):
        raise SystemExit('ScanMail kunne ikke starte privat D-Bus eller finde containerens bruger. Kør reparationsscriptet.') from None
    os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name('server.py'))])


if __name__ == '__main__':
    main()
