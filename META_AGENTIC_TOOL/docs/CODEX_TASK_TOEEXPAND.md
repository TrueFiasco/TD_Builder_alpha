# Codex Task: Reverse Engineer toeexpand/collapse for .toe/.tox File Building

## Context

We're building a TouchDesigner knowledge base and agentic tool system. Two parallel workstreams are happening:

**Claude is handling:**
- Web scraping https://derivative.ca/UserGuide and https://derivative.ca/UserGuide/Learn_TouchDesigner
- Extracting video transcripts (each video has titled transcripts with workflow content)
- Adding workflow/tutorial documents to our vector embedding database (ChromaDB)
- This addresses gaps in our KB for "how do I accomplish X" type queries

**You (Codex) are handling:**
- Reverse engineering TouchDesigner's `toeexpand.exe` and the inverse collapse process
- Goal: Reliably build .toe and .tox files programmatically from JSON/text representations
- This enables our agentic system to output actual TouchDesigner project files

## What We Know

- `toeexpand.exe` is located at: `C:\Program Files\Derivative\TouchDesigner\bin\toeexpand.exe`
- We have extracted snippet data in: `data/snippets\semantic\` (JSON files with operator definitions, parameters, connections)
- The META_AGENTIC_TOOL project is at: `C:\TD_Projects\META_AGENTIC_TOOL\`
- Per `INTEROP_AND_POLICY.md`, output order should be: toe → tox → Text DAT → instructions

## Your Task

1. **Analyze toeexpand** - Run `toeexpand.exe --help` and document all flags/options
2. **Study the format** - Expand some existing .tox files to understand the text/JSON format TD uses
3. **Document the schema** - What fields are required? How are connections represented? How are parameters encoded?
4. **Build the inverse** - Create a Python script that can take our semantic JSON and produce valid .tox/.toe files
5. **Test round-trip** - Expand → modify → collapse → verify in TD

## Files to Reference

- `C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic\INTEROP_AND_POLICY.md` - Schema requirements
- `data/snippets\semantic\blurTOP_semantic.json` - Example of our extracted format
- `C:\TD_Projects\Learn\OPSnippets\Snippets\` - Source .tox files to test with

## Expected Output

- Documentation of toeexpand format in `C:\TD_Projects\META_AGENTIC_TOOL\docs\TOEEXPAND_FORMAT.md`
- Python script: `toe_builder.py` that can construct .tox files
- Test results showing successful round-trip

## Coordination

- Claude's work will be in the KB/embeddings pipeline
- Your work will be in the file generation pipeline
- Both feed into the meta_agentic system for TD project building
- Document findings so both workstreams can integrate

Proceed with your existing plan and document findings as you go.
