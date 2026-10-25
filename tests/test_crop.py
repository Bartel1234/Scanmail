"""Crop pixels before PDF encoding and OCR; preserve source for explicit undo."""
import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
import test_scanmail as legacy

s = legacy.s


class CropTests(unittest.TestCase):
    setUp = legacy.ScanMailTests.setUp
    request = legacy.ScanMailTests.request
    login = legacy.ScanMailTests.login
    job = legacy.ScanMailTests.job

    def edit(self, job, action, **data):
        return s.edit_document(job, dict(action=action, revision=job.get('revision', 0), **data))

    def test_crop_pixels_pdf_size_and_restore_source(self):
        job = self.job()
        source = s.WORK / job['id'] / '1.jpg'
        original = source.read_bytes()
        self.edit(job, 'crop', page=1, box=[.1, .2, .6, .8])
        with s.oriented_image(job, 1) as image:
            self.assertEqual(image.size, (150, 360))
        with s.oriented_image(job, 1, full=True) as image:
            self.assertEqual(image.size, (300, 600))
        reader = PdfReader(io.BytesIO(s.make_pdf(job)))
        self.assertEqual(tuple(reader.pages[0].mediabox)[2:], (72, 172.8))
        self.assertEqual(next(iter(reader.pages[0].images)).image.size, (150, 360))
        self.assertEqual(source.read_bytes(), original)
        self.edit(job, 'uncrop', page=1)
        with s.oriented_image(job, 1) as image:
            self.assertEqual(image.size, (300, 600))

    def test_rotated_editor_coordinates_map_to_source_and_survive_reordering(self):
        job = self.job(pages=2)
        self.edit(job, 'rotate', page=1)
        self.edit(job, 'crop', page=1, box=[.2, .1, .8, .6])
        self.assertEqual(job['crops'][1], [.1, .2, .6, .8])
        with s.oriented_image(job, 1) as image:
            self.assertEqual(image.size, (360, 150))
        self.edit(job, 'move', page=1, destination=2)
        self.assertEqual(s.job_info(job)['crop_boxes'][1], [.2, .1, .8, .6])
        self.edit(job, 'rotate', page=2)
        self.assertEqual(s.job_info(job)['crop_boxes'][1], [.4, .2, .9, .8])
        self.edit(job, 'delete', page=1)
        self.assertEqual(s.page_order(job), [1])
        self.assertEqual(s.job_info(job)['crop_boxes'][0], [.4, .2, .9, .8])

    def test_crop_rejects_invalid_values_and_stale_edits(self):
        job = self.job()
        for box in (None, [], [0, 0, 1], [-.1,0,1,1], [0,0,1.1,1],
                    [0,0,0,1], [0,0,.00001,1], [0,0,float('nan'),1],
                    [0,0,float('inf'),1], [False,0,1,1], ['0',0,1,1]):
            with self.subTest(box=box), self.assertRaises(ValueError):
                self.edit(job, 'crop', page=1, box=box)
        self.edit(job, 'rotate', page=1)
        with self.assertRaises(ValueError):
            s.edit_document(job, dict(action='crop', revision=0, page=1, box=[0,0,1,1]))
        self.assertNotIn('crops', job)

    def test_full_preview_and_crop_require_owner_csrf_and_editable_job(self):
        cookie, csrf = self.login()
        job = self.job()
        body = dict(job_id=job['id'], action='crop', revision=0, page=1, box=[.1,.1,.9,.9])
        self.assertEqual(self.request('/api/jobs/' + job['id'] + '/full/1', cookie=cookie)[0], 404)
        self.assertEqual(self.request('/api/edit', body, cookie, csrf)[0], 400)
        job['owner'] = cookie.split('=', 1)[1]
        self.assertEqual(self.request('/api/edit', body, cookie)[0], 403)
        self.assertEqual(self.request('/api/edit', body, cookie, csrf)[0], 200)
        full = self.request('/api/jobs/' + job['id'] + '/full/1', cookie=cookie)
        cropped = self.request('/api/jobs/' + job['id'] + '/preview/1', cookie=cookie)
        self.assertEqual(Image.open(io.BytesIO(full[1])).size, (300,600))
        self.assertEqual(Image.open(io.BytesIO(cropped[1])).size, (240,480))
        job.update(sent=True, status='sent')
        with self.assertRaises(ValueError):
            self.edit(job, 'uncrop', page=1)

    @unittest.skipUnless(shutil.which('tesseract'), 'Tesseract not installed')
    def test_real_ocr_removes_previously_recognized_text_outside_crop(self):
        job = self.job()
        image = Image.new('RGB', (1400, 700), 'white')
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 72)
        draw = ImageDraw.Draw(image)
        draw.text((80, 100), 'PRIVATE 98765', font=font, fill='black')
        draw.text((80, 440), 'KEEP 12345', font=font, fill='black')
        image.save(s.WORK / job['id'] / '1.jpg', quality=95)
        job['ocr'] = True
        before = PdfReader(io.BytesIO(s.make_pdf(job))).pages[0].extract_text()
        self.assertIn('PRIVATE', before)
        self.assertIn('KEEP', before)
        self.edit(job, 'crop', page=1, box=[0, .5, 1, 1])
        self.assertFalse(list((s.WORK / job['id']).glob('ocr-1-*.tsv')))
        after_pdf = PdfReader(io.BytesIO(s.make_pdf(job)))
        after = after_pdf.pages[0].extract_text()
        self.assertIn('KEEP', after)
        self.assertNotIn('PRIVATE', after)
        self.assertNotIn('98765', after)
        self.assertEqual(next(iter(after_pdf.pages[0].images)).image.size, (1400,350))
        self.edit(job, 'uncrop', page=1)
        restored = PdfReader(io.BytesIO(s.make_pdf(job))).pages[0].extract_text()
        self.assertIn('PRIVATE', restored)
