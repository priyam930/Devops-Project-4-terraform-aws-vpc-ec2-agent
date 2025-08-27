## Gemini Agent for Terraform (Review and Create)

This agent uses Google Gemini to:
- Review your Terraform (validate/plan, security, cost) and write a Markdown report to `report.md` in your workdir.
- Create new Terraform scaffolds from a text spec into an output folder.

Advisory only: it never applies changes.

### Prerequisites
- Python 3.10+
- Terraform CLI on PATH
- Optional: `tfsec` or `checkov` for security, `infracost` for cost
- `GEMINI_API_KEY` (via .env or env var)

### Install
```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r agent\requirements.txt
```

### Review mode (writes report.md)
```powershell
python agent\main.py --mode review --workdir .
```

### Create mode (generate Terraform files)
- Inline spec:
```powershell
python agent\main.py --mode create --workdir . --out-dir .\generated_tf --spec "VPC with 2 private subnets, NAT, SG for 443, S3 with SSE-KMS"
```
- Spec from file:
```powershell
python agent\main.py --mode create --workdir . --out-dir .\generated_tf --spec-file .\agent\example_spec.txt
```

### .env example
```
GEMINI_API_KEY=your_key_here
TERRAFORM_WORKDIR=..
TOOLS_ALLOWLIST=run_terraform,run_security_scan,run_infracost,read_repo_files,write_report
TOOLS_TIMEOUT_SECONDS=120
```
