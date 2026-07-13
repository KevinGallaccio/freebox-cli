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
    handler = logging.NullHandler()
    redaction.install(handler)
    redaction.install(handler)
    assert sum(isinstance(f, redaction.RedactingFilter) for f in handler.filters) == 1


def test_handler_filter_scrubs_child_logger_records(capsys):
    # Regression: the filter must live on the HANDLER, because a filter on the
    # parent `fbx` logger is never applied to records propagated from child
    # loggers (fbx.auth, fbx.client). This mirrors the real CLI wiring.
    import io

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    redaction.install(handler)
    parent = logging.getLogger("fbx.test.tree")
    parent.handlers.clear()
    parent.addHandler(handler)
    parent.setLevel(logging.DEBUG)

    child = logging.getLogger("fbx.test.tree.client")  # a propagating child
    child.debug("opened session_token=hunter2 header X-Fbx-App-Auth: SEKRET")

    out = stream.getvalue()
    assert "hunter2" not in out
    assert "SEKRET" not in out
    assert "«redacted»" in out
