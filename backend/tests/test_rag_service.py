"""Tests for grounded answer generation."""

from uuid import uuid4
from unittest.mock import patch, MagicMock

from services.rag_service import generate_answer, GroqClient


def test_generate_answer_applies_threshold_after_retrieval():
    workspace_id = uuid4()
    document_id = uuid4()
    chunk_id = str(uuid4())
    chunk = {
        "id": chunk_id,
        "content": "The station walls are cobalt blue.",
        "page_number": 1,
        "chunk_index": 0,
        "similarity": 0.9,
        "pdf_name": "integration-check.pdf",
    }

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        f"<thinking>1. Analysis: direct fact.\n2. Evidence: cobalt blue walls.\n3. Reasoning: explicit.</thinking>\n"
        f"The station walls are cobalt blue [chunk_id: {chunk_id}]."
    )

    with patch("services.rag_service.search_similar_chunks", return_value=[chunk]) as search:
        response = generate_answer(
            question="What color are the station walls?",
            workspace_id=workspace_id,
            document_id=document_id,
            top_k=4,
            min_similarity=0.5,
            client=mock_client,
        )

    search.assert_called_once()
    called_kwargs = search.call_args.kwargs
    assert "What color are the station walls?" in called_kwargs["query"]
    assert called_kwargs["workspace_id"] == str(workspace_id)
    assert called_kwargs["top_k"] == 4
    assert response.abstained is False
    assert response.sources[0]["cited"] is True
    assert "cobalt blue" in response.answer.lower()
