import ast
import subprocess
import sys
import tempfile
import logging
from typing import Any

from app.config import CONFIG

logger = logging.getLogger(__name__)

APPROVED_IMPORTS = set(CONFIG.dqe.approved_imports)
TIMEOUT = CONFIG.dqe.execution_timeout_seconds
BANNED_NODES = {"AsyncFunctionDef"}
BANNED_CALLS = {"exec", "eval", "open", "compile", "__import__"}


class SafetyFilterError(Exception):
    pass


def _check_imports(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [node.module] if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
            )
            for name in names:
                root = (name or "").split(".")[0]
                if root not in APPROVED_IMPORTS:
                    raise SafetyFilterError(f"Import not allowed: {root}")


def _check_banned_calls(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BANNED_CALLS:
                    raise SafetyFilterError(f"Banned call: {node.func.id}")
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {"system", "popen", "run", "Popen"}:
                    if not _is_allowed_subprocess(node):
                        raise SafetyFilterError(f"Banned subprocess method: {node.func.attr}")


def _is_allowed_subprocess(node: ast.Call) -> bool:
    # allow subprocess.run with capture_output only — no shell=True
    if not isinstance(node.func, ast.Attribute):
        return False
    for kw in node.keywords:
        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
            raise SafetyFilterError("subprocess shell=True is not allowed")
    return True


def run_static_filter(code: str) -> None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SafetyFilterError(f"Syntax error in code: {e}")
    _check_imports(tree)
    _check_banned_calls(tree)


def execute_sandboxed(code: str) -> dict[str, Any]:
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip(), "output": None}

        return {"success": True, "output": result.stdout.strip(), "error": None}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Execution exceeded {TIMEOUT}s timeout", "output": None}
    except Exception as e:
        logger.error(f"Sandbox execution failed: {e}")
        return {"success": False, "error": str(e), "output": None}
