import httpx
import pytest
from unittest.mock import Mock, patch

from services.knowledge_analyzer import KnowledgeAnalysisResult
from services.question_analyzer import QuestionAnalysisResult
from services.rag_service import GroqClient, LLMError
from services.reasoning_engine import reason_about_question


def test_reasoning_engine_sends_images_to_existing_chat_provider():
    analysis = QuestionAnalysisResult(
        topic="Image",
        subtopic="Visual details",
        question_type="explanation",
        intent="Describe the attached image.",
        required_knowledge=[],
        answer_depth="medium",
        search_queries=["Describe the attached image."],
    )
    knowledge = KnowledgeAnalysisResult(
        directly_supported_concepts=[],
        partially_supported_concepts=[],
        missing_concepts=[],
        coverage_level="unrelated",
        is_unrelated=True,
        evidence_summary="No matching documents found in knowledge base.",
        consolidated_context="(No matching documents found in knowledge base)",
    )
    client = Mock()
    client.generate.return_value = "The image contains a landscape."
    image = "data:image/png;base64,iVBORw0KGgo="

    result = reason_about_question(
        question="Describe this image",
        analysis=analysis,
        knowledge=knowledge,
        client=client,
        image_data_urls=[image],
    )

    user_content = client.generate.call_args.args[0][1]["content"]
    assert any(part.get("type") == "image_url" for part in user_content)
    assert result.raw_answer == "The image contains a landscape."
    assert result.reasoning_status == "completed"


def test_vision_model_error_is_actionable():
    client = GroqClient()
    client.openrouter_api_key = None
    request = httpx.Request("POST", "https://api.example.test/chat/completions")
    response = httpx.Response(400, request=request, text="model does not support image input")
    error = httpx.HTTPStatusError("bad request", request=request, response=response)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
        ],
    }]

    with patch.object(client, "_call_groq", side_effect=error):
        with pytest.raises(LLMError, match="vision-capable"):
            client.generate(messages)
