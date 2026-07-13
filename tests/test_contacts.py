"""`fbx contacts` — the address book (empty on the reference box)."""

from __future__ import annotations

import json

import respx
from typer.testing import CliRunner

from fbx.cli.main import app
from tests.helpers import authorize, mock_get, mock_login, mock_write, sent_json

runner = CliRunner()

CONTACTS = [
    {
        "id": 1,
        "display_name": "person-1",
        "first_name": "person",
        "last_name": "1",
        "company": "ACME",
        "numbers": [{"id": 1, "number": "+3310000001", "type": "mobile"}],
    }
]


@respx.mock
def test_empty_book_normalizes_to_empty_list():
    authorize()
    mock_login()
    # Captured reality: empty address book → bare {"success": true}, no result.
    mock_get("contact/", envelope={"success": True})
    result = runner.invoke(app, ["--json", "contacts", "list"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


@respx.mock
def test_empty_book_table_renders():
    authorize()
    mock_login()
    mock_get("contact/", envelope={"success": True})
    result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0
    assert "Contacts — 0" in result.stdout


@respx.mock
def test_list_table_shows_contact():
    authorize()
    mock_login()
    mock_get("contact/", CONTACTS)
    result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0
    assert "person-1" in result.stdout
    assert "ACME" in result.stdout
    assert "+3310000001" in result.stdout


# -- writes ----------------------------------------------------------------


@respx.mock
def test_add_posts_fields():
    authorize()
    mock_login()
    route = mock_write("post", "contact/", result={"id": 10, "display_name": "Sandy Kilo"})
    result = runner.invoke(
        app, ["contacts", "add", "Sandy Kilo", "--first", "Sandy", "--last", "Kilo"]
    )
    assert result.exit_code == 0
    assert sent_json(route) == {
        "display_name": "Sandy Kilo",
        "first_name": "Sandy",
        "last_name": "Kilo",
    }


@respx.mock
def test_edit_puts_partial():
    authorize()
    mock_login()
    route = mock_write("put", "contact/", startswith=True, result={"id": 4})
    result = runner.invoke(app, ["contacts", "edit", "4", "--company", "Freebox"])
    assert result.exit_code == 0
    assert sent_json(route) == {"company": "Freebox"}


@respx.mock
def test_rm_deletes():
    authorize()
    mock_login()
    route = mock_write("delete", "contact/4", envelope={"success": True})
    result = runner.invoke(app, ["contacts", "rm", "4"])
    assert result.exit_code == 0
    assert route.called


@respx.mock
def test_contacts_write_needs_contacts_permission():
    authorize()
    mock_login(permissions={"contacts": False})
    result = runner.invoke(app, ["contacts", "add", "X"])
    assert result.exit_code == 4
