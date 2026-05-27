from __future__ import annotations
from schemas.session_schemas import CanvasStateModel


def render_ascii_canvas(canvas: CanvasStateModel) -> str:
    REGIONS = [
        ["top_left", "top_center", "top_right"],
        ["middle_left", "center", "middle_right"],
        ["bottom_left", "bottom_center", "bottom_right"],
    ]
    ownership = canvas.region_ownership
    AGENT_A_SYM = "A"
    AGENT_B_SYM = "B"
    EMPTY_SYM = "."

    lines = ["┌──────────────────────────────────┐"]
    for row in REGIONS:
        cells = []
        for region in row:
            owner = ownership.get(region, "")
            if "agent_a" in owner:
                sym = AGENT_A_SYM
            elif "agent_b" in owner:
                sym = AGENT_B_SYM
            else:
                sym = EMPTY_SYM
            cells.append(f"   {sym}   ")
        lines.append("│" + "│".join(cells) + "│")
        if row != REGIONS[-1]:
            lines.append("├──────────────────────────────────┤")
    lines.append("└──────────────────────────────────┘")
    lines.append("  A=Agent A  B=Agent B  .=Empty")
    return "\n".join(lines)
