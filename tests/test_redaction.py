"""Token redaction — a leaked token in a log is a real incident."""

from __future__ import annotations

import logging

from fbx.core import redaction


def test_redacts_json_secrets():
    text = '{"session_token": "abc123", "firmware": "4.12.2"}'
    out = redaction.redact(text)
    assert "abc123" not in out
    assert "4.12.2" in out  # non-secrets untouched


def test_redacts_header_and_kv_forms():
    assert "SECRET" not in redaction.redact("X-Fbx-App-Auth: SECRETvalue")
    assert "SECRET" not in redaction.redact("app_token=SECRETvalue")
    assert "SECRET" not in redaction.redact('"password":"SECRETvalue"')


def test_filter_scrubs_log_record(caplog):
    logger = logging.getLogger("fbx.test.redaction")
    redaction.install(logger)
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.DEBUG)

    with caplog.at_level(logging.DEBUG, logger="fbx.test.redaction"):
        logger.debug('opened session_token=hunter2 for app')
    assert "hunter2" not in caplog.text


def test_install_is_idempotent():
    logger = logging.getLogger("fbx.test.redaction.idem")
    redaction.install(logger)
    redaction.install(logger)
    assert sum(isinstance(f, redaction.RedactingFilter) for f in logger.filters) == 1
