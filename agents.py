"""
Agent Classes
═════════════
PaintingAgent  — wraps an LLM with a creative persona (used for Agent A & B).
CriticAgent    — evaluates the canvas after each round.

Each agent uses its OWN OpenAI API key so the two sides have separate rate limits.
"""

import time
from openai import OpenAI, APIError, RateLimitError, AuthenticationError

from config import MODEL_NAME
from protocol import (
    AgentMessage,
    CriticEvaluation,
    parse_agent_response,
    parse_critic_response,
)


# Maximum retries on transient API errors
MAX_RETRIES = 3


def _call_openai(client: OpenAI, messages: list[dict], temperature: float = 0.9, max_tokens: int = 800) -> str:
    """Call OpenAI with retries on transient errors."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except AuthenticationError:
            print(f"\n    ❌ AUTHENTICATION FAILED: Your OpenAI API key is invalid.")
            print(f"       Get a valid key at: https://platform.openai.com/api-keys")
            raise
        except RateLimitError:
            wait = 2 ** (attempt + 1)
            print(f"    ⏳ Rate limited — waiting {wait}s...")
            time.sleep(wait)
        except APIError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"    ⚠ API error ({e}), retrying...")
                time.sleep(1)
            else:
                raise
    raise RuntimeError("Max retries exceeded")


# ══════════════════════════════════════════════
#  PAINTING AGENT  (Agent A / Agent B)
# ══════════════════════════════════════════════

class PaintingAgent:
    """
    A creative painting agent with a distinct persona.
    Each call to generate_message() produces a structured JSON message
    following the protocol from Section 4.2 of the paper.
    """

    def __init__(self, agent_id: str, config: dict, theme: str, api_key: str):
        self.agent_id = agent_id
        self.config = config
        self.client = OpenAI(api_key=api_key)
        self.theme = theme
        self.conversation_history: list[dict] = []
        self.system_prompt = self._build_system_prompt()

    # ──────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        c = self.config
        p = c["personality"]

        return f"""You are {c['name']}, a creative painting agent collaborating on a shared virtual canvas with another AI artist.

YOUR PERSONA
━━━━━━━━━━━━
• Artistic Style: {c['style']}
• Skill Level:    {c['skill_level']}
• Boldness:       {p['boldness']:.0%}  (willingness to make strong creative choices)
• Deference:      {p['deference']:.0%}  (tendency to accommodate partner's proposals)
• Whimsy:         {p['whimsy']:.0%}  (propensity for unexpected creative choices)

{c['description']}

THE ARTWORK THEME
━━━━━━━━━━━━━━━━━
"{self.theme}"

COMMUNICATION PROTOCOL
━━━━━━━━━━━━━━━━━━━━━━
You MUST respond with ONLY a valid JSON object — nothing else.
The JSON must have these fields:

{{
  "sender": "{self.agent_id}",
  "round": <current round number>,
  "intent": "propose" | "acknowledge" | "dispute" | "yield",
  "theme": "<your thematic direction for this turn>",
  "region": "<canvas zone: top-left | top-right | center | bottom-left | bottom-right>",
  "style_note": "<HOW you will paint — specific to your style>",
  "mark_ops": ["<2-4 vivid, specific painting operations>"],
  "open_question": "<a creative question for your partner, or null>",
  "emotion_tag": "<dominant emotion: wonder, tension, serenity, melancholy, joy, chaos, etc.>"
}}

INTENT RULES
• "propose"     — You propose what to paint this round (used when you go first).
• "acknowledge" — You accept your partner's proposal and add your complementary contribution.
• "dispute"     — You disagree with part of the proposal. Explain why and suggest an alternative.
• "yield"       — You defer to your partner's vision for this round.

CREATIVE RULES
1. ONLY output valid JSON. No extra text.
2. mark_ops must be vivid and specific (e.g. "sweeping arc of cadmium yellow across the horizon").
3. Stay true to your style ({c['style']}) in all operations.
4. Engage with your partner's work — reference what they've done and build on it.
5. Your open_question should push the creative dialogue forward.
6. Each round, develop the theme further — don't repeat yourself."""

    # ──────────────────────────────────────────

    def generate_message(
        self,
        canvas_state: str,
        partner_message: AgentMessage | None,
        critic_feedback: CriticEvaluation | None,
        round_num: int,
        is_proposer: bool = True,
    ) -> AgentMessage:
        """Generate a structured message for the current round."""

        # ── Build the user prompt ──
        parts = [f"ROUND {round_num}", "", canvas_state, ""]

        if critic_feedback:
            directive = (
                critic_feedback.directive_agent_a
                if "A" in self.config["name"]
                else critic_feedback.directive_agent_b
            )
            parts.append(
                f"CRITIC FEEDBACK FROM LAST ROUND:\n"
                f"  Compositional Coherence: {critic_feedback.compositional_coherence}/10\n"
                f"  Stylistic Dialogue:      {critic_feedback.stylistic_dialogue}/10\n"
                f"  Thematic Depth:          {critic_feedback.thematic_depth}/10\n"
                f"  Technical Execution:     {critic_feedback.technical_execution}/10\n"
                f"  Directive for you: {directive}\n"
            )

        if partner_message:
            parts.append(
                f"YOUR PARTNER'S MESSAGE:\n{partner_message.to_json()}\n\n"
                f"Respond to your partner's proposal. Choose: acknowledge, dispute, or yield."
            )
        else:
            parts.append(
                f"You go first this round. PROPOSE your contribution for Round {round_num}.\n"
                f"Pick a canvas region and describe your painting operations."
            )

        user_content = "\n".join(parts)

        # ── Manage conversation history (rolling window of 20) ──
        self.conversation_history.append({"role": "user", "content": user_content})

        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.conversation_history[-20:],
        ]

        # ── Call OpenAI LLM ──
        raw = _call_openai(self.client, messages, temperature=0.9, max_tokens=800)

        self.conversation_history.append({"role": "assistant", "content": raw})

        return parse_agent_response(raw, self.agent_id, round_num)


# ══════════════════════════════════════════════
#  CRITIC AGENT  (Agent C)
# ══════════════════════════════════════════════

class CriticAgent:
    """
    Evaluative agent that scores the canvas after each painting round
    across four dimensions (Section 3.4) and gives directives to both agents.
    """

    def __init__(self, config: dict, api_key: str):
        self.config = config
        self.client = OpenAI(api_key=api_key)
        self.evaluation_history: list[CriticEvaluation] = []

        self.system_prompt = """You are the Critic Agent in a collaborative AI art system. You do NOT paint.

YOUR ROLE
━━━━━━━━━
After each painting round you evaluate the canvas and give structured feedback
to both painting agents. Your goal is to push them toward more cohesive,
expressive, and technically excellent collaborative artwork.

You MUST respond with ONLY a valid JSON object:

{
  "round": <current round number>,
  "compositional_coherence": <0-10>,
  "stylistic_dialogue":      <0-10>,
  "thematic_depth":          <0-10>,
  "technical_execution":     <0-10>,
  "directive_agent_a": "<specific, actionable suggestion for Agent A>",
  "directive_agent_b": "<specific, actionable suggestion for Agent B>",
  "overall_commentary": "<2-3 sentences about the artwork's development>"
}

SCORING DIMENSIONS
• Compositional Coherence — Does the work cohere as a unified composition?
• Stylistic Dialogue      — Is there productive stylistic interaction between agents?
• Thematic Depth          — Does the piece communicate a discernible theme or emotion?
• Technical Execution     — Are mark-making choices faithful to declared styles?

GUIDELINES
1. Be specific — reference actual operations, regions, and emotions.
2. Scores should start moderate (4-6) early and reflect genuine progress.
3. Don't inflate scores. Be honest about disconnects.
4. Track whether agents incorporate your previous feedback.
5. ONLY output JSON. No extra text."""

    # ──────────────────────────────────────────

    def evaluate(
        self,
        canvas_state: str,
        round_num: int,
        agent_a_message: AgentMessage,
        agent_b_message: AgentMessage,
    ) -> CriticEvaluation:
        """Evaluate the canvas after a painting round."""

        parts = [
            f"ROUND {round_num} — EVALUATE THE CANVAS",
            "",
            canvas_state,
            "",
            f"AGENT A'S CONTRIBUTION THIS ROUND:\n{agent_a_message.to_json()}",
            "",
            f"AGENT B'S CONTRIBUTION THIS ROUND:\n{agent_b_message.to_json()}",
        ]

        # Include previous evaluation for continuity
        if self.evaluation_history:
            prev = self.evaluation_history[-1]
            parts.append(
                f"\nYOUR PREVIOUS EVALUATION (Round {prev.round}):\n"
                f"  Coherence: {prev.compositional_coherence}/10 | "
                f"Dialogue: {prev.stylistic_dialogue}/10 | "
                f"Depth: {prev.thematic_depth}/10 | "
                f"Execution: {prev.technical_execution}/10\n"
                f"  Commentary: {prev.overall_commentary}\n"
                f"\nDid the agents incorporate your feedback? Adjust scores accordingly."
            )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": "\n".join(parts)},
        ]

        raw = _call_openai(self.client, messages, temperature=0.7, max_tokens=600)

        evaluation = parse_critic_response(raw, round_num)
        self.evaluation_history.append(evaluation)
        return evaluation
