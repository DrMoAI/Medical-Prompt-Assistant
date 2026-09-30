"""
Scores a medical prompt with the language model.

Replaces the old Celery task: same rubric and same result shape, but it runs
directly (app.py runs it in a background thread), so Redis and Celery are not needed.
"""
import json
import os
import re
from datetime import datetime

import json5

import llm_client
from validators import validate_medical_prompt_result

LOG_FILE = os.path.join("logs", "evaluations.jsonl")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

CAPS = {
    "safety": 30,
    "clinical_clarity": 25,
    "specificity": 20,
    "instructional_style": 15,
    "medical_terminology": 10,
}

SYSTEM_INSTRUCTION = (
    "Return only raw JSON. Do not use any markdown fences or triple-quotes.\n\n"
    "You are a clinical prompt evaluation expert and AI safety auditor.\n\n"
    "Your task is to assess prompts intended for medical or healthcare settings only.\n\n"
    "Use the following scoring rubric (max 100 points):\n"
    "- \"safety\": 0–30 — Prompt must actively guide a safe, clinically responsible, and bounded response.\n"
    "  Award full points only if the prompt constrains dangerous interpretations (e.g., clarifies type, audience, or clinical setting).\n"
    "  Broad or ambiguous prompts may still be non-harmful but should score 20–25 due to risk of oversimplification.\n"
    "- \"clinical_clarity\": 0–25 — Measures how clear, coherent, and clinically focused the prompt is.\n"
    "  Prompts should specify clinical context (diagnosis, stage, or decision point).\n"
    "  Full score requires both linguistic clarity and medical framing. Vague questions (e.g., “Tell me about X”) score lower (10–15).\n"
    "- \"specificity\": 0–20 — Measures how precisely the prompt defines the clinical scenario.\n"
    "  Full score requires inclusion of multiple relevant details such as patient age, sex, diagnosis, severity, comorbidities, or care setting.\n"
    "  Generic prompts that mention only a disease name without context should score ≤10.\n"
    "- \"instructional_style\": 0–15 — Prompts should request a clear output structure: steps, summaries, overviews, or actions.\n"
    "  Award full points only if the prompt uses directive language (e.g., “outline,” “list,” “compare”) and implies an organized response.\n"
    "  Open-ended or loosely phrased prompts without a clear task format should score ≤10.\n"
    "- \"medical_terminology\": 0–10 — Evaluates use of appropriate clinical terms in the prompt itself.\n"
    "  Full credit requires accurate and relevant terminology (e.g., “first-line treatment,” “lifestyle modification,” “antihypertensives”).\n"
    "  Prompts using everyday language or vague phrasing (e.g., “get better,” “fix blood sugar”) score ≤5.\n"
    "  Overly technical or irrelevant jargon does not raise the score.\n\n"
    "⚠️ Additional Guideline:\n"
    "- If the prompt is very short (fewer than 12 words), apply stricter scoring across all categories unless it is unusually specific and well-structured.\n"
    "- Do not award full points to vague, overly brief prompts.\n\n"
    "Respond in this strict JSON structure:\n"
    "{\n"
    "  \"score\": total_score_integer,\n"
    "  \"criteria\": {\n"
    "    \"safety\": int,\n"
    "    \"clinical_clarity\": int,\n"
    "    \"specificity\": int,\n"
    "    \"instructional_style\": int,\n"
    "    \"medical_terminology\": int\n"
    "  },\n"
    "  \"suggestions\": [\n"
    "    \"Concrete suggestion 1\",\n"
    "    \"Concrete suggestion 2\",\n"
    "    \"Concrete suggestion 3\"\n"
    "  ]\n"
    "}\n\n"
    "RULES:\n"
    "- Only evaluate prompts clearly related to medicine.\n"
    "- If not relevant, respond exactly: {\"error\": \"Prompt is not medically relevant.\"}\n"
    "- If unsafe (e.g., suicide), respond: {\"error\": \"Prompt blocked due to safety concerns.\"}\n"
    "- Use only double quotes.\n"
    "- Suggestions max 25 words each.\n"
    "- No explanation, markdown, or extra text."
)

# Only used when the model answers in plain prose instead of JSON.
POLICY_PHRASES = [
    "i cannot assist", "i can't assist", "i'm sorry, but i can't",
    "cannot help with", "against policy", "not permitted",
]

REJECTION_PHRASES = [
    "not medically relevant", "not a medical prompt", "this is not a medical",
    "invalid prompt", "please provide a medical",
]


def log_evaluation(prompt, result, backend="unknown"):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "backend": backend,
        "prompt": prompt,
        "result": result,
        "score": result.get("score", 0) if isinstance(result, dict) else 0,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break an evaluation


def clean_llm_output(text):
    """Strip code fences and keep only the outermost {...}."""
    text = re.sub(r"```(?:json)?|```", "", text)
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        text = text[first:last + 1]
    return text


def auto_close_json(text):
    """Add missing closing brackets if the model was cut off."""
    text += "]" * max(0, text.count("[") - text.count("]"))
    text += "}" * max(0, text.count("{") - text.count("}"))
    return text


def _non_medical(reason, prompt, backend):
    result = {"error": "non_medical_prompt", "reason": reason}
    log_evaluation(prompt, result, backend)
    return result


def evaluate_prompt(prompt):
    """
    Score one prompt. Always returns a dict:
      success -> {"score", "criteria", "suggestions", "prompt"}
      failure -> {"error", "reason"}
    """
    backend = "unknown"
    try:
        user_message = (
            f"Prompt:\n{prompt}\n\nReturn JSON with score, suggestions, criteria."
        )
        content, backend = llm_client.chat(
            SYSTEM_INSTRUCTION, user_message,
            temperature=0.15, max_tokens=700, json_mode=True,
        )

        cleaned = auto_close_json(clean_llm_output(content))
        if "{" not in cleaned:
            if any(p in content.lower() for p in POLICY_PHRASES):
                return _non_medical("Harmful or unsafe content detected", prompt, backend)
            raise ValueError("Model did not return JSON.")

        parsed = json5.loads(cleaned)
        if isinstance(parsed, list) and len(parsed) == 1:
            parsed = parsed[0]

        # Model refused / said not medical, using the error format we asked for.
        if isinstance(parsed, dict) and "error" in parsed and "score" not in parsed:
            msg = str(parsed.get("error", ""))
            if "safety" in msg.lower():
                reason = "Harmful or self-harm content detected"
            else:
                reason = "Direct LLM response with no scoring"
            return _non_medical(reason, prompt, backend)

        missing = {"score", "criteria", "suggestions"} - set(parsed)
        if missing:
            raise ValueError(f"Missing top-level fields: {missing}")

        # Clamp each criterion to its maximum, then recompute the total ourselves.
        criteria = {str(k).replace(" ", "_"): v for k, v in parsed["criteria"].items()}
        for k in criteria:
            try:
                criteria[k] = int(min(float(criteria[k]), CAPS.get(k, 100)))
            except (TypeError, ValueError):
                criteria[k] = 0
        parsed["criteria"] = criteria
        parsed["score"] = sum(criteria.get(k, 0) for k in CAPS)

        ok, reason = validate_medical_prompt_result(parsed)
        if not ok:
            raise ValueError(f"Validation failed: {reason}")

        # If the suggestions themselves say "this isn't a medical prompt", treat as rejected.
        suggestion_text = " ".join(parsed["suggestions"]).lower()
        if any(p in suggestion_text for p in REJECTION_PHRASES):
            return _non_medical("LLM response indicates vague or non-clinical input", prompt, backend)

        # Very short prompts should not reach the top of the scale.
        if len(prompt.split()) < 12 and parsed["score"] > 90:
            ratio = 85 / parsed["score"]
            for k in parsed["criteria"]:
                parsed["criteria"][k] = round(parsed["criteria"][k] * ratio)
            parsed["score"] = sum(parsed["criteria"].values())

        # Score 0 with almost no feedback means the model rejected it.
        if parsed["score"] == 0:
            harm_flags = ["harmful", "dangerous", "unsafe", "triggering", "kill", "suicide", "hurt", "illegal"]
            if any(f in suggestion_text for f in harm_flags):
                result = {"error": "non_medical_prompt",
                          "reason": "Score is 0 and suggestions indicate potentially harmful or unsafe prompt."}
            else:
                result = {"error": "non_medical_prompt",
                          "reason": "Score is 0 and structure suggests vague or non-medical prompt."}
            log_evaluation(prompt, result, backend)
            return result

        if parsed["score"] <= 45:
            parsed["suggestions"].insert(
                0,
                "⚠️ This prompt may be too vague or broad. Consider adding clinical context "
                "(e.g., patient type, symptom detail).",
            )

        parsed["prompt"] = prompt
        log_evaluation(prompt, parsed, backend)
        return parsed

    except Exception as e:
        result = {"error": "Exception during evaluation", "reason": str(e)}
        log_evaluation(prompt, result, backend)
        return result
