import json
import json5
import os
import re
from datetime import datetime
import requests
from celery import Celery
from validators import validate_medical_prompt_result  # ✅ import validator

# Setup Celery
celery = Celery(
    'tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Setup logging directory
LOG_FILE = os.path.join("logs", "evaluations.jsonl")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_evaluation(prompt, result, model="llama3:8b-instruct-q4_K_M"):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "model": model,
        "prompt": prompt,
        "result": result
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            json.dump(entry, f)
            f.write("\n")
    except Exception as e:
        print(f"[Logging Error] Failed to write log: {e}")

def clean_llm_output(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[len("```"):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]
    return text

def repair_llm_json(text):
    """
    Fix missing commas between number values and JSON keys.
    Example: "medical_terminology": 10 "suggestions" → adds comma
    """
    text = re.sub(r'(\d+)\s*(")', r'\1,\n\2', text)
    return text

@celery.task
def evaluate_with_llama(prompt):
    is_retry = prompt.endswith(" [retry]")
    if is_retry:
        prompt = prompt.replace(" [retry]", "")

    system_instruction = (
        "You are a world-class expert in clinical prompt evaluation and AI safety auditing.\n\n"
        "Evaluate the user's medical prompt with precision and consistency using the following criteria:\n"
        "- Safety (30 points): Avoids unsafe, misleading, or harmful advice.\n"
        "- Clinical Clarity (25 points): Clear and clinically coherent.\n"
        "- Specificity (20 points): Includes patient age, history, symptoms, or context.\n"
        "- Instructional Style (15 points): Requests actionable, clear guidance.\n"
        "- Medical Terminology (10 points): Uses accurate medical language.\n\n"
        "Return a JSON object with ONLY these keys:\n"
        "  \"score\": integer (0–100), sum of criteria scores,\n"
        "  \"criteria\": {\"safety\": 0–30, \"clinical_clarity\": 0–25, \"specificity\": 0–20, \"instructional_style\": 0–15, \"medical_terminology\": 0–10},\n"
        "  \"suggestions\": list of up to 3 concrete suggestions to improve the prompt.\n\n"
        "Do NOT include any explanations, markdown, or extra text — only the strict JSON.\n"
        "If the prompt is not related to medicine or healthcare, respond with:\n"
        "{\"error\": \"Prompt is not medically relevant.\"}\n"
        "IMPORTANT: Enclose ALL property names in double quotes. Do not use colons without quoted keys."
    )

    payload = {
        "model": "llama3:8b-instruct-q4_K_M",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 300,
        "temperature": 0.15,
    }

    try:
        res = requests.post("http://localhost:11434/v1/chat/completions", json=payload, timeout=60)
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content']
        print("\n--- RAW LLM OUTPUT ---")
        print(content)
        print("--- END RAW OUTPUT ---\n")

        cleaned = clean_llm_output(content)
        cleaned = repair_llm_json(cleaned)

        try:
            parsed = json5.loads(cleaned)

            # Unwrap if LLM returned a single-item list
            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                parsed = parsed[0]

            required_keys = {"score", "criteria", "suggestions"}
            if not required_keys.issubset(parsed):
                missing = required_keys - set(parsed.keys())
                # 🚨 If missing keys, propagate error up, don't "fix" result!
                raise Exception(f"Missing one or more top-level fields: {', '.join(missing)}")

        except Exception as e1:
            print(f"[JSON5 Parsing Error]: {e1}")
            print("[DEBUG] Cleaned Content:\n", cleaned)
            print("[📦 Original RAW LLM output]:\n", content)
            # 🚨 Return an error result immediately!
            error_result = {
                "error": "JSON parse failure",
                "reason": str(e1),
                "raw_content": content,
                "raw_cleaned": cleaned
            }
            log_evaluation(prompt, error_result)
            return error_result

        # Ensure output is dict
        if not isinstance(parsed, dict):
            error_result = {
                "error": "Invalid response type",
                "reason": "Expected dict after parsing.",
                "raw_response": parsed
            }
            log_evaluation(prompt, error_result)
            return error_result

        if "error" in parsed:
            error_result = {
                "error": parsed["error"],
                "reason": parsed["error"],
                "raw_response": parsed
            }
            log_evaluation(prompt, error_result)
            return error_result

        criteria_scores = parsed.get("criteria", {})

        # Clip scores to valid range before validation
        max_allowed = {
            "safety": 30,
            "clinical_clarity": 25,
            "specificity": 20,
            "instructional_style": 15,
            "medical_terminology": 10
        }
        for k in criteria_scores:
            if isinstance(criteria_scores[k], (int, float)):
                criteria_scores[k] = min(criteria_scores[k], max_allowed.get(k, 100))

        parsed["criteria"] = criteria_scores  # Reassign cleaned data

        parsed["score"] = sum(criteria_scores.get(k, 0) for k in [
            "safety", "clinical_clarity", "specificity", "instructional_style", "medical_terminology"
        ])

        # ---------- CRITICAL POST-PARSE VALIDATION BLOCKS BELOW ----------

        is_valid, reason = validate_medical_prompt_result(parsed)
        if not is_valid:
            error_result = {
                "error": "Validation failed",
                "reason": reason,
                "raw_response": parsed
            }
            log_evaluation(prompt, error_result)
            return error_result

        # HARD BLOCK: Detect fake fallback output (all zeros + generic suggestions)
        generic_suggestions = [
            "Provide a clear and concise medical question or request for guidance.",
            "Incorporate relevant patient information, such as symptoms or medical history.",
            "Use proper medical terminology to ensure accurate and helpful responses."
        ]
        if (
            all(parsed["criteria"].get(k, 0) == 0 for k in [
                "safety", "clinical_clarity", "specificity", "instructional_style", "medical_terminology"
            ])
            and parsed.get("score", 0) == 0
            and any(sugg in parsed.get("suggestions", []) for sugg in generic_suggestions)
        ):
            error_result = {
                "error": "LLM returned generic fallback output.",
                "reason": "Model hallucinated valid-looking response for an invalid/non-medical prompt.",
                "raw_response": parsed
            }
            log_evaluation(prompt, error_result)
            return error_result
        
                # HARD BLOCK: Detect fake 100/100 on non-medical prompts (LLM hallucination)
        if (
            all(parsed["criteria"].get(k, 0) == max_allowed[k] for k in max_allowed) and
            parsed.get("score", 0) == 100 and
            any(
                ("not related to medicine" in s.lower() or "provide a medical-related prompt" in s.lower())
                for s in parsed.get("suggestions", [])
            )
        ):
            error_result = {
                "error": "LLM returned fake perfect score for a non-medical prompt.",
                "reason": "Model hallucinated 100/100 response for a non-medical prompt.",
                "raw_response": parsed
            }
            log_evaluation(prompt, error_result)
            return error_result

        # Block non-medical prompts after parsing, regardless of score
        medical_keywords = [
            "patient", "diagnosis", "treatment", "medical", "disease", "symptom", "therapy", "prescription",
            "hospital", "doctor", "nurse", "medication", "surgery", "health", "chronic", "acute", "illness",
            "pharmacy", "procedure", "imaging", "consultation", "assessment", "follow-up", "clinical", "signs"
        ]
        if not any(word in prompt.lower() for word in medical_keywords):
            error_result = {
                "error": "Prompt is not medically relevant.",
                "reason": "Prompt content did not match known medical keywords.",
                "raw_response": parsed
            }
            log_evaluation(prompt, error_result)
            return error_result

        # Everything good, return validated result
        parsed["prompt"] = prompt
        log_evaluation(prompt, parsed)
        return parsed

    except Exception as e:
        print("[Fallback] Exception:", str(e))
        fail_result = {
            "error": "Exception during evaluation",
            "reason": str(e)
        }
        log_evaluation(prompt, fail_result)
        return fail_result
