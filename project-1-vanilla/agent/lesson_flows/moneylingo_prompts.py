"""MoneyLingo v1 — prompts authored from the PDF (runtime does not parse the PDF)."""

# Master sequence from MoneyLingoLessonTemplate-v1.pdf (section 1 — Master Template).
# The live lesson follows the **code-defined** 8-step skeleton in ``moneylingo_outline.py``;
# these rules tell the model what to write inside each step.
MONEYLINGO_V1_BLOCK_RULES = """
## MoneyLingo v1 — what each step must contain (fixed app skeleton)

The application has already fixed **step order and types** (8 steps). Your job is to **fill content** for the student topic and profile. Do not add or remove steps.

**Section breaks in markdown (`content` and similar fields):** never use a line that is only `---`, `***`, or `___` (yields dull horizontal rules). Use `###` subheadings, bold callouts, blank lines, or a plain line of `·` / `━` (not `---`).

1. **Hook** (`intro`) — 2–4 short lines, real-life scenario, curiosity, tension or question. **Do not** define the core financial term yet.
2. **Context video** (`video`) — One repository video from `get_videos` (copy ids/urls/embed_url exactly). Short watch prompt.
3. **Core lesson** (`content`) — One-sentence definition, then **3–5** bullets in plain language on how it works in real life.
4. **Aha moment** (`content`) — **Real numbers**: amounts, time frame, **two** contrasting scenarios, **monthly payment**, **total paid**, **exact dollar difference**, strong punchline.
5. **Word wallet** (`content`) — **3–5** terms; each: brief definition plus a line starting with **Here's how it works:** and real-life impact.
6. **Quiz** (`quiz`) — Exactly **5** multiple-choice questions, options **A–D**, one correct each, in `assessment`.
7. **Simulation** (`game`) — Pick one game from `get_games` (copy embed_path etc. exactly). If nothing fits, use `challenge` with a 2–3 choice scenario and consequences (coordinate with step type in JSON).
8. **IRL** (`content`) — Exactly **three** actionable bullets or numbered items. Each item: short description, link when relevant, and end with the exact phrase: **Go now | Save this in my Financial Moves**. For breaks between parts, use the same visual separation rules as above (no `---` / `***` / `___` lines).

If step 7 must be `challenge` instead of `game`, keep the same pedagogical intent (simulation / choices).
"""


MONEYLINGO_V1_SYSTEM_ADDENDUM = """
## MoneyLingo v1 (code-defined flow)
This lesson uses the **MoneyLingo v1** format. The step sequence is **fixed by the application** (not read from a PDF at runtime). Follow the block rules below when expanding each step.

""" + MONEYLINGO_V1_BLOCK_RULES + """

### Tools and media
- Call `get_videos`, `get_games`, `search_educational_content`, and `fetch_jumpstart_topic` during the tool phase before final lesson JSON.
- **Videos / games:** Use repository tools first; copy tool fields exactly into lesson JSON per global schema rules.
- Output **one** final lesson object matching the global FinCoach JSON schema.
"""


def moneylingo_v1_initial_user_text(
    *,
    topic: str,
    student_name: str,
    age_s: str,
    audience_level: str,
    proficiency: str,
) -> str:
    return f"""You are building a **MoneyLingo v1** lesson (fixed 8-step structure in code).

**Student:** {student_name or "Anonymous"}, age {age_s}
**Band:** {audience_level.replace("_", " ")}, **proficiency:** {proficiency}
**Topic:** {topic!r}

**Phase 1 — tools:** Fetch JumpStart context, articles, videos, and games for this topic and profile. Use generous `max_results` where applicable.

**Phase 2 — after tools:** The app will supply a fixed outline matching MoneyLingo v1; you will expand each step with full content following the MoneyLingo block rules in your system instructions.

Begin with tool calls now."""
