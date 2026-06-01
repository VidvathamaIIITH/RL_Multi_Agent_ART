#!/usr/bin/env python3
"""
CanvasMind — Backend-only Multi-Agent Conversation Simulator
============================================================

Runs the ENTIRE multi-agent creative dialogue in the terminal, on the VM,
with NO frontend, NO proxy, NO ports, NO WebSocket. Three AI agents — ARIA
(Creative Director), NEXUS (Creative Challenger) and JUDGE (Critic) — talk to
each other in real time using their real personalities, and converge on a
unified artwork plan.

This is the bulletproof way to demo CanvasMind on a remote VM: it only needs
Azure OpenAI credentials in backend/.env and a working internet connection.

USAGE (from the backend/ directory, with venv active):

    python simulate_chat.py
    python simulate_chat.py --prompt "A serene mountain lake at golden hour"
    python simulate_chat.py --prompt "A cyberpunk forest" --rounds 6 --style "neon noir"

It reuses the real production classes so the conversation is identical to what
the full app produces — nothing is mocked, nothing is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr so the box-drawing characters and colour bars
# render on every platform (Windows consoles default to cp1252 and would
# otherwise crash on the banner). On Linux/macOS this is a harmless no-op.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Make the script runnable from anywhere: anchor to the backend/ directory so
# that `import config`, `import providers...`, `import agents...` resolve and
# so config.load_dotenv() finds backend/.env regardless of the caller's cwd.
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

# Importing config validates Azure credentials and prints the startup banner.
# If any required env var is missing it exits with a clear message — exactly
# like the real backend does.
from config import validate_config, settings  # noqa: E402
from providers.azure_openai_provider import AzureOpenAIProvider  # noqa: E402
from agents.creative_director import CreativeDirector  # noqa: E402
from agents.creative_challenger import CreativeChallenger  # noqa: E402
from agents.critic_agent import CriticAgent  # noqa: E402
from schemas.agent_message import AgentMessage  # noqa: E402
from schemas.critic_evaluation import CriticEvaluation  # noqa: E402


# ---------------------------------------------------------------------------
# Terminal colours (ANSI). Auto-disable if output is not a TTY (e.g. piped to
# a file or journald) so logs stay clean.
# ---------------------------------------------------------------------------
class C:
    _on = sys.stdout.isatty()

    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""

    ARIA = "\033[96m" if _on else ""      # bright cyan
    NEXUS = "\033[95m" if _on else ""     # bright magenta
    JUDGE = "\033[93m" if _on else ""     # bright yellow
    GREEN = "\033[92m" if _on else ""
    RED = "\033[91m" if _on else ""
    GREY = "\033[90m" if _on else ""
    BLUE = "\033[94m" if _on else ""


def hr(char: str = "─", color: str = C.GREY) -> None:
    print(f"{color}{char * 78}{C.RESET}")


def banner(text: str, color: str) -> None:
    hr("═", color)
    print(f"{color}{C.BOLD}  {text}{C.RESET}")
    hr("═", color)


def wrap(text: str, indent: int = 6, width: int = 72) -> str:
    """Word-wrap a paragraph with a hanging indent for readable terminal output."""
    import textwrap

    pad = " " * indent
    lines = textwrap.wrap(text or "", width=width)
    return "\n".join(pad + ln for ln in lines) if lines else pad + ""


# ---------------------------------------------------------------------------
# Pretty-printers for the structured agent / critic outputs.
# ---------------------------------------------------------------------------
def print_agent_message(msg: AgentMessage, color: str, display_name: str, role: str) -> None:
    print()
    print(f"{color}{C.BOLD}┌─ {display_name} {C.RESET}{color}({role}){C.RESET}"
          f"   {C.DIM}intent={msg.intent.value} · confidence={msg.confidence_score:.0%}{C.RESET}")

    print(f"{color}│{C.RESET} {C.BOLD}Artistic goal:{C.RESET}")
    print(wrap(msg.artistic_goal))

    if msg.palette:
        swatches = "  ".join(msg.palette[:8])
        print(f"{color}│{C.RESET} {C.BOLD}Palette:{C.RESET}  {C.DIM}{swatches}{C.RESET}")

    if msg.region:
        print(f"{color}│{C.RESET} {C.BOLD}Region:{C.RESET}  {C.DIM}{msg.region}{C.RESET}")

    print(f"{color}│{C.RESET} {C.BOLD}Composition:{C.RESET}")
    print(wrap(msg.composition_notes))

    print(f"{color}│{C.RESET} {C.BOLD}Emotional register:{C.RESET}  {C.DIM}{msg.emotional_register}{C.RESET}")

    print(f"{color}│{C.RESET} {C.BOLD}Reasoning:{C.RESET}")
    print(wrap(msg.reasoning))

    if msg.critique:
        print(f"{color}│{C.RESET} {C.BOLD}{C.RED}Critique:{C.RESET}")
        print(wrap(msg.critique))

    print(f"{color}│{C.RESET} {C.BOLD}{C.GREEN}Next action →{C.RESET}")
    print(wrap(msg.next_action))
    print(f"{color}└{'─' * 60}{C.RESET}")


def print_critic(evaluation: CriticEvaluation) -> None:
    s = evaluation.scores
    print()
    print(f"{C.JUDGE}{C.BOLD}╔═ JUDGE {C.RESET}{C.JUDGE}(Critic Agent) — Round {evaluation.round}{C.RESET}")

    def bar(score: float) -> str:
        filled = int(round(score))
        col = C.GREEN if score >= 7.5 else (C.JUDGE if score >= 5 else C.RED)
        return f"{col}{'█' * filled}{C.GREY}{'░' * (10 - filled)}{C.RESET} {col}{score:.1f}{C.RESET}"

    print(f"{C.JUDGE}║{C.RESET}  Compositional Coherence  {bar(s.compositional_coherence)}")
    print(f"{C.JUDGE}║{C.RESET}  Style Fidelity           {bar(s.style_fidelity)}")
    print(f"{C.JUDGE}║{C.RESET}  Emotional Resonance      {bar(s.emotional_resonance)}")
    print(f"{C.JUDGE}║{C.RESET}  Originality              {bar(s.originality)}")
    print(f"{C.JUDGE}║{C.RESET}  Clarity of Next Action   {bar(s.clarity_of_next_action)}")
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}COMPOSITE{C.RESET}                {bar(s.composite)}")

    print(f"{C.JUDGE}║{C.RESET}")
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}Assessment:{C.RESET}")
    print(wrap(evaluation.reasoning))

    if evaluation.contradictions_detected:
        print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.RED}Contradictions:{C.RESET}")
        for c in evaluation.contradictions_detected:
            print(f"{C.RED}        • {c}{C.RESET}")

    if evaluation.weak_ideas:
        print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}Weak ideas to strengthen:{C.RESET}")
        for w in evaluation.weak_ideas:
            print(f"{C.DIM}        • {w}{C.RESET}")

    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.ARIA}→ Directive for ARIA:{C.RESET}")
    print(wrap(evaluation.directive_agent_a))
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.NEXUS}→ Directive for NEXUS:{C.RESET}")
    print(wrap(evaluation.directive_agent_b))

    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.GREEN}Recommended next step:{C.RESET}")
    print(wrap(evaluation.recommended_next_step))

    sig = (f"{C.GREEN}YES — agents have converged{C.RESET}"
           if evaluation.convergence_signal else f"{C.DIM}not yet{C.RESET}")
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}Convergence signal:{C.RESET}  {sig}")
    print(f"{C.JUDGE}╚{'═' * 60}{C.RESET}")


# ---------------------------------------------------------------------------
# A small live "thinking" indicator that prints a dot every few streamed
# tokens, so you can see the agent is actively generating without dumping raw
# JSON to the screen.
# ---------------------------------------------------------------------------
def make_ticker(color: str):
    counter = {"n": 0}

    async def on_token(_token: str) -> None:
        counter["n"] += 1
        if counter["n"] % 18 == 0:
            sys.stdout.write(f"{color}.{C.RESET}")
            sys.stdout.flush()

    return on_token


def readable(msg: AgentMessage) -> str:
    """Compact text form of an agent message for the shared transcript."""
    parts = [f"{msg.sender} (intent={msg.intent.value}): {msg.artistic_goal}."]
    if msg.composition_notes:
        parts.append(f"Composition: {msg.composition_notes}.")
    if msg.palette:
        parts.append(f"Palette: {', '.join(msg.palette[:6])}.")
    if msg.critique:
        parts.append(f"Critique: {msg.critique}.")
    parts.append(f"Next: {msg.next_action}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main simulation loop.
# ---------------------------------------------------------------------------
async def simulate(prompt: str, rounds: int, style_hint: str) -> None:
    provider = AzureOpenAIProvider()
    aria = CreativeDirector(provider)
    nexus = CreativeChallenger(provider)
    judge = CriticAgent(provider)

    session_context = (
        f"User prompt: {prompt}\n"
        f"Style hint: {style_hint or 'none'}\n"
        f"Goal: ARIA and NEXUS collaborate over up to {rounds} rounds to converge "
        f"on a single, richly-specified artwork plan. JUDGE scores each round."
    )

    # Shared dialogue transcript (role/content pairs). The original prompt is
    # the seed user turn; agent messages are appended as assistant turns.
    transcript: list[dict] = [{"role": "user", "content": prompt}]

    # An evolving plain-text description of the current artistic direction,
    # used in place of a rendered canvas image for this backend-only demo.
    canvas_description = "Blank canvas. No operations yet."

    last_critic_feedback_a: str | None = None
    last_critic_feedback_b: str | None = None
    composite_history: list[float] = []
    converged = False
    start = time.time()

    banner("CanvasMind — Multi-Agent Creative Dialogue (backend simulation)", C.BLUE)
    print(f"  {C.BOLD}Prompt:{C.RESET}  {prompt}")
    if style_hint:
        print(f"  {C.BOLD}Style :{C.RESET}  {style_hint}")
    print(f"  {C.BOLD}Rounds:{C.RESET}  up to {rounds}")
    print(f"  {C.BOLD}Model :{C.RESET}  {settings.deployment_text}")
    print()

    for rnd in range(1, rounds + 1):
        print()
        hr("━", C.BOLD)
        print(f"{C.BOLD}  ROUND {rnd} / {rounds}{C.RESET}")
        hr("━", C.BOLD)

        # ---------------- ARIA (Creative Director) ----------------
        sys.stdout.write(f"\n{C.ARIA}  ARIA is composing{C.RESET} ")
        sys.stdout.flush()
        try:
            aria_msg = await aria.generate_response(
                conversation_history=transcript + [
                    {"role": "user",
                     "content": f"It is round {rnd}. As ARIA, the Creative Director, "
                                f"advance the artwork with a decisive, concrete proposal."}
                ],
                canvas_description=canvas_description,
                critic_feedback=last_critic_feedback_a,
                session_context=session_context,
                on_token=make_ticker(C.ARIA),
            )
        except Exception as exc:
            print(f"\n{C.RED}  ARIA failed this round: {exc}{C.RESET}")
            break

        print_agent_message(aria_msg, C.ARIA, "ARIA", "Creative Director")
        transcript.append({"role": "assistant", "content": readable(aria_msg)})
        canvas_description = (
            f"Round {rnd} direction (ARIA): {aria_msg.artistic_goal}. "
            f"{aria_msg.composition_notes} Emotional register: {aria_msg.emotional_register}."
        )

        # ---------------- NEXUS (Creative Challenger) ----------------
        sys.stdout.write(f"\n{C.NEXUS}  NEXUS is examining{C.RESET} ")
        sys.stdout.flush()
        try:
            nexus_msg = await nexus.generate_response(
                conversation_history=transcript + [
                    {"role": "user",
                     "content": f"It is round {rnd}. As NEXUS, the Creative Challenger, "
                                f"respond to ARIA's latest proposal — challenge a genuine "
                                f"weakness or propose a richer alternative."}
                ],
                canvas_description=canvas_description,
                critic_feedback=last_critic_feedback_b,
                session_context=session_context,
                on_token=make_ticker(C.NEXUS),
            )
        except Exception as exc:
            print(f"\n{C.RED}  NEXUS failed this round: {exc}{C.RESET}")
            break

        print_agent_message(nexus_msg, C.NEXUS, "NEXUS", "Creative Challenger")
        transcript.append({"role": "assistant", "content": readable(nexus_msg)})

        # ---------------- JUDGE (Critic) ----------------
        sys.stdout.write(f"\n{C.JUDGE}  JUDGE is evaluating{C.RESET} ")
        sys.stdout.flush()
        try:
            evaluation = await judge.evaluate(
                conversation_history=transcript,
                canvas_description=canvas_description,
                round_number=rnd,
                on_token=make_ticker(C.JUDGE),
            )
        except Exception as exc:
            print(f"\n{C.RED}  JUDGE failed this round: {exc}{C.RESET}")
            break

        print_critic(evaluation)
        composite_history.append(evaluation.scores.composite)

        # Feed the critic's directives into the next round for each agent.
        last_critic_feedback_a = evaluation.directive_agent_a
        last_critic_feedback_b = evaluation.directive_agent_b

        # ---------------- Convergence check ----------------
        if evaluation.convergence_signal and evaluation.scores.composite >= 7.5:
            converged = True
            print()
            banner(f"CONVERGED in round {rnd}  ·  composite {evaluation.scores.composite:.1f}/10", C.GREEN)
            break

    # ---------------- Final summary ----------------
    elapsed = time.time() - start
    print()
    banner("SESSION SUMMARY", C.BLUE)
    print(f"  {C.BOLD}Outcome      :{C.RESET}  "
          f"{C.GREEN + 'Converged' + C.RESET if converged else C.JUDGE + 'Max rounds reached' + C.RESET}")
    print(f"  {C.BOLD}Rounds run   :{C.RESET}  {len(composite_history)}")
    if composite_history:
        trend = "  ".join(f"{v:.1f}" for v in composite_history)
        print(f"  {C.BOLD}Score trend  :{C.RESET}  {trend}")
        print(f"  {C.BOLD}Final score  :{C.RESET}  {composite_history[-1]:.1f}/10")
    print(f"  {C.BOLD}Elapsed time :{C.RESET}  {elapsed:.1f}s")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CanvasMind backend-only multi-agent conversation simulator."
    )
    parser.add_argument(
        "--prompt",
        default="A surreal cyberpunk forest at dusk, bioluminescent and rain-soaked",
        help="The creative brief the agents collaborate on.",
    )
    parser.add_argument(
        "--rounds", type=int, default=5,
        help="Maximum number of negotiation rounds (default 5).",
    )
    parser.add_argument(
        "--style", default="",
        help="Optional style hint (e.g. 'baroque', 'neon noir', 'impressionist').",
    )
    args = parser.parse_args()

    # Validate Azure credentials and print the startup banner (exits cleanly
    # with a helpful message if backend/.env is missing required values).
    validate_config()

    try:
        asyncio.run(simulate(args.prompt, max(1, min(args.rounds, 20)), args.style))
    except KeyboardInterrupt:
        print(f"\n{C.DIM}Interrupted by user.{C.RESET}")


if __name__ == "__main__":
    main()
