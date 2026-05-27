import pytest
import asyncio
from pathlib import Path
import tempfile
import os

from session.session_manager import SessionManager
from schemas.session_schemas import SessionStatus


@pytest.fixture
def tmp_session_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_STORAGE_PATH", str(tmp_path))
    from config import Settings
    import config
    config.settings.session_storage_path = str(tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_create_and_get_session(tmp_session_dir):
    sm = SessionManager.__new__(SessionManager)
    from pathlib import Path
    sm._path = lambda sid: tmp_session_dir / f"{sid}.json"

    session = await sm.create_session(
        "Paint a cat in Da Vinci style",
        {"max_rounds": 5, "title": "Da Vinci Cat"}
    )
    assert session.user_prompt == "Paint a cat in Da Vinci style"
    assert session.max_rounds == 5

    loaded = await sm.get_session(session.session_id)
    assert loaded.session_id == session.session_id
    assert loaded.title == "Da Vinci Cat"


@pytest.mark.asyncio
async def test_list_sessions(tmp_session_dir):
    sm = SessionManager.__new__(SessionManager)
    sm._path = lambda sid: tmp_session_dir / f"{sid}.json"

    s1 = await sm.create_session("Prompt A", {"max_rounds": 3})
    s2 = await sm.create_session("Prompt B", {"max_rounds": 5})

    summaries = await sm.list_sessions()
    ids = [s.session_id for s in summaries]
    assert s1.session_id in ids
    assert s2.session_id in ids


@pytest.mark.asyncio
async def test_delete_session(tmp_session_dir):
    sm = SessionManager.__new__(SessionManager)
    sm._path = lambda sid: tmp_session_dir / f"{sid}.json"

    session = await sm.create_session("Test delete", {})
    await sm.delete_session(session.session_id)

    with pytest.raises(ValueError):
        await sm.get_session(session.session_id)
