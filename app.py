from flask import Flask, render_template, request, jsonify
import re, json, os, requests
from datetime import datetime
from dotenv import load_dotenv
from celery_worker import evaluate_with_llama
from validators import validate_medical_prompt_result

load_dotenv()
app = Flask(__name__)

# ✅ Set secure content policy headers
@app.after_request
def apply_csp(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; connect-src 'self'; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "object-src 'none'; frame-ancestors 'none'; "
    )
    return response

# ✅ Append evaluation log to local file
def write_log_entry(prompt, model, score):
    log_file_path = 'logs.jsonl'
    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "model": model,
        "score": score
    }
    with open(log_file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')

# ✅ Lightweight local regex-based evaluator (fast fallback)
def regex_evaluate_prompt(prompt):
    criteria = {
        "clinical_clarity": {"pattern": r'\b(patient|symptom|diagnosis|condition|history)\b', "weight": 0.25},
        "specificity": {"pattern": r'\b(step-by-step|list|rank|compare|outline|guide)\b', "weight": 0.20},
        "safety": {"pattern": r'\b(risk|contraindication|warning|side effect|precaution)\b', "weight": 0.30},
        "instructional_style": {"pattern": r'\b(guide|steps|structured|instructions|metaphor|tip)\b', "weight": 0.15},
        "medical_term": {"pattern": r'\b(diabetes|hypertension|cholesterol|asthma|insulin|medication)\b', "weight": 0.10},
    }
    results = {}
    total = 0
    suggestions = []
    for key, rule in criteria.items():
        if re.search(rule["pattern"], prompt, re.IGNORECASE):
            results[key] = True
            total += rule["weight"]
        else:
            results[key] = False
            suggestions.append(f"Consider strengthening: {key.replace('_',' ').title()}")
    score = round(total * 100)
    return score, results, suggestions

# === ROUTES ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/evaluate', methods=['POST'])
def evaluate_prompt():
    prompt = request.get_json().get('prompt', '').strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400
    score, criteria, suggestions = regex_evaluate_prompt(prompt)
    write_log_entry(prompt, "regex", score)
    return jsonify({
        "score": score,
        "criteria_scores": criteria,
        "suggestions": suggestions
    })

@app.route('/api/evaluate_llama', methods=['POST'])
def evaluate_prompt_llama():
    prompt = request.get_json().get('prompt', '').strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    system_instruction = (
        "You are a prompt evaluator for medical prompts. "
        "Evaluate based on Safety (30), Clinical Clarity (25), Specificity (20), "
        "Instructional Style (15), Medical Terminology (10). Score 0–100 and give suggestions."
    )
    model_name = os.getenv("OLLAMA_MODEL", "llama3:8b-instruct-q4_K_M")
    ollama_url = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512,
        "temperature": 0.2
    }

    try:
        res = requests.post(ollama_url, json=payload, timeout=60)
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        cleaned = re.sub(r'```json\s*|\s*```', '', content).strip()
        result = json.loads(cleaned)
        is_valid, reason = validate_medical_prompt_result(result)
        if not is_valid:
            return jsonify({"error": "Validation failed", "reason": reason}), 400
        score = result.get("score", 0)
        write_log_entry(prompt, "phi3", score)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/async_evaluate', methods=['POST'])
def async_evaluate():
    prompt = request.get_json().get('prompt', '').strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    system_instruction = (
        "You are a prompt evaluator for medical prompts. "
        "Evaluate based on Safety (30), Clinical Clarity (25), Specificity (20), "
        "Instructional Style (15), Medical Terminology (10). Return only a JSON object."
    )
    task_input = f"{system_instruction}\n\nPrompt:\n{prompt}\n\nReturn JSON with score, suggestions, criteria."
    task = evaluate_with_llama.delay(task_input)
    return jsonify({"task_id": task.id}), 202

@app.route('/api/task/<task_id>', methods=['GET'])
@app.route('/api/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    async_result = evaluate_with_llama.AsyncResult(task_id)
    state = async_result.state

    if state == 'PENDING':
        return jsonify({"status": "pending"}), 202
    if state == 'SUCCESS':
        result = async_result.result
        if isinstance(result, list) and result and isinstance(result[0], dict):
            result = result[0]
        if isinstance(result, dict) and ("error" in result or "reason" in result):
            return jsonify({"status": "failed", **result}), 422
        if not isinstance(result, dict):
            return jsonify({"status": "error", "error": "Unexpected result format"}), 500
        prompt = result.get("prompt", "[async prompt not returned]")
        score = result.get("score", 0)
        write_log_entry(prompt, "phi3 (async)", score)
        return jsonify({"status": "completed", "result": result}), 200
    if state == 'FAILURE':
        return jsonify({"status": "failed", "error": str(async_result.info)}), 500

    return jsonify({"status": state}), 200

@app.route('/logs', methods=['GET'])
def get_logs():
    try:
        with open('logs.jsonl', 'r', encoding='utf-8') as f:
            logs = [json.loads(line) for line in f if line.strip()]
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": "Failed to read logs", "details": str(e)}), 500

@app.route('/api/improve_prompt', methods=['POST'])
def improve_prompt():
    prompt = request.get_json().get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    system_instruction = (
        "You are a clinical prompt editor. Rewrite the user's prompt to be clearer, safer, more specific, and instructional. "
        "Do not explain. Return ONLY the improved prompt, nothing else."
    )

    payload = {
        "model": "llama3:8b-instruct-q4_K_M",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512,
        "temperature": 0.3
    }

    try:
        res = requests.post("http://localhost:11434/v1/chat/completions", json=payload, timeout=60)
        res.raise_for_status()
        content = res.json()['choices'][0]['message']['content'].strip()
        return jsonify({"improved": content})
    except Exception:
        return jsonify({"improved": prompt, "error": "LLM failed"}), 200

# ✅ FINAL: disable debug mode before launch
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
