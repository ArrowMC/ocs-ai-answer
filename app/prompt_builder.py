import json
import re

from app.utils import parse_options

SYSTEM_PROMPT = """You are an assistant that answers educational questions accurately.
Given a question, its type, and its options, determine the correct answer.

Rules:
- For "single" (single choice): return exactly one letter, e.g. "A"
- For "multiple" (multi choice): return all correct letters joined by #, e.g. "A#C"
- For "judgement" (true/false): return "A" for true/correct, "B" for false/incorrect. If the options are not A/B, choose the letter matching the correct option.
- For "completion" (fill in blank): return the exact text that fills the blank
- If options are provided, choose ONLY from the given options. Never invent new options.

Respond in strict JSON format with no additional text:
{"answer": "<answer>", "reasoning": "<one-sentence explanation>"}"""


def build_user_prompt(title: str, qtype: str, options: str | None) -> str:
    opts = parse_options(options)
    lines = [
        f"Question: {title}",
        f"Type: {qtype or 'unknown'}",
    ]
    if opts:
        lines.append("Options:")
        for opt in opts:
            lines.append(f"  {opt}")
    return "\n".join(lines)


def parse_ai_response(text: str) -> str:
    # Try strict JSON first
    try:
        data = json.loads(text)
        return data["answer"]
    except (json.JSONDecodeError, KeyError):
        pass

    # Try extracting JSON block from markdown code fences
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            return data["answer"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Try regex for JSON object anywhere in text
    m = re.search(r'\{[^{}]*"answer"\s*:\s*"([^"]*)"[^{}]*\}', text)
    if m:
        return m.group(1)

    # Try to find a single letter answer (A, B, C, D...)
    m = re.search(r'\b([A-E])\b', text)
    if m:
        return m.group(1)

    raise ValueError(f"Cannot parse answer from AI response: {text[:200]}")
