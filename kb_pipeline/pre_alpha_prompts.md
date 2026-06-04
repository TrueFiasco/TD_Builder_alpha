# Pre-Alpha Dogfood Prompt Suite (edit this)

## Parameter lookups (docs-first)
- List and describe all parameters for `Speed CHOP` and what each does.
- Explain `Field POP` key parameters used in typical particle setups.
- What does `exportmethod` do (in context of CHOP export)?

## Snippet patterns (snippets-first)
- Find a real example of beat detection from audio and explain the network dataflow.
- Show me a robust smoothing pattern for noisy sensor input and explain why it works.

## Palette components (palette-first)
- Which palette component should I use for audio analysis? Summarize and tell me how it connects.
- Which palette component helps with OSC / networking control? Give usage steps.

## How-to (hybrid)
- How do I make a feedback trail effect and keep it stable at 60fps?
- How do I build a UI with sliders/buttons to control parameters cleanly?

## Build requests (pre-alpha)
### Phase A (until JSON builder is 100%): python output
- Build a simple audio-reactive color pulse network (Text DAT python) inside `/project1/dogfood1`.

### Phase B (target): JSON → toe/tox
- Build a `.tox` that exposes parameters for an audio-reactive level + blur chain and can be dropped into a project.

