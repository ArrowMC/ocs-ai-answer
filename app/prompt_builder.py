import json
import logging
import re

from app.utils import parse_options

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_DEEP = """Answer this exam question. First analyze each option briefly (1-2 lines each), then give the answer as JSON on the LAST line.

Example response format:
A: correct because ... B: incorrect because ... C: incorrect because ... D: incorrect because ...
{"answer":"A"}

RULES:
- single choice → one letter: {"answer":"A"}
- multiple choice → letters joined by #: {"answer":"A#C"}
- judgement → "A" for true/correct, "B" for false/incorrect
- completion → fill-in text: {"answer":"Beijing"}
- Pick ONLY from the given options.
- If web search results are provided, reference them in your analysis.
- The VERY LAST LINE must be the JSON. Nothing after it."""


def build_user_prompt(title: str, qtype: str, options: str | None,
                      search_context: str = "") -> str:
    opts = parse_options(options)
    lines = [
        f"Question: {title}",
        f"Type: {qtype or 'unknown'}",
    ]
    if opts:
        lines.append("Options:")
        for opt in opts:
            lines.append(f"  {opt}")
    if search_context:
        lines.append(f"\n--- Web Search Results (for reference) ---\n{search_context}")
    return "\n".join(lines)


def _try_json_extraction(text: str) -> str | None:
    """Try multiple strategies to extract JSON answer from text."""
    # 1. Try whole text as JSON
    try:
        answer = json.loads(text)["answer"]
        logger.debug("JSON layer 1 (strict): extracted answer=%s", answer)
        return answer
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.debug("JSON layer 1 (strict): failed — %s", e)

    # 2. Try extracting JSON block from markdown fenced code
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            answer = json.loads(m.group(1))["answer"]
            logger.debug("JSON layer 2 (fenced): extracted answer=%s", answer)
            return answer
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("JSON layer 2 (fenced): failed — %s", e)

    # 3. Find JSON-like object containing "answer" key (lenient, handles nested braces)
    for match in re.finditer(r'\{', text):
        depth = 0
        start = match.start()
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        answer = json.loads(candidate)["answer"]
                        logger.debug("JSON layer 3 (brace-matching): extracted answer=%s from candidate=%s",
                                     answer, candidate[:100])
                        return answer
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.debug("JSON layer 3 (brace-matching): candidate failed — %s | candidate=%s",
                                     e, candidate[:100])
                        break

    logger.debug("JSON extraction: all 3 layers failed")
    return None


def _try_pattern_extraction(text: str) -> str | None:
    """Try regex patterns to extract answers from free-text AI responses."""

    # Multi-select: A#B#C or A#B or A#B#C#D
    m = re.search(r'\b([A-H](?:#[A-H])+)\b', text)
    if m:
        logger.debug("Pattern layer: multi-select match=%s", m.group(1))
        return m.group(1)

    # Answer field in plain text: "answer": "A" or answer: A
    m = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    if m:
        logger.debug("Pattern layer: quoted answer field match=%s", m.group(1))
        return m.group(1)
    m = re.search(r'answer\s*[:：]\s*"?([A-H](?:#[A-H])*)"?', text, re.IGNORECASE)
    if m:
        logger.debug("Pattern layer: plain answer field match=%s", m.group(1))
        return m.group(1)

    # Chinese judgement patterns
    if re.search(r'(正确|是对的|正确选项|答案.*?对|√|✅|true)', text, re.IGNORECASE):
        logger.debug("Pattern layer: chinese judgement → A")
        return "A"
    if re.search(r'(错误|是错的|不正确|答案.*?错|×|❌|false)', text, re.IGNORECASE):
        logger.debug("Pattern layer: chinese judgement → B")
        return "B"

    # Single letter: A-H, possibly with brackets or punctuation
    m = re.search(r'(?:^|\s|选|选择|选项|[\(（])\s*([A-H])\s*(?:$|\s|[\)）\.。,，]|选项)', text)
    if m:
        logger.debug("Pattern layer: contextual single letter match=%s", m.group(1))
        return m.group(1)
    # Bare single letter as last resort
    m = re.search(r'\b([A-H])\b', text)
    if m:
        logger.debug("Pattern layer: bare single letter match=%s", m.group(1))
        return m.group(1)

    logger.debug("Pattern layer: no match found")
    return None


def _try_completion_fallback(text: str) -> str | None:
    """Last resort: extract free-text completion answer."""
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if lines:
        for line in reversed(lines):
            if not line.startswith('#') and not line.startswith('```') and len(line) < 200:
                line = re.sub(r'^(答案|填空|回答|Answer|The answer is|答)[:：]?\s*', '', line, flags=re.IGNORECASE)
                line = line.strip('"\'')
                if line:
                    logger.debug("Completion fallback: extracted=%s", line)
                    return line
    logger.debug("Completion fallback: no usable line found")
    return None


def parse_ai_response(text: str) -> str:
    # Layer 1: JSON extraction (strict, fenced, lenient)
    answer = _try_json_extraction(text)
    if answer is not None:
        logger.info("Answer extracted via JSON parsing: %s", answer)
        return answer

    # Layer 2: Regex pattern extraction
    answer = _try_pattern_extraction(text)
    if answer is not None:
        logger.warning("Answer extracted via regex fallback: %s", answer)
        logger.warning("Raw AI response: %s", text[:500])
        return answer

    # Layer 3: Completion fallback
    answer = _try_completion_fallback(text)
    if answer is not None:
        logger.warning("Answer extracted via completion fallback: %s", answer)
        logger.warning("Raw AI response: %s", text[:500])
        return answer

    logger.error("=== PARSE FAILURE ===")
    logger.error("All 3 layers failed. Full AI response (%d chars):\n%s", len(text), text)
    raise ValueError(f"Cannot parse answer from AI response: {text[:300]}")