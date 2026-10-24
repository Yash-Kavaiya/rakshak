"""CLI demo: `python -m rakshak.demo data/calls/digital_arrest_hi.wav [--realtime] [--play]`.

Prints a live timeline of the call and a red warning box the moment Rakshak
decides it is a scam.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading

from dotenv import load_dotenv

load_dotenv(override=True)

from rakshak.monitor import CallMonitor  # noqa: E402
from rakshak.tools import RED_FLAGS  # noqa: E402

RED, GREEN, YELLOW, BOLD, RESET = (
    "\033[91m",
    "\033[92m",
    "\033[93m",
    "\033[1m",
    "\033[0m",
)
COLOR = {"safe": GREEN, "suspicious": YELLOW, "scam": RED}


def _play(path: str) -> None:
    try:
        import winsound

        threading.Thread(
            target=winsound.PlaySound, args=(path, winsound.SND_FILENAME), daemon=True
        ).start()
    except ImportError:
        print("(audio playback only supported on Windows; continuing silently)")


def render_alert(event: dict) -> str:
    a = event["alert"]
    flags = "\n".join(f"   • {f}: {RED_FLAGS.get(f, '')}" for f in a["red_flags"])
    return (
        f"\n{RED}{BOLD}{'!' * 64}\n"
        f"  ⚠  SCAM ALERT at {event['end']:.0f}s — {a['scam_type'].replace('_', ' ').upper()}"
        f"  (confidence {float(a['confidence']):.0%})\n{RESET}{RED}"
        f"  हिंदी:   {a['warning_hindi']}\n"
        f"  ગુજરાતી: {a['warning_gujarati']}\n"
        f"  Heard:  {a['evidence']}\n"
        f"  Red flags:\n{flags}\n"
        f"{BOLD}{'!' * 64}{RESET}\n"
    )


async def run(path: str, realtime: bool, play: bool, chunk_seconds: float) -> dict:
    if play:
        _play(path)
    print(f"{BOLD}Rakshak listening to {path}{RESET}", flush=True)
    done = {}
    async for ev in CallMonitor().stream(
        path, realtime=realtime or play, chunk_seconds=chunk_seconds
    ):
        if ev["type"] == "chunk":
            c = COLOR.get(ev["risk_level"], "")
            print(
                f"[{ev['start']:5.1f}-{ev['end']:5.1f}s] {c}{ev['risk_level']:<10}{RESET} {ev['heard']}",
                flush=True,
            )
        elif ev["type"] == "alert":
            print(render_alert(ev), flush=True)
        else:
            done = ev
            verdict = (
                f"{RED}SCAM" if ev["verdict"] == "scam" else f"{GREEN}SAFE — no alert"
            )
            when = (
                f" (first alert at {ev['first_alert_at']:.0f}s of {ev['duration']:.0f}s)"
                if ev["first_alert_at"]
                else ""
            )
            print(f"\n{BOLD}Verdict: {verdict}{RESET}{when}", flush=True)
    return done


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wav")
    p.add_argument(
        "--realtime", action="store_true", help="pace chunks like a live call"
    )
    p.add_argument(
        "--play", action="store_true", help="play the call audio (implies --realtime)"
    )
    p.add_argument("--chunk", type=float, default=5.0, help="chunk length in seconds")
    args = p.parse_args()
    asyncio.run(run(args.wav, args.realtime, args.play, args.chunk))


if __name__ == "__main__":
    main()
