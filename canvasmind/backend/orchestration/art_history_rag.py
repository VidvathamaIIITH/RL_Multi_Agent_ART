"""ArtHistoryRAG — lean keyword-matching context router.

If an agent's persona/brief mentions a known style or technique, precise
stylistic keywords are injected to enrich the prompt. Uses a local knowledge
base (no external vector store required); the `enrich()` interface mirrors a
retriever so it can later be swapped for a true embedding vector store.
"""
from __future__ import annotations

from typing import Dict, List


class ArtHistoryRAG:
    KB: Dict[str, str] = {
        "chiaroscuro": "strong light-dark modelling, a single dramatic light source, deep velvety shadow",
        "baroque": "theatrical movement, ornate gilded ornament, rich tenebrism, classical grandeur",
        "surrealism": "dream logic, impossible juxtapositions, uncanny scale, melting organic form",
        "biomorphic": "curved organic contours, cell-like structures, forms that appear grown not built",
        "cyberpunk": "neon signage, holographic haze, rain-wet reflection, dense industrial decay",
        "neon": "saturated emissive colour, glowing rim light, bloom and reflection on wet surfaces",
        "noir": "hard shadows, low-key lighting, silhouetted figures, moody high contrast",
        "minimalism": "extreme reduction, generous negative space, precise geometry, restrained palette",
        "bauhaus": "primary colours, clean geometry, functional balance, sans-serif rigor",
        "futurism": "dynamic diagonals, motion blur, repeated forms implying speed, fractured planes",
        "impressionism": "broken brushwork, dappled light, vibrating complementary colour, soft edges",
        "ukiyo-e": "flat colour planes, bold contour lines, woodblock texture, asymmetric composition",
        "art nouveau": "sinuous whiplash curves, botanical motifs, decorative linear rhythm",
        "brutalism": "raw concrete mass, monolithic geometry, stark shadow, heavy monumental weight",
        "vaporwave": "pastel neon gradients, retro-digital glitch, marble-and-chrome kitsch",
        "gothic": "pointed arches, spectral gloom, intricate tracery, vertical aspiration",
    }

    def __init__(self, extra: Dict[str, str] | None = None) -> None:
        self.kb = dict(self.KB)
        if extra:
            self.kb.update(extra)

    def enrich(self, text: str, max_hits: int = 3) -> str:
        low = (text or "").lower()
        hits: List[str] = []
        for key, val in self.kb.items():
            if key in low and val not in hits:
                hits.append(val)
            if len(hits) >= max_hits:
                break
        return "; ".join(hits)

    # retriever-style alias so this can stand in for a vector store later
    def retrieve(self, query: str, k: int = 3) -> List[str]:
        low = (query or "").lower()
        out: List[str] = []
        for key, val in self.kb.items():
            if key in low:
                out.append(val)
            if len(out) >= k:
                break
        return out
