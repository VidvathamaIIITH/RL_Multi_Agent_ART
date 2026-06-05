#!/usr/bin/env python3
"""
CanvasMind — Backend-only Multi-Agent Conversation Simulator
============================================================

Standalone Azure OpenAI REST version.

This version avoids the OpenAI Python SDK and avoids the existing
AzureOpenAIProvider class because your current provider is sending
`max_tokens`, while your GPT-5.2 deployment requires `max_completion_tokens`.

Usage:

    python simulate_chat.py
    python simulate_chat.py --prompt "A serene mountain lake at golden hour"
    python simulate_chat.py --prompt "A cathedral interior" --rounds 6 --style "baroque chiaroscuro"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# ---------------------------------------------------------------------------
# UTF-8 terminal safety
# ---------------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Paths and simple .env loader
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)


def load_env_file(path: Path) -> None:
    """
    Simple .env loader that ignores malformed lines instead of crashing.
    This avoids python-dotenv parse warnings.
    """
    if not path.exists():
        return

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            print(f"⚠️ Ignoring malformed .env line {line_number}: {raw_line}")
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not key:
            print(f"⚠️ Ignoring malformed .env line {line_number}: {raw_line}")
            continue

        # Do not overwrite already exported shell variables
        os.environ.setdefault(key, value)


load_env_file(BACKEND_DIR / ".env")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_GPTTEXT52 = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTTEXT52")
AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1 = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1")


# ---------------------------------------------------------------------------
# Terminal colors
# ---------------------------------------------------------------------------
class C:
    _on = sys.stdout.isatty()

    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""

    ARIA = "\033[96m" if _on else ""
    NEXUS = "\033[95m" if _on else ""
    JUDGE = "\033[93m" if _on else ""
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
    pad = " " * indent
    lines = textwrap.wrap(text or "", width=width)
    return "\n".join(pad + ln for ln in lines) if lines else pad


def fail(message: str) -> None:
    print(f"\n{C.RED}❌ FAILED:{C.RESET} {message}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_config() -> None:
    required = {
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
        "AZURE_OPENAI_DEPLOYMENT_GPTTEXT52": AZURE_OPENAI_DEPLOYMENT_GPTTEXT52,
    }

    missing = [name for name, value in required.items() if not value]

    if missing:
        fail(
            "Missing required environment variables:\n"
            + "\n".join(f"  - {name}" for name in missing)
            + "\n\nFix backend/.env or export them in your shell."
        )

    bad_values = []
    for name, value in required.items():
        if value and "os.getenv" in value:
            bad_values.append(f"{name}={value}")

    if bad_values:
        fail(
            "Your .env contains Python code instead of actual values:\n"
            + "\n".join(f"  - {item}" for item in bad_values)
            + "\n\n.env must contain actual values, not os.getenv(...)."
        )

    if not AZURE_OPENAI_ENDPOINT.startswith("https://"):
        fail("AZURE_OPENAI_ENDPOINT must start with https://")

    if not AZURE_OPENAI_ENDPOINT.rstrip("/").endswith("openai.azure.com"):
        fail("AZURE_OPENAI_ENDPOINT should look like https://your-resource.openai.azure.com/")

    banner("CanvasMind — Multi-Agent Creative AI Painting System", C.BLUE)
    print(f"  Azure Endpoint  : {AZURE_OPENAI_ENDPOINT}")
    print(f"  API Key         : ****{AZURE_OPENAI_API_KEY[-4:]}")
    print(f"  API Version     : {AZURE_OPENAI_API_VERSION}")
    print(f"  Text Deployment : {AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}")
    print(f"  Image Deployment: {AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1 or 'not set'}")
    print(f"  Backend Dir     : {BACKEND_DIR}")
    hr("═", C.BLUE)


# ---------------------------------------------------------------------------
# Azure REST call
# ---------------------------------------------------------------------------
def azure_chat_completion(
    messages: List[Dict[str, str]],
    max_completion_tokens: int = 1800,
    timeout: int = 180,
) -> str:
    """
    Calls Azure OpenAI chat/completions using REST.

    Important:
    This uses max_completion_tokens because GPT-5.2 rejects max_tokens.
    """

    endpoint = AZURE_OPENAI_ENDPOINT.rstrip("/")

    url = (
        f"{endpoint}/openai/deployments/"
        f"{AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}/chat/completions"
        f"?api-version={AZURE_OPENAI_API_VERSION}"
    )

    headers = {
        "api-key": AZURE_OPENAI_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Azure OpenAI request failed.\n"
            f"HTTP status: {response.status_code}\n"
            f"URL: {url}\n"
            f"Response: {response.text}"
        )

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(
            "Could not read assistant response from Azure response:\n"
            + json.dumps(data, indent=2)
        ) from exc

    if not content:
        raise RuntimeError(
            "Azure returned an empty response. Raw response:\n"
            + json.dumps(data, indent=2)
        )

    return content.strip()


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def extract_json_object(text: str) -> Dict[str, Any]:
    """
    Extracts a JSON object from model output.
    Handles raw JSON or JSON inside markdown fences.
    """
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in model output:\n{text}")

    json_text = cleaned[start : end + 1]
    return json.loads(json_text)


def safe_get(data: Dict[str, Any], key: str, default: Any = "") -> Any:
    value = data.get(key, default)
    return default if value is None else value


# ---------------------------------------------------------------------------
# Agent prompts
# ---------------------------------------------------------------------------
AGENT_JSON_SCHEMA = """
Return only valid JSON with this structure:
{
  "sender": "ARIA or NEXUS",
  "intent": "propose | critique | refine | converge",
  "confidence_score": 0.0,
  "artistic_goal": "...",
  "palette": ["...", "..."],
  "region": "...",
  "composition_notes": "...",
  "emotional_register": "...",
  "reasoning": "...",
  "critique": "...",
  "next_action": "..."
}
"""

CRITIC_JSON_SCHEMA = """
Return only valid JSON with this structure:
{
  "round": 1,
  "scores": {
    "compositional_coherence": 0.0,
    "style_fidelity": 0.0,
    "emotional_resonance": 0.0,
    "originality": 0.0,
    "clarity_of_next_action": 0.0,
    "composite": 0.0
  },
  "reasoning": "...",
  "contradictions_detected": ["..."],
  "weak_ideas": ["..."],
  "directive_agent_a": "...",
  "directive_agent_b": "...",
  "recommended_next_step": "...",
  "convergence_signal": false
}
"""


def build_agent_messages(
    agent_name: str,
    role_name: str,
    prompt: str,
    style_hint: str,
    round_number: int,
    transcript: List[str],
    canvas_description: str,
    critic_feedback: Optional[str],
) -> List[Dict[str, str]]:

    if agent_name == "ARIA":
        personality = (
            "You are ARIA, the Creative Director. You are decisive, visual, "
            "composition-focused, and skilled at turning vague ideas into a coherent artwork plan."
        )
    else:
        personality = (
            "You are NEXUS, the Creative Challenger. You question weak ideas, "
            "increase originality, add conceptual tension, and improve the plan without derailing it."
        )

    user_content = f"""
Creative brief:
{prompt}

Style hint:
{style_hint or "none"}

Current round:
{round_number}

Current canvas description:
{canvas_description}

Critic feedback for you:
{critic_feedback or "none yet"}

Conversation so far:
{chr(10).join(transcript[-8:]) if transcript else "none yet"}

Task:
As {agent_name}, produce the next structured contribution to the artwork discussion.
Be concrete, visual, and useful. Do not be generic.

{AGENT_JSON_SCHEMA}
"""

    return [
        {"role": "system", "content": personality},
        {"role": "user", "content": user_content},
    ]


def build_critic_messages(
    prompt: str,
    style_hint: str,
    round_number: int,
    transcript: List[str],
    canvas_description: str,
) -> List[Dict[str, str]]:

    system = (
        "You are JUDGE, a rigorous visual-art critic. You evaluate ARIA and NEXUS, "
        "score their current plan, identify contradictions, and decide whether the agents have converged."
    )

    user_content = f"""
Creative brief:
{prompt}

Style hint:
{style_hint or "none"}

Round:
{round_number}

Current canvas description:
{canvas_description}

Conversation to evaluate:
{chr(10).join(transcript[-10:])}

Instructions:
Score strictly from 0 to 10.
Set convergence_signal to true only if the plan is coherent, actionable, visually unified, and composite >= 7.5.

{CRITIC_JSON_SCHEMA}
"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Pretty printers
# ---------------------------------------------------------------------------
def print_agent_message(msg: Dict[str, Any], color: str, display_name: str, role: str) -> None:
    confidence = safe_get(msg, "confidence_score", 0.0)
    try:
        confidence_float = float(confidence)
    except Exception:
        confidence_float = 0.0

    print()
    print(
        f"{color}{C.BOLD}┌─ {display_name} {C.RESET}{color}({role}){C.RESET}"
        f"   {C.DIM}intent={safe_get(msg, 'intent', 'unknown')} · "
        f"confidence={confidence_float:.0%}{C.RESET}"
    )

    print(f"{color}│{C.RESET} {C.BOLD}Artistic goal:{C.RESET}")
    print(wrap(str(safe_get(msg, "artistic_goal"))))

    palette = safe_get(msg, "palette", [])
    if isinstance(palette, list) and palette:
        print(f"{color}│{C.RESET} {C.BOLD}Palette:{C.RESET}  {C.DIM}{'  '.join(map(str, palette[:8]))}{C.RESET}")

    region = safe_get(msg, "region", "")
    if region:
        print(f"{color}│{C.RESET} {C.BOLD}Region:{C.RESET}  {C.DIM}{region}{C.RESET}")

    print(f"{color}│{C.RESET} {C.BOLD}Composition:{C.RESET}")
    print(wrap(str(safe_get(msg, "composition_notes"))))

    print(f"{color}│{C.RESET} {C.BOLD}Emotional register:{C.RESET}  {C.DIM}{safe_get(msg, 'emotional_register')}{C.RESET}")

    print(f"{color}│{C.RESET} {C.BOLD}Reasoning:{C.RESET}")
    print(wrap(str(safe_get(msg, "reasoning"))))

    critique = safe_get(msg, "critique", "")
    if critique:
        print(f"{color}│{C.RESET} {C.BOLD}{C.RED}Critique:{C.RESET}")
        print(wrap(str(critique)))

    print(f"{color}│{C.RESET} {C.BOLD}{C.GREEN}Next action →{C.RESET}")
    print(wrap(str(safe_get(msg, "next_action"))))

    print(f"{color}└{'─' * 60}{C.RESET}")


def score_bar(score: float) -> str:
    score = max(0.0, min(10.0, float(score)))
    filled = int(round(score))
    col = C.GREEN if score >= 7.5 else (C.JUDGE if score >= 5 else C.RED)
    return f"{col}{'█' * filled}{C.GREY}{'░' * (10 - filled)}{C.RESET} {col}{score:.1f}{C.RESET}"


def print_critic(evaluation: Dict[str, Any]) -> None:
    scores = evaluation.get("scores", {})

    def sc(key: str) -> float:
        try:
            return float(scores.get(key, 0.0))
        except Exception:
            return 0.0

    print()
    print(f"{C.JUDGE}{C.BOLD}╔═ JUDGE {C.RESET}{C.JUDGE}(Critic Agent) — Round {safe_get(evaluation, 'round', '?')}{C.RESET}")

    print(f"{C.JUDGE}║{C.RESET}  Compositional Coherence  {score_bar(sc('compositional_coherence'))}")
    print(f"{C.JUDGE}║{C.RESET}  Style Fidelity           {score_bar(sc('style_fidelity'))}")
    print(f"{C.JUDGE}║{C.RESET}  Emotional Resonance      {score_bar(sc('emotional_resonance'))}")
    print(f"{C.JUDGE}║{C.RESET}  Originality              {score_bar(sc('originality'))}")
    print(f"{C.JUDGE}║{C.RESET}  Clarity of Next Action   {score_bar(sc('clarity_of_next_action'))}")
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}COMPOSITE{C.RESET}                {score_bar(sc('composite'))}")

    print(f"{C.JUDGE}║{C.RESET}")
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}Assessment:{C.RESET}")
    print(wrap(str(safe_get(evaluation, "reasoning"))))

    contradictions = safe_get(evaluation, "contradictions_detected", [])
    if isinstance(contradictions, list) and contradictions:
        print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.RED}Contradictions:{C.RESET}")
        for item in contradictions:
            print(f"{C.RED}        • {item}{C.RESET}")

    weak_ideas = safe_get(evaluation, "weak_ideas", [])
    if isinstance(weak_ideas, list) and weak_ideas:
        print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}Weak ideas to strengthen:{C.RESET}")
        for item in weak_ideas:
            print(f"{C.DIM}        • {item}{C.RESET}")

    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.ARIA}→ Directive for ARIA:{C.RESET}")
    print(wrap(str(safe_get(evaluation, "directive_agent_a"))))

    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.NEXUS}→ Directive for NEXUS:{C.RESET}")
    print(wrap(str(safe_get(evaluation, "directive_agent_b"))))

    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}{C.GREEN}Recommended next step:{C.RESET}")
    print(wrap(str(safe_get(evaluation, "recommended_next_step"))))

    signal = bool(safe_get(evaluation, "convergence_signal", False))
    sig_text = f"{C.GREEN}YES — agents have converged{C.RESET}" if signal else f"{C.DIM}not yet{C.RESET}"
    print(f"{C.JUDGE}║{C.RESET}  {C.BOLD}Convergence signal:{C.RESET}  {sig_text}")

    print(f"{C.JUDGE}╚{'═' * 60}{C.RESET}")


def readable_agent_message(msg: Dict[str, Any]) -> str:
    sender = safe_get(msg, "sender", "Agent")
    intent = safe_get(msg, "intent", "unknown")
    artistic_goal = safe_get(msg, "artistic_goal", "")
    composition = safe_get(msg, "composition_notes", "")
    palette = safe_get(msg, "palette", [])
    critique = safe_get(msg, "critique", "")
    next_action = safe_get(msg, "next_action", "")

    parts = [f"{sender} intent={intent}: {artistic_goal}"]

    if composition:
        parts.append(f"Composition: {composition}")

    if isinstance(palette, list) and palette:
        parts.append(f"Palette: {', '.join(map(str, palette[:6]))}")

    if critique:
        parts.append(f"Critique: {critique}")

    if next_action:
        parts.append(f"Next: {next_action}")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
def run_agent(
    agent_name: str,
    role_name: str,
    color: str,
    prompt: str,
    style_hint: str,
    round_number: int,
    transcript: List[str],
    canvas_description: str,
    critic_feedback: Optional[str],
) -> Dict[str, Any]:

    sys.stdout.write(f"\n{color}  {agent_name} is thinking{C.RESET} ")
    sys.stdout.flush()

    messages = build_agent_messages(
        agent_name=agent_name,
        role_name=role_name,
        prompt=prompt,
        style_hint=style_hint,
        round_number=round_number,
        transcript=transcript,
        canvas_description=canvas_description,
        critic_feedback=critic_feedback,
    )

    raw = azure_chat_completion(messages, max_completion_tokens=1800)

    try:
        data = extract_json_object(raw)
    except Exception:
        # Fallback: keep the simulation alive even if JSON formatting is imperfect.
        data = {
            "sender": agent_name,
            "intent": "propose" if agent_name == "ARIA" else "critique",
            "confidence_score": 0.7,
            "artistic_goal": raw[:700],
            "palette": [],
            "region": "whole canvas",
            "composition_notes": "The model returned unstructured text; using it as the creative proposal.",
            "emotional_register": "evocative",
            "reasoning": raw[:900],
            "critique": "",
            "next_action": "Continue refining the artwork plan in the next turn.",
        }

    data["sender"] = agent_name
    print_agent_message(data, color, agent_name, role_name)
    return data


def run_critic(
    prompt: str,
    style_hint: str,
    round_number: int,
    transcript: List[str],
    canvas_description: str,
) -> Dict[str, Any]:

    sys.stdout.write(f"\n{C.JUDGE}  JUDGE is evaluating{C.RESET} ")
    sys.stdout.flush()

    messages = build_critic_messages(
        prompt=prompt,
        style_hint=style_hint,
        round_number=round_number,
        transcript=transcript,
        canvas_description=canvas_description,
    )

    raw = azure_chat_completion(messages, max_completion_tokens=1800)

    try:
        data = extract_json_object(raw)
    except Exception:
        data = {
            "round": round_number,
            "scores": {
                "compositional_coherence": 6.0,
                "style_fidelity": 6.0,
                "emotional_resonance": 6.0,
                "originality": 6.0,
                "clarity_of_next_action": 6.0,
                "composite": 6.0,
            },
            "reasoning": raw[:900],
            "contradictions_detected": [],
            "weak_ideas": ["Critic returned unstructured text; continue refining."],
            "directive_agent_a": "Clarify the composition and focal hierarchy.",
            "directive_agent_b": "Challenge the weakest visual idea and add specificity.",
            "recommended_next_step": "Continue another round.",
            "convergence_signal": False,
        }

    data["round"] = round_number
    print_critic(data)
    return data


def simulate(prompt: str, rounds: int, style_hint: str) -> None:
    session_start = time.time()

    transcript: List[str] = [f"USER BRIEF: {prompt}"]
    canvas_description = "Blank canvas. No operations yet."

    last_critic_feedback_a: Optional[str] = None
    last_critic_feedback_b: Optional[str] = None
    composite_history: List[float] = []
    converged = False

    banner("CanvasMind — Multi-Agent Creative Dialogue", C.BLUE)
    print(f"  {C.BOLD}Prompt:{C.RESET}  {prompt}")
    if style_hint:
        print(f"  {C.BOLD}Style :{C.RESET}  {style_hint}")
    print(f"  {C.BOLD}Rounds:{C.RESET}  up to {rounds}")
    print(f"  {C.BOLD}Model :{C.RESET}  {AZURE_OPENAI_DEPLOYMENT_GPTTEXT52}")
    print()

    for rnd in range(1, rounds + 1):
        print()
        hr("━", C.BOLD)
        print(f"{C.BOLD}  ROUND {rnd} / {rounds}{C.RESET}")
        hr("━", C.BOLD)

        try:
            aria_msg = run_agent(
                agent_name="ARIA",
                role_name="Creative Director",
                color=C.ARIA,
                prompt=prompt,
                style_hint=style_hint,
                round_number=rnd,
                transcript=transcript,
                canvas_description=canvas_description,
                critic_feedback=last_critic_feedback_a,
            )
        except Exception as exc:
            print(f"\n{C.RED}  ARIA failed this round:{C.RESET} {exc}")
            break

        transcript.append(readable_agent_message(aria_msg))
        canvas_description = (
            f"Round {rnd} ARIA direction: {safe_get(aria_msg, 'artistic_goal')}. "
            f"{safe_get(aria_msg, 'composition_notes')} "
            f"Emotional register: {safe_get(aria_msg, 'emotional_register')}."
        )

        try:
            nexus_msg = run_agent(
                agent_name="NEXUS",
                role_name="Creative Challenger",
                color=C.NEXUS,
                prompt=prompt,
                style_hint=style_hint,
                round_number=rnd,
                transcript=transcript,
                canvas_description=canvas_description,
                critic_feedback=last_critic_feedback_b,
            )
        except Exception as exc:
            print(f"\n{C.RED}  NEXUS failed this round:{C.RESET} {exc}")
            break

        transcript.append(readable_agent_message(nexus_msg))

        try:
            evaluation = run_critic(
                prompt=prompt,
                style_hint=style_hint,
                round_number=rnd,
                transcript=transcript,
                canvas_description=canvas_description,
            )
        except Exception as exc:
            print(f"\n{C.RED}  JUDGE failed this round:{C.RESET} {exc}")
            break

        scores = evaluation.get("scores", {})
        try:
            composite = float(scores.get("composite", 0.0))
        except Exception:
            composite = 0.0

        composite_history.append(composite)

        last_critic_feedback_a = str(safe_get(evaluation, "directive_agent_a", ""))
        last_critic_feedback_b = str(safe_get(evaluation, "directive_agent_b", ""))

        if bool(safe_get(evaluation, "convergence_signal", False)) and composite >= 7.5:
            converged = True
            print()
            banner(f"CONVERGED in round {rnd} · composite {composite:.1f}/10", C.GREEN)
            break

    elapsed = time.time() - session_start

    print()
    banner("SESSION SUMMARY", C.BLUE)
    outcome = f"{C.GREEN}Converged{C.RESET}" if converged else f"{C.JUDGE}Max rounds reached{C.RESET}"
    print(f"  {C.BOLD}Outcome      :{C.RESET}  {outcome}")
    print(f"  {C.BOLD}Rounds run   :{C.RESET}  {len(composite_history)}")

    if composite_history:
        trend = "  ".join(f"{score:.1f}" for score in composite_history)
        print(f"  {C.BOLD}Score trend  :{C.RESET}  {trend}")
        print(f"  {C.BOLD}Final score  :{C.RESET}  {composite_history[-1]:.1f}/10")

    print(f"  {C.BOLD}Elapsed time :{C.RESET}  {elapsed:.1f}s")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
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
        "--rounds",
        type=int,
        default=5,
        help="Maximum number of negotiation rounds.",
    )
    parser.add_argument(
        "--style",
        default="",
        help="Optional style hint, for example: 'baroque', 'neon noir', 'impressionist'.",
    )

    args = parser.parse_args()

    validate_config()

    try:
        rounds = max(1, min(args.rounds, 20))
        simulate(args.prompt, rounds, args.style)
    except KeyboardInterrupt:
        print(f"\n{C.DIM}Interrupted by user.{C.RESET}")


if __name__ == "__main__":
    main()