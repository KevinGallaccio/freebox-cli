"""`fbx downloads` — task list and stats against captured shapes."""

from __future__ import annotations

import json
import os
import tempfile

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from fbx.core import fspath
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_form, sent_json

runner = CliRunner()

TASKS = [
    {
        "id": 1,
        "type": "http",
        "status": "error",
        "name": "file-1",
        "size": 425860000,
        "rx_bytes": 0,
        "tx_bytes": 0,
        "rx_rate": 0,
        "tx_rate": 0,
        "rx_pct": 0,
        "tx_pct": 10000,
        "eta": 0,
        "queue_pos": 1,
        "io_priority": "normal",
        "stop_ratio": 0,
        "archive_password": "",
        "download_dir": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0x",
        "info_hash": "",
        "piece_length": 0,
        "created_ts": 1726316875,
        "error": "none",
    },
    {
        "id": 2,
        "type": "bt",
        "status": "downloading",
        "name": "file-2",
        "size": 1000000000,
        "rx_rate": 2500000,
        "rx_pct": 5000,
        "eta": 200,
        "error": "none",
    },
]

STATS = {
    "nb_tasks": 2,
    "nb_tasks_error": 1,
    "nb_tasks_active": 1,
    "nb_tasks_downloading": 1,
    "nb_tasks_seeding": 0,
    "nb_tasks_queued": 0,
    "nb_tasks_stopped": 0,
    "nb_tasks_done": 0,
    "rx_rate": 2500000,
    "tx_rate": 0,
    "throttling_mode": "normal",
    "throttling_rate": {"rx_rate": 0, "tx_rate": 0},
    "throttling_is_scheduled": False,
    "dht_stats": {"enabled": False, "node_count": 0},
    "nb_peer": 4,
    "conn_ready": True,
    "nb_rss": 0,
    "nb_rss_items_unread": 0,
    "nzb_config_status": {"status": "not_checked", "error": "none"},
}


@respx.mock
def test_list_json_is_whole_result():
    authorize()
    mock_login()
    mock_get("downloads/", TASKS)
    result = runner.invoke(app, ["--json", "downloads", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == TASKS


@respx.mock
def test_list_table_shows_progress_from_rx_pct():
    authorize()
    mock_login()
    mock_get("downloads/", TASKS)
    result = runner.invoke(app, ["downloads", "list"])
    assert result.exit_code == 0
    assert "50%" in result.stdout  # rx_pct is per-10000
    assert "file-1" in result.stdout
    assert "error" in result.stdout


@respx.mock
def test_progress_floors_instead_of_rounding_up():
    authorize()
    mock_login()
    nearly_done = [dict(TASKS[1], rx_pct=9999)]
    mock_get("downloads/", nearly_done)
    result = runner.invoke(app, ["downloads", "list"])
    assert result.exit_code == 0
    assert "99%" in result.stdout  # 9999/10000 must not display as done
    assert "100%" not in result.stdout


@respx.mock
def test_empty_list_normalizes():
    authorize()
    mock_login()
    mock_get("downloads/", envelope={"success": True})
    result = runner.invoke(app, ["--json", "downloads", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


@respx.mock
def test_stats_table_and_json():
    authorize()
    mock_login()
    mock_get("downloads/stats", STATS)
    result = runner.invoke(app, ["--json", "downloads", "stats"])
    assert json.loads(result.stdout) == STATS
    result = runner.invoke(app, ["downloads", "stats"])
    assert result.exit_code == 0
    assert "2.5 MB/s" in result.stdout
    assert "normal" in result.stdout


# -- writes ----------------------------------------------------------------


@respx.mock
def test_add_url_is_form_encoded_with_base64_dir():
    authorize()
    mock_login()
    route = mock_write("post", "downloads/add", result={"id": 5})
    result = runner.invoke(
        app, ["downloads", "add", "https://example.com/x.iso", "--dir", "/Freebox/Téléchargements"]
    )
    assert result.exit_code == 0
    form = sent_form(route)
    assert form["download_url"] == "https://example.com/x.iso"
    # download_dir must be base64-encoded on the wire
    assert form["download_dir"] == fspath.encode("/Freebox/Téléchargements")


@respx.mock
def test_add_magnet_and_recursive():
    authorize()
    mock_login()
    route = mock_write("post", "downloads/add", result={"id": 6})
    result = runner.invoke(
        app, ["downloads", "add", "magnet:?xt=urn:btih:deadbeef", "--recursive"]
    )
    assert result.exit_code == 0
    form = sent_form(route)
    assert form["download_url"].startswith("magnet:?")
    assert form["recursive"] == "true"


@respx.mock
def test_add_file_is_multipart():
    authorize()
    mock_login()
    route = mock_write("post", "downloads/add", result={"id": 7})
    fd, path = tempfile.mkstemp(suffix=".torrent")
    os.write(fd, b"d8:announce...")
    os.close(fd)
    try:
        result = runner.invoke(app, ["downloads", "add-file", path])
    finally:
        os.unlink(path)
    assert result.exit_code == 0
    assert route.called
    assert "multipart/form-data" in route.calls.last.request.headers["content-type"]


@respx.mock
def test_pause_sets_status_stopped():
    authorize()
    mock_login()
    route = mock_write("put", "downloads/", startswith=True, result={"status": "stopping"})
    result = runner.invoke(app, ["downloads", "pause", "3"])
    assert result.exit_code == 0
    assert sent_json(route) == {"status": "stopped"}


@respx.mock
def test_resume_sets_status_downloading():
    authorize()
    mock_login()
    route = mock_write("put", "downloads/", startswith=True, result={"status": "downloading"})
    result = runner.invoke(app, ["downloads", "resume", "3"])
    assert result.exit_code == 0
    assert sent_json(route) == {"status": "downloading"}


@respx.mock
def test_priority_sets_io_priority():
    authorize()
    mock_login()
    route = mock_write("put", "downloads/", startswith=True, result={"io_priority": "high"})
    result = runner.invoke(app, ["downloads", "priority", "3", "high"])
    assert result.exit_code == 0
    assert sent_json(route) == {"io_priority": "high"}


@respx.mock
def test_rm_keeps_files():
    authorize()
    mock_login()
    route = mock_write("delete", "downloads/3", envelope={"success": True})
    result = runner.invoke(app, ["downloads", "rm", "3"])
    assert result.exit_code == 0
    assert route.called
    # the erase variant must NOT be what we hit
    assert route.calls.last.request.url.path.endswith("/downloads/3")


@respx.mock
def test_erase_confirms_then_hits_erase_endpoint():
    authorize()
    mock_login()
    route = mock_write("delete", "downloads/3/erase", envelope={"success": True})
    # decline first
    declined = runner.invoke(app, ["downloads", "erase", "3"], input="n\n")
    assert declined.exit_code != 0
    assert not route.called
    # then with --yes
    result = runner.invoke(app, ["downloads", "erase", "3", "--yes"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_throttle_switch():
    authorize()
    mock_login()
    route = mock_write("put", "downloads/throttling", result={"throttling": "slow"})
    result = runner.invoke(app, ["downloads", "throttle", "slow"])
    assert result.exit_code == 0
    assert sent_json(route) == {"throttling": "slow"}
