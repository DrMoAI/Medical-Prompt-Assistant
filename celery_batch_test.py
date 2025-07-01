import json
import os
from celery import Celery
from dotenv import load_dotenv
from time import sleep

# === Load environment variables and Celery setup ===
load_dotenv()
app = Celery("manual", broker=os.getenv("CELERY_BROKER_URL"))
app.conf.result_backend = os.getenv("CELERY_RESULT_BACKEND")

# === Path to batch file ===
BATCH_DIR = "prompts_sets"
FILENAME = "final_stability_test_prompts.json"  # 🔁 Change to any of: prompts_medical_bad.json, prompts_mixed.json, etc.
PROMPT_FILE = os.path.join(BATCH_DIR, FILENAME)

# === Load prompts ===
with open(PROMPT_FILE, "r", encoding="utf-8") as f:
    prompts = json.load(f)

# === Run evaluations one by one ===
for i, item in enumerate(prompts):
    prompt = item["prompt"]
    model = item.get("model", "phi3")

    print(f"\n🔍 Prompt {i+1}/{len(prompts)}")
    print(f">>> {prompt[:80]}...")

    result = app.send_task("tasks.evaluate_with_llama", kwargs={
        "prompt": prompt
    })

    print(f"⏳ Task ID: {result.id}")
    while True:
        async_result = app.AsyncResult(result.id)
        if async_result.ready():
            try:
                output = async_result.get(timeout=3)
                print("✅ Result:\n", json.dumps(output, indent=2, ensure_ascii=False))
            except Exception as e:
                print("❌ Error:", e)
            break
        sleep(0.6)
