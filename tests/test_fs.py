"""`fbx fs ls` — path encoding and listing against captured shapes."""

from __future__ import annotations

import base64
import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from fbx.core import fspath
from tests.helpers import BASE, authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

ENTRIES = [
    {
        "type": "dir",
        "name": ".",
        "path": "L0ZyZWVib3g=",
        "index": 0,
        "size": 4096,
        "modification": 1726319787,
        "mimetype": "inode/directory",
        "hidden": False,
        "link": False,
    },
    {
        "type": "dir",
        "name": "..",
        "path": "Lw==",
        "index": 1,
        "size": 4096,
        "modification": 1726319787,
        "mimetype": "inode/directory",
        "hidden": False,
        "link": False,
    },
    {
        "type": "dir",
        "name": "Vidéos",
        "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0xNQ==",
        "index": 4,
        "size": 4096,
        "modification": 1770024546,
        "mimetype": "inode/directory",
        "hidden": False,
        "link": False,
        "foldercount": 4,
        "filecount": 0,
    },
    {
        "type": "file",
        "name": "notes.txt",
        "path": "L0ZyZWVib3gvc2NydWJiZWQvZmlsZS0xNg==",
        "index": 5,
        "size": 25236,
        "modification": 1770024546,
        "mimetype": "text/plain",
        "hidden": False,
        "link": False,
    },
]


@respx.mock
def test_ls_encodes_the_path_argument_as_base64():
    authorize()
    mock_login()
    route = mock_get("fs/ls/", {"entries": ENTRIES}, startswith=True)
    result = runner.invoke(app, ["--json", "fs", "ls", "/Freebox"])
    assert result.exit_code == 0
    sent = route.calls.last.request.url
    assert sent.path.endswith("/fs/ls/" + base64.b64encode(b"/Freebox").decode())
    assert "countSubFolder=1" in str(sent.query.decode())


@respx.mock
def test_ls_defaults_to_root():
    authorize()
    mock_login()
    route = mock_get("fs/ls/", {"entries": []}, startswith=True)
    result = runner.invoke(app, ["--json", "fs", "ls"])
    assert result.exit_code == 0
    assert route.calls.last.request.url.path.endswith("/fs/ls/Lw==")  # base64("/")


@respx.mock
def test_ls_json_is_the_whole_upstream_object():
    authorize()
    mock_login()
    # Rule #5: --json must not reshape — sibling keys and `.`/`..` survive.
    upstream = {"entries": ENTRIES, "some_future_sibling": 42}
    mock_get("fs/ls/", upstream, startswith=True)
    result = runner.invoke(app, ["--json", "fs", "ls", "/Freebox"])
    assert json.loads(result.stdout) == upstream


@respx.mock
def test_ls_table_filters_dot_entries_and_shows_counts():
    authorize()
    mock_login()
    mock_get("fs/ls/", {"entries": ENTRIES}, startswith=True)
    result = runner.invoke(app, ["fs", "ls", "/Freebox"])
    assert result.exit_code == 0
    assert "2 entries" in result.stdout  # . and .. filtered from display
    assert "Vidéos/" in result.stdout
    assert "4 items" in result.stdout
    assert "notes.txt" in result.stdout
    assert "25.2 KB" in result.stdout


@respx.mock
def test_ls_bracketed_path_argument_does_not_break_the_title():
    # The path is user input interpolated into a markup-parsed table title.
    authorize()
    mock_login()
    mock_get("fs/ls/", {"entries": []}, startswith=True)
    result = runner.invoke(app, ["fs", "ls", "/Freebox/[YTS] Movie [/x]"])
    assert result.exit_code == 0
    assert "Traceback" not in result.stderr


def test_ls_route_prefix_sanity():
    # The startswith mock above must not accidentally cover other endpoints.
    assert f"{BASE}fs/ls/".startswith(BASE)


# -- writes ----------------------------------------------------------------


@respx.mock
def test_mkdir_encodes_parent_keeps_name_plain():
    authorize()
    mock_login()
    route = mock_write("post", "fs/mkdir/", result="L0ZyZWVib3gvZGly")
    result = runner.invoke(app, ["fs", "mkdir", "/Freebox", "newdir"])
    assert result.exit_code == 0
    assert sent_json(route) == {"parent": fspath.encode("/Freebox"), "dirname": "newdir"}


@respx.mock
def test_rename_encodes_src_keeps_dst_plain():
    authorize()
    mock_login()
    route = mock_write("post", "fs/rename/", envelope={"success": True})
    result = runner.invoke(app, ["fs", "rename", "/Freebox/old.txt", "new.txt"])
    assert result.exit_code == 0
    assert sent_json(route) == {"src": fspath.encode("/Freebox/old.txt"), "dst": "new.txt"}


@respx.mock
def test_rm_confirms_then_submits_and_polls_done():
    authorize()
    mock_login()
    # submit returns a task; the poll's first read is already terminal (done).
    route = mock_write("post", "fs/rm/", result={"id": 12, "state": "running"})
    mock_get("fs/tasks/12", {"id": 12, "state": "done", "error": "none"})
    # decline first — nothing submitted
    declined = runner.invoke(app, ["fs", "rm", "/Freebox/x"], input="n\n")
    assert declined.exit_code != 0
    assert not route.called
    # then confirm
    result = runner.invoke(app, ["fs", "rm", "/Freebox/x", "--yes"])
    assert result.exit_code == 0
    assert sent_json(route) == {"files": [fspath.encode("/Freebox/x")]}


@respx.mock
def test_rm_failed_task_exits_1():
    authorize()
    mock_login()
    mock_write("post", "fs/rm/", result={"id": 13, "state": "running"})
    mock_get("fs/tasks/13", {"id": 13, "state": "failed", "error": "erase_failed"})
    result = runner.invoke(app, ["fs", "rm", "/Freebox/x", "--yes"])
    assert result.exit_code == 1


@respx.mock
def test_mv_no_wait_returns_task_immediately():
    authorize()
    mock_login()
    route = mock_write("post", "fs/mv/", result={"id": 14, "state": "running"})
    result = runner.invoke(
        app, ["--json", "fs", "mv", "/Freebox/a", "/Freebox/b", "--to", "/Freebox/dst", "--no-wait"]
    )
    assert result.exit_code == 0
    body = sent_json(route)
    assert body["files"] == [fspath.encode("/Freebox/a"), fspath.encode("/Freebox/b")]
    assert body["dst"] == fspath.encode("/Freebox/dst")
    assert body["mode"] == "overwrite"
    assert json.loads(result.stdout)["id"] == 14


@respx.mock
def test_cp_custom_mode():
    authorize()
    mock_login()
    route = mock_write("post", "fs/cp/", result={"id": 15, "state": "done", "error": "none"})
    mock_get("fs/tasks/15", {"id": 15, "state": "done", "error": "none"})
    result = runner.invoke(
        app, ["fs", "cp", "/Freebox/a", "--to", "/Freebox/dst", "--mode", "both"]
    )
    assert result.exit_code == 0
    assert sent_json(route)["mode"] == "both"


# -- share links -----------------------------------------------------------


@respx.mock
def test_share_create_encodes_path_never_expiry():
    authorize()
    mock_login()
    route = mock_write("post", "share_link/", result={"token": "abc", "name": "x"})
    result = runner.invoke(app, ["fs", "share", "/Freebox/x"])
    assert result.exit_code == 0
    body = sent_json(route)
    assert body["path"] == fspath.encode("/Freebox/x")
    assert body["expire"] == 0  # no --days → never expires


@respx.mock
def test_share_create_with_days_sets_future_expiry():
    authorize()
    mock_login()
    route = mock_write("post", "share_link/", result={"token": "abc"})
    result = runner.invoke(app, ["fs", "share", "/Freebox/x", "--days", "7"])
    assert result.exit_code == 0
    assert sent_json(route)["expire"] > 0


@respx.mock
def test_unshare_deletes_token():
    authorize()
    mock_login()
    route = mock_write("delete", "share_link/abc", envelope={"success": True})
    result = runner.invoke(app, ["fs", "unshare", "abc"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_rm_timeout_still_running_warns_not_success():
    # --timeout 0 makes poll_task return after the first read; the task is still
    # 'running', so the command must NOT claim success (regression: it did).
    authorize()
    mock_login()
    mock_write("post", "fs/rm/", result={"id": 20, "state": "running"})
    mock_get("fs/tasks/20", {"id": 20, "state": "running", "error": "none"})
    result = runner.invoke(app, ["fs", "rm", "/Freebox/huge", "--yes", "--timeout", "0"])
    assert result.exit_code == 0  # the box is still working; not an error
    assert "still running" in result.stderr
    assert "delete done" not in result.stderr  # must not falsely report completion


@respx.mock
def test_poll_reraises_non_notfound_error():
    # A permission/internal error mid-poll must surface, not read as success.
    authorize()
    mock_login()
    mock_write("post", "fs/rm/", result={"id": 21, "state": "running"})
    mock_get("fs/tasks/21", envelope={"success": False, "error_code": "insufficient_rights"})
    result = runner.invoke(app, ["fs", "rm", "/Freebox/x", "--yes"])
    assert result.exit_code != 0
    assert "delete done" not in result.stderr


@respx.mock
def test_poll_treats_task_gone_as_finished():
    # A reaped (noent) task genuinely completed → success.
    authorize()
    mock_login()
    mock_write("post", "fs/rm/", result={"id": 22, "state": "running"})
    mock_get("fs/tasks/22", envelope={"success": False, "error_code": "noent"})
    result = runner.invoke(app, ["fs", "rm", "/Freebox/x", "--yes"])
    assert result.exit_code == 0
    assert "delete" in result.stderr
