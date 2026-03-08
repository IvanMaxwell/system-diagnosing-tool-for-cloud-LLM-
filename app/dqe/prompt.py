from app.config import CONFIG

APPROVED_IMPORTS = CONFIG.dqe.approved_imports
TIMEOUT = CONFIG.dqe.execution_timeout_seconds


def build_dqe_prompt(intent: str) -> str:
    imports_str = ", ".join(APPROVED_IMPORTS)
    return f"""The user asked: "{intent}"

This query did not match any built-in diagnostic category.
You must write Python code to retrieve the requested system information.

STRICT RULES:
1. Only import from this whitelist: [{imports_str}]
2. No network calls. No file writes. No exec(). No eval().
3. Code must complete within {TIMEOUT} seconds.
4. Print results as JSON to stdout.
5. You MUST also write a plain English explanation of exactly what the code does.

Return ONLY this JSON structure, nothing else:
{{
  "code": "your python code here",
  "explanation": "plain English explanation for non-technical user"
}}"""


def build_rejection_prompt(reason: str) -> str:
    imports_str = ", ".join(APPROVED_IMPORTS)
    return f"""Your previous code was rejected by the safety filter.

Reason: {reason}

Rewrite the code following these rules strictly:
- Only import: {imports_str}
- No network calls, file writes, exec(), or eval()
- Must complete within {TIMEOUT} seconds
- Return JSON to stdout only

Return the same JSON structure: {{"code": "...", "explanation": "..."}}"""
