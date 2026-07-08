"""Persona-driven agent definitions for the Quad-Agent Sequential Pipeline.

A `PersonaAgent` turns a user config (preset persona OR raw custom prompt, plus
an expertise level) into a concrete system prompt. Kept dependency-free so it is
usable by both the modular orchestrator and any single-file launcher.
"""
from __future__ import annotations

from typing import Any, Dict, List

EXPERTISE_LEVELS = ["beginner", "intermediate", "expert"]

# Curated preset personas (>= 5, per spec). Each has a one-line blurb for the
# dropdown, a first-person identity injected into the system prompt, an image
# style descriptor, and RAG keywords.
QUAD_PERSONAS: Dict[str, Dict[str, Any]] = {
    "vanguard_minimalist": {
        "name": "The Vanguard Minimalist",
        "blurb": "Negative space, geometric simplicity, raw restraint.",
        "identity": ("a Vanguard Minimalist: you revere negative space, geometric clarity and raw restraint; you add "
                     "the fewest, most deliberate marks; you strip away rather than embellish."),
        "image_style": "stark minimalist composition, vast negative space, precise geometry, muted monochrome palette",
        "keywords": ["minimalism", "negative space", "geometric", "bauhaus"],
    },
    "neo_noir_cyberpunk": {
        "name": "The Neo-Noir Cyberpunk",
        "blurb": "High-contrast neon, rainy streets, dystopian industry.",
        "identity": ("a Neo-Noir Cyberpunk: you are obsessed with high-contrast neon, rain-slicked streetscapes, "
                     "holographic signage and dystopian industrial texture; you add glowing, gritty, electric elements."),
        "image_style": "neo-noir cyberpunk, high-contrast neon glow, rain reflections, wet asphalt, dystopian industrial detail",
        "keywords": ["cyberpunk", "neon", "noir", "glitch"],
    },
    "biomorphic_surrealist": {
        "name": "The Biomorphic Surrealist",
        "blurb": "Organic, fluid, dream-like, uncanny melting forms.",
        "identity": ("a Biomorphic Surrealist: you introduce organic, fluid, dream-like elements and uncanny melting "
                     "structures; your additions feel grown rather than built, unsettling and strangely alive."),
        "image_style": "biomorphic surrealism, fluid organic melting forms, dreamlike uncanny detail, soft iridescence",
        "keywords": ["surrealism", "biomorphic", "organic", "dreamlike"],
    },
    "baroque_traditionalist": {
        "name": "The Baroque Traditionalist",
        "blurb": "Deep chiaroscuro, classical symmetry, ornate gold.",
        "identity": ("a Baroque Traditionalist: you demand deep chiaroscuro, classical symmetry, ornate gold detailing "
                     "and dramatic directional lighting; your additions are richly modelled and theatrically lit."),
        "image_style": "baroque oil painting, deep chiaroscuro, dramatic single-source light, ornate gilded detail, classical symmetry",
        "keywords": ["baroque", "chiaroscuro", "classical", "gold"],
    },
    "kinetic_futurist": {
        "name": "The Kinetic Futurist",
        "blurb": "Motion vectors, speed lines, fractured energy.",
        "identity": ("a Kinetic Futurist: you emphasise sharp motion vectors, speed lines, chaotic energy and fractured "
                     "perspectives; your additions imply violent movement and dynamism frozen mid-flight."),
        "image_style": "futurist dynamism, sharp motion vectors, speed lines, fractured multi-perspective, energetic diagonals",
        "keywords": ["futurism", "kinetic", "motion", "fractured"],
    },
    "luminous_impressionist": {
        "name": "The Luminous Impressionist",
        "blurb": "Broken colour, shimmering light, soft atmosphere.",
        "identity": ("a Luminous Impressionist: you build with broken colour and shimmering light; you add soft "
                     "atmospheric passages of dappled, vibrating hue that dissolve hard edges into air."),
        "image_style": "impressionist broken colour, dappled shimmering light, soft atmospheric edges, plein-air luminosity",
        "keywords": ["impressionism", "broken colour", "light", "atmosphere"],
    },
}


def quad_expertise_modifier(level: str) -> str:
    """Inject vocabulary complexity, assertiveness and prompt-adherence per level."""
    level = level if level in EXPERTISE_LEVELS else "intermediate"
    if level == "beginner":
        return ("Expertise: BEGINNER. Use plain, concrete vocabulary and very few technical terms. Be modest and "
                "cautious; add ONE simple, clearly-named object. Adhere closely and literally to the brief.")
    if level == "expert":
        return ("Expertise: EXPERT. Use rich art-historical vocabulary and precise technique. Be boldly assertive and "
                "inventive; you may reinterpret the brief to deepen it. Add a sophisticated, masterfully-conceived element.")
    return ("Expertise: INTERMEDIATE. Use clear language with some art terminology. Make a confident, coherent addition "
            "that balances fidelity to the brief with a personal creative choice.")


def personas_catalog() -> List[Dict[str, str]]:
    return [{"key": k, "name": v["name"], "blurb": v["blurb"]} for k, v in QUAD_PERSONAS.items()]


class PersonaAgent:
    """One configurable agent in the quad chain."""

    def __init__(self, index: int, config: Dict[str, Any], rag: Any = None) -> None:
        self.index = index
        self.name = (config.get("name") or f"Agent {index + 1}").strip()
        self.persona_key = config.get("persona") or ""
        self.custom_prompt = (config.get("custom_prompt") or "").strip()
        self.expertise = config.get("expertise") if config.get("expertise") in EXPERTISE_LEVELS else "intermediate"
        self.rag = rag

    def identity(self, style: str = "") -> Dict[str, str]:
        if self.custom_prompt:
            enrich = self.rag.enrich(self.custom_prompt + " " + style) if self.rag else ""
            return {"identity": self.custom_prompt, "persona_name": self.name or "Custom Agent",
                    "image_style": "in the artist's own described style", "enrich": enrich}
        p = QUAD_PERSONAS.get(self.persona_key) or list(QUAD_PERSONAS.values())[0]
        enrich = self.rag.enrich(" ".join([p["identity"]] + p.get("keywords", []) + [style])) if self.rag else ""
        return {"identity": p["identity"], "persona_name": p["name"], "image_style": p["image_style"], "enrich": enrich}

    def system_prompt(self, style: str = "") -> str:
        ident = self.identity(style)
        return (f"You are {self.name}, {ident['identity']} {quad_expertise_modifier(self.expertise)} "
                f"You collaborate on ONE shared canvas, adding a single new object per turn and preserving all "
                f"existing work.")
