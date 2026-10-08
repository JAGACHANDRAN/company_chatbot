import pytest
import asyncio
from unittest.mock import MagicMock, patch

from app.services.multi_stage_search import (
    extract_core_company_name,
    generate_query_variants,
    _calculate_fuzzy_score,
    execute_multi_stage_retrieval
)
from app.services.source_resolver import get_record_sources, get_record_source_display
from app.routes.chat import format_api_sources_and_records
from app.schemas import ChatResponse
from app.services.query_understanding import StructuredQuery


def test_extract_core_company_name():
    assert extract_core_company_name("give me tvs company details") == "tvs"
    assert extract_core_company_name("tvs companies list") == "tvs"
    assert extract_core_company_name("ashok lelyland companies") == "ashok leyland"
    assert extract_core_company_name("premier cnc preri shop pvt ltd") == "premier cnc preri shop"
    assert extract_core_company_name("who are at Bosch?") == "bosch"


def test_generate_query_variants():
    variants_tvs = generate_query_variants("tvs")
    assert "tvs" in variants_tvs
    assert "t v s" in variants_tvs

    variants_t_v_s = generate_query_variants("t v s")
    assert "t v s" in variants_t_v_s
    assert "tvs" in variants_t_v_s

    variants_ashok = generate_query_variants("ashok leyland")
    assert "ashok leyland" in variants_ashok
    assert "ashokleyland" in variants_ashok


def test_fuzzy_score_accuracy():
    # Similar company typos
    assert _calculate_fuzzy_score("tvz", "tvs") >= 60.0
    assert _calculate_fuzzy_score("ashok leyland", "ashok leyland motors") >= 80.0
    assert _calculate_fuzzy_score("premier cnc", "premier cnc machines") >= 80.0
    # Dissimilar strings
    assert _calculate_fuzzy_score("apple", "microsoft") < 40.0
    # Short string random length difference guard
    assert _calculate_fuzzy_score("s s", "s s engineering and manufacturing enterprise") < 80.0


def test_source_resolver_and_dataset_attribution():
    # Synthetic test records
    synthetic_rec_1 = {
        "dataset_name": "Synthetic_Exhibition_Dataset",
        "Source File": "Synthetic_Exhibition_2024.xlsx",
        "company": "Synthetic Precision Components",
        "norm_company": "synthetic precision components",
        "person": "John Doe",
        "email": "johndoe@syntheticprecision.com",
        "phone": "+91 99999 11111"
    }
    synthetic_rec_merged = {
        "dataset_name": "Synthetic_Exhibition_Dataset",
        "Sources": "Sheet_A.xlsx | Sheet_B.xlsx",
        "company": "Synthetic Toolings Ltd",
        "norm_company": "synthetic toolings ltd",
        "person": "Jane Smith"
    }
    synthetic_rec_fallback = {
        "dataset_name": "Synthetic_Master_Dataset",
        "company": "Synthetic Auto Parts"
    }

    assert get_record_sources(synthetic_rec_1) == ["Synthetic_Exhibition_Dataset"]
    assert get_record_sources(synthetic_rec_merged) == ["Synthetic_Exhibition_Dataset"]
    assert get_record_sources(synthetic_rec_fallback) == ["Synthetic_Master_Dataset"]

    formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(
        [synthetic_rec_1, synthetic_rec_merged, synthetic_rec_fallback],
        display_dataset_name="Synthetic_Master_Dataset"
    )

    assert len(display_records) == 3
    for d in display_records:
        assert "embedding" not in d
        assert d["dataset"] in ("Synthetic_Exhibition_Dataset", "Synthetic_Master_Dataset")
        assert d["dataset"] != "dataset_records"


def test_multi_stage_retrieval_synthetic_pipeline():
    synthetic_docs = [
        {
            "_id": "mock_id_1",
            "company": "TVS Motor Company",
            "norm_company": "tvs motor company",
            "search_text": "tvs motor company chennai manufacturing",
            "source_file": "Auto_Directory.xlsx",
            "dataset_name": "Auto_Master_2024"
        },
        {
            "_id": "mock_id_2",
            "company": "Premier CNC Preri Shop",
            "norm_company": "premier cnc preri shop",
            "search_text": "premier cnc preri shop machining tools",
            "source_file": "CNC_Expo.xlsx",
            "dataset_name": "Expo_2024"
        }
    ]

    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_db.__getitem__.return_value = mock_collection

    # Mock Stage A and B to return synthetic docs
    mock_collection.find.return_value.limit.return_value = synthetic_docs
    mock_collection.aggregate.return_value = []
    mock_collection.distinct.return_value = ["tvs motor company", "premier cnc preri shop"]

    async def _runner():
        with patch("app.services.multi_stage_search.get_database", return_value=mock_db), \
             patch("app.services.multi_stage_search.get_configured_collection_names", return_value=["test_collection"]), \
             patch("app.services.multi_stage_search.embed_query", return_value=[0.1] * 768):

            result = await execute_multi_stage_retrieval("tvs motor")
            assert result["core_name"] == "tvs motor"
            assert result["stages"]["A"] >= 0 or result["stages"]["B"] >= 0
            assert len(result["records"]) > 0
            assert result["records"][0]["company"] in ("TVS Motor Company", "Premier CNC Preri Shop")
            assert "embedding" not in result["records"][0]

    asyncio.run(_runner())
