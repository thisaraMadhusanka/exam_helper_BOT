"""
Reasoning Engine Service for Phase 3.
Executes Step 5: Synthesizes syllabus knowledge with pretrained LLM intelligence,
reasons through multi-concept examination questions, applies rules, and constructs
a transparent 4-stage thinking summary.
"""

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from services.question_analyzer import QuestionAnalysisResult
from services.knowledge_analyzer import KnowledgeAnalysisResult

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
REASONING_PROMPT_FILE = PROMPTS_DIR / "reasoning_system.txt"


@dataclass
class ReasoningResult:
    """Structured output of independent reasoning."""
    question_understanding: str
    retrieval_summary: str
    evidence_analysis: str
    reasoning_summary: str
    additional_knowledge_used: bool
    raw_answer: str
    reasoning_status: str
    full_thinking: str


def _load_system_prompt() -> str:
    """Load reasoning system prompt from prompts/ directory."""
    if REASONING_PROMPT_FILE.exists():
        try:
            return REASONING_PROMPT_FILE.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("Failed to read reasoning_system.txt: %s", e)

    return (
        "You are an intelligent university examination assistant.\n"
        "Your task is to answer questions using an uploaded educational knowledge base as your primary learning reference.\n"
        "Think like a student who has studied and understood the uploaded syllabus.\n"
        "Always reason before answering."
    )


def reason_about_question(
    question: str,
    analysis: QuestionAnalysisResult,
    knowledge: KnowledgeAnalysisResult,
    marks: Optional[int] = None,
    answer_style: Optional[str] = "exam",
    client: Optional[Any] = None,
    image_data_urls: Optional[list[str]] = None,
) -> ReasoningResult:
    """
    Step 5: Reason about the question using consolidated syllabus context
    and pretrained intelligence.
    """
    if client is None:
        from services.rag_service import GroqClient
        client = GroqClient()

    system_prompt = _load_system_prompt()

    marks_str = f"{marks} marks" if marks else "examination standard"
    verbs_str = ", ".join(analysis.instruction_verbs) if analysis.instruction_verbs else "explain / answer"

    user_instructions = f"""EXAMINATION QUESTION SPECIFICATIONS:
- Question: "{question}"
- Question Type: {analysis.question_type}
- Key Action Verbs: {verbs_str}
- Mark Allocation: {marks_str}
- Expected Depth: {analysis.answer_depth}
- Answer Style: {answer_style or "exam"}

CONSOLIDATED SYLLABUS REFERENCES:
{knowledge.consolidated_context}

REASONING INSTRUCTIONS:
Structure your response into two distinct sections:
<thinking>
1. Question Understanding:
   - Topic: {analysis.topic} | Subtopic: {analysis.subtopic}
   - Intent: {analysis.intent}
   - If the question is completely outside the scope of the uploaded syllabus (e.g. World War I on an ICT paper), clearly state that it is outside course scope.
2. Knowledge Retrieval:
   - Summary of documents and topics retrieved.
3. Evidence Analysis:
   - Direct evidence found: {', '.join(knowledge.directly_supported_concepts) or 'None explicit'}
   - Partial / outline concepts: {', '.join(knowledge.partially_supported_concepts) or 'None'}
   - Concepts to bridge via reasoning: {', '.join(knowledge.missing_concepts) or 'None'}
4. Reasoning Summary:
   - How the retrieved principles apply to answer this question.
   - Note if additional conceptual knowledge or practical examples were used.
   - If uncertain or non-existent technical claims are requested, acknowledge uncertainty.
</thinking>

Everything after the closing </thinking> tag must be only the final answer. Do not repeat, summarize, or expose any internal analysis.

EXAMINATION ANSWER GUIDELINES:
1. Start directly with the answer (avoid meta-introductions like "Based on the text...").
2. Write in your own words with proper academic and technical terminology. Do NOT copy-paste blocks from the PDF.
3. Structure with clear headings, numbered points, or comparison tables where appropriate for the question type.
4. Use retrieved syllabus information internally; do not include citations, references, document names, page numbers, or source lists in the final answer.
5. NEVER output database UUIDs, chunk IDs, or tokens like [chunk_id: ...].
6. Do not add answer labels, reference sections, retrieval summaries, or unnecessary introductory or concluding text. NEVER output specification labels or metadata tags like "(Definition – concise, exam style)", "Definition – concise, exam style", or "Answer:". Begin immediately with the substantive answer text.
7. Use concise wording for definition questions and sufficient detail for explanation, comparison, or analysis questions; format lists, tables, and code clearly when appropriate.
8. If the question is completely outside the scope of the uploaded subject, state politely and directly: "This question is outside the scope of the uploaded syllabus and educational materials."
9. If the syllabus mentions only a topic heading, provide a complete academic explanation using reliable knowledge without describing retrieval or adding source references.

Now, formulate your thinking and your examination answer."""

    if image_data_urls:
        user_instructions += (
            "\n\nVISUAL INPUT: Analyze the attached user image as part of the question. "
            "Describe only visible details relevant to the request, and distinguish visual "
            "observations from syllabus evidence."
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                [
                    {"type": "text", "text": user_instructions},
                    *[
                        {"type": "image_url", "image_url": {"url": image}}
                        for image in image_data_urls
                    ],
                ]
                if image_data_urls
                else user_instructions
            ),
        },
    ]

    raw_response = client.generate(messages)

    # Parse <thinking>
    full_thinking = ""
    raw_answer = raw_response.strip()

    thinking_match = re.search(r"<thinking>(.*?)</thinking>", raw_response, re.DOTALL | re.IGNORECASE)
    if thinking_match:
        full_thinking = thinking_match.group(1).strip()
        raw_answer = re.sub(r"<thinking>.*?</thinking>", "", raw_response, flags=re.DOTALL | re.IGNORECASE).strip()

    # Extract 4-stage transparent summaries from thinking or build structured defaults
    qu_match = re.search(r"1\.\s*Question Understanding:(.*?)(?=2\.|$)", full_thinking, re.DOTALL | re.IGNORECASE)
    kr_match = re.search(r"2\.\s*Knowledge Retrieval:(.*?)(?=3\.|$)", full_thinking, re.DOTALL | re.IGNORECASE)
    ea_match = re.search(r"3\.\s*Evidence Analysis:(.*?)(?=4\.|$)", full_thinking, re.DOTALL | re.IGNORECASE)
    rs_match = re.search(r"4\.\s*Reasoning Summary:(.*?)$", full_thinking, re.DOTALL | re.IGNORECASE)

    question_understanding = qu_match.group(1).strip() if qu_match else f"Identified {analysis.question_type} question regarding {analysis.topic}."
    retrieval_summary = kr_match.group(1).strip() if kr_match else f"Retrieved knowledge chunks for {', '.join(analysis.required_knowledge[:3])}."
    evidence_analysis = ea_match.group(1).strip() if ea_match else knowledge.evidence_summary
    reasoning_summary = rs_match.group(1).strip() if rs_match else "Synthesized syllabus concepts with independent technical reasoning."

    # Assess status and additional knowledge usage
    ans_lower = raw_answer.lower()
    think_lower = full_thinking.lower()

    is_unrelated = not image_data_urls and (
        knowledge.is_unrelated
        or "outside the scope of the uploaded" in ans_lower
        or "outside the scope of the uploaded" in think_lower
        or "outside the uploaded syllabus" in ans_lower
    )

    if is_unrelated:
        reasoning_status = "abstain_unrelated"
        additional_knowledge_used = False
    elif "cannot reliably establish" in ans_lower or "does not contain sufficient reliable" in ans_lower:
        reasoning_status = "abstain_uncertain"
        additional_knowledge_used = True
    else:
        reasoning_status = "completed"
        additional_knowledge_used = (
            knowledge.coverage_level in ("partial", "syllabus_topic_only")
            or len(knowledge.missing_concepts) > 0
            or analysis.question_type in ("explanation", "advantages_disadvantages", "comparison", "application", "scenario", "analytical")
        )

    logger.info("Reasoning complete: status=%s, additional_knowledge=%s", reasoning_status, additional_knowledge_used)

    return ReasoningResult(
        question_understanding=question_understanding,
        retrieval_summary=retrieval_summary,
        evidence_analysis=evidence_analysis,
        reasoning_summary=reasoning_summary,
        additional_knowledge_used=additional_knowledge_used,
        raw_answer=raw_answer,
        reasoning_status=reasoning_status,
        full_thinking=full_thinking,
    )
