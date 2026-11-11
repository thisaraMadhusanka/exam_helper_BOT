"""
Phase 3 Test Suite: Intelligent AI Thinking, Knowledge Retrieval & Answer Generation.
Covers the 8 core evaluation scenarios specified in Section 5:
TEST A — Direct Knowledge ("What is HTML?")
TEST B — Independent Explanation ("Explain five advantages of using CSS...")
TEST C — Multi-Concept Reasoning ("Explain how HTML, CSS and JavaScript work together...")
TEST D — Application-Based Reasoning (Button click text change scenario)
TEST E — Missing Exact Answer (Heading "Responsive Web Design" only)
TEST F — Analytical Question (Browser communicating with web server)
TEST G — Unrelated Question ("Explain the causes of World War I" vs Web dev syllabus)
TEST H — Source Accuracy (Genuine page numbers, excerpts, zero fabricated citations)
Plus unit tests for question analyzer, knowledge analyzer, and live milestone stream generator.
"""

import sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend directory is in python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.question_analyzer import analyze_question, QuestionAnalysisResult
from services.knowledge_retriever import retrieve_knowledge, KnowledgeRetrievalResult
from services.knowledge_analyzer import analyze_knowledge, KnowledgeAnalysisResult
from services.reasoning_engine import reason_about_question, ReasoningResult
from services.answer_generator import generate_exam_answer
from services.answer_validator import validate_answer
from services.rag_service import generate_answer, generate_answer_stream, GroqClient


def test_generate_exam_answer_removes_trailing_references_and_labels():
    analysis = analyze_question("What is the World Wide Web?")
    answer = generate_exam_answer(
        "**Answer:**\n**Definition \u2013 concise, exam style**\n"
        "The **World Wide Web (WWW)** is a system of interlinked documents.\n\n"
        "**Reference:** 03-Fundamental of Web Technologies, p. 4",
        analysis,
    )

    assert answer == "The **World Wide Web (WWW)** is a system of interlinked documents."
    assert "Reference" not in answer


def test_generate_exam_answer_removes_parenthesized_definition_labels():
    analysis = analyze_question("What is HTML?")
    
    # Variation 1: Leading parenthesis with trailing asterisks
    ans1 = generate_exam_answer(
        "(Definition – concise, exam style)**\nHTML is the standard markup language.",
        analysis,
    )
    assert ans1 == "HTML is the standard markup language."

    # Variation 2: Asterisks wrapping parentheses
    ans2 = generate_exam_answer(
        "**(Definition – concise, exam style)**\nHTML is the standard markup language.",
        analysis,
    )
    assert ans2 == "HTML is the standard markup language."

    # Variation 3: With Answer prefix and hyphen
    ans3 = generate_exam_answer(
        "**Answer:**\n**(Definition - concise, exam style)**\nHTML is the standard markup language.",
        analysis,
    )
    assert ans3 == "HTML is the standard markup language."


def test_generate_exam_answer_preserves_markdown_and_inline_math():
    analysis = analyze_question("Explain this expression.")
    raw_answer = "The **coefficient** is 2 * 3 = 6.\n\n```text\nx * y\n```"

    assert generate_exam_answer(raw_answer, analysis) == raw_answer


def test_generate_exam_answer_removes_uppercase_uuid_tokens():
    analysis = analyze_question("Define a token.")
    answer = generate_exam_answer(
        "A token identifies a record: ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB.",
        analysis,
    )

    assert "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB" not in answer


# ============================================================================
# Unit Tests: Question Understanding & Retrieval Planning (Steps 1 & 2)
# ============================================================================

def test_question_analyzer_web_technologies():
    q = "What is a webpage made of?"
    res = analyze_question(q)
    assert res.topic == "Web Technologies"
    assert "HTML" in res.required_knowledge
    assert "CSS" in res.required_knowledge
    assert "JavaScript" in res.required_knowledge
    assert len(res.search_queries) >= 2


def test_question_analyzer_marks_and_instruction_verbs():
    q = "Explain five advantages of using CSS in web development [10 marks]"
    res = analyze_question(q)
    assert res.question_type == "advantages_disadvantages"
    assert "explain" in res.instruction_verbs
    assert res.marks == 10
    assert res.answer_depth == "comprehensive"


# ============================================================================
# Unit Tests: Live Processing Milestones (Streaming)
# ============================================================================

def test_live_processing_milestones_stream():
    """Verify that generate_answer_stream genuinely emits all 7 sequential milestones."""
    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Direct explanation.\n"
        "2. Knowledge Retrieval: Found HTML definition.\n"
        "3. Evidence Analysis: Direct support.\n"
        "4. Reasoning Summary: Structured answer.\n"
        "</thinking>\n"
        "HTML is the standard markup language used to structure web documents."
    )

    pdf_chunk = {
        "id": "c1",
        "content": "HTML is used to define the structure of a webpage.",
        "page_number": 2,
        "chunk_index": 0,
        "similarity": 0.85,
        "pdf_name": "Web_Basics.pdf",
    }

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=[pdf_chunk]):
        events = list(generate_answer_stream("What is HTML?", client=mock_client))

    stages = [e["stage"] for e in events]
    assert stages == [1, 2, 3, 4, 5, 6, 7]
    assert "Understanding your question" in events[0]["status"]
    assert "Planning knowledge retrieval" in events[1]["status"]
    assert "Searching your study materials" in events[2]["status"]
    assert "Analyzing relevant concepts" in events[3]["status"]
    assert "Reasoning and constructing" in events[4]["status"]
    assert "Verifying answer and sources" in events[5]["status"]
    assert "Answer ready" in events[6]["status"]
    assert "HTML" in events[6]["result"]["answer"]


# ============================================================================
# Core Scenario Tests: TEST A through TEST H
# ============================================================================

def test_scenario_a_direct_knowledge():
    """
    TEST A — Direct Knowledge
    PDF contains: HTML is used to define the structure of a webpage.
    Question: "What is HTML?"
    Expected: A clear definition based on PDF knowledge.
    """
    chunk = {
        "id": "html_def",
        "content": "HTML (HyperText Markup Language) is used to define the structure of a webpage, organizing text, headings, and multimedia.",
        "page_number": 4,
        "chunk_index": 1,
        "similarity": 0.90,
        "pdf_name": "Web_Fundamentals.pdf",
    }

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Direct definition of HTML [2 marks].\n"
        "2. Knowledge Retrieval: Found Web_Fundamentals.pdf page 4 with exact definition.\n"
        "3. Evidence Analysis: Directly supported definition of HTML as structural markup language.\n"
        "4. Reasoning Summary: Formulate concise definition in own words.\n"
        "</thinking>\n"
        "HTML (HyperText Markup Language) is the foundational markup language used to structure and present content on the World Wide Web. "
        "It defines headings, paragraphs, links, images, and other structural blocks that web browsers render."
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=[chunk]):
        response = generate_answer("What is HTML?", client=mock_client)

    assert response.abstained is False
    assert response.question_analysis["topic"] == "Web Technologies"
    assert "markup language" in response.answer.lower()
    assert len(response.sources) > 0
    assert response.sources[0]["page_number"] == 4
    assert response.sources[0]["support_type"] == "direct"


def test_scenario_b_independent_explanation():
    """
    TEST B — Independent Explanation
    PDF contains: A brief explanation of CSS.
    Question: "Explain five advantages of using CSS in web development."
    Expected: The AI identifies CSS from the PDF and independently explains five relevant advantages.
    """
    chunk = {
        "id": "css_intro",
        "content": "CSS (Cascading Style Sheets) is a stylesheet language used for describing the presentation of a document written in HTML.",
        "page_number": 9,
        "chunk_index": 3,
        "similarity": 0.78,
        "pdf_name": "Web_Styling.pdf",
    }

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Explain 5 distinct advantages of CSS in web development [10 marks].\n"
        "2. Knowledge Retrieval: Web_Styling.pdf page 9 introduces CSS as presentation styling for HTML.\n"
        "3. Evidence Analysis: Core CSS role is supported; specific 5 advantages are bridged via pretrained technical reasoning.\n"
        "4. Reasoning Summary: Organize into 5 clear numbered points highlighting separation of concerns, reusability, maintenance, page loading speed, and device responsiveness.\n"
        "</thinking>\n"
        "Cascading Style Sheets (CSS) provide substantial technical advantages in modern web development:\n\n"
        "1. **Separation of Content and Presentation**: Decouples HTML structure from visual styling, enhancing code clarity.\n"
        "2. **Site-Wide Reusability**: A single external stylesheet can control the appearance of an entire multi-page website.\n"
        "3. **Ease of Maintenance**: Global design updates require modifying only a single CSS rule rather than every HTML file.\n"
        "4. **Faster Page Loading**: Cached stylesheets reduce bandwidth usage and improve browser rendering performance.\n"
        "5. **Responsive and Adaptive Layouts**: Media queries enable fluid designs across mobile, tablet, and desktop viewports.\n\n"
        "(Note: The syllabus introduces CSS on page 9; these five detailed advantages are formulated through independent technical reasoning.)"
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=[chunk]):
        response = generate_answer("Explain five advantages of using CSS in web development.", client=mock_client)

    assert response.abstained is False
    assert response.additional_knowledge_used is True
    assert "separation of content" in response.answer.lower() or "reusability" in response.answer.lower()
    assert response.thinking_summary["additional_knowledge_used"] is True


def test_scenario_c_multi_concept_reasoning():
    """
    TEST C — Multi-Concept Reasoning
    PDF contains: Information about HTML, CSS and JavaScript in separate sections.
    Question: "Explain how HTML, CSS and JavaScript work together to create a website."
    Expected: The AI retrieves and combines information from all three sections.
    """
    chunks = [
        {"id": "c_html", "content": "HTML provides structure and tags.", "page_number": 2, "chunk_index": 1, "similarity": 0.82, "pdf_name": "Web_Architecture.pdf"},
        {"id": "c_css", "content": "CSS provides visual styling, colors, and layouts.", "page_number": 8, "chunk_index": 6, "similarity": 0.80, "pdf_name": "Web_Architecture.pdf"},
        {"id": "c_js", "content": "JavaScript enables interactive behavior and dynamic DOM updates.", "page_number": 15, "chunk_index": 12, "similarity": 0.79, "pdf_name": "Web_Architecture.pdf"},
    ]

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Multi-concept synthesis of HTML, CSS, and JS cooperation.\n"
        "2. Knowledge Retrieval: Retrieved HTML (p.2), CSS (p.8), and JS (p.15) from Web_Architecture.pdf.\n"
        "3. Evidence Analysis: High coverage of all three foundational pillars across distinct syllabus sections.\n"
        "4. Reasoning Summary: Explain architectural synergy: HTML as the skeleton, CSS as the presentation skin, and JavaScript as the muscle/behavior.\n"
        "</thinking>\n"
        "A modern website is created through the coordinated interaction of three foundational web layers:\n\n"
        "1. **Structure (HTML)**: Defines the semantic structure and content hierarchy of the webpage (headings, sections, forms, and media).\n"
        "2. **Presentation (CSS)**: Formats and styles the structured elements, applying typography, color schemes, grid layouts, and responsive media queries.\n"
        "3. **Behavior (JavaScript)**: Adds programmable interactivity, handling user events, validating input data, and updating the Document Object Model (DOM) asynchronously.\n\n"
        "Together, these layers separate content, design, and functionality, producing resilient, maintainable web applications."
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=chunks):
        response = generate_answer("Explain how HTML, CSS and JavaScript work together to create a website.", client=mock_client)

    assert response.abstained is False
    assert len(response.sources) >= 3
    pages = sorted(list(set(s["page_number"] for s in response.sources)))
    assert 2 in pages and 8 in pages and 15 in pages
    assert "structure" in response.answer.lower()
    assert "presentation" in response.answer.lower()
    assert "behavior" in response.answer.lower() or "interactivity" in response.answer.lower()


def test_scenario_d_application_based_reasoning():
    """
    TEST D — Application-Based Reasoning
    PDF contains: Basic information about JavaScript.
    Question: "A webpage has a button that should change the text when clicked. Which technology would be used and how?"
    Expected: The AI applies its knowledge of JavaScript and provides an appropriate explanation.
    """
    chunk = {
        "id": "js_basics",
        "content": "JavaScript is a client-side programming language that can access the Document Object Model (DOM) and attach event listeners to elements.",
        "page_number": 12,
        "chunk_index": 4,
        "similarity": 0.75,
        "pdf_name": "JS_Basics.pdf",
    }

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Application scenario — changing text on button click.\n"
        "2. Knowledge Retrieval: JS_Basics.pdf page 12 mentions DOM access and event listeners.\n"
        "3. Evidence Analysis: Core principle exists; apply to step-by-step technical implementation.\n"
        "4. Reasoning Summary: Identify JavaScript as the required technology and explain DOM selection (getElementById/querySelector) plus addEventListener('click').\n"
        "</thinking>\n"
        "To change text dynamically when a user clicks a button, **JavaScript** is the required technology.\n\n"
        "### How It Works Step-by-Step:\n"
        "1. **HTML Element Identification**: Assign an `id` or class to the target text and button elements.\n"
        "2. **DOM Selection**: In JavaScript, select the elements using `document.getElementById('myButton')` and `document.getElementById('myText')`.\n"
        "3. **Event Listener Attachment**: Register a `'click'` event listener on the button using `.addEventListener('click', callback)`.\n"
        "4. **DOM Property Modification**: Inside the event callback function, update the `.textContent` or `.innerText` property of the target text element.\n\n"
        "```javascript\n"
        "const button = document.getElementById('changeBtn');\n"
        "const text = document.getElementById('message');\n"
        "button.addEventListener('click', () => {\n"
        "  text.textContent = 'Updated message after click!';\n"
        "});\n"
        "```"
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=[chunk]):
        response = generate_answer("A webpage has a button that should change the text when clicked. Which technology would be used and how?", client=mock_client)

    assert response.question_analysis["question_type"] == "application"
    assert response.abstained is False
    assert "javascript" in response.answer.lower()
    assert "addeventlistener" in response.answer.lower() or "event" in response.answer.lower()


def test_scenario_e_missing_exact_answer_topic_heading_only():
    """
    TEST E — Missing Exact Answer
    PDF contains: Only the topic heading "Responsive Web Design".
    Question: "Explain the importance of responsive web design and describe how it works."
    Expected: The AI uses the syllabus topic as a knowledge reference and supplements it with reliable pretrained knowledge.
    """
    chunk = {
        "id": "rwd_heading",
        "content": "Module 3: Responsive Web Design",
        "page_number": 1,
        "chunk_index": 0,
        "similarity": 0.50,
        "pdf_name": "Web_Syllabus_Outline.pdf",
    }

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Explain importance and mechanisms of Responsive Web Design.\n"
        "2. Knowledge Retrieval: Web_Syllabus_Outline.pdf contains topic heading 'Module 3: Responsive Web Design' with no detailed subtext.\n"
        "3. Evidence Analysis: Syllabus topic only; must use pretrained intelligence to explain principles.\n"
        "4. Reasoning Summary: Explain importance (mobile-first indexing, user experience) and mechanisms (fluid grids, flexible media, CSS media queries).\n"
        "</thinking>\n"
        "**Responsive Web Design (RWD)** is an approach to web development where websites adapt seamlessly to varying screen dimensions and device orientations.\n\n"
        "### Importance:\n"
        "- **Device Compatibility**: Ensures optimal viewing across smartphones, tablets, laptops, and ultra-wide monitors.\n"
        "- **SEO & Performance**: Search engines prioritize mobile-friendly responsive pages.\n\n"
        "### How It Works:\n"
        "1. **Fluid Grids**: Proportional sizing using percentages (`%`) or `fr` units rather than fixed pixel dimensions.\n"
        "2. **Flexible Images**: Media styled with `max-width: 100%` so images scale down without overflowing container boundaries.\n"
        "3. **CSS Media Queries**: `@media` rules applying conditional CSS styles depending on viewport width breakpoints.\n\n"
        "(Note: The syllabus lists 'Module 3: Responsive Web Design' as an instructional topic; this comprehensive explanation is derived through independent technical reasoning.)"
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=[chunk]):
        response = generate_answer("Explain the importance of responsive web design and describe how it works.", client=mock_client)

    assert response.abstained is False
    assert response.additional_knowledge_used is True
    assert "fluid" in response.answer.lower() or "media queries" in response.answer.lower()


def test_scenario_f_analytical_question():
    """
    TEST F — Analytical Question
    PDF contains: Information about client-server architecture and web protocols.
    Question: "Explain how a browser communicates with a web server when a user opens a webpage."
    Expected: The AI retrieves related concepts and constructs a logical step-by-step explanation.
    """
    chunks = [
        {"id": "proto1", "content": "Web communication relies on client requests and server responses over HTTP/HTTPS protocols.", "page_number": 3, "chunk_index": 1, "similarity": 0.76, "pdf_name": "Web_Protocols.pdf"},
        {"id": "proto2", "content": "TCP establishes a reliable connection between client and server via a 3-way handshake before transmitting data packets.", "page_number": 7, "chunk_index": 5, "similarity": 0.74, "pdf_name": "Web_Protocols.pdf"},
    ]

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Analytical step-by-step process of browser-to-server communication.\n"
        "2. Knowledge Retrieval: Retrieved HTTP/HTTPS requests/responses (p.3) and TCP handshake (p.7).\n"
        "3. Evidence Analysis: Good theoretical basis across network protocol sections.\n"
        "4. Reasoning Summary: Structure chronological sequence from URL input to final page rendering.\n"
        "</thinking>\n"
        "When a user requests a webpage in a browser, communication proceeds through the following sequential stages:\n\n"
        "1. **DNS Resolution**: The browser queries DNS servers to translate the domain name into an IP address.\n"
        "2. **TCP Connection Establishment**: The browser and server perform a three-way TCP handshake (SYN, SYN-ACK, ACK) to establish a reliable transport socket.\n"
        "3. **TLS Handshake (HTTPS)**: If secure HTTP is used, cryptographic keys are exchanged for encryption.\n"
        "4. **HTTP GET Request**: The browser sends an HTTP GET request header specifying the requested document path.\n"
        "5. **Server Processing & Response**: The server processes the request and returns an HTTP status code (e.g., `200 OK`) and the HTML payload.\n"
        "6. **Critical Rendering Path**: The browser parses the HTML, issues secondary requests for linked CSS, images, and JavaScript, and renders the visual page."
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=chunks):
        response = generate_answer("Explain how a browser communicates with a web server when a user opens a webpage.", client=mock_client)

    assert response.question_analysis["question_type"] == "analytical"
    assert response.abstained is False
    assert "dns" in response.answer.lower()
    assert "handshake" in response.answer.lower() or "tcp" in response.answer.lower()
    assert "http" in response.answer.lower()


def test_scenario_g_unrelated_question():
    """
    TEST G — Unrelated Question
    PDF contains: Web development syllabus.
    Question: "Explain the causes of World War I."
    Expected: The AI identifies that the question is unrelated to the uploaded course material.
    """
    chunk = {
        "id": "web1",
        "content": "HTML structure, CSS cascading rules, and JavaScript scripting fundamentals.",
        "page_number": 1,
        "chunk_index": 0,
        "similarity": 0.10,
        "pdf_name": "Web_Dev_Syllabus.pdf",
    }

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: User asks about historical geopolitical causes of World War I.\n"
        "2. Knowledge Retrieval: Only Web_Dev_Syllabus.pdf available (peak similarity 0.10).\n"
        "3. Evidence Analysis: Zero overlap; question is completely outside the syllabus subject scope.\n"
        "4. Reasoning Summary: Abstain honestly without fabricating a syllabus connection.\n"
        "</thinking>\n"
        "This question is outside the scope of the uploaded syllabus and educational materials. The uploaded course materials cover Web Technologies, not 20th-century world history."
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=[chunk]):
        response = generate_answer("Explain the causes of World War I.", client=mock_client)

    assert response.abstained is True
    assert response.answer_status == "abstain_unrelated"
    assert "outside the scope of the uploaded" in response.answer.lower()


def test_scenario_h_source_accuracy():
    """
    TEST H — Source Accuracy
    Ask a question supported by several PDF pages.
    Expected: The answer includes genuine supporting page references, without fabricated citations or unrelated sources.
    """
    chunks = [
        {"id": "src_p1", "content": "HTML headings range from H1 to H6.", "page_number": 3, "chunk_index": 2, "similarity": 0.85, "pdf_name": "HTML_Guide.pdf"},
        {"id": "src_p2", "content": "Paragraph tags and anchor elements create text blocks and hyperlinks.", "page_number": 5, "chunk_index": 6, "similarity": 0.81, "pdf_name": "HTML_Guide.pdf"},
    ]

    mock_client = MagicMock(spec=GroqClient)
    mock_client.generate.return_value = (
        "<thinking>\n"
        "1. Question Understanding: Basic HTML text formatting elements.\n"
        "2. Knowledge Retrieval: HTML_Guide.pdf pages 3 and 5.\n"
        "3. Evidence Analysis: Grounded excerpts.\n"
        "4. Reasoning Summary: Direct syllabus citations.\n"
        "</thinking>\n"
        "HTML text structuring includes heading tags (H1 through H6) and paragraph tags (<p>) along with anchor hyperlinks (<a>)."
    )

    with patch("services.knowledge_retriever.search_similar_chunks", return_value=chunks):
        response = generate_answer("What elements structure text and links in HTML?", client=mock_client)

    assert len(response.sources) == 2
    for s in response.sources:
        assert s["document_name"] == "HTML_Guide.pdf"
        assert s["page_number"] in (3, 5)
        assert len(s["excerpt"]) > 10
        assert s["support_type"] in ("direct", "explanatory", "context")
        # Ensure no chunk_id leaked in final answer
        assert "src_p1" not in response.answer
        assert "src_p2" not in response.answer
