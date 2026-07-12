# CanvasMind / RL_Multi_Agent — papers

Three ACL-format papers, each **self-contained** and buildable on a bare
TeX Live / MiKTeX / Overleaf with **no bibtex step** (references are embedded).

| File | Covers | Reference file | Build |
|------|--------|----------------|-------|
| `canvasmind_acl.tex` | **Both** systems — the dual RL story + the quad control (the full work) | `references_embedded.tex` (59 refs) | 2× pdflatex |
| `canvasmind_dual.tex` | **Dual only** — ARIA/NEXUS + the inference-time RL layer, the audit, the five fixes, the before/after ablation | `references_dual.tex` (58 refs) | 2× pdflatex |
| `canvasmind_quad.tex` | **Quad only** — the configurable four-agent sequential pipeline (no RL layer) | `references_quad.tex` (23 refs) | 2× pdflatex |

Each `.tex` submits **independently**: ship it together with its one
`references_*.tex` file (and, if you want the official ACL look, `acl.sty` +
`acl_natbib.bst`). Nothing else is required.

## Build

```bash
cd paper
pdflatex canvasmind_dual   && pdflatex canvasmind_dual     # dual paper
pdflatex canvasmind_quad   && pdflatex canvasmind_quad     # quad paper
pdflatex canvasmind_acl    && pdflatex canvasmind_acl      # combined paper
```

**Run `pdflatex` twice.** No `bibtex` run is needed — the bibliography is an
embedded `thebibliography` block (author-year, natbib-compatible). The first pass
writes the citation labels to the `.aux`; the **second pass reads them back**, so
citations resolve then.

> **Troubleshooting — citations show as `?` or `(????)`:**
> 1. You ran `pdflatex` only **once** → run it a **second** time. (Overleaf does
>    this automatically; a one-shot local `pdflatex` does not.)
> 2. The matching `references_*.tex` file is **not in the same folder** as the
>    `.tex` → keep them together (e.g. `canvasmind_dual.tex` **+**
>    `references_dual.tex`). If you rename the `.tex`, do **not** move or drop the
>    references file.
>
> Do **not** run `bibtex` — there is no `\bibliography{}` to process; the refs are
> already in the document.

Each file compiles two ways, chosen automatically by `\IfFileExists`:
- **With** the official ACL style files (`acl.sty`, `acl_natbib.bst`) present → the
  true ACL layout. Get them from <https://github.com/acl-org/acl-style-files>.
- **Without** them → a faithful ACL-layout emulation (letter, two columns, Times).

On Overleaf: upload the `.tex` + its `references_*.tex` (+ optionally the ACL
style files) and hit Recompile. All figures are TikZ — **no external images**.

## Files

| File | What it is |
|------|-----------|
| `canvasmind_acl.tex` | Combined paper (dual + quad). |
| `canvasmind_dual.tex` | Standalone dual-system paper. |
| `canvasmind_quad.tex` | Standalone quad-system paper. |
| `references_embedded.tex` | Embedded bibliography, all 59 refs (for the combined paper). |
| `references_dual.tex` | Cited subset for the dual paper (58). |
| `references_quad.tex` | Cited subset for the quad paper (23). |
| `custom.bib` | The original BibTeX file, kept for anyone who prefers the bibtex workflow. |

## Regenerating the embedded bibliographies

If you edit `custom.bib`, regenerate the embedded blocks:

```bash
python ../ablation/../  # (see scratchpad bib2embed.py) — or re-run the converter
```

The converter turns each `custom.bib` entry into a natbib author-year
`\bibitem[Author(Year)]{key}`, wraps URLs in `\url{}`, and sorts by author; the
per-paper subsets keep only the keys each paper cites.

## Every number is reproducible

The quantitative claims in the dual/combined papers come from
`../ablation/run_ablation.py`, which imports the **real** decision code from
`../canvasmind_app.py` and replaces only the Azure-backed oracles with a
calibrated stochastic reward environment. **These are simulation results, not
live-system results, and the papers say so** (abstract, ablation section). The
quad paper reports **no** quality numbers — it describes the system only.

```bash
python ../ablation/run_ablation.py     # writes ../ablation/results/*.csv + summary.json
```

## Relationship to the older paper

`../RL_Multi_Agent_ACL.tex` (June) describes the pre-RL system and is superseded by
these; it is left untouched for provenance.
