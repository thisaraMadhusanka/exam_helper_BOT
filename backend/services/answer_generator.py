"""
Answer Generator Service for Phase 3.
Executes Step 6: Formats clean, structured Markdown examination answers,
ensures proper technical terminology, headings, and removes leaked internal tokens.
"""

import re
import logging
from typing import Optional

from services.question_analyzer import QuestionAnalysisResult

logger = logging.getLogger(__name__)


def generate_exam_answer(
    raw_answer: str,
    analysis: QuestionAnalysisResult,
    marks: Optional[int] = None,
    answer_style: Optional[str] = "exam",
) -> str:
    """
    Step 6: Normalize the final examination answer without altering valid Markdown.
    """
    answer = raw_answer.strip()

    # 1. Remove leaked [chunk_id: ...] tokens or raw UUIDs
    answer = re.sub(r'\[chunk_id:\s*[a-zA-Z0-9_-]+\]', '', answer)
    answer = re.sub(
        r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
        '',
        answer,
        flags=re.IGNORECASE,
    )

    # Strip standalone answer labels and specification tags without altering Markdown inside the answer.
    label_patterns = [
        r'^(?:\*\*)?(?:Final Answer|Answer)(?:\*\*)?:?(?:\*\*)?\s*\n*',
        r'(?i)(?:^|\n)\s*(?:#{1,6}\s*)?(?:\d+[\.\)]\s*)?(?:\*\*)?\(?\s*(?:definition|explanation|short answer|comparison|analytical)\s*[-\u2013\u2014:,]\s*(?:concise|medium|comprehensive|detailed),?\s*exam\s*style\s*\)?(?:\*\*)?:?\s*(?:\n+|$)?',
        r'(?i)(?:\*\*)?\(?\s*definition\s*[-\u2013\u2014:,]\s*concise,?\s*exam\s*style\s*\)?(?:\*\*)?:?\s*',
    ]
    for pattern in label_patterns:
        answer = re.sub(pattern, '', answer).strip()

    # Remove trailing source material if the model adds it despite the prompt.
    lines = answer.splitlines()
    section_heading = re.compile(
        r'^\s{0,3}(?:#{1,6}\s*)?(?:\*{1,2})?(?:references?|sources|grounded knowledge sources)(?:\*{1,2})?\s*:?\s*$',
        re.IGNORECASE,
    )
    reference_line = re.compile(
        r'^\s*(?:\*{1,2})?(?:references?|sources?)\s*(?:\*{1,2})?:\s*(?:\*{1,2})?.+?(?:\*{1,2})?\s*$',
        re.IGNORECASE,
    )
    heading_index = next((i for i, line in enumerate(lines) if section_heading.match(line)), None)
    if heading_index is not None:
        lines = lines[:heading_index]
    while lines and (not lines[-1].strip() or reference_line.match(lines[-1])):
        lines.pop()
    answer = "\n".join(lines)

    # Clean excessive line breaks without changing meaningful Markdown.
    answer = re.sub(r'\n{3,}', '\n\n', answer).strip()

    return answer
