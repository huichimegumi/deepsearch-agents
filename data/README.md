# Local Data

This directory is for local runtime data that should not be committed.

## RAG Corpus

Place local knowledge-base source documents under `data/knowledge_base/`.
Each first-level subdirectory is imported as one knowledge base by:

```bash
uv run python -m app.rag.bootstrap data/knowledge_base
```

Supported source files are currently `.pdf`, `.docx`, `.md`, and `.txt`.
The source documents in `data/knowledge_base/` are ignored by git; keep only
non-sensitive examples or instructions in tracked files.
