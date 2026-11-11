"""
Question Analyzer Service for Phase 3.
Analyzes examination questions to determine topic, subtopic, intent,
question type, action verbs, required concepts, and intelligent retrieval search queries.
"""

import re
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
QUESTION_ANALYSIS_PROMPT_FILE = PROMPTS_DIR / "question_analysis.txt"

INSTRUCTION_VERBS = [
    "define", "describe", "explain", "discuss", "compare", "differentiate",
    "analyze", "evaluate", "justify", "demonstrate", "calculate", "identify",
    "list", "outline", "state", "distinguish", "illustrate", "apply"
]


class QuestionType(str, Enum):
    """Supported question classifications."""
    DEFINITION = "definition"
    ADVANTAGES_DISADVANTAGES = "advantages_disadvantages"
    COMPARISON = "comparison"
    APPLICATION = "application"
    CALCULATION = "calculation"
    EXPLANATION = "explanation"
    ANALYTICAL = "analytical"
    SCENARIO = "scenario"
    PRACTICAL_TECHNICAL = "practical_technical"
    STRUCTURED = "structured"
    ESSAY = "essay"
    SHORT_ANSWER = "short_answer"


@dataclass
class QuestionAnalysisResult:
    """Structured question analysis output."""
    topic: str
    subtopic: str
    question_type: str
    intent: str
    required_knowledge: list[str]
    answer_depth: str
    search_queries: list[str]
    marks: Optional[int] = None
    instruction_verbs: list[str] = field(default_factory=list)
    raw_question: str = ""

    @property
    def expected_depth(self) -> str:
        return self.answer_depth

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "subtopic": self.subtopic,
            "question_type": self.question_type,
            "intent": self.intent,
            "required_knowledge": self.required_knowledge,
            "answer_depth": self.answer_depth,
            "search_queries": self.search_queries,
            "marks": self.marks,
            "instruction_verbs": self.instruction_verbs,
        }


def _extract_marks(question: str) -> Optional[int]:
    """Extract marks from question if present (e.g. [10 marks] or (5 marks))."""
    match = re.search(r"\[\s*(\d+)\s*(?:marks?|pts?)\s*\]|\(\s*(\d+)\s*(?:marks?|pts?)\s*\)", question, re.IGNORECASE)
    if match:
        return int(match.group(1) or match.group(2))
    return None


def _classify_question_type(q_lower: str) -> str:
    """Classify the question into one of the 12 standard examination question types."""
    if any(k in q_lower for k in ["define", "what is meant by", "definition of", "what is a ", "what is an ", "what is "]):
        if any(c in q_lower for c in ["compare", "difference", "versus", "vs."]):
            return "comparison"
        if any(a in q_lower for a in ["advantage", "benefit", "pros and cons", "drawback"]):
            return "advantages_disadvantages"
        return "definition"
    elif any(k in q_lower for k in ["compare", "difference", "differentiate", "distinguish", "versus", "vs.", "between"]):
        return "comparison"
    elif any(k in q_lower for k in ["advantage", "benefit", "disadvantage", "drawback", "pros and cons", "merit"]):
        return "advantages_disadvantages"
    elif any(k in q_lower for k in ["calculate", "compute", "formula", "numerical"]):
        return "calculation"
    elif any(k in q_lower for k in ["scenario", "case study", "suppose", "consider a situation", "imagine"]):
        return "scenario"
    elif any(k in q_lower for k in ["how can", "how would you apply", "can solve", "solve this problem", "solve the problem", "solve problem", "apply", "solve a problem", "which technology would be used"]):
        return "application"
    elif any(k in q_lower for k in ["analyze", "examine why", "investigate", "critique", "how a browser communicates", "how does"]):
        return "analytical"
    elif any(k in q_lower for k in ["implement", "code", "syntax", "practical", "technical steps", "script"]):
        return "practical_technical"
    elif any(k in q_lower for k in ["(a)", "(b)", "part i", "part 1", "structured"]):
        return "structured"
    elif any(k in q_lower for k in ["discuss in detail", "write an essay", "comprehensive analysis"]):
        return "essay"
    elif any(k in q_lower for k in ["state", "list", "name", "identify", "short note"]):
        return "short_answer"
    return "explanation"


def _extract_intent_and_topics(question: str) -> tuple[str, str, str, list[str]]:
    """Extract topic, subtopic, intent, and required knowledge concepts."""
    q_lower = question.lower()
    cleaned = re.sub(r"\[\s*\d+\s*(?:marks?|pts?)\s*\]|\(\s*\d+\s*(?:marks?|pts?)\s*\)", "", question, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(what is|explain|describe|define|compare|analyze|evaluate|discuss|advantages of|disadvantages of|how does|how can|how)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\s-]", " ", cleaned).strip()

    tokens = [w for w in cleaned.split() if len(w) > 2 and w.lower() not in {
        "the", "and", "for", "with", "from", "that", "this", "can", "using", "between",
        "work", "together", "made", "used", "would", "when", "which", "create"
    }]

    # Domain topic detection
    if any(k in q_lower for k in ["html", "css", "javascript", "webpage", "web", "website", "browser", "responsive"]):
        topic = "Web Technologies"
        if "responsive" in q_lower:
            subtopic = "Responsive Web Design"
            required = ["Responsive Web Design", "Media Queries", "Fluid Layouts", "CSS"]
        elif "html" in q_lower and "css" in q_lower and "javascript" in q_lower:
            subtopic = "Webpage Architecture"
            required = ["HTML", "CSS", "JavaScript"]
        elif "html" in q_lower:
            subtopic = "HTML & Page Structure"
            required = ["HTML", "Page Structure", "HyperText Markup Language"]
        elif "css" in q_lower:
            subtopic = "CSS & Styling"
            required = ["CSS", "Styling", "Cascading Style Sheets", "Layouts"]
        elif "javascript" in q_lower or "button" in q_lower or "click" in q_lower:
            subtopic = "Client-Side Scripting"
            required = ["JavaScript", "DOM Manipulation", "Event Handling"]
        elif "browser" in q_lower or "server" in q_lower:
            subtopic = "Client-Server Web Architecture"
            required = ["Browser", "Web Server", "HTTP Protocol", "Client-Server"]
        else:
            subtopic = "Webpage Components"
            required = ["HTML", "CSS", "JavaScript"]
    elif any(k in q_lower for k in ["oop", "object-oriented", "inheritance", "class", "object", "polymorphism"]):
        topic = "Object-Oriented Programming"
        subtopic = "Inheritance & Polymorphism" if "inheritance" in q_lower else "OOP Principles"
        required = ["OOP", "Classes", "Objects", "Inheritance"]
    elif any(k in q_lower for k in ["database", "normalization", "sql", "table", "redundancy"]):
        topic = "Database Systems"
        subtopic = "Normalization" if "normalization" in q_lower else "Relational Databases"
        required = ["Database", "Normalization", "Redundancy", "Relations"]
    elif any(k in q_lower for k in ["network", "subnet", "ip", "tcp", "udp", "router"]):
        topic = "Computer Networks"
        subtopic = "Networking Protocols"
        required = ["Computer Networks", "Protocols", "Communication"]
    elif any(k in q_lower for k in ["world war", "war", "history", "treaty"]):
        topic = "World History"
        subtopic = "World War I"
        required = ["World War I", "History"]
    else:
        topic = tokens[0].capitalize() if tokens else "General Computing"
        subtopic = tokens[1].capitalize() if len(tokens) > 1 else "Core Principles"
        required = [w.capitalize() for w in tokens[:4]]

    intent = f"Explain and address: {question.strip()}"
    return topic, subtopic, intent, required


def _build_search_plan(question: str, topic: str, subtopic: str, required_knowledge: list[str]) -> list[str]:
    """Generate focused multi-query search plan to retrieve relevant syllabus knowledge."""
    queries = [question.strip()]

    # Query 2: Focused keywords
    if required_knowledge:
        req_query = " ".join(required_knowledge)
        if req_query not in queries:
            queries.append(req_query)

    # Query 3: Topic and subtopic combination
    topic_query = f"{topic} {subtopic}".strip()
    if topic_query and topic_query not in queries:
        queries.append(topic_query)

    return queries[:3]


def analyze_question(
    question: str,
    marks: Optional[int] = None,
    answer_style: Optional[str] = "exam",
    client: Optional[Any] = None,
) -> QuestionAnalysisResult:
    """
    Step 1 & Step 2: Understand the question, classify action verbs and question type,
    identify required concepts, and construct an intelligent search retrieval plan.
    """
    q_lower = question.lower().strip()

    # 1. Action verbs
    found_verbs = [v for v in INSTRUCTION_VERBS if re.search(rf"\b{v}\b", q_lower)]

    # 2. Extract marks
    detected_marks = marks if marks is not None else _extract_marks(question)

    # 3. Question type
    q_type = _classify_question_type(q_lower)

    # 4. Answer depth
    if detected_marks is not None:
        if detected_marks <= 2:
            answer_depth = "concise"
        elif detected_marks <= 6:
            answer_depth = "medium"
        else:
            answer_depth = "comprehensive"
    else:
        if q_type in ("definition", "short_answer"):
            answer_depth = "concise"
        elif q_type in ("essay", "analytical", "comparison"):
            answer_depth = "comprehensive"
        else:
            answer_depth = "medium"

    # 5. Extract topic, subtopic, intent, required concepts
    topic, subtopic, intent, required_knowledge = _extract_intent_and_topics(question)

    # 6. Build intelligent search plan
    search_queries = _build_search_plan(question, topic, subtopic, required_knowledge)

    logger.info(
        "Question analyzed: topic='%s', subtopic='%s', type='%s', depth='%s', queries=%d",
        topic, subtopic, q_type, answer_depth, len(search_queries)
    )

    return QuestionAnalysisResult(
        topic=topic,
        subtopic=subtopic,
        question_type=q_type,
        intent=intent,
        required_knowledge=required_knowledge,
        answer_depth=answer_depth,
        search_queries=search_queries,
        marks=detected_marks,
        instruction_verbs=found_verbs,
        raw_question=question,
    )


# Backward-compatibility alias and helper
QuestionAnalysis = QuestionAnalysisResult


def expand_queries(question: str, analysis: QuestionAnalysisResult) -> list[str]:
    """Return expanded retrieval queries including the original question."""
    queries = list(analysis.search_queries)
    if question not in queries:
        queries.insert(0, question)
    return queries

