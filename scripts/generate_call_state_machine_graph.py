from __future__ import annotations

from pathlib import Path
import sys

from transitions.extensions import GraphMachine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.detection.call_state_machine import STATES


TRANSITIONS = [
    ("start_call", "IDLE", "DIALING"),
    ("ringing_detected", "DIALING", "RINGING"),
    ("answer_detected", "RINGING", "ANSWER_DETECTED"),
    ("begin_analysis", "ANSWER_DETECTED", "EARLY_ANALYSIS"),
    ("human_candidate", "EARLY_ANALYSIS", "HUMAN_CANDIDATE"),
    ("voicemail_candidate", "EARLY_ANALYSIS", "VOICEMAIL_CANDIDATE"),
    ("ivr_candidate", "EARLY_ANALYSIS", "IVR_CANDIDATE"),
    ("confirm_human", "HUMAN_CANDIDATE", "HUMAN"),
    ("confirm_voicemail", "VOICEMAIL_CANDIDATE", "VOICEMAIL"),
    ("confirm_ivr", "IVR_CANDIDATE", "IVR"),
    ("busy_detected", "RINGING", "BUSY"),
    ("ring_timeout", "RINGING", "NO_ANSWER"),
    ("operator_hangup", "ANY NON-FINAL", "ENDED"),
]


def main() -> None:
    docs = Path("docs")
    docs.mkdir(exist_ok=True)
    write_markdown(docs / "call_state_machine.md")
    write_png(docs / "call_state_machine.png")


def write_markdown(path: Path) -> None:
    lines = [
        "# Call State Machine",
        "",
        "The live call detector centralizes state decisions in `src/detection/call_state_machine.py`.",
        "Evidence modules score DOM, audio, transcript, and timing signals; only `CallStateMachine` transitions state.",
        "",
        "## States",
        "",
        *[f"- `{state}`" for state in STATES],
        "",
        "## Transitions",
        "",
        "| Trigger | From | To |",
        "|---|---|---|",
        *[f"| `{trigger}` | `{source}` | `{dest}` |" for trigger, source, dest in TRANSITIONS],
        "",
        "## Fusion Weights",
        "",
        "- DOM evidence: 40%",
        "- Audio evidence: 20%",
        "- Speech content: 30%",
        "- Timing patterns: 10%",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_png(path: Path) -> None:
    graph_transitions = [
        {"trigger": trigger, "source": source, "dest": dest}
        for trigger, source, dest in TRANSITIONS
        if source != "ANY NON-FINAL"
    ]
    try:
        machine = GraphMachine(
            states=STATES,
            transitions=graph_transitions,
            initial="IDLE",
            auto_transitions=False,
            show_conditions=True,
        )
        graph = machine.get_graph()
        graph.draw(str(path), prog="dot")
        return
    except Exception:
        write_fallback_png(path)


def write_fallback_png(path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1500, 950
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    positions = {
        "IDLE": (80, 80),
        "DIALING": (280, 80),
        "RINGING": (500, 80),
        "ANSWER_DETECTED": (730, 80),
        "EARLY_ANALYSIS": (1010, 80),
        "HUMAN_CANDIDATE": (860, 290),
        "VOICEMAIL_CANDIDATE": (860, 430),
        "IVR_CANDIDATE": (860, 570),
        "HUMAN": (1180, 290),
        "VOICEMAIL": (1180, 430),
        "IVR": (1180, 570),
        "BUSY": (500, 270),
        "NO_ANSWER": (500, 430),
        "FAILED": (260, 680),
        "ENDED": (500, 680),
    }

    def box(state: str) -> None:
        x, y = positions[state]
        color = "#e2f3e8" if state in {"HUMAN", "VOICEMAIL", "IVR", "BUSY", "NO_ANSWER", "ENDED"} else "#eef2ff"
        draw.rounded_rectangle((x, y, x + 180, y + 56), radius=8, fill=color, outline="#334155", width=2)
        draw.text((x + 14, y + 20), state, fill="#0f172a", font=font)

    def arrow(source: str, dest: str, label: str) -> None:
        sx, sy = positions[source]
        dx, dy = positions[dest]
        start = (sx + 180, sy + 28)
        end = (dx, dy + 28)
        if dx < sx:
            start = (sx + 90, sy + 56)
            end = (dx + 90, dy)
        draw.line((start, end), fill="#475569", width=2)
        draw.ellipse((end[0] - 4, end[1] - 4, end[0] + 4, end[1] + 4), fill="#475569")
        lx = (start[0] + end[0]) // 2
        ly = (start[1] + end[1]) // 2
        draw.text((lx + 4, ly - 12), label, fill="#334155", font=font)

    for state in STATES:
        box(state)
    for trigger, source, dest in TRANSITIONS:
        if source in positions and dest in positions:
            arrow(source, dest, trigger)
    image.save(path)


if __name__ == "__main__":
    main()
