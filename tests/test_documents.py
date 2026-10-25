"""Document editing, asynchronous preparation, image compression and searchable PDF tests."""
import io
from pathlib import Path
import random
import shutil
import subprocess
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
import test_scanmail as legacy
from pypdf import PdfReader

s = legacy.s


class DocumentTests(unittest.TestCase):
    setUp = legacy.ScanMailTests.setUp
    request = legacy.ScanMailTests.request
    login = legacy.ScanMailTests.login
    job = legacy.ScanMailTests.job
    wait_job = legacy.ScanMailTests.wait_job

    def edit(self, job, action, **data):
        return s.edit_document(job, dict(action=action, revision=job.get('revision', 0), **data))

    def test_rotate_reorder_delete_and_pdf_geometry(self):
        job = self.job(pages=3)
        for n, color in enumerate(('red', 'green', 'blue'), 1):
            Image.new('RGB', (300, 600), color).save(s.WORK / job['id'] / f'{n}.jpg')
        self.edit(job, 'rotate', page=1)
        self.edit(job, 'move', page=3, destination=1)
        reader = PdfReader(io.BytesIO(s.make_pdf(job)))
        self.assertEqual(len(reader.pages), 3)
        self.assertEqual(tuple(reader.pages[1].mediabox)[2:], (288, 144))
        first = next(iter(reader.pages[0].images)).image.convert('RGB')
        self.assertGreater(first.getpixel((50, 50))[2], 200)
        self.edit(job, 'delete', page=2)
        self.assertEqual(s.page_order(job), [3, 2])
        self.assertFalse((s.WORK / job['id'] / '1.jpg').exists())
        self.assertFalse(job['pdf_ready'])
        self.assertEqual(len(PdfReader(io.BytesIO(s.make_pdf(job))).pages), 2)

    def test_four_rotations_restore_dimensions(self):
        job = self.job()
        for _ in range(4):
            self.edit(job, 'rotate', page=1)
        with s.oriented_image(job, 1) as image:
            self.assertEqual(image.size, (300, 600))

    def test_stale_revision_and_invalid_positions_are_rejected(self):
        job = self.job()
        self.edit(job, 'rotate', page=1)
        for data in (dict(action='delete', page=1, revision=0),
                     dict(action='delete', page='../settings', revision=1),
                     dict(action='move', page=1, destination=2, revision=1)):
            with self.assertRaises(ValueError):
                s.edit_document(job, data)
        self.assertEqual(job['pages'], 1)

    def test_frozen_and_busy_documents_cannot_be_edited(self):
        job = self.job()
        for status, sent, uncertain in (('processing', False, False), ('sending', False, False),
                                        ('sent', True, False), ('error', False, True)):
            job.update(status=status, sent=sent, delivery_uncertain=uncertain)
            with self.assertRaises(ValueError):
                self.edit(job, 'rotate', page=1)

    def test_preview_edit_and_prepare_require_owner_and_csrf(self):
        cookie, csrf = self.login()
        job = self.job()
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '/preview/1', cookie=cookie)[0], 404)
        for endpoint in ('/api/edit', '/api/prepare'):
            body = dict(job_id=job['id'], action='rotate', page=1, revision=0)
            self.assertEqual(self.request(endpoint, body, cookie, csrf)[0], 400)
            self.assertEqual(self.request(endpoint, body, cookie)[0], 403)
        job['owner'] = cookie.split('=', 1)[1]
        self.edit(job, 'rotate', page=1)
        code, image, _ = self.request('/api/jobs/' + job['id'] + '/preview/1', cookie=cookie)
        self.assertEqual(code, 200)
        self.assertEqual(Image.open(io.BytesIO(image)).size, (600, 300))
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '/preview/2', cookie=cookie)[0], 404)

    def test_small_pdf_is_smaller_with_same_physical_page_size(self):
        job = self.job()
        job['dpi'] = 300
        image = Image.frombytes('RGB', (1200, 1800), random.Random(42).randbytes(1200 * 1800 * 3))
        image.save(s.WORK / job['id'] / '1.jpg', quality=94)
        high = s.make_pdf(job)
        self.edit(job, 'options', quality='small', ocr=False)
        small = s.make_pdf(job)
        self.assertLess(len(small), len(high) * .5)
        self.assertEqual(PdfReader(io.BytesIO(small)).pages[0].mediabox,
                         PdfReader(io.BytesIO(high)).pages[0].mediabox)
        self.assertEqual(s.job_info(job)['pdf_bytes'], len(small))

    def test_prepare_publishes_pdf_only_after_success(self):
        cookie, csrf = self.login()
        job = self.job(cookie.split('=', 1)[1])
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '/pdf', cookie=cookie)[0], 409)
        self.assertEqual(self.request('/api/prepare', {'job_id':job['id']}, cookie, csrf)[0], 202)
        self.wait_job(job)
        self.assertTrue(job['pdf_ready'])
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '/pdf', cookie=cookie)[0], 200)

    def test_mock_ocr_is_invisible_searchable_and_cached_across_quality_changes(self):
        job = self.job()
        job.update(ocr=True, status='processing')
        def engine(command, **kwargs):
            kwargs['stdout'].write(b'level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t20\t150\t20\t95\tScanmail\n')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(s.subprocess, 'run', side_effect=engine) as run:
            reader = PdfReader(io.BytesIO(s.make_pdf(job)))
            self.assertIn('Scanmail', reader.pages[0].extract_text())
            self.assertIn(b'3 Tr', reader.pages[0].get_contents().get_data())
            job['status'] = 'ready'
            self.edit(job, 'options', quality='small', ocr=True)
            s.make_pdf(job)
            run.assert_called_once()
            self.edit(job, 'rotate', page=1)
            s.make_pdf(job)
            self.assertEqual(run.call_count, 2)

    def test_ocr_timeout_fails_cleanly_and_allows_switching_it_off(self):
        job = self.job()
        job.update(ocr=True, status='processing')
        with patch.object(s.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tesseract', 90)):
            s.prepare_document(job)
        self.assertEqual(job['status'], 'error')
        self.assertFalse(job.get('pdf_ready', False))
        self.assertFalse((s.WORK / job['id'] / 'ocr-input.png').exists())
        self.edit(job, 'options', ocr=False)
        s.prepare_document(job)
        self.assertTrue(job['pdf_ready'])

    @unittest.skipUnless(shutil.which('tesseract'), 'Tesseract not installed')
    def test_real_ocr_text_can_be_extracted_from_pdf(self):
        job = self.job()
        image = Image.new('RGB', (1400, 500), 'white')
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 72)
        ImageDraw.Draw(image).text((80, 140), 'SCANMAIL TEST 12345', fill='black', font=font)
        image.save(s.WORK / job['id'] / '1.jpg', quality=95)
        job['ocr'] = True
        payload = s.make_pdf(job)
        text = PdfReader(io.BytesIO(payload)).pages[0].extract_text()
        self.assertIn('SCANMAIL', text)
        self.assertIn('12345', text)
