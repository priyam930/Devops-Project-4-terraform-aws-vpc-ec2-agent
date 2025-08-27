import os
from typing import Dict, List, Tuple

import google.generativeai as genai

from .tools import (
    write_report,
    read_repo_files,
    run_infracost,
    run_security_scan,
    run_terraform,
)


def _configure_model() -> genai.GenerativeModel:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")


def _safe(val: Dict) -> str:
    return (val or {}).get("stdout") or (val or {}).get("error") or ""


def run_review_flow() -> str:
    """
    Orchestrator-driven flow: executes tools (read files, terraform validate/plan/show,
    security, cost) and then asks Gemini to produce a single concise Markdown report.
    """
    model = _configure_model()

    files_res = read_repo_files(["*.tf"])  # keep it small; user can expand later

    tf_init = run_terraform("init")
    tf_validate = run_terraform("validate")
    tf_plan = run_terraform("plan -out tf.plan")
    tf_show_json = run_terraform("show -json tf.plan")
    tf_show_text = run_terraform("show tf.plan") if not tf_show_json.get("ok") else {"ok": True, "stdout": ""}

    sec = run_security_scan()
    cost = run_infracost()

    instructions = (
        "You are a Terraform PR reviewer. Using the provided files and tool outputs, "
        "write a concise, actionable Markdown report with these sections: \n"
        "1) Summary (top risks, quick wins)\n"
        "2) Validation/Plan (key changes, errors if any)\n"
        "3) Security (notable issues, severities, suggestions)\n"
        "4) Cost (estimated monthly impact, hotspots, savings ideas)\n"
        "5) Suggested Diffs (minimal changes to improve security/cost/compliance).\n"
        "Avoid verbosity; prefer bullet points. If a tool failed or is missing, note it briefly and proceed.\n"
        "Do not include any apply steps."
    )

    parts: List[Dict[str, str]] = []
    if files_res.get("ok"):
        files = files_res.get("files", {})
        for rel, content in files.items():
            parts.append({"text": f"File: {rel}\n```hcl\n{content}\n```"})
    else:
        parts.append({"text": f"Could not read files: {files_res.get('error','')}"})

    parts.append({"text": f"Terraform init:\n```\n{_safe(tf_init)}\n```"})
    parts.append({"text": f"Terraform validate:\n```\n{_safe(tf_validate)}\n```"})

    if tf_show_json.get("ok"):
        parts.append({"text": f"Terraform plan (JSON):\n```json\n{tf_show_json.get('stdout','')}\n```"})
    else:
        parts.append({"text": f"Terraform plan (text):\n```\n{_safe(tf_show_text)}\n```"})

    if sec.get("ok"):
        parts.append({"text": f"Security scan ({sec.get('tool','unknown')}):\n```json\n{sec.get('stdout','')}\n```"})
    else:
        parts.append({"text": f"Security scan unavailable: {sec.get('error','')}"})

    if cost.get("ok"):
        parts.append({"text": f"Infracost:\n```json\n{cost.get('stdout','')}\n```"})
    else:
        parts.append({"text": f"Infracost unavailable: {cost.get('error','')}"})

    content = [{"text": instructions}] + parts
    response = model.generate_content(content)
    final_text = response.text or ""

    write_report(final_text)
    return final_text


def _extract_first_json_block(text: str) -> str:
    if not text:
        return ""
    start = None
    depth = 0
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            depth = 1
            break
    if start is None:
        return ""
    for j in range(start + 1, len(text)):
        if text[j] in "[{":
            depth += 1
        elif text[j] in "]}":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return ""


def run_create_flow(spec_text: str, out_dir: str) -> Tuple[List[str], str]:
    model = _configure_model()

    system = (
        "Generate a Terraform scaffold as JSON. Output only JSON with the following shape: \n"
        "{\n  \"files\": [\n    { \"path\": \"main.tf\", \"content\": \"hcl content\" },\n    { \"path\": \"variables.tf\", \"content\": \"hcl content\" },\n    { \"path\": \"outputs.tf\", \"content\": \"hcl content\" }\n  ]\n}\n"
        "Use secure defaults (encryption, least-privilege, tags). Keep content concise and valid."
    )

    prompt = f"Spec for Terraform scaffold:\n{spec_text}\n\nReturn ONLY the JSON object as specified."

    resp = model.generate_content([
        {"text": system},
        {"text": prompt},
    ])
    text = resp.text or ""

    import json

    json_block = _extract_first_json_block(text)
    if not json_block:
        return [], "Model did not return JSON."
    try:
        data = json.loads(json_block)
    except Exception as e:
        return [], f"Failed to parse JSON: {e}"

    files = data.get("files", [])
    written: List[str] = []

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    for f in files:
        path = f.get("path")
        content = f.get("content", "")
        if not path:
            continue
        dest_path = os.path.join(out_dir, path)
        dest_dir = os.path.dirname(dest_path)
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        written.append(dest_path)

    return written, f"Wrote {len(written)} files to {out_dir}."
