"""
Inter-Agent Communication Protocol
═══════════════════════════════════
Implements the message schema from the Computational Creativity paper (Section 4.2).

Message Schema:
  sender, round, intent, theme, region, style_note, mark_ops, open_question, emotion_tag

Intents:
  propose | acknowledge | dispute | yield
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional


VALID_INTENTS = {"propose", "acknowledge", "dispute", "yield"}


# ──────────────────────────────────────────────
#  AGENT MESSAGE
# ──────────────────────────────────────────────

@dataclass
class AgentMessage:
    """Structured message exchanged between painting agents."""

    sender: str
    round: int
    intent: str            # propose | acknowledge | dispute | yield
    theme: str
    region: str
    style_note: str
    mark_ops: list = field(default_factory=list)
    open_question: Optional[str] = None
    emotion_tag: str = "neutral"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        """Create an AgentMessage from a dict, ignoring unknown keys."""
        known_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def validate(self) -> list:
        """Return a list of validation errors (empty = valid)."""
        errors = []
        if self.intent not in VALID_INTENTS:
            errors.append(f"Invalid intent '{self.intent}'. Must be one of: {VALID_INTENTS}")
        if not self.theme:
            errors.append("Theme cannot be empty")
        if not self.region:
            errors.append("Region cannot be empty")
        if not isinstance(self.mark_ops, list):
            errors.append("mark_ops must be a list")
        return errors


# ──────────────────────────────────────────────
#  CRITIC EVALUATION
# ──────────────────────────────────────────────

@dataclass
class CriticEvaluation:
    """Structured evaluation from the Critic agent (Section 3.4)."""

    round: int
    compositional_coherence: int   # 0-10
    stylistic_dialogue: int        # 0-10
    thematic_depth: int            # 0-10
    technical_execution: int       # 0-10
    directive_agent_a: str
    directive_agent_b: str
    overall_commentary: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "CriticEvaluation":
        known_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @property
    def average_score(self) -> float:
        return (
            self.compositional_coherence
            + self.stylistic_dialogue
            + self.thematic_depth
            + self.technical_execution
        ) / 4.0


# ──────────────────────────────────────────────
#  JSON EXTRACTION HELPERS
# ──────────────────────────────────────────────

def _extract_json(raw_text: str) -> dict | None:
    """Try multiple strategies to pull a JSON object out of an LLM response."""
    text = raw_text.strip()

    # Strategy 1: Markdown code block
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    # Strategy 2: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 3: Find the outermost { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


def parse_agent_response(raw_text: str, sender: str, round_num: int) -> AgentMessage:
    """Parse an LLM text response into a validated AgentMessage."""
    data = _extract_json(raw_text)

    if data is None:
        # Fallback: wrap the raw text as a style_note so nothing is lost
        data = {
            "intent": "propose",
            "theme": "continuation",
            "region": "center",
            "style_note": raw_text[:300],
            "mark_ops": [],
            "open_question": None,
            "emotion_tag": "neutral",
        }

    # Force correct sender / round regardless of what the LLM wrote
    data["sender"] = sender
    data["round"] = round_num

    # Ensure mark_ops is always a list of strings
    ops = data.get("mark_ops", [])
    if isinstance(ops, str):
        ops = [ops]
    elif not isinstance(ops, list):
        ops = []
    data["mark_ops"] = [str(o) for o in ops]

    # Ensure intent is valid
    if data.get("intent") not in VALID_INTENTS:
        data["intent"] = "propose"

    # Defaults for missing fields
    data.setdefault("theme", "continuation")
    data.setdefault("region", "center")
    data.setdefault("style_note", "")
    data.setdefault("emotion_tag", "neutral")

    return AgentMessage.from_dict(data)


def parse_critic_response(raw_text: str, round_num: int) -> CriticEvaluation:
    """Parse an LLM text response into a validated CriticEvaluation."""
    data = _extract_json(raw_text)

    if data is None:
        data = {}

    data["round"] = round_num

    # Defaults
    data.setdefault("compositional_coherence", 5)
    data.setdefault("stylistic_dialogue", 5)
    data.setdefault("thematic_depth", 5)
    data.setdefault("technical_execution", 5)
    data.setdefault("directive_agent_a", "Continue developing your contributions.")
    data.setdefault("directive_agent_b", "Continue developing your contributions.")
    data.setdefault("overall_commentary", "The collaboration is progressing.")

    # Clamp scores to 0–10
    for key in [
        "compositional_coherence",
        "stylistic_dialogue",
        "thematic_depth",
        "technical_execution",
    ]:
        try:
            data[key] = max(0, min(10, int(data[key])))
        except (ValueError, TypeError):
            data[key] = 5

    return CriticEvaluation.from_dict(data)
