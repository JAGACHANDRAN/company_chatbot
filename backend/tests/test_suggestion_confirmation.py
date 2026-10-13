import pytest
import asyncio
from app.routes.chat import execute_rag_pipeline
from app.services.session_cache import store_last_suggestions, clear_session, clear_last_suggestions


def test_suggestion_confirmation_via_session_cache():
    session_id = "test_sugg_session_1"
    clear_session(session_id)
    clear_last_suggestions(session_id)

    # Simulate bot suggesting 'Delphi Tvs'
    store_last_suggestions(session_id, ["Delphi Tvs"], original_query="dephli tvs", unfound_names=["dephli tvs"])

    # User replies 'yes'
    res = asyncio.run(execute_rag_pipeline("yes", session_id=session_id))
    assert res.found is True
    assert res.count == 24
    assert "Delphi Tvs" in res.message


def test_suggestion_confirmation_via_history():
    session_id = "test_sugg_session_2"
    clear_session(session_id)
    clear_last_suggestions(session_id)

    hist = [
        {"role": "user", "content": "dephli tvs"},
        {"role": "assistant", "content": "No matching records found for 'dephli tvs'. Did you mean: Delphi Tvs?"}
    ]

    # User replies 'yes please'
    res = asyncio.run(execute_rag_pipeline("yes please", history=hist, session_id=session_id))
    assert res.found is True
    assert res.count == 24
    assert "Delphi Tvs" in res.message


def test_spelling_mistake_auto_correction():
    session_id = "test_sugg_session_3"
    clear_session(session_id)
    clear_last_suggestions(session_id)

    # User directly searches with spelling mistake 'dephli tvs'
    res = asyncio.run(execute_rag_pipeline("dephli tvs", session_id=session_id))
    assert res.found is True
    assert res.count == 24
    assert "Delphi Tvs" in res.message
    assert "corrected spelling from 'dephli tvs'" in res.message
