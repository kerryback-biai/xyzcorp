"""Claude tool definitions for the chatbot."""
from app.database.duckdb_manager import SYSTEM_NAMES

QUERY_DATABASE_TOOL = {
    "name": "query_database",
    "description": (
        "Execute a read-only SQL query against a specific enterprise system. "
        "Each system has its own tables with its own naming conventions and ID schemes. "
        "You CANNOT join across systems in a single query. "
        "To combine data from multiple systems, query each separately and use run_python to merge with Python. "
        "Returns columns and rows as JSON. Maximum 500 rows returned."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A SELECT SQL query to execute against the specified system's tables.",
            },
            "system": {
                "type": "string",
                "enum": SYSTEM_NAMES,
                "description": "The enterprise system to query.",
            },
        },
        "required": ["sql", "system"],
    },
}

RUN_PYTHON_TOOL = {
    "name": "run_python",
    "description": (
        "Execute Python code on the server. Use for data analysis, chart generation, "
        "merging cross-system data, and reviewing generated files. "
        "Available libraries: pandas, numpy, matplotlib, seaborn, scipy, "
        "scikit-learn, statsmodels, statistics, openpyxl (for reading/reviewing xlsx). "
        "Use save_file(filename) to get the output path for saving files. "
        "For charts, print base64 PNG with the CHART_BASE64: prefix to display inline. "
        "Generated files persist — you can re-read them in later tool calls using save_file(filename)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute.",
            },
        },
        "required": ["code"],
    },
}

RUN_NODE_TOOL = {
    "name": "run_node",
    "description": (
        "Execute Node.js code on the server. Use for generating high-quality "
        "Word documents (.docx), PowerPoint presentations (.pptx), and Excel spreadsheets (.xlsx). "
        "Available packages: docx (Word), pptxgenjs (PowerPoint). "
        "IMPORTANT: Before generating a document, call read_skill_docs to get the API reference. "
        "Use saveFile(filename) to get the output path. "
        "Example: doc.save(saveFile('report.docx')) or pres.writeFile({ fileName: saveFile('deck.pptx') })"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Node.js code to execute.",
            },
        },
        "required": ["code"],
    },
}

READ_SKILL_DOCS_TOOL = {
    "name": "read_skill_docs",
    "description": (
        "Load API reference documentation for document generation libraries. "
        "Call this BEFORE using run_node to generate documents. "
        "Available skills: 'docx' (Word via docx npm), 'pptx' (PowerPoint via pptxgenjs), "
        "'xlsx' (Excel formatting standards). "
        "Returns the full API reference with code examples and best practices."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "enum": ["docx", "pptx", "xlsx"],
                "description": "The document type to get API docs for.",
            },
        },
        "required": ["skill"],
    },
}


SEARCH_DOCUMENTS_TOOL = {
    "name": "search_documents",
    "description": (
        "Search the corporate document knowledge base (policies, handbooks, procedures, memos, contracts). "
        "Use this when the user asks about company policies, rules, guidelines, or any information "
        "that would live in written documents rather than in transactional/numerical data. "
        "Returns the most relevant document excerpts with source references."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A natural-language search query describing what information you need.",
            },
        },
        "required": ["query"],
    },
}


def get_tools() -> list[dict]:
    return [QUERY_DATABASE_TOOL, RUN_PYTHON_TOOL, RUN_NODE_TOOL, READ_SKILL_DOCS_TOOL, SEARCH_DOCUMENTS_TOOL]
