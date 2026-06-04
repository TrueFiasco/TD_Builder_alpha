Param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("build-vectors","embed","build-graph","build-chroma","serve")]
  [string]$Task
)

$ErrorActionPreference = "Stop"

$py = "C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe"
$kb = "C:\TD_Projects\kb_pipeline"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $kb
$env:ANONYMIZED_TELEMETRY = "False"

switch ($Task) {
  "build-vectors" {
    & $py "$kb\build_vectors.py" --fallback-only
  }
  "embed" {
    & $py "$kb\generate_embeddings_simple.py"
  }
  "build-graph" {
    & $py "$kb\build_graph.py"
  }
  "build-chroma" {
    & $py "$kb\create_chroma_from_embeddings.py" --out "$kb\vector_db_chroma" --collection "td_unified"
  }
  "serve" {
    & $py "$kb\mcp\unified_mcp_server.py"
  }
}

