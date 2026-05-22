"""
Shared Canvas State
═══════════════════
Manages the virtual canvas that both agents paint on.
Tracks regions, operations, history, and annotations.
"""

import json
from dataclasses import dataclass
from protocol import AgentMessage


@dataclass
class CanvasRegion:
    """A single region on the canvas."""
    name: str
    owner: str | None = None   # "agent_a", "agent_b", or None
    status: str = "free"       # "free", "owned", "contested"


class SharedCanvas:
    """
    The shared data structure representing the current state of the artwork.
    Each agent may read the entire canvas but writes only to regions
    allocated during negotiation.
    """

    def __init__(self, region_names: list[str]):
        self.regions: dict[str, CanvasRegion] = {
            name: CanvasRegion(name=name) for name in region_names
        }
        self.history: list[dict] = []          # All mark operations
        self.annotations: list[dict] = []      # Semantic intent layer
        self.negotiation_record: list[dict] = []  # Full dialogue history

    # ──────────────────────────────────────────
    #  WRITE
    # ──────────────────────────────────────────

    def apply_operations(self, message: AgentMessage) -> None:
        """Apply an agent's mark operations to the canvas."""

        # Update region ownership
        region_name = message.region
        if region_name in self.regions:
            region = self.regions[region_name]
            if region.owner is None:
                region.owner = message.sender
                region.status = "owned"
            elif region.owner != message.sender:
                region.status = "contested"

        # Log each painting operation
        for op in message.mark_ops:
            self.history.append({
                "round": message.round,
                "agent": message.sender,
                "region": message.region,
                "operation": op,
                "emotion": message.emotion_tag,
            })

        # Record semantic annotation
        self.annotations.append({
            "round": message.round,
            "agent": message.sender,
            "intent": message.style_note,
            "theme": message.theme,
        })

        # Add to negotiation record
        self.negotiation_record.append(message.to_dict())

    # ──────────────────────────────────────────
    #  READ
    # ──────────────────────────────────────────

    def get_state_summary(self) -> str:
        """Build a text summary of the canvas state for agent context windows."""
        lines = ["=== CURRENT CANVAS STATE ===", ""]

        # Region map
        lines.append("REGIONS:")
        for name, region in self.regions.items():
            tag = region.status
            if region.owner:
                tag += f" (owner: {region.owner})"
            lines.append(f"  • {name}: {tag}")

        # Recent mark operations (last 12)
        lines.append("")
        if self.history:
            lines.append("RECENT MARK OPERATIONS:")
            for entry in self.history[-12:]:
                lines.append(
                    f"  Round {entry['round']} | {entry['agent']} | "
                    f"{entry['region']}: {entry['operation']} [{entry['emotion']}]"
                )
        else:
            lines.append("CANVAS IS BLANK — No operations yet.")

        # Recent annotations (last 8)
        if self.annotations:
            lines.append("")
            lines.append("SEMANTIC ANNOTATIONS:")
            for ann in self.annotations[-8:]:
                lines.append(
                    f"  Round {ann['round']} | {ann['agent']}: "
                    f"{ann['intent']} (theme: {ann['theme']})"
                )

        return "\n".join(lines)

    def get_full_log(self) -> dict:
        """Export the complete canvas state for saving to JSON transcript."""
        return {
            "regions": {
                name: {"owner": r.owner, "status": r.status}
                for name, r in self.regions.items()
            },
            "history": self.history,
            "annotations": self.annotations,
            "negotiation_record": self.negotiation_record,
        }
