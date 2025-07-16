import os
from dotenv import load_dotenv
load_dotenv()  # Load your .env with REDIS config

import json
import json5
import re
from datetime import datetime
import requests
from json.decoder import JSONDecodeError
from celery import Celery, Task
from validators import validate_medical_prompt_result

celery = Celery(
    'tasks',
    broker=os.getenv('CELERY_BROKER_URL'),
    backend=os.getenv('CELERY_RESULT_BACKEND')
)

LOG_FILE = os.path.join("logs", "evaluations.jsonl")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def flatten_suggestions(suggestions):
    if isinstance(suggestions, list):
        return [
            str(item).strip()
            for sublist in suggestions
            for item in (sublist if isinstance(sublist, list) else [sublist])
            if isinstance(item, str) and item.strip()
        ]
    return []

def is_soft_rejection(parsed):
    if not isinstance(parsed, dict):
        return False
    score = parsed.get("score", 0)
    criteria = parsed.get("criteria", {})
    suggestions = parsed.get("suggestions", [])
    if score != 0:
        return False
    if not isinstance(criteria, dict):
        return False
    all_zero = all(criteria.get(k, 0) == 0 for k in [
        "safety", "clinical_clarity", "specificity", "instructional_style", "medical_terminology"
    ])
    few_suggestions = len(suggestions) <= 1
    vague = True if suggestions and len(suggestions[0].split()) < 12 else False
    return all_zero and (few_suggestions or vague)

def log_evaluation(prompt, result, model="llama3:8b-instruct-q4_K_M"):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "model": model,
        "prompt": prompt,
        "result": result,
        "score": result.get("score", 0) if isinstance(result, dict) else 0,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        return {
            "error": "Exception during evaluation",
            "reason": str(e),
            "status": "failed"
        }

POLICY_PHRASES = [
    "not allowed", "against policy", "not permitted", "cannot help with",
    "violates", "against ethical", "not appropriate", "i cannot assist",
    "safety guidelines", "not medically appropriate", "i'm sorry, but i can't"
]

def is_policy_rejection(text):
    text = text.lower()
    return any(phrase in text for phrase in POLICY_PHRASES)

def clean_llm_output(text):
    text = re.sub(r'```(?:json)?|```', '', text)
    text = text.replace('"""', '')
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    return text

def repair_llm_json(text):
    return re.sub(r'(\d+)\s*(")', r'\1,\n\2', text)

def auto_close_json(text):
    open_braces = text.count("{")
    close_braces = text.count("}")
    open_brackets = text.count("[")
    close_brackets = text.count("]")
    while close_brackets < open_brackets:
        text += "]"
        close_brackets += 1
    while close_braces < open_braces:
        text += "}"
        close_braces += 1
    return text

@celery.task(
    bind=True,
    name="tasks.evaluate_with_llama",
    autoretry_for=(JSONDecodeError, ValueError, Exception),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    retry_backoff=False,
    retry_jitter=False
)
def evaluate_with_llama(self, prompt):
    orig_prompt = prompt
    actual_prompt = re.search(r"Prompt:\s*(.*?)\n\nReturn JSON", orig_prompt, re.DOTALL)
    prompt_for_count = actual_prompt.group(1).strip() if actual_prompt else orig_prompt

    system_instruction = (
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

    payload = {
        "model": "llama3:8b-instruct-q4_K_M",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512,
        "temperature": 0.15,
    }

    try:
        res = requests.post("http://localhost:11434/v1/chat/completions", json=payload, timeout=60)
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']

        if is_policy_rejection(content):
            result = {
                "error": "non_medical_prompt",
                "reason": "Harmful or unsafe content detected"
            }
            log_evaluation(orig_prompt, result)
            return result

        cleaned = auto_close_json(repair_llm_json(clean_llm_output(content)))

        if "Prompt is not medically relevant" in cleaned:
            reason = "Harmful or self-harm content detected" if "kill yourself" in orig_prompt.lower() else "Direct LLM response with no scoring"
            result = {
                "error": "non_medical_prompt",
                "reason": reason
            }
            log_evaluation(orig_prompt, result)
            return result

        parsed = json5.loads(cleaned)
        if isinstance(parsed, list) and len(parsed) == 1:
            parsed = parsed[0]

        required_keys = {"score", "criteria", "suggestions"}
        if not required_keys.issubset(parsed):
            raise Exception(f"Missing top-level fields: {required_keys - set(parsed)}")

        criteria = parsed.get("criteria", {})
        cap = {"safety": 30, "clinical_clarity": 25, "specificity": 20, "instructional_style": 15, "medical_terminology": 10}
        for k in criteria:
            try:
                value = float(criteria[k])  # handle both string and numeric input
                criteria[k] = int(min(value, cap.get(k, 100)))
            except (ValueError, TypeError):
                criteria[k] = 0

        parsed["criteria"] = criteria
        criteria = {k.replace(" ", "_"): v for k, v in criteria.items()}
        parsed["score"] = int(sum(criteria.get(k, 0) for k in cap))

        if not validate_medical_prompt_result(parsed)[0]:
            raise Exception("Validation failed")

        text_to_check = (
            " ".join(parsed.get("suggestions", [])) +
            " " + str(parsed.get("prompt", "")) +
            " " + str(parsed.get("reason", ""))
        ).lower()

        rejection_phrases = [
            "not medically relevant", "not a medical prompt", "this is not a medical",
            "invalid prompt", "please provide a medical", "please provide a more specific and clinically relevant prompt",
            "please rephrase the prompt to include a clear clinical context and specific instructions",
            "please rephrase the prompt to include a clear clinical context and specific questions",
            "please provide a more specific and clear prompt to ensure safety and clinical relevance"
        ]
        if any(bad in text_to_check for bad in rejection_phrases):
            parsed.update({
                "score": 0,
                "criteria": {k: 0 for k in cap},
                "suggestions": ["Prompt is not medically valid. Please provide a clear clinical context."],
                "error": "non_medical_prompt",
                "reason": "LLM response indicates vague or non-clinical input"
            })

        word_count = len(prompt_for_count.split())
        if word_count < 12 and parsed.get("score", 0) > 90:
            original_score = parsed["score"]
            new_score = 85
            ratio = new_score / original_score if original_score else 1
            for k in parsed["criteria"]:
                parsed["criteria"][k] = round(parsed["criteria"][k] * ratio)
            parsed["score"] = sum(parsed["criteria"].values())
            if not validate_medical_prompt_result(parsed)[0]:
                raise Exception("Validation failed")
            log_evaluation(orig_prompt, parsed)
            return parsed

        if is_soft_rejection(parsed):
            parsed["error"] = "non_medical_prompt"
            parsed["reason"] = "Score is 0 and structure suggests vague or non-medical prompt."
            harm_flags = ["harmful", "dangerous", "unsafe", "triggering", "kill", "suicide", "hurt"]
            suggestion_text = " ".join(parsed.get("suggestions", [])).lower()
            if any(flag in suggestion_text for flag in harm_flags):
                parsed["harmful"] = True

        elif parsed.get("score", 0) == 0 and "error" not in parsed:
            fallback_suggestions = parsed.get("suggestions", [])
            if any(
                any(keyword in suggestion.lower() for keyword in ["harmful", "triggering", "dangerous", "illegal", "unsafe"])
                for suggestion in fallback_suggestions
            ):
                parsed["error"] = "non_medical_prompt"
                parsed["reason"] = "Score is 0 and suggestions indicate potentially harmful or unsafe prompt."

        if 0 < parsed["score"] <= 45 and "error" not in parsed:
            parsed.setdefault("suggestions", []).insert(0,
                "⚠️ This prompt may be too vague or broad. Consider adding clinical context (e.g., patient type, symptom detail)."
            )

        parsed["prompt"] = orig_prompt
        log_evaluation(orig_prompt, parsed)
        return parsed

    except Exception as e:
        result = {"error": "Exception during evaluation", "reason": str(e)}
        log_evaluation(orig_prompt, result)
        return result
