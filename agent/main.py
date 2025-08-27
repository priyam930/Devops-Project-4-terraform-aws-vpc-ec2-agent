import argparse
import os
import re
import sys

from dotenv import load_dotenv, find_dotenv

try:
    from .config import get_workdir
    from .orchestrator import run_review_flow, run_create_flow
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.config import get_workdir  # type: ignore
    from agent.orchestrator import run_review_flow, run_create_flow  # type: ignore


def _load_env():
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path)
    agent_env = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(agent_env):
        load_dotenv(agent_env, override=False)


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.strip().lower()
    # Keep alphanumerics, replace others with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "generated-tf"
    return text[:max_len]


def _derive_out_dir(spec_text: str, base_dir: str) -> str:
    # Use first ~8 words to build slug
    head = " ".join(spec_text.split()[:8]) if spec_text else "generated tf"
    slug = _slugify(head)
    candidate = os.path.join(base_dir, slug)
    if not os.path.exists(candidate):
        return candidate
    # Avoid collisions by adding numeric suffix
    i = 2
    while True:
        alt = os.path.join(base_dir, f"{slug}-{i}")
        if not os.path.exists(alt):
            return alt
        i += 1


def main():
    _load_env()

    parser = argparse.ArgumentParser(description="Gemini Terraform Agent")
    parser.add_argument("--mode", choices=["review", "create"], default="review")
    parser.add_argument("--workdir", default=None, help="Path to Terraform project (defaults to repo root)")
    parser.add_argument("--out-dir", default=None, help="Output directory for create mode")
    parser.add_argument("--spec", default=None, help="Inline text spec for create mode")
    parser.add_argument("--spec-file", default=None, help="Path to text spec file for create mode")
    args = parser.parse_args()

    if args.workdir:
        os.environ["TERRAFORM_WORKDIR"] = args.workdir

    if args.mode == "review":
        markdown = run_review_flow()
        print("Report written to report.md in workdir.")
        return

    if args.mode == "create":
        base_dir = get_workdir()
        spec_text = args.spec
        if not spec_text and args.spec_file:
            with open(args.spec_file, "r", encoding="utf-8") as fh:
                spec_text = fh.read()
        if not spec_text:
            print("Provide --spec or --spec-file for create mode.")
            return
        out_dir = args.out_dir or _derive_out_dir(spec_text, base_dir)
        written, msg = run_create_flow(spec_text, out_dir)
        print(msg)
        for p in written:
            print(p)


if __name__ == "__main__":
    main()
