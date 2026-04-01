"""Sandboxed Python and Node.js code execution for the data assistant."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Directory for generated files (persists across tool calls within a session)
OUTPUT_DIR = Path(tempfile.gettempdir()) / "meridian_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

TIMEOUT_SECONDS = 30
CHART_PREFIX = "CHART_BASE64:"

# Skill documentation directory
SKILLS_DIR = Path.home() / ".claude" / "skills"

# Map of skill names to their documentation files
SKILL_DOCS = {
    "docx": [
        SKILLS_DIR / "docx" / "docx-js.md",
    ],
    "pptx": [
        SKILLS_DIR / "_anthropic_temp" / "skills" / "pptx" / "pptxgenjs.md",
    ],
    "xlsx": [
        SKILLS_DIR / "xlsx" / "SKILL.md",
        SKILLS_DIR / "xlsx" / "financial-modeling-standards.md",
    ],
}

# Python prelude — sets up output dir and save_file helper
PYTHON_PRELUDE = f"""
import os as _os
_OUTPUT_DIR = {str(OUTPUT_DIR)!r}
_os.makedirs(_OUTPUT_DIR, exist_ok=True)

def save_file(filename):
    \"\"\"Return the full path to save a file in the output directory.\"\"\"
    return _os.path.join(_OUTPUT_DIR, filename)
"""

# Node.js prelude — same helpers in JavaScript
# Uses _private names to avoid colliding with user code that also requires fs/path
NODE_PRELUDE = f"""
const _fs = require('fs');
const _path = require('path');
const _OUTPUT_DIR = {str(OUTPUT_DIR).replace(chr(92), '/')!r};
_fs.mkdirSync(_OUTPUT_DIR, {{ recursive: true }});

function saveFile(filename) {{
    return _path.join(_OUTPUT_DIR, filename);
}}
"""


def _scan_new_files(existing_files: set[str]) -> list[dict]:
    """Scan OUTPUT_DIR for newly created files."""
    files = []
    for f in OUTPUT_DIR.iterdir():
        if f.is_file() and f.name not in existing_files and f.suffix.lower() in (
            ".docx", ".pptx", ".xlsx", ".csv", ".pdf", ".png", ".jpg", ".html", ".txt",
        ):
            files.append({
                "filename": f.name,
                "path": str(f),
                "url": f"/api/files/{f.name}",
            })
    return files


def _extract_charts(stdout: str) -> tuple[str, list[str]]:
    """Extract base64 chart images from stdout. Returns (cleaned_stdout, charts)."""
    charts = []
    lines = []
    for line in stdout.split("\n"):
        if line.startswith(CHART_PREFIX):
            charts.append(line[len(CHART_PREFIX):].strip())
        else:
            lines.append(line)
    return "\n".join(lines).strip(), charts


def _run_subprocess(cmd: list[str], code: str, extra_env: dict | None = None) -> dict:
    """Run a subprocess with the given command and code, return structured result."""
    existing_files = set(f.name for f in OUTPUT_DIR.iterdir() if f.is_file())
    env = {**os.environ, **(extra_env or {})}

    try:
        result = subprocess.run(
            cmd + [code],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=str(OUTPUT_DIR),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {TIMEOUT_SECONDS} seconds.",
            "files": [],
            "charts": [],
            "success": False,
        }

    cleaned_stdout, charts = _extract_charts(result.stdout)
    files = _scan_new_files(existing_files)

    return {
        "stdout": cleaned_stdout,
        "stderr": result.stderr.strip() if result.stderr else "",
        "files": files,
        "charts": charts,
        "success": result.returncode == 0,
    }


def execute_python(code: str) -> dict:
    """Execute Python code in a subprocess."""
    full_code = PYTHON_PRELUDE + "\n" + code
    return _run_subprocess(
        [sys.executable, "-c"],
        full_code,
        extra_env={"MPLBACKEND": "Agg"},
    )


def _find_npm_global_prefix() -> str:
    """Find the global npm node_modules directory."""
    try:
        result = subprocess.run(
            [shutil.which("npm") or "npm", "root", "-g"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# Cache the npm global path at import time
_NPM_GLOBAL_MODULES = _find_npm_global_prefix()


def execute_node(code: str) -> dict:
    """Execute Node.js code in a subprocess."""
    node_path = shutil.which("node")
    if not node_path:
        return {
            "stdout": "",
            "stderr": "Node.js is not installed.",
            "files": [],
            "charts": [],
            "success": False,
        }
    full_code = NODE_PRELUDE + "\n" + code
    extra_env = {}
    if _NPM_GLOBAL_MODULES:
        extra_env["NODE_PATH"] = _NPM_GLOBAL_MODULES
    return _run_subprocess([node_path, "-e"], full_code, extra_env=extra_env)


def read_skill_docs(skill: str) -> dict:
    """Read skill documentation files for a given document type."""
    if skill not in SKILL_DOCS:
        return {
            "content": "",
            "error": f"Unknown skill: {skill}. Available: {', '.join(SKILL_DOCS.keys())}",
        }

    content_parts = []
    for doc_path in SKILL_DOCS[skill]:
        if doc_path.is_file():
            content_parts.append(doc_path.read_text(encoding="utf-8"))
        else:
            content_parts.append(f"[File not found: {doc_path.name}]")

    return {
        "content": "\n\n---\n\n".join(content_parts),
        "error": "",
    }


def get_file_path(filename: str) -> Path | None:
    """Get the full path to a generated file, or None if it doesn't exist."""
    path = OUTPUT_DIR / filename
    # Prevent directory traversal
    if not path.resolve().parent == OUTPUT_DIR.resolve():
        return None
    if path.is_file():
        return path
    return None
