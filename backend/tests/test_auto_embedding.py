import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.embeddings import (
    strip_embedding,
    embed_dataset_records_background,
    backfill_missing_embeddings_job
)


def test_strip_embedding():
    """Verify strip_embedding removes 768-d embedding field from dicts and lists."""
    dummy_doc = {
        "company": "Synthetic Alpha Tech",
        "email": "contact@synthetic-alpha.test",
        "embedding": [0.123] * 768,
        "nested": {
            "embedding": [0.456] * 768,
            "city": "Chennai"
        }
    }
    cleaned = strip_embedding(dummy_doc)
    assert "embedding" not in cleaned
    assert "embedding" not in cleaned["nested"]
    assert cleaned["company"] == "Synthetic Alpha Tech"
    assert cleaned["nested"]["city"] == "Chennai"


@pytest.mark.anyio
async def test_auto_embedding_background_mocked():
    """Verify background batch embedding on synthetic dataset upload."""
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_db.__getitem__.return_value = mock_col

    synthetic_docs = [
        {
            "_id": f"syn_doc_{i}",
            "company": f"Synthetic Beta Corp {i}",
            "person": f"Test User {i}",
            "designation": "Quality Engineer",
            "phone": f"+91 90000 0000{i}",
            "email": f"user{i}@synthetic-beta.test",
            "city": "Hosur",
            "state": "Tamil Nadu"
        }
        for i in range(10)
    ]

    mock_col.find.return_value = synthetic_docs

    with patch("app.services.embeddings.get_database", return_value=mock_db), \
         patch("app.services.embeddings.is_ollama_available", return_value=True), \
         patch("app.services.embeddings.embed_documents_async", new_callable=AsyncMock) as mock_embed:
        
        mock_embed.return_value = [[0.05] * 768 for _ in range(10)]
        res = await embed_dataset_records_background("synthetic_dataset_123", batch_size=32)

        assert res["status"] == "completed"
        assert res["count"] == 10
        assert mock_col.bulk_write.called


@pytest.mark.anyio
async def test_auto_embedding_ollama_offline_handling():
    """Verify graceful handling when Ollama is offline (marks status as pending)."""
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_db.__getitem__.return_value = mock_col
    mock_col.count_documents.return_value = 5

    with patch("app.services.embeddings.get_database", return_value=mock_db), \
         patch("app.services.embeddings.is_ollama_available", return_value=False):
        
        res = await embed_dataset_records_background("synthetic_dataset_456", batch_size=32)
        assert res["status"] == "pending"
        assert res["count"] == 5


@pytest.mark.anyio
async def test_backfill_missing_embeddings_job():
    """Verify periodic backfill embeds docs missing 768-d vector."""
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_db.__getitem__.return_value = mock_col

    synthetic_missing = [
        {"_id": "m1", "company": "Synthetic Missing 1"},
        {"_id": "m2", "company": "Synthetic Missing 2"}
    ]

    mock_col.count_documents.return_value = 2
    mock_col.find.return_value.limit.return_value = synthetic_missing

    with patch("app.services.embeddings.get_database", return_value=mock_db), \
         patch("app.services.embeddings.is_ollama_available", return_value=True), \
         patch("app.services.embeddings.embed_documents_async", new_callable=AsyncMock, return_value=[[0.01] * 768, [0.01] * 768]):
        
        res = await backfill_missing_embeddings_job(batch_size=32)
        assert res["embedded"] == 2
        assert mock_col.bulk_write.called
