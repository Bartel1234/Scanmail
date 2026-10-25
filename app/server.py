#!/usr/bin/env python3
"""Local ScanMail server. Standard library + Pillow; hardware through SANE."""
import hashlib
import hmac
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import smtplib
import ssl
import subprocess
import tempfile
import threading
import time
from email.message import EmailMessage
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

VERSION = '0.2.0'
DATA = Path(os.environ.get('DATA_DIR', '/data'))
DATA.mkdir(parents=True, exist_ok=True)
CONFIG = DATA / 'settings.json'
STATIC = Path(__file__).parent / 'static'
SCANNER_IP = os.environ.get('SCANNER_IP', '172.16.60.252')
try:
    ipaddress.IPv4Address(SCANNER_IP)
except ValueError:
    raise RuntimeError('SCANNER_IP skal være en IPv4-adresse.')
DEVICE = f'hpaio:/net/HP_Color_LaserJet_Pro_MFP_M176n?ip={SCANNER_IP}'
DEMO = os.environ.get('SCANMAIL_DEMO') == '1'
PASSWORD_HASH = os.environ.get('SCANMAIL_PASSWORD_HASH', '')
Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_STORAGE = 256 * 1024 * 1024
WORK = Path(tempfile.mkdtemp(prefix='scanmail-'))
LOCK = threading.RLock()
HARDWARE = threading.Lock()
SESSIONS = {}
FAILURES = {}
JOBS = {}
SETTINGS = {'host': 'smtp.gmail.com', 'port': 587, 'tls': 'starttls',
            'username': '', 'password': '', 'sender': '', 'favorites': []}
if CONFIG.exists():
    SETTINGS.update(json.loads(CONFIG.read_text()))


def verify_password(password):
    try:
        salt, expected = PASSWORD_HASH.split(':', 1)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def email_address(value):
    value = str(value).strip()
    if len(value) > 254 or not re.fullmatch(r'[^\s<>@,;\r\n]+@[^\s<>@,;\r\n]+\.[^\s<>@,;\r\n]+', value):
        raise ValueError('Skriv én gyldig mailadresse.')
    return value


def public_settings():
    with LOCK:
        return {**{k: v for k, v in SETTINGS.items() if k != 'password'},
                'password_saved': bool(SETTINGS['password'])}


def save_settings(data):
    with LOCK:
        result = dict(SETTINGS)
        for key in ('host', 'tls', 'username', 'sender'):
            if key in data:
                result[key] = str(data[key]).strip()
        if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', result['host']):
            raise ValueError('SMTP-serverens navn er ugyldigt.')
        result['port'] = int(data.get('port', result['port']))
        if not 1 <= result['port'] <= 65535 or result['tls'] not in ('starttls', 'ssl'):
            raise ValueError('Vælg en gyldig port og TLS-type.')
        if any(len(result[key]) > 512 or '\r' in result[key] or '\n' in result[key] for key in ('username', 'sender')):
            raise ValueError('Mailkonto eller afsender er ugyldig.')
        if result['sender']:
            result['sender'] = email_address(result['sender'])
        if data.get('clear_password'):
            result['password'] = ''
        elif data.get('password'):
            result['password'] = str(data['password'])
            if result['host'] == 'smtp.gmail.com':
                result['password'] = result['password'].replace(' ', '')
        if 'favorites' in data:
            if not isinstance(data['favorites'], list) or len(data['favorites']) > 25:
                raise ValueError('Du kan gemme højst 25 favoritter.')
            result['favorites'] = list(dict.fromkeys(email_address(x) for x in data['favorites'] if str(x).strip()))
        tmp = CONFIG.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG)
        SETTINGS.update(result)


def cleanup():
    now = time.time()
    with LOCK:
        for key in list(SESSIONS):
            if SESSIONS[key]['expires'] < now:
                del SESSIONS[key]
        for key in list(FAILURES):
            if FAILURES[key][1] < now - 900:
                del FAILURES[key]
        for key in list(JOBS):
            job = JOBS[key]
            if job['updated'] < now - 3600 and job['status'] not in ('scanning', 'sending'):
                shutil.rmtree(WORK / key, ignore_errors=True)
                del JOBS[key]


def get_job(job_id, owner, touch=True):
    with LOCK:
        job = JOBS.get(job_id)
        if not job or job['owner'] != owner:
            raise ValueError('Dokumentet findes ikke længere. Start et nyt scan.')
        if touch:
            job['updated'] = time.time()
        return job


def job_info(job):
    return {key: job[key] for key in ('id', 'status', 'pages', 'error', 'dpi', 'mode', 'sent', 'delivery_uncertain')}


def scanner_error(detail):
    detail = detail.lower()
    if 'plugin' in detail or 'bb_marvell' in detail:
        return 'HP-plugin mangler eller kan ikke indlæses. Kør plugin-installationen igen med samme HPLIP-version.'
    if any(word in detail for word in ('open device', 'i/o error', 'invalid argument', 'no devices')):
        return 'Scanneren kunne ikke åbnes. Kontrollér printerens IP, netværk og HP-plugin. Brug Test scanner.'
    return 'Scannerdriveren fejlede. Kontrollér printer, netværk og HP-plugin. Brug Test scanner.'


def scan_page(job):
    path = WORK / job['id']
    raw = path / 'current.png'
    try:
        if DEMO:
            image = Image.new('RGB', (1240, 1754), '#ffffff')
            draw = ImageDraw.Draw(image)
            draw.text((90, 120), 'DEMO - SCANMAIL', fill='#152b40', font_size=48)
            draw.text((90, 240), f"Testside {job['pages'] + 1}", fill='#152b40', font_size=36)
            draw.text((90, 340), 'Dette er ikke en fysisk scanning.', fill='#152b40', font_size=24)
            image.save(raw)
            image.close()
        else:
            command = ['prlimit', '--fsize=50331648', '--', 'scanimage', '--device-name', DEVICE, '--format=png',
                       '--mode', job['mode'], '--resolution', str(job['dpi'])]
            with raw.open('wb') as output:
                proc = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, timeout=180, start_new_session=True)
            if proc.returncode:
                detail = proc.stderr.decode(errors='replace')[-1400:]
                raise ValueError(scanner_error(detail))
        with Image.open(raw) as source:
            if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('Scanningen er for stor. Brug 150 dpi eller kontrollér driveren.')
            image = source.convert('RGB')
        image.save(path / f"{job['pages'] + 1}.jpg", 'JPEG', quality=88)
        image.thumbnail((440, 620))
        image.save(path / f"thumb-{job['pages'] + 1}.jpg", 'JPEG', quality=80)
        image.close()
        with LOCK:
            if sum(f.stat().st_size for f in WORK.rglob('*') if f.is_file()) > MAX_STORAGE:
                (path / f"{job['pages'] + 1}.jpg").unlink(missing_ok=True)
                (path / f"thumb-{job['pages'] + 1}.jpg").unlink(missing_ok=True)
                raise ValueError('Lagergrænsen er nået. Slet dokumenter eller brug færre sider.')
            job['pages'] += 1
            job['status'] = 'ready'
            job['error'] = ''
    except subprocess.TimeoutExpired:
        with LOCK:
            job['status'] = 'error'
            job['error'] = 'Scanningen tog over 3 minutter. Kontrollér printeren og prøv igen.'
    except FileNotFoundError:
        with LOCK:
            job.update(status='error', error='Scannerdriveren mangler. Kontrollér installationen af SANE og HPLIP.')
    except Exception as exc:
        with LOCK:
            job['status'] = 'error'
            job['error'] = str(exc) if isinstance(exc, ValueError) else 'Scanningen kunne ikke læses eller gemmes. Kontrollér driver og ledig plads.'
    finally:
        raw.unlink(missing_ok=True)
        with LOCK:
            job['updated'] = time.time()
        HARDWARE.release()


def start_scan(owner, data):
    dpi = int(data.get('dpi', 300))
    mode = data.get('mode', 'Color')
    if dpi not in (150, 300) or mode not in ('Color', 'Gray'):
        raise ValueError('Vælg 150/300 dpi og farve/gråtoner.')
    if not HARDWARE.acquire(blocking=False):
        raise ValueError('Scanneren er optaget. Vent, til scanningen er færdig.')
    try:
        with LOCK:
            cleanup()
            if data.get('job_id'):
                job = get_job(data['job_id'], owner)
                if job['sent'] or job['delivery_uncertain']:
                    raise ValueError('Start et nyt dokument efter afsendelse eller uklar levering.')
                if job['status'] in ('scanning', 'sending') or job['pages'] >= 20:
                    raise ValueError('Dokumentet er optaget eller har nået grænsen på 20 sider.')
                if dpi != job['dpi'] or mode != job['mode']:
                    raise ValueError('Brug samme farve og opløsning på dokumentets sider.')
            else:
                if len(JOBS) >= 10:
                    raise ValueError('Der er for mange dokumenter. Slet et eller vent en time.')
                job_id = secrets.token_hex(16)
                (WORK / job_id).mkdir(mode=0o700)
                job = {'id': job_id, 'owner': owner, 'pages': 0, 'dpi': dpi, 'mode': mode,
                       'status': 'ready', 'error': '', 'updated': time.time(), 'sent': False, 'delivery_uncertain': False}
                JOBS[job_id] = job
            job.update(status='scanning', error='', sent=False, updated=time.time())
            info = job_info(job)
        threading.Thread(target=scan_page, args=(job,), daemon=True).start()
        return info
    except Exception:
        HARDWARE.release()
        raise


def make_pdf(job):
    if not job['pages']:
        raise ValueError('Scan mindst én side først.')
    output = io.BytesIO()
    document = canvas.Canvas(output, pageCompression=1)
    for i in range(1, job['pages'] + 1):
        path = WORK / job['id'] / f'{i}.jpg'
        with Image.open(path) as image:
            width, height = [pixels * 72 / job['dpi'] for pixels in image.size]
        document.setPageSize((width, height))
        document.drawImage(str(path), 0, 0, width=width, height=height)
        document.showPage()
    document.save()
    return output.getvalue()


def smtp_send(settings, message):
    context = ssl.create_default_context()
    if settings['tls'] == 'ssl':
        connection = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=30, context=context)
    else:
        connection = smtplib.SMTP(settings['host'], settings['port'], timeout=30)
    smtp = connection
    try:
        if settings['tls'] == 'starttls':
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(settings['username'], settings['password'])
        smtp.send_message(message)
        # QUIT failure after a successful DATA response must not imply failed delivery.
        try:
            smtp.quit()
        except (OSError, smtplib.SMTPException):
            smtp.close()
    finally:
        smtp.close()


def send_document(job, recipient, subject, body, settings):
    transmission_started = False
    try:
        payload = make_pdf(job)
        if len(payload) > 17 * 1024 * 1024:
            raise ValueError('PDF er for stor til mail. Download den eller scan færre sider ved 150 dpi.')
        message = EmailMessage()
        message['From'] = email_address(settings['sender'] or settings['username'])
        message['To'] = recipient
        message['Subject'] = subject or 'Scannet dokument'
        message.set_content(body or 'Vedhæftet finder du dit scannede dokument.')
        message.add_attachment(payload, maintype='application', subtype='pdf', filename='scanning.pdf')
        transmission_started = True
        smtp_send(settings, message)
        with LOCK:
            job.update(status='sent', error='', sent=True)
    except smtplib.SMTPAuthenticationError:
        with LOCK:
            job.update(status='error', error='Login til mailserveren blev afvist. Ved Gmail skal du bruge en app-adgangskode.')
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        with LOCK:
            job.update(status='error', error='Mailserveren afviste afsender, modtager eller dokument. Kontrollér indstillingerne.')
    except Exception:
        # Connection failures after DATA can mean delivery is uncertain. Never retry automatically.
        with LOCK:
            job.update(status='error', delivery_uncertain=transmission_started, error=(
                'Levering er uklar. Kontrollér modtagerens indbakke og mailudbyderens log. Afsendelse er låst for dette dokument for at undgå dubletter.'
                if transmission_started else 'PDF kunne ikke klargøres til mail. Download dokumentet eller brug færre sider ved 150 dpi.'))
    finally:
        with LOCK:
            job['updated'] = time.time()


class Handler(BaseHTTPRequestHandler):
    server_version = 'ScanMail'

    def log_message(self, fmt, *args):
        # Do not log addresses, job URLs, credentials or message contents.
        pass

    def reply(self, value, code=200, mime='application/json; charset=utf-8', headers=None):
        if not isinstance(value, bytes):
            value = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(value)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(value)

    def session(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie', ''))
        except cookies.CookieError:
            return None, None
        token = jar.get('scanmail')
        token = token.value if token else ''
        with LOCK:
            entry = SESSIONS.get(token)
            if entry and entry['expires'] > time.time():
                return token, entry
        return None, None

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def do_GET(self):
        try:
            self.get()
        except (ValueError, KeyError, FileNotFoundError):
            self.reply({'error': 'Dokumentet findes ikke længere.'}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply({'error': 'Der opstod en intern fejl.'}, 500)

    def get(self):
        path = urlparse(self.path).path
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in files:
            name, mime = files[path]
            return self.reply((STATIC / name).read_bytes(), mime=mime)
        if path == '/healthz':
            return self.reply({'status': 'ok', 'version': VERSION})
        cleanup()
        token, session = self.session()
        if path == '/api/session':
            with LOCK:
                owned = [j for j in JOBS.values() if j['owner'] == token]
                latest = max(owned, key=lambda j: j['updated']) if owned else None
                if latest:
                    latest['updated'] = time.time()
            return self.reply({'authenticated': bool(session), 'csrf': session['csrf'] if session else '',
                               'version': VERSION, 'demo': DEMO, 'job': job_info(latest) if latest else None})
        if not session:
            return self.reply({'error': 'Log ind for at fortsætte.'}, 401)
        cleanup()
        if path == '/api/settings':
            return self.reply({**public_settings(), 'scanner_ip': SCANNER_IP})
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(pdf|thumb/\d+))?', path)
        if match:
            with LOCK:
                job = get_job(match[1], token)
                if not match[2]:
                    return self.reply(job_info(job))
                if match[2] == 'pdf':
                    if job['status'] in ('scanning', 'sending'):
                        return self.reply({'error': 'Vent til dokumentet er klar.'}, 409)
                    return self.reply(make_pdf(job), mime='application/pdf', headers={'Content-Disposition': 'attachment; filename="scanning.pdf"'})
                n = int(match[2].split('/')[1])
                if n < 1 or n > job['pages']:
                    raise ValueError('Ugyldig side')
                return self.reply((WORK / job['id'] / f'thumb-{n}.jpg').read_bytes(), mime='image/jpeg')
        self.reply({'error': 'Siden findes ikke.'}, 404)

    def do_POST(self):
        try:
            self.post()
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.reply({'error': str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply({'error': 'Der opstod en intern fejl. Kontrollér indstillingerne.'}, 500)

    def post(self):
        # Reject browser cross-origin requests, including login, before reading secrets.
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.reply({'error': 'Forespørgslen blev afvist.'}, 403)
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.reply({'error': 'Forespørgslen blev afvist.'}, 403)
        if self.headers.get_content_type() != 'application/json':
            return self.reply({'error': 'JSON er påkrævet.'}, 415)
        size = int(self.headers.get('Content-Length', 0))
        if size < 1 or size > 32768:
            return self.reply({'error': 'Ugyldig forespørgselsstørrelse.'}, 413)
        try:
            data = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError('Ugyldig JSON.')
        if not isinstance(data, dict):
            raise ValueError('Ugyldig forespørgsel.')
        path = urlparse(self.path).path
        if path == '/api/login':
            cleanup()
            ip = self.client_address[0]
            with LOCK:
                count, last = FAILURES.get(ip, (0, 0))
                if count >= 8 and time.time() - last < 900:
                    return self.reply({'error': 'For mange loginforsøg. Vent 15 minutter.'}, 429)
            if not verify_password(str(data.get('password', ''))):
                with LOCK:
                    FAILURES[ip] = (count + 1, time.time())
                return self.reply({'error': 'Forkert adgangskode.'}, 401)
            with LOCK:
                if len(SESSIONS) >= 50:
                    return self.reply({'error': 'For mange sessioner. Prøv senere.'}, 429)
                token = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(32)
                SESSIONS[token] = {'csrf': csrf, 'expires': time.time() + 12 * 3600}
                FAILURES.pop(ip, None)
            secure = '; Secure' if os.environ.get('COOKIE_SECURE') == '1' else ''
            return self.reply({'csrf': csrf}, headers={'Set-Cookie': f'scanmail={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}'})
        token, session = self.session()
        if not session:
            return self.reply({'error': 'Log ind for at fortsætte.'}, 401)
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
            return self.reply({'error': 'Genindlæs siden og prøv igen.'}, 403)
        if path == '/api/logout':
            with LOCK:
                SESSIONS.pop(token, None)
                for job in list(JOBS.values()):
                    if job['owner'] == token and job['status'] not in ('scanning', 'sending'):
                        shutil.rmtree(WORK / job['id'], ignore_errors=True)
                        del JOBS[job['id']]
            return self.reply({'ok': True}, headers={'Set-Cookie': 'scanmail=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        if path == '/api/settings':
            save_settings(data)
            return self.reply(public_settings())
        if path == '/api/scanner-test':
            if not HARDWARE.acquire(blocking=False):
                raise ValueError('Scanneren er optaget.')
            try:
                if DEMO:
                    return self.reply({'ok': True, 'detail': 'DEMO: fysisk scanner er ikke testet.'})
                result = subprocess.run(['scanimage', '-d', DEVICE, '-A'], stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=45)
                return self.reply({'ok': result.returncode == 0,
                                   'detail': result.stdout.decode(errors='replace')[-6000:]})
            except subprocess.TimeoutExpired:
                raise ValueError('Ingen svar fra scanneren inden for 45 sekunder.')
            finally:
                HARDWARE.release()
        if path == '/api/scan':
            return self.reply(start_scan(token, data), 202)
        if path in ('/api/send', '/api/delete'):
            with LOCK:
                job = get_job(data['job_id'], token)
                if job['status'] in ('scanning', 'sending'):
                    raise ValueError('Vent til den igangværende opgave er færdig.')
                if path == '/api/delete':
                    shutil.rmtree(WORK / job['id'])
                    del JOBS[job['id']]
                    return self.reply({'ok': True})
                if DEMO:
                    raise ValueError('DEMO kan ikke sende mails.')
                if not job['pages']:
                    raise ValueError('Scan mindst én side først.')
                if job['delivery_uncertain']:
                    raise ValueError('Levering er uklar. Afsendelse er låst. Kontrollér modtagerens indbakke før du starter et nyt dokument.')
                if job['sent']:
                    raise ValueError('Dokumentet er allerede sendt. Start et nyt dokument for en ny forsendelse.')
                recipient = email_address(data.get('recipient', ''))
                subject = str(data.get('subject', '')).strip()
                body = str(data.get('body', '')).strip()
                if '\r' in subject or '\n' in subject or len(subject) > 200 or len(body) > 5000:
                    raise ValueError('Emne eller besked er ugyldig eller for lang.')
                settings = dict(SETTINGS)
                if not settings['username'] or not settings['password']:
                    raise ValueError('Gem mailkonto og app-adgangskode under Indstillinger først.')
                email_address(settings['sender'] or settings['username'])
                job.update(status='sending', error='', updated=time.time())
                info = job_info(job)
            threading.Thread(target=send_document, args=(job, recipient, subject, body, settings), daemon=True).start()
            return self.reply(info, 202)
        self.reply({'error': 'Siden findes ikke.'}, 404)


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    slots = threading.BoundedSemaphore(24)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def sys_exit():
    raise SystemExit(0)


def main():
    if not PASSWORD_HASH or not verify_hash_format(PASSWORD_HASH):
        raise SystemExit('SCANMAIL_PASSWORD_HASH mangler. Brug install-unraid.sh til første opsætning.')
    threading.stack_size(1024 * 1024)
    signal.signal(signal.SIGTERM, lambda *_: sys_exit())
    server = BoundedHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler)
    server.daemon_threads = True
    print(f'ScanMail {VERSION} klar. Scanner: {SCANNER_IP}. Demo: {DEMO}', flush=True)
    def janitor():
        while True:
            time.sleep(60)
            cleanup()
    threading.Thread(target=janitor, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        shutil.rmtree(WORK, ignore_errors=True)


def verify_hash_format(value):
    return bool(re.fullmatch(r'[a-f0-9]{32}:[a-f0-9]{64}', value))


if __name__ == '__main__':
    main()
