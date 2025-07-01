import time
from celery_worker import celery

# 1) Dispatch the task via the real worker’s Celery instance:
res = celery.send_task("tasks.evaluate_with_llama", args=["trigger retry"])
print("🚀 Dispatched Task ID:", res.id)
print("👀 Now switch to your Celery worker console to watch for retry logs…")

# 2) (Optional) Poll until done—no unpacking here, just quiet polling
while not res.ready():
    time.sleep(1)

# 3) Once complete, print whether it succeeded or raised:
try:
    out = res.get(timeout=1)
    print("✅ Task completed:", out)
except Exception as e:
    print("❌ Task failed after retries:", repr(e))
