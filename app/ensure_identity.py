"""Create the numeric runtime identity at image build time (never at app startup)."""
import grp
import pwd
from pathlib import Path


def ensure_identity(uid=1000, gid=1000, passwd_path=Path('/etc/passwd'), group_path=Path('/etc/group')):
    try:
        pwd.getpwuid(uid)
    except KeyError:
        with passwd_path.open('a') as output:
            output.write(f'scanmail:x:{uid}:{gid}:ScanMail:/tmp:/usr/sbin/nologin\n')
    try:
        grp.getgrgid(gid)
    except KeyError:
        with group_path.open('a') as output:
            output.write(f'scanmail:x:{gid}:\n')


if __name__ == '__main__':
    ensure_identity()
