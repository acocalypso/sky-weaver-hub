import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "skyweaver"
SUBPROCESS_CALLS = {"run", "Popen", "call", "check_call", "check_output"}
ASYNCIO_SUBPROCESS_CALLS = {"create_subprocess_exec", "create_subprocess_shell"}


def test_production_code_does_not_use_shell_true_or_os_system():
    violations: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = dotted_name(node.func)
            if call_name == "os.system":
                violations.append(
                    f"{path.relative_to(BACKEND_ROOT.parent)}:{node.lineno} uses os.system"
                )
            if call_name in {f"subprocess.{name}" for name in SUBPROCESS_CALLS}:
                if keyword_bool(node, "shell") is True:
                    violations.append(
                        f"{path.relative_to(BACKEND_ROOT.parent)}:{node.lineno} "
                        "uses subprocess shell=True"
                    )
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    violations.append(
                        f"{path.relative_to(BACKEND_ROOT.parent)}:{node.lineno} "
                        f"passes a string command to {call_name}"
                    )
            if call_name == "asyncio.create_subprocess_shell":
                violations.append(
                    f"{path.relative_to(BACKEND_ROOT.parent)}:{node.lineno} "
                    "uses asyncio.create_subprocess_shell"
                )

    assert not violations, "Unsafe subprocess patterns found:\n" + "\n".join(violations)


def test_production_subprocess_usage_prefers_exec_or_argument_arrays():
    calls: list[str] = []
    for path in BACKEND_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = dotted_name(node.func)
            subprocess_names = {f"subprocess.{name}" for name in SUBPROCESS_CALLS}
            asyncio_names = {f"asyncio.{name}" for name in ASYNCIO_SUBPROCESS_CALLS}
            if call_name in subprocess_names | asyncio_names:
                calls.append(f"{path.relative_to(BACKEND_ROOT.parent)}:{node.lineno}:{call_name}")

    assert calls, (
        "Expected at least one production subprocess call to keep the safety scanner meaningful"
    )


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def keyword_bool(node: ast.Call, name: str) -> bool | None:
    for keyword in node.keywords:
        if (
            keyword.arg == name
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, bool)
        ):
            return keyword.value.value
    return None
