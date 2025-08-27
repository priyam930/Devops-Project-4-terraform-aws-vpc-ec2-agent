import os
from typing import List, Optional


def get_workdir(default: str = "..") -> str:
    return os.getenv("TERRAFORM_WORKDIR", default)


def get_tools_allowlist() -> Optional[List[str]]:
    raw = os.getenv("TOOLS_ALLOWLIST")
    if not raw:
        return None  # None means all tools allowed
    return [t.strip() for t in raw.split(",") if t.strip()]


def get_tools_timeout_seconds() -> int:
    try:
        return int(os.getenv("TOOLS_TIMEOUT_SECONDS", "120"))
    except ValueError:
        return 120


def is_tool_allowed(tool_name: str) -> bool:
    allow = get_tools_allowlist()
    if allow is None:
        return True
    return tool_name in allow
