"""Offline integration tests: HTTP handlers and real PDF, mocked scanner and SMTP."""
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import smtplib
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = TEMP.name
salt = bytes.fromhex('12' * 16)
os.environ['SCANMAIL_PASSWORD_HASH'] = salt.hex() + ':' + hashlib.pbkdf2_hmac('sha256', b'test-password', salt, 260000).hex()
spec = importlib.util.spec_from_file_location('scanmail', ROOT / 'app/server.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class ScanMailTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(s.WORK, ignore_errors=True)
        TEMP.cleanup()

    def setUp(self):
        with s.LOCK:
            s.SESSIONS.clear()
            s.FAILURES.clear()
            s.JOBS.clear()
        for path in s.WORK.iterdir():
            shutil.rmtree(path)
        s.DEMO = False
        s.SETTINGS.update(host='smtp.gmail.com', port=587, tls='starttls', username='sender@example.com',
                          password='secret', sender='', favorites=[])

    def request(self, path, data=None, cookie='', csrf='', headers=None):
        hdr = {'Host': 'localhost', 'Cookie': cookie, 'X-CSRF-Token': csrf}
        if headers:
            hdr.update(headers)
        payload = b'' if data is None else json.dumps(data).encode()
        if data is not None:
            hdr['Content-Type'] = 'application/json'
            hdr['Content-Length'] = str(len(payload))
        method = 'GET' if data is None else 'POST'
        raw = (f'{method} {path} HTTP/1.0\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in hdr.items()) + '\r\n').encode() + payload
        class Transport:
            def __init__(self):
                self.output = bytearray()
            def makefile(self, mode, *args):
                return io.BytesIO(raw)
            def sendall(self, value):
                self.output.extend(value)
            def settimeout(self, value):
                pass
        transport = Transport()
        s.Handler(transport, ('127.0.0.1', 12345), MagicMock())
        head, body = bytes(transport.output).split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        response_headers = dict(line.split(': ', 1) for line in lines[1:])
        result = json.loads(body) if 'application/json' in response_headers.get('Content-Type', '') else body
        return int(lines[0].split()[1]), result, response_headers

    def login(self):
        code, data, headers = self.request('/api/login', {'password': 'test-password'})
        self.assertEqual(code, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        return headers['Set-Cookie'].split(';')[0], data['csrf']

    def job(self, owner='owner', pages=1):
        key = 'a' * 32
        (s.WORK / key).mkdir(exist_ok=True)
        job = dict(id=key, owner=owner, pages=pages, dpi=150, mode='Gray', sent=False,
                   delivery_uncertain=False, status='ready', error='', updated=time.time())
        s.JOBS[key] = job
        for page in range(1, pages + 1):
            Image.new('RGB', (300, 600), 'white').save(s.WORK / key / f'{page}.jpg')
        return job

    def wait_job(self, job):
        deadline = time.monotonic() + 5
        while job['status'] in ('scanning', 'sending') and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertNotIn(job['status'], ('scanning', 'sending'))

    def test_login_csrf_origin_logout(self):
        self.assertEqual(self.request('/api/settings')[0], 401)
        self.assertEqual(self.request('/api/login', {'password': 'bad'})[0], 401)
        cookie, csrf = self.login()
        self.assertEqual(self.request('/api/settings', {}, cookie)[0], 403)
        self.assertEqual(self.request('/api/settings', {}, cookie, csrf,
                                      {'Origin': 'http://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/login', {'password': 'test-password'},
                                      headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        job = self.job(cookie.split('=', 1)[1])
        self.assertEqual(self.request('/api/logout', {}, cookie, csrf)[0], 200)
        self.assertNotIn(job['id'], s.JOBS)
        self.assertEqual(self.request('/api/settings', cookie=cookie)[0], 401)

    def test_login_throttle_and_session_expiry(self):
        for _ in range(8):
            self.request('/api/login', {'password': 'bad'})
        self.assertEqual(self.request('/api/login', {'password': 'test-password'})[0], 429)
        s.FAILURES.clear()
        cookie, _ = self.login()
        s.SESSIONS[cookie.split('=', 1)[1]]['expires'] = 0
        self.assertEqual(self.request('/api/settings', cookie=cookie)[0], 401)

    def test_document_isolation_and_paths(self):
        cookie, csrf = self.login()
        job = self.job()
        for suffix in ('', '/pdf', '/thumb/1'):
            self.assertEqual(self.request('/api/jobs/' + job['id'] + suffix, cookie=cookie)[0], 404)
        for path in ('/api/delete', '/api/send'):
            self.assertEqual(self.request(path, {'job_id': job['id']}, cookie, csrf)[0], 400)
        self.assertEqual(self.request('/../../etc/passwd', cookie=cookie)[0], 404)

    def test_mock_scan_multipage_pdf_reload(self):
        cookie, csrf = self.login()
        owner = cookie.split('=', 1)[1]
        def scan(command, **kwargs):
            self.assertIn('--fsize=50331648', command)
            self.assertIn(s.DEVICE, command)
            Image.new('RGB', (600, 900), 'white').save(kwargs['stdout'], format='PNG')
            return subprocess.CompletedProcess(command, 0, stderr=b'')
        with patch.object(s.subprocess, 'run', side_effect=scan):
            code, result, _ = self.request('/api/scan', {'dpi': 150, 'mode': 'Gray'}, cookie, csrf)
            self.assertEqual(code, 202)
            job = s.JOBS[result['id']]
            self.wait_job(job)
            self.assertEqual(job['pages'], 1)
            self.assertEqual(self.request('/api/jobs/' + job['id'] + '/thumb/1', cookie=cookie)[0], 200)
            self.assertEqual(self.request('/api/scan', {'job_id': job['id'], 'dpi': 150, 'mode': 'Gray'}, cookie, csrf)[0], 202)
            self.wait_job(job)
        session = self.request('/api/session', cookie=cookie)[1]
        self.assertEqual((session['job']['dpi'], session['job']['mode']), (150, 'Gray'))
        pdf = self.request('/api/jobs/' + job['id'] + '/pdf', cookie=cookie)[1]
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertEqual(len(re.findall(rb'/Type /Page\b', pdf)), 2)
        self.assertIn(b'/MediaBox [ 0 0 288 432 ]', pdf)
        self.assertEqual(s.get_job(job['id'], owner)['pages'], 2)

    def test_scanner_failures_release_lock(self):
        for failure, expected in ((FileNotFoundError(), 'mangler'),
                                  (subprocess.TimeoutExpired('scanimage', 180), '3 minutter')):
            with patch.object(s.subprocess, 'run', side_effect=failure):
                result = s.start_scan('owner', {})
                job = s.JOBS[result['id']]
                self.wait_job(job)
                self.assertEqual(job['status'], 'error')
                self.assertIn(expected, job['error'])
                self.assertTrue(s.HARDWARE.acquire(timeout=1))
                s.HARDWARE.release()
        with patch.object(s.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, stderr=b'plugin missing')):
            job = s.JOBS[s.start_scan('owner', {})['id']]
            self.wait_job(job)
            self.assertIn('HP-plugin', job['error'])
        s.HARDWARE.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'optaget'):
                s.start_scan('another', {})
        finally:
            s.HARDWARE.release()

    def test_settings_permissions_secret_and_injection(self):
        s.save_settings({'password': 'abcd efgh', 'favorites': ['a@example.com', 'a@example.com']})
        self.assertEqual(s.CONFIG.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('password', s.public_settings())
        self.assertEqual(s.SETTINGS['password'], 'abcdefgh')
        self.assertEqual(s.public_settings()['favorites'], ['a@example.com'])
        with self.assertRaises(ValueError):
            s.email_address('a@example.com\r\nBcc: bad@example.com')
        with self.assertRaises(ValueError):
            s.save_settings({'tls': 'none'})

    def test_smtp_tls_order_and_no_plaintext_fallback(self):
        for kind in ('starttls', 'ssl'):
            settings = dict(s.SETTINGS, tls=kind)
            with patch.object(s.smtplib, 'SMTP') as plain, patch.object(s.smtplib, 'SMTP_SSL') as encrypted:
                client = (plain if kind == 'starttls' else encrypted).return_value
                s.smtp_send(settings, s.EmailMessage())
                names = [call[0] for call in client.method_calls]
                if kind == 'starttls':
                    self.assertEqual(names[:5], ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'])
                    context = client.starttls.call_args.kwargs['context']
                else:
                    plain.assert_not_called()
                    context = encrypted.call_args.kwargs['context']
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        with patch.object(s.smtplib, 'SMTP') as smtp:
            smtp.return_value.starttls.side_effect = smtplib.SMTPNotSupportedError('no TLS')
            with self.assertRaises(smtplib.SMTPNotSupportedError):
                s.smtp_send(s.SETTINGS, s.EmailMessage())
            smtp.return_value.login.assert_not_called()
            smtp.return_value.send_message.assert_not_called()

    def test_smtp_quit_error_does_not_change_acceptance(self):
        with patch.object(s.smtplib, 'SMTP') as smtp:
            smtp.return_value.quit.side_effect = smtplib.SMTPServerDisconnected()
            s.smtp_send(s.SETTINGS, s.EmailMessage())
            smtp.return_value.send_message.assert_called_once()

    def test_send_success_auth_failure_uncertain_and_duplicates(self):
        cookie, csrf = self.login()
        job = self.job(cookie.split('=', 1)[1])
        data = dict(job_id=job['id'], recipient='to@example.com', subject='Test')
        for failure in (smtplib.SMTPAuthenticationError(535, b'secret'), OSError('secret'), None):
            job.update(status='ready', sent=False, delivery_uncertain=False)
            with patch.object(s, 'smtp_send', side_effect=failure) as smtp:
                self.assertEqual(self.request('/api/send', data, cookie, csrf)[0], 202)
                self.wait_job(job)
                smtp.assert_called_once()
                self.assertNotIn('secret', job['error'])
            if type(failure) is OSError or failure is None:
                self.assertEqual(self.request('/api/send', data, cookie, csrf)[0], 400)
                with self.assertRaises(ValueError):
                    s.start_scan(job['owner'], dict(job_id=job['id'], dpi=150, mode='Gray'))
        self.assertTrue(job['sent'])

    def test_busy_send_and_header_validation(self):
        cookie, csrf = self.login()
        job = self.job(cookie.split('=', 1)[1])
        data = dict(job_id=job['id'], recipient='to@example.com', subject='bad\r\nBcc: bad@example.com')
        self.assertEqual(self.request('/api/send', data, cookie, csrf)[0], 400)
        job['status'] = 'sending'
        for path in ('/api/send', '/api/delete'):
            self.assertEqual(self.request(path, data, cookie, csrf)[0], 400)

    def test_cleanup_idle_active_and_touch(self):
        job = self.job()
        job['updated'] = time.time() - 3601
        s.cleanup()
        self.assertNotIn(job['id'], s.JOBS)
        self.assertFalse((s.WORK / job['id']).exists())
        job = self.job()
        job.update(updated=0, status='scanning')
        s.cleanup()
        self.assertIn(job['id'], s.JOBS)
        job['status'] = 'ready'
        s.get_job(job['id'], 'owner')
        s.cleanup()
        self.assertIn(job['id'], s.JOBS)


if __name__ == '__main__':
    unittest.main()
