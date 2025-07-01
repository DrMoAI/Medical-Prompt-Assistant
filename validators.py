def validate_medical_prompt_result(parsed, tolerance=1):
    """
    Validates LLM evaluation output for correct structure, types, and scoring.
    Returns (True, "") if valid, (False, "reason") if not.
    Accepts structured scores OR error objects.
    """

    # 1. Top-level type check
    if not isinstance(parsed, dict):
        return False, "Result is not a valid JSON object."

    # 2. Accept error-based rejections
    if "error" in parsed:
        allowed_errors = {
            "Prompt is not medically relevant.",
            "Prompt blocked due to safety concerns.",
        }
        if parsed["error"] in allowed_errors:
            return True, ""
        return False, f"Unrecognized error message: {parsed['error']}"

    # 3. Must have all 3 required keys for evaluation result
    for key in ("score", "criteria", "suggestions"):
        if key not in parsed:
            return False, f"Missing top-level field: '{key}'."

    # 4. Criteria type and structure
    criteria = parsed["criteria"]
    if not isinstance(criteria, dict):
        return False, "Field 'criteria' must be a dict."

    expected = {
        "safety": 30,
        "clinical_clarity": 25,
        "specificity": 20,
        "instructional_style": 15,
        "medical_terminology": 10,
    }
    total = 0
    for name, max_val in expected.items():
        if name not in criteria:
            return False, f"Missing criterion: '{name}'."
        val = criteria[name]
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        elif isinstance(val, str) and val.isdigit():
            val = int(val)
        if not (isinstance(val, int) and 0 <= val <= max_val):
            return False, f"Invalid score for '{name}': {val} (must be 0–{max_val})."
        total += val

    # 5. Score validation
    score = parsed["score"]
    if not isinstance(score, int):
        return False, "Field 'score' must be an integer."
    if abs(score - total) > tolerance:
        return False, f"Reported score {score} does not match sum {total} (tolerance {tolerance})."

    # 6. Suggestions
    suggestions = parsed["suggestions"]
    if not isinstance(suggestions, list):
        return False, "Field 'suggestions' must be a list."
    if not suggestions:
        return False, "Suggestions list cannot be empty."
    for idx, s in enumerate(suggestions):
        if not (isinstance(s, str) and s.strip()):
            return False, f"Suggestion at index {idx} must be a non-empty string."

    return True, ""
