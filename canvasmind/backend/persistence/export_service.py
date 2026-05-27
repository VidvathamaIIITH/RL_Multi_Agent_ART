from __future__ import annotations
import io
import json
import zipfile
import base64
from datetime import datetime
from typing import Any, Dict

from schemas.session_schemas import Session


class ExportService:

    async def export_json(self, session: Session) -> Dict[str, Any]:
        return json.loads(session.model_dump_json())

    async def export_markdown(self, session: Session) -> str:
        lines = [
            f"# CanvasMind Session Report",
            f"",
            f"**Session ID:** `{session.session_id}`",
            f"**Title:** {session.title}",
            f"**Prompt:** {session.user_prompt}",
            f"**Status:** {session.status.value}",
            f"**Rounds:** {session.current_round}/{session.max_rounds}",
            f"**Convergence Score:** {session.convergence_score:.1%}",
            f"**Created:** {session.created_at.isoformat()}",
            f"",
            f"---",
            f"",
            f"## Critic Scores by Round",
            f"",
            f"| Round | Composition | Style | Emotion | Originality | Clarity | **Composite** |",
            f"|-------|-------------|-------|---------|-------------|---------|---------------|",
        ]
        for ev in session.critic_evaluations:
            s = ev.scores
            lines.append(
                f"| {ev.round} | {s.compositional_coherence} | {s.style_fidelity} | "
                f"{s.emotional_resonance} | {s.originality} | {s.clarity_of_next_action} | **{s.composite:.1f}** |"
            )

        lines += ["", "---", "", "## Agent Dialogue Transcript", ""]
        for msg in session.messages:
            lines.append(f"### Round {msg.round} — {msg.sender.upper()} [{msg.intent.value}]")
            lines.append(f"**Goal:** {msg.artistic_goal}")
            lines.append(f"**Composition:** {msg.composition_notes}")
            lines.append(f"**Next Action:** {msg.next_action}")
            if msg.critique:
                lines.append(f"**Critique:** {msg.critique}")
            lines.append("")

        if session.finalized_plan:
            lines += ["---", "", "## Final Convergence Plan", "", "```", session.finalized_plan, "```", ""]

        lines += ["---", "", "## Canvas Operation Log", ""]
        for op in session.canvas_state.operations_history:
            lines.append(
                f"- **Round {op.round}** | `{op.agent}` | `{op.operation_type.value}` @ `{op.region.value}`: {op.description}"
            )

        if session.user_interventions:
            lines += ["", "---", "", "## User Interventions", ""]
            for iv in session.user_interventions:
                lines.append(f"- {iv.get('timestamp', '')}: {iv.get('action', '')} — {iv.get('instruction', '')}")

        return "\n".join(lines)

    async def export_transcript(self, session: Session) -> str:
        lines = [f"CANVASMIND SESSION TRANSCRIPT", f"Prompt: {session.user_prompt}", "=" * 60, ""]
        for msg in session.messages:
            if msg.sender == "user":
                lines.append(f"[USER INTERVENTION]: {msg.next_action}")
            else:
                lines.append(f"[Round {msg.round}] {msg.sender.upper()} ({msg.intent.value}):")
                lines.append(f"  {msg.artistic_goal}")
                lines.append(f"  Next: {msg.next_action}")
            lines.append("")
        return "\n".join(lines)

    async def export_replay(self, session: Session) -> Dict[str, Any]:
        events = []
        for msg in session.messages:
            events.append({
                "type": "agent_message",
                "timestamp": msg.timestamp.isoformat(),
                "agent": msg.sender,
                "round": msg.round,
                "intent": msg.intent.value,
                "content": msg.raw_text or msg.artistic_goal,
            })
        for ev in session.critic_evaluations:
            events.append({
                "type": "critic_evaluation",
                "timestamp": ev.timestamp.isoformat(),
                "round": ev.round,
                "composite_score": ev.scores.composite,
                "convergence_signal": ev.convergence_signal,
            })
        events.sort(key=lambda e: e["timestamp"])
        return {
            "session_id": session.session_id,
            "prompt": session.user_prompt,
            "replay_events": events,
            "metadata": self.generate_provenance_metadata(session),
        }

    async def export_canvas_history(self, session: Session) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for snap in session.canvas_state.snapshots:
                if snap.image_base64:
                    img_bytes = base64.b64decode(snap.image_base64)
                    zf.writestr(f"round_{snap.round:02d}.png", img_bytes)
                snap_json = json.dumps(snap.model_dump(), indent=2, default=str)
                zf.writestr(f"round_{snap.round:02d}_metadata.json", snap_json)
        buf.seek(0)
        return buf.read()

    def generate_provenance_metadata(self, session: Session) -> Dict[str, Any]:
        return {
            "session_id": session.session_id,
            "title": session.title,
            "prompt": session.user_prompt,
            "status": session.status.value,
            "rounds_completed": session.current_round,
            "convergence_score": session.convergence_score,
            "agent_messages_count": len(session.messages),
            "critic_evaluations_count": len(session.critic_evaluations),
            "canvas_operations_count": len(session.canvas_state.operations_history),
            "user_interventions_count": len(session.user_interventions),
            "created_at": session.created_at.isoformat(),
            "finalized_at": session.updated_at.isoformat(),
            "convergence_trace": [
                {"round": e.round, "composite": e.scores.composite, "signal": e.convergence_signal}
                for e in session.critic_evaluations
            ],
        }
