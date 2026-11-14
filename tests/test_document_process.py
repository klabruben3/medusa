import io
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from app.utils.document_process import _run_parser, extract_source_isolated
from app.utils.documents import DocumentError


def crash(connection, *_):
    os._exit(7)


def hang(connection, *_):
    time.sleep(30)


def malformed(connection, name, data, mime, scratch):
    (Path(scratch) / 'private-ocr.png').write_bytes(data)
    connection.send(('unknown', 'not a parser result'))
    connection.close()


class DocumentProcessTests(unittest.TestCase):
    def test_actual_searchable_pdf_preserves_text_and_source_provenance(self):
        from reportlab.pdfgen import canvas
        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.drawString(40, 700, 'ABC123 Assessment plan. Class test: 40 marks. Weight: 100%.')
        pdf.save()
        source, notes = extract_source_isolated('plan.pdf', data.getvalue(), 'application/pdf')
        self.assertIn('40 marks', source['text'])
        self.assertTrue(source['blocks'])
        self.assertTrue(all(block['source_file'] == 'plan.pdf' for block in source['blocks']))
        self.assertEqual(notes, [])

    def test_known_document_rejection_preserves_status_and_code(self):
        with self.assertRaises(DocumentError) as result:
            extract_source_isolated('plan.exe', b'fixture', 'application/octet-stream')
        self.assertEqual(result.exception.status, 415)
        self.assertEqual(result.exception.code, 'unsupported_file')

    def test_crashed_native_child_is_a_retryable_failure_and_does_not_kill_the_parent(self):
        before = {child.pid for child in multiprocessing.active_children()}
        with self.assertRaises(DocumentError) as result:
            _run_parser('plan.pdf', b'private-fixture', worker=crash, timeout=10)
        self.assertEqual(result.exception.code, 'document_parser_unavailable')
        self.assertEqual(result.exception.status, 503)
        self.assertNotIn('private-fixture', str(result.exception))
        self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)

    def test_hung_child_is_terminated_and_does_not_remain_after_timeout(self):
        before = {child.pid for child in multiprocessing.active_children()}
        with self.assertRaises(DocumentError) as result:
            _run_parser('plan.pdf', b'fixture', worker=hang, timeout=.2)
        self.assertEqual(result.exception.code, 'document_parse_timeout')
        self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)

    def test_malformed_child_result_never_becomes_a_completed_document(self):
        with self.assertRaises(DocumentError) as result:
            _run_parser('plan.pdf', b'fixture', worker=malformed, timeout=10)
        self.assertEqual(result.exception.code, 'document_parser_unavailable')

    def test_private_ocr_scratch_is_removed_after_a_failed_child(self):
        created = []
        original = tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            directory = original(*args, **kwargs)
            created.append(Path(directory.name))
            return directory
        with patch('app.utils.document_process.tempfile.TemporaryDirectory', side_effect=temporary):
            with self.assertRaises(DocumentError):
                _run_parser('plan.pdf', b'private-fixture', worker=malformed, timeout=30)
        self.assertTrue(created)
        self.assertTrue(all(not directory.exists() for directory in created))
