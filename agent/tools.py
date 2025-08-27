import os
import shutil
import subprocess
from glob import glob
from typing import Dict, List, Tuple

from .config import get_workdir, get_tools_timeout_seconds, is_tool_allowed


class ToolError(Exception):
    pass


def _run(cmd: List[str], cwd: str, timeout: int) -> Tuple[int, str, str]:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise ToolError(f"Command timed out: {' '.join(cmd)}")
    return process.returncode, stdout, stderr


def _ensure_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise ToolError(f"Binary not found on PATH: {name}")


def run_terraform(cmd: str) -> Dict:
    """
    Execute a safe subset of terraform commands: init, validate, plan, show
    Returns a structured dict with exit_code, stdout, stderr.
    """
    tool_name = "run_terraform"
    if not is_tool_allowed(tool_name):
        return {"ok": False, "error": f"Tool not allowed: {tool_name}"}

    timeout = get_tools_timeout_seconds()
    cwd = os.path.abspath(get_workdir())

    try:
        _ensure_binary("terraform")
        parts = cmd.strip().split()
        if not parts:
            raise ToolError("Empty terraform command")
        sub = parts[0]
        safe_subs = {"init", "validate", "plan", "show", "version"}
        if sub not in safe_subs:
            raise ToolError(f"Disallowed terraform subcommand: {sub}")
        # Enforce non-interactive for safety
        if sub == "init":
            cmd_list = ["terraform", "init", "-input=false"] + parts[1:]
        elif sub == "plan":
            cmd_list = ["terraform", "plan", "-input=false", "-no-color"] + parts[1:]
        elif sub == "show":
            cmd_list = ["terraform", "show", "-no-color"] + parts[1:]
        elif sub == "validate":
            cmd_list = ["terraform", "validate", "-no-color"] + parts[1:]
        else:
            cmd_list = ["terraform"] + parts

        code, out, err = _run(cmd_list, cwd=cwd, timeout=timeout)
        return {"ok": code == 0, "exit_code": code, "stdout": out, "stderr": err}
    except ToolError as te:
        return {"ok": False, "error": str(te)}


def run_security_scan() -> Dict:
    """
    Run tfsec if available; otherwise checkov. Returns JSON or text results.
    """
    tool_name = "run_security_scan"
    if not is_tool_allowed(tool_name):
        return {"ok": False, "error": f"Tool not allowed: {tool_name}"}

    timeout = get_tools_timeout_seconds()
    cwd = os.path.abspath(get_workdir())

    # Try tfsec first
    if shutil.which("tfsec") is not None:
        cmd_list = ["tfsec", "--format", "json", "--no-color", "."]
        code, out, err = _run(cmd_list, cwd=cwd, timeout=timeout)
        ok = code == 0 or code == 1  # tfsec returns 1 when issues found
        return {"ok": ok, "tool": "tfsec", "exit_code": code, "stdout": out, "stderr": err}

    # Fallback to checkov
    if shutil.which("checkov") is not None:
        cmd_list = [
            "checkov",
            "-d",
            ".",
            "--output",
            "json",
        ]
        code, out, err = _run(cmd_list, cwd=cwd, timeout=timeout)
        ok = code in (0, 1)  # issues may return non-zero
        return {"ok": ok, "tool": "checkov", "exit_code": code, "stdout": out, "stderr": err}

    return {"ok": False, "error": "Neither tfsec nor checkov found on PATH"}


def run_infracost() -> Dict:
    """
    Run infracost breakdown for the workdir. Returns JSON or text results.
    """
    tool_name = "run_infracost"
    if not is_tool_allowed(tool_name):
        return {"ok": False, "error": f"Tool not allowed: {tool_name}"}

    timeout = get_tools_timeout_seconds()
    cwd = os.path.abspath(get_workdir())

    if shutil.which("infracost") is None:
        return {"ok": False, "error": "Infracost not found on PATH"}

    cmd_list = [
        "infracost",
        "breakdown",
        "--path",
        ".",
        "--format",
        "json",
        "--no-color",
    ]
    code, out, err = _run(cmd_list, cwd=cwd, timeout=timeout)
    ok = code == 0
    return {"ok": ok, "exit_code": code, "stdout": out, "stderr": err}


def read_repo_files(globs_patterns: List[str]) -> Dict:
    tool_name = "read_repo_files"
    if not is_tool_allowed(tool_name):
        return {"ok": False, "error": f"Tool not allowed: {tool_name}"}

    cwd = os.path.abspath(get_workdir())
    files: Dict[str, str] = {}
    try:
        for pattern in globs_patterns:
            for path in glob(os.path.join(cwd, pattern), recursive=True):
                if os.path.isdir(path):
                    continue
                try:
                    if os.path.getsize(path) > 1_000_000:
                        continue
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        rel = os.path.relpath(path, cwd)
                        files[rel] = f.read()
                except Exception:
                    continue
        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def write_report(markdown: str) -> Dict:
    """
    Write the Markdown report to <workdir>/report.md.
    """
    tool_name = "write_report"
    if not is_tool_allowed(tool_name):
        return {"ok": False, "error": f"Tool not allowed: {tool_name}"}

    workdir = os.path.abspath(get_workdir())
    out_path = os.path.join(workdir, "report.md")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        return {"ok": True, "path": out_path}
    except Exception as e:
        return {"ok": False, "error": str(e)}
