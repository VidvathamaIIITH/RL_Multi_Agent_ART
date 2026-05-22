"""
Computational Creativity Chatbot — Main Runner
═══════════════════════════════════════════════
Run two AI painting agents negotiating over a shared canvas for N rounds.
Each agent uses its OWN OpenAI API key for separate rate limits.

Usage:
    python main.py                               # 10 rounds (default)
    python main.py --rounds 5                    # 5 rounds
    python main.py --rounds 20 --theme "Fire"    # 20 rounds, custom theme
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Fix Windows console encoding for emoji/unicode output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Fix Windows ANSI color support
try:
    import colorama
    colorama.just_fix_windows_console()
except ImportError:
    pass

from dotenv import load_dotenv

# Load .env BEFORE importing modules that create API clients
load_dotenv()

from config import (
    NUM_ROUNDS,
    THEME,
    AGENT_A_CONFIG,
    AGENT_B_CONFIG,
    CRITIC_CONFIG,
    CANVAS_REGIONS,
)
from agents import PaintingAgent, CriticAgent
from canvas import SharedCanvas
from protocol import AgentMessage, CriticEvaluation


# ══════════════════════════════════════════════
#  ANSI COLORS
# ══════════════════════════════════════════════

CYAN    = "\033[96m"
MAGENTA = "\033[95m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
RED     = "\033[91m"
BLUE    = "\033[94m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"
WHITE   = "\033[97m"


# ══════════════════════════════════════════════
#  PRETTY PRINTERS
# ══════════════════════════════════════════════

def print_header(num_rounds: int, theme: str):
    a_style = f"{AGENT_A_CONFIG['style']} ({AGENT_A_CONFIG['skill_level']})"
    b_style = f"{AGENT_B_CONFIG['style']} ({AGENT_B_CONFIG['skill_level']})"
    print(f"""
{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════╗
║          🎨  COMPUTATIONAL CREATIVITY CHATBOT  🎨           ║
║          Two AI Agents Collaborating on Art                  ║
║          ═══════════════════════════════════                  ║
║          Powered by OpenAI (2 separate API keys)             ║
╠══════════════════════════════════════════════════════════════╣
║  Rounds:  {num_rounds:<49}║
║  Theme:   {theme[:48]:<49}║
║  Agent A: {a_style:<49}║
║  Agent B: {b_style:<49}║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def print_round_header(round_num: int, total: int):
    print(f"""
{WHITE}{BOLD}{'═' * 60}
  ◆  ROUND {round_num} of {total}
{'═' * 60}{RESET}
""")


def print_agent_message(agent_label: str, config: dict, msg: AgentMessage):
    """Pretty-print an agent's structured message."""
    if "A" in agent_label:
        color, icon = CYAN, "🎨"
    else:
        color, icon = MAGENTA, "🎭"

    intent_colors = {
        "propose": GREEN,
        "acknowledge": BLUE,
        "dispute": RED,
        "yield": YELLOW,
    }
    ic = intent_colors.get(msg.intent, WHITE)

    ops_lines = ""
    for op in msg.mark_ops:
        ops_lines += f"    │   • {op}\n"
    if not ops_lines:
        ops_lines = "    │   (none)\n"

    q = msg.open_question if msg.open_question else "(none)"

    print(f"""{color}{BOLD}  {icon} {config['name']} ({config['style']}, {config['skill_level']}){RESET}
    {ic}Intent: [{msg.intent.upper()}]{RESET}
    ┌─────────────────────────────────────────────────────
    │ Theme:    {msg.theme}
    │ Region:   {msg.region}
    │ Style:    {msg.style_note}
    │ Emotion:  {msg.emotion_tag}
    │ Operations:
{ops_lines}    │ Question: {q}
    └─────────────────────────────────────────────────────
""")


def print_critic_evaluation(ev: CriticEvaluation):
    """Pretty-print the critic's scored evaluation."""

    def bar(score: int) -> str:
        return "█" * score + "░" * (10 - score)

    print(f"""{YELLOW}{BOLD}  📋 CRITIC EVALUATION — Round {ev.round}{RESET}
    ┌─────────────────────────────────────────────────────
    │ Compositional Coherence: {bar(ev.compositional_coherence)} {ev.compositional_coherence}/10
    │ Stylistic Dialogue:      {bar(ev.stylistic_dialogue)} {ev.stylistic_dialogue}/10
    │ Thematic Depth:          {bar(ev.thematic_depth)} {ev.thematic_depth}/10
    │ Technical Execution:     {bar(ev.technical_execution)} {ev.technical_execution}/10
    │ ─────────────────────────────────────────────
    │ Average: {ev.average_score:.1f}/10
    │
    │ {CYAN}→ Agent A:{RESET} {ev.directive_agent_a}
    │ {MAGENTA}→ Agent B:{RESET} {ev.directive_agent_b}
    │
    │ {DIM}{ev.overall_commentary}{RESET}
    └─────────────────────────────────────────────────────
""")


def print_mediation(msg: AgentMessage):
    """Print a mediation-round message."""
    color = CYAN if "agent_a" in msg.sender else MAGENTA
    print(f"""    {color}{BOLD}⚡ MEDIATION — {msg.sender}{RESET}
    │ Intent: {msg.intent.upper()}
    │ Style:  {msg.style_note}
    │ Question: {msg.open_question or '(none)'}
""")


def print_final_decision(session_log: dict):
    """Print the final collaborative art decision summary."""
    print(f"""
{GREEN}{BOLD}╔══════════════════════════════════════════════════════════════╗
║           🖼️  FINAL ART PIECE DECISION  🖼️                  ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")

    if not session_log.get("rounds"):
        return

    # Collect the final round's data
    final_round = session_log["rounds"][-1]
    final_exchanges = final_round.get("exchanges", [])
    final_critic = final_round.get("critic", {})

    # Print last Agent A and B messages
    for exchange in final_exchanges:
        agent = exchange.get("agent", "?")
        msg = exchange.get("message", {})
        if exchange.get("type") == "mediation":
            continue  # Skip mediation messages, show final proposals
        if agent == "A":
            color = CYAN
            icon = "🎨"
        else:
            color = MAGENTA
            icon = "🎭"
        print(f"  {color}{BOLD}{icon} Agent {agent}'s Final Contribution:{RESET}")
        print(f"    Theme:    {msg.get('theme', 'N/A')}")
        print(f"    Region:   {msg.get('region', 'N/A')}")
        print(f"    Style:    {msg.get('style_note', 'N/A')}")
        print(f"    Emotion:  {msg.get('emotion_tag', 'N/A')}")
        ops = msg.get("mark_ops", [])
        if ops:
            print(f"    Strokes:")
            for op in ops:
                print(f"      • {op}")
        print()

    # Print final critic verdict
    if final_critic:
        avg = (
            final_critic.get("compositional_coherence", 0) +
            final_critic.get("stylistic_dialogue", 0) +
            final_critic.get("thematic_depth", 0) +
            final_critic.get("technical_execution", 0)
        ) / 4.0
        print(f"  {YELLOW}{BOLD}📋 Final Critic Verdict:{RESET}")
        print(f"    Average Score: {avg:.1f}/10")
        print(f"    Commentary:    {final_critic.get('overall_commentary', 'N/A')}")
        print()

    # Print full canvas region summary
    canvas_data = session_log.get("final_canvas", {})
    regions = canvas_data.get("regions", {})
    if regions:
        print(f"  {WHITE}{BOLD}🗺️  Canvas Region Ownership:{RESET}")
        for name, info in regions.items():
            owner = info.get("owner", "none")
            status = info.get("status", "free")
            print(f"    • {name}: {status} (owner: {owner})")
        print()


def save_transcript(log_dir: str, session_data: dict) -> str:
    """Save the full session to a JSON file in logs/."""
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(log_dir, f"session_{timestamp}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)
    print(f"\n{GREEN}  💾 Transcript saved to: {filepath}{RESET}")
    return filepath


# ══════════════════════════════════════════════
#  MAIN SESSION LOOP
# ══════════════════════════════════════════════

def run_session(num_rounds: int, theme: str):
    """Run a complete N-round painting session between Agent A, Agent B, and the Critic."""

    # ── Verify both OpenAI API keys ──
    key_a = os.environ.get("OPENAI_API_KEY_AGENT_A")
    key_b = os.environ.get("OPENAI_API_KEY_AGENT_B")

    missing = []
    if not key_a:
        missing.append("OPENAI_API_KEY_AGENT_A")
    if not key_b:
        missing.append("OPENAI_API_KEY_AGENT_B")

    if missing:
        print(f"""
{RED}{BOLD}╔══════════════════════════════════════════════════════════════╗
║  ERROR: Missing OpenAI API key(s)!                           ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  Missing: {', '.join(missing)}

  To fix this:
    1. Open the file:  {BOLD}.env{RESET}
    2. Paste your TWO OpenAI API keys:
       OPENAI_API_KEY_AGENT_A=sk-your-first-key
       OPENAI_API_KEY_AGENT_B=sk-your-second-key
    3. Save and run this script again

  Get API keys at: https://platform.openai.com/api-keys
""")
        sys.exit(1)

    print_header(num_rounds, theme)

    print(f"  {DIM}Using OpenAI API Key 1 for Agent A (Impressionist){RESET}")
    print(f"  {DIM}Using OpenAI API Key 2 for Agent B (Cubist) + Critic{RESET}")
    print()

    # ── Initialise agents & canvas ──
    # Agent A uses its OWN OpenAI API key
    agent_a = PaintingAgent("agent_a", AGENT_A_CONFIG, theme, api_key=key_a)

    # Agent B uses a SEPARATE OpenAI API key
    agent_b = PaintingAgent("agent_b", AGENT_B_CONFIG, theme, api_key=key_b)

    # Critic uses Agent B's key (to balance rate limits across the two keys)
    critic  = CriticAgent(CRITIC_CONFIG, api_key=key_b)

    canvas  = SharedCanvas(CANVAS_REGIONS)

    # ── Session log ──
    session_log = {
        "theme": theme,
        "num_rounds": num_rounds,
        "model": __import__("config").MODEL_NAME,
        "agent_a_config": AGENT_A_CONFIG,
        "agent_b_config": AGENT_B_CONFIG,
        "started_at": datetime.now().isoformat(),
        "rounds": [],
    }

    last_critic_feedback: CriticEvaluation | None = None

    # ══════════════════════════════════════
    #  ROUND LOOP
    # ══════════════════════════════════════

    for round_num in range(1, num_rounds + 1):
        print_round_header(round_num, num_rounds)
        round_log: dict = {"round": round_num, "exchanges": []}

        # ── Step 1: Agent A proposes ──────────────────────
        print(f"  {DIM}Agent A is composing a proposal...{RESET}", flush=True)
        msg_a = agent_a.generate_message(
            canvas_state=canvas.get_state_summary(),
            partner_message=None,
            critic_feedback=last_critic_feedback,
            round_num=round_num,
            is_proposer=True,
        )
        print_agent_message("A", AGENT_A_CONFIG, msg_a)
        round_log["exchanges"].append({"agent": "A", "message": msg_a.to_dict()})

        # ── Step 2: Agent B responds ──────────────────────
        print(f"  {DIM}Agent B is considering the proposal...{RESET}", flush=True)
        msg_b = agent_b.generate_message(
            canvas_state=canvas.get_state_summary(),
            partner_message=msg_a,
            critic_feedback=last_critic_feedback,
            round_num=round_num,
            is_proposer=False,
        )
        print_agent_message("B", AGENT_B_CONFIG, msg_b)
        round_log["exchanges"].append({"agent": "B", "message": msg_b.to_dict()})

        # ── Step 3: Handle disputes (mediation) ──────────
        if msg_b.intent == "dispute":
            print(f"  {RED}{BOLD}  ⚡ DISPUTE DETECTED — Entering mediation...{RESET}\n")

            for _mediation_turn in range(2):
                # Agent A responds to the dispute
                print(f"  {DIM}Agent A mediating...{RESET}", flush=True)
                med_a = agent_a.generate_message(
                    canvas_state=canvas.get_state_summary(),
                    partner_message=msg_b,
                    critic_feedback=last_critic_feedback,
                    round_num=round_num,
                    is_proposer=True,
                )
                print_mediation(med_a)
                round_log["exchanges"].append({
                    "agent": "A", "type": "mediation", "message": med_a.to_dict()
                })

                # Agent B responds
                print(f"  {DIM}Agent B mediating...{RESET}", flush=True)
                med_b = agent_b.generate_message(
                    canvas_state=canvas.get_state_summary(),
                    partner_message=med_a,
                    critic_feedback=last_critic_feedback,
                    round_num=round_num,
                    is_proposer=False,
                )
                print_mediation(med_b)
                round_log["exchanges"].append({
                    "agent": "B", "type": "mediation", "message": med_b.to_dict()
                })

                # Update final messages for canvas application
                msg_a = med_a
                msg_b = med_b

                if med_b.intent in ("acknowledge", "yield"):
                    print(f"  {GREEN}  ✓ Mediation resolved!{RESET}\n")
                    break
            else:
                print(f"  {YELLOW}  ⚠ Mediation limit reached — proceeding with last proposals.{RESET}\n")

        # ── Step 4: Apply operations to canvas ───────────
        canvas.apply_operations(msg_a)
        canvas.apply_operations(msg_b)

        # ── Step 5: Critic evaluates ─────────────────────
        print(f"  {DIM}Critic is evaluating the canvas...{RESET}", flush=True)
        critic_feedback = critic.evaluate(
            canvas_state=canvas.get_state_summary(),
            round_num=round_num,
            agent_a_message=msg_a,
            agent_b_message=msg_b,
        )
        print_critic_evaluation(critic_feedback)
        last_critic_feedback = critic_feedback
        round_log["critic"] = critic_feedback.to_dict()

        session_log["rounds"].append(round_log)

    # ══════════════════════════════════════
    #  SESSION COMPLETE
    # ══════════════════════════════════════

    session_log["finished_at"] = datetime.now().isoformat()
    session_log["final_canvas"] = canvas.get_full_log()

    print(f"""
{GREEN}{BOLD}╔══════════════════════════════════════════════════════════════╗
║               ✅  SESSION COMPLETE!                          ║
║               {num_rounds} round(s) of collaborative painting{' ' * max(0, 16 - len(str(num_rounds)))}          ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")

    # Score progression
    if critic.evaluation_history:
        print(f"{BOLD}  📊 SCORE PROGRESSION:{RESET}")
        for ev in critic.evaluation_history:
            avg = ev.average_score
            bar_len = int(avg * 3)
            bar_char = "█" * bar_len + "░" * (30 - bar_len)
            print(f"    Round {ev.round:2d}: {bar_char} {avg:.1f}/10")
        print()

    # Print final decision summary
    print_final_decision(session_log)

    # Save transcript
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    save_transcript(log_dir, session_log)

    return session_log


# ══════════════════════════════════════════════
#  CLI ENTRY POINT
# ══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Computational Creativity: Two AI Agents Collaborating on Art",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    # 10 rounds, default theme
  python main.py --rounds 5                         # 5 rounds
  python main.py -n 3 --theme "A burning forest"    # 3 rounds, custom theme
        """,
    )
    parser.add_argument(
        "--rounds", "-n",
        type=int,
        default=NUM_ROUNDS,
        help=f"Number of painting rounds (default: {NUM_ROUNDS})",
    )
    parser.add_argument(
        "--theme", "-t",
        type=str,
        default=THEME,
        help=f'Artwork theme (default: "{THEME}")',
    )
    args = parser.parse_args()

    run_session(args.rounds, args.theme)


if __name__ == "__main__":
    main()
