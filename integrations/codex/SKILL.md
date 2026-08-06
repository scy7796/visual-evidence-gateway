---
name: visual-evidence-gateway
description: >
  Use only when task correctness depends on visible pixels in a local image,
  including OCR, UI state, chart or diagram interpretation, or visual
  before/after verification. Prefer source text or structured data when
  sufficient. Call the single vision.inspect tool and use its compact evidence.
---

# Visual Evidence Gateway gate

Use `vision.inspect` only when the answer depends on information that cannot be
reliably obtained from text, source code, logs, DOM, SVG, or structured data.

Do not infer image contents from filenames.

Required triggers:
- the user asks about an image or screenshot;
- visible UI state or layout is material;
- image-only text must be read;
- a chart or diagram itself is evidence;
- visual before/after verification is required.

Do not trigger:
- an image merely exists in the repository;
- equivalent text or structured data is available;
- the task is code-only;
- no readable image path exists.

Use:
- `rigor=normal` for ordinary inspection;
- `rigor=critical` for final acceptance or material numeric conclusions;
- `rigor=cheap` for bulk coarse screening.

Do not request a specific backend.
Do not call the tool repeatedly with the same image and question.
Do not claim visual verification if the tool returns partial or failed.
