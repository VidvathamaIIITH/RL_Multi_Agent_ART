from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Optional

from schemas.canvas_operation import CanvasOperation
from schemas.session_schemas import CanvasStateModel, CanvasSnapshot

logger = logging.getLogger(__name__)


class CanvasManager:

    def apply_operations(
        self,
        canvas: CanvasStateModel,
        operations: List[CanvasOperation],
        round_num: int,
    ) -> CanvasStateModel:
        canvas.operations_history.extend(operations)
        for op in operations:
            canvas.region_ownership[op.region.value] = op.agent
        canvas.current_round = round_num
        canvas.last_updated = datetime.utcnow()
        snapshot = self.take_snapshot(canvas, round_num)
        canvas.snapshots.append(snapshot)
        return canvas

    def take_snapshot(self, canvas: CanvasStateModel, round_num: int) -> CanvasSnapshot:
        ops_this_round = [op for op in canvas.operations_history if op.round == round_num]
        return CanvasSnapshot(
            round=round_num,
            image_base64=canvas.current_image_base64,
            operations=ops_this_round,
            region_map=dict(canvas.region_ownership),
            annotations=[],
            artistic_intent_summary=self.get_canvas_summary(canvas),
            timestamp=datetime.utcnow(),
        )

    def rollback_to_round(self, canvas: CanvasStateModel, round_num: int) -> CanvasStateModel:
        canvas.operations_history = [op for op in canvas.operations_history if op.round <= round_num]
        canvas.snapshots = [s for s in canvas.snapshots if s.round <= round_num]
        canvas.current_round = round_num

        snapshot = next((s for s in reversed(canvas.snapshots) if s.round == round_num), None)
        if snapshot:
            canvas.region_ownership = dict(snapshot.region_map)
            canvas.current_image_base64 = snapshot.image_base64
        else:
            canvas.region_ownership = {}
            canvas.current_image_base64 = None

        canvas.last_updated = datetime.utcnow()
        return canvas

    def get_region_description(self, canvas: CanvasStateModel) -> str:
        if not canvas.region_ownership:
            return "Canvas is empty — no regions claimed yet."
        lines = ["Region ownership:"]
        for region, agent in canvas.region_ownership.items():
            lines.append(f"  {region}: owned by {agent}")
        return "\n".join(lines)

    def update_region_ownership(
        self, canvas: CanvasStateModel, region: str, agent: str
    ) -> CanvasStateModel:
        prev = canvas.region_ownership.get(region)
        if prev and prev != agent:
            if region not in canvas.contested_regions:
                canvas.contested_regions.append(region)
        canvas.region_ownership[region] = agent
        return canvas

    def get_canvas_summary(self, canvas: CanvasStateModel) -> str:
        if not canvas.operations_history:
            return "Canvas is blank. No operations have been applied yet."

        lines = [f"Canvas {canvas.width}x{canvas.height} | Round {canvas.current_round}"]
        lines.append(f"Total operations: {len(canvas.operations_history)}")

        if canvas.region_ownership:
            lines.append("\nRegion map:")
            for region, agent in canvas.region_ownership.items():
                lines.append(f"  [{region}] -> {agent}")

        if canvas.contested_regions:
            lines.append(f"\nContested regions: {', '.join(canvas.contested_regions)}")

        recent = canvas.operations_history[-5:]
        if recent:
            lines.append("\nRecent operations:")
            for op in recent:
                palette_str = ", ".join(op.color_palette[:3]) if op.color_palette else "no palette"
                lines.append(
                    f"  Round {op.round} | {op.agent} | {op.operation_type.value} "
                    f"@ {op.region.value}: {op.description[:80]}... [{palette_str}]"
                )

        return "\n".join(lines)

    async def generate_visual_representation(
        self,
        canvas: CanvasStateModel,
        provider,
    ) -> str:
        summary = self.get_canvas_summary(canvas)
        recent_ops = canvas.operations_history[-10:]
        op_descriptions = "; ".join(
            f"{op.region.value}: {op.description}" for op in recent_ops
        )
        palettes = []
        for op in recent_ops:
            palettes.extend(op.color_palette)
        unique_palettes = list(dict.fromkeys(palettes))[:8]

        image_prompt = (
            f"A painting with the following composition: {op_descriptions}. "
            f"Color palette: {', '.join(unique_palettes) if unique_palettes else 'varied'}. "
            "High artistic quality, detailed brushwork, museum-quality composition."
        )
        return await provider.generate_image(image_prompt, size="1024x1024")
