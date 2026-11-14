"""Bound native PDF/OCR work and clean its private per-document scratch space."""
import multiprocessing
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from .documents import DocumentError

DOCUMENT_PARSE_TIMEOUT = 120


def _parse_document(connection, name, data, mime, scratch):
    # The parent owns this private directory and removes it even after a crash.
    # pytesseract and its subprocess inherit it for temporary OCR images.
    tempfile.tempdir = scratch
    for variable in ('TMPDIR', 'TEMP', 'TMP'):
        os.environ[variable] = scratch
    if os.name == 'posix':
        os.setsid()
    from .documents import extract_source
    try:
        source, notes = extract_source(name, data, mime)
        connection.send(('ok', source, notes))
    except DocumentError as error:
        connection.send(('error', str(error), error.status, error.code))
    except Exception:
        # Parser/library messages can contain document text. Never transport them.
        connection.send(('error', 'This document could not be read. Try another export.', 422, 'invalid_document'))
    finally:
        connection.close()


def _stop_process_tree(process):
    if os.name == 'posix':
        try:
            # The actual parser establishes a separate session before parsing.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.is_alive():
        # Terminate OCR descendants before their Python parent on Windows.
        command = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'taskkill.exe'
        try:
            subprocess.run([str(command), '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if process.is_alive():
        process.terminate()
    process.join(2)
    if process.is_alive():
        process.kill()
        process.join(2)


def _run_parser_process(name, data, mime, *, timeout, worker, scratch):
    # Spawn avoids forking the API's event loop, threads and active requests.
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=worker, args=(sender, name, data, mime, scratch), daemon=True)
    try:
        process.start()
        sender.close()
        if not receiver.poll(timeout):
            raise DocumentError('Reading this document took too long. Try a smaller assessment plan or searchable export.',
                                503, 'document_parse_timeout')
        try:
            message = receiver.recv()
        except (EOFError, OSError):
            raise DocumentError('The document reader stopped unexpectedly. Try another export or retry.',
                                503, 'document_parser_unavailable') from None
        if isinstance(message, tuple) and len(message) == 3 and message[0] == 'ok':
            return message[1], message[2]
        if isinstance(message, tuple) and len(message) == 4 and message[0] == 'error':
            raise DocumentError(message[1], message[2], message[3])
        raise DocumentError('The document reader could not finish. Retry with another export.',
                            503, 'document_parser_unavailable')
    except (OSError, RuntimeError):
        raise DocumentError('The document reader is temporarily unavailable. Try again shortly.',
                            503, 'document_parser_unavailable') from None
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None:
            # A reply can precede interpreter cleanup. Bound cleanup as well.
            process.join(1)
            if process.is_alive() or process.exitcode != 0:
                _stop_process_tree(process)
            if not process.is_alive():
                process.close()


def _run_parser(name, data, mime=None, *, timeout=DOCUMENT_PARSE_TIMEOUT, worker=_parse_document):
    with tempfile.TemporaryDirectory(prefix='academiq-parse-') as scratch:
        return _run_parser_process(name, data, mime, timeout=timeout, worker=worker, scratch=scratch)


def extract_source_isolated(name, data, mime=None):
    return _run_parser(name, data, mime)
