from celery_worker import evaluate_with_llama

if __name__ == "__main__":
    test_prompt = "Write a warm, reassuring, concise explanation of high cholesterol for a 65-year-old patient, using simple, everyday language without medical jargon. Clearly explain what it is and why it matters, avoiding alarm. Include one practical, positive lifestyle tip the patient can start today. Keep it under 100 words, formatted as a friendly paragraph for a doctor's office handout. Optionally, compare your response to a provided example to assess tone, clarity, and approach."
    task = evaluate_with_llama.delay(test_prompt)
    print(f"Task submitted. Task ID: {task.id}")
    print("Waiting for result...")

    result_dict = task.get(timeout=90)
    print("Result:", result_dict)

    # Access individual fields by key, never by unpacking
    print("Score:", result_dict.get("score"))
    print("Criteria:", result_dict.get("criteria"))
    print("Suggestions:", result_dict.get("suggestions"))
