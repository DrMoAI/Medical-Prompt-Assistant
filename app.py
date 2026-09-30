from flask import Flask, render_template, request, jsonify
import re, json, uuid, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from dotenv import load_dotenv
import llm_client
from evaluator import evaluate_prompt as run_llm_evaluation

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
    prompt, err = get_prompt()
    if err:
        return err
    score, criteria, suggestions = regex_evaluate_prompt(prompt)
    write_log_entry(prompt, "regex", score)
    return jsonify({
        "score": score,
        "criteria_scores": criteria,
        "suggestions": suggestions
    })

MAX_PROMPT_CHARS = 500


def get_prompt():
    """Read and validate the prompt from the request. Returns (prompt, error_response)."""
    data = request.get_json(silent=True) or {}
    prompt = str(data.get('prompt', '')).strip()
    if not prompt:
        return None, (jsonify({"error": "Prompt is required"}), 400)
    if len(prompt) > MAX_PROMPT_CHARS:
        return None, (jsonify({"error": f"Prompt is too long (max {MAX_PROMPT_CHARS} characters)"}), 400)
    return prompt, None


@app.route('/api/evaluate_llama', methods=['POST'])
def evaluate_prompt_llama():
    """Synchronous LLM evaluation (waits for the answer)."""
    prompt, err = get_prompt()
    if err:
        return err
    result = run_llm_evaluation(prompt)
    if "error" in result:
        return jsonify(result), 422
    return jsonify(result)


# Background jobs. Kept in memory: fine for a single local user, and it means
# no Redis or Celery is needed. Jobs are lost if the app restarts.
_executor = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_jobs_lock = threading.Lock()
MAX_JOBS = 200


def _run_job(task_id, prompt):
    result = run_llm_evaluation(prompt)
    with _jobs_lock:
        _jobs[task_id] = {"done": True, "result": result}


@app.route('/api/async_evaluate', methods=['POST'])
def async_evaluate():
    prompt, err = get_prompt()
    if err:
        return err
    task_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[task_id] = {"done": False}
        while len(_jobs) > MAX_JOBS:          # forget the oldest jobs
            _jobs.pop(next(iter(_jobs)))
    _executor.submit(_run_job, task_id, prompt)
    return jsonify({"task_id": task_id}), 202


@app.route('/api/task/<task_id>', methods=['GET'])
@app.route('/api/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    with _jobs_lock:
        job = _jobs.get(task_id)
    if job is None:
        return jsonify({"status": "failed", "error": "Unknown or expired task"}), 404
    if not job["done"]:
        return jsonify({"status": "pending"}), 202
    result = job["result"]
    if "error" in result:
        return jsonify({"status": "failed", **result}), 422
    return jsonify({"status": "completed", "result": result}), 200


def _is_local_request():
    return request.remote_addr in ("127.0.0.1", "::1")


@app.route('/logs', methods=['GET'])
def get_logs():
    # Logs contain every prompt that was submitted, so only this computer may read them.
    if not _is_local_request():
        return jsonify({"error": "Forbidden"}), 403
    try:
        with open('logs.jsonl', 'r', encoding='utf-8') as f:
            logs = [json.loads(line) for line in f if line.strip()]
        return jsonify(logs)
    except FileNotFoundError:
        return jsonify([])
    except Exception as e:
        return jsonify({"error": "Failed to read logs", "details": str(e)}), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Shows which model backend is configured (never the key itself)."""
    return jsonify(llm_client.status())


@app.route('/api/improve_prompt', methods=['POST'])
def improve_prompt():
    prompt, err = get_prompt()
    if err:
        return err

    system_instruction = (
        "You are a clinical prompt editor. Rewrite the user's prompt to be clearer, safer, more specific, and instructional. "
        "Do not explain. Return ONLY the improved prompt, nothing else."
    )
    try:
        improved, backend = llm_client.chat(system_instruction, prompt, temperature=0.3, max_tokens=512)
        return jsonify({"improved": improved, "backend": backend})
    except llm_client.LLMError as e:
        # Report the failure honestly instead of echoing the user's own prompt back.
        return jsonify({"error": "LLM failed", "details": str(e)}), 502


# ✅ FINAL: disable debug mode before launch
if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5000)
