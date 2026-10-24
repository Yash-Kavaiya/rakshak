"""Build ADK evalsets from the call scripts (and the rendered call audio).

One user turn per spoken line, in the same `[CALL CHUNK n | t0s-t1s]` format the
live monitor uses. Expected tool trajectory per turn:
  - before the scam is evident  -> log_call_status
  - the line where it is evident -> raise_scam_alert (scripts' `alert_line`)
  - afterwards                   -> log_call_status
Genuine calls expect log_call_status on every turn (never an alert).

Outputs (each directory has its own test_config.json):
  rakshak/evals/transcript/{scam,genuine}/   text transcripts, committed
  rakshak/evals/audio/{scam,genuine}/        real audio per line, generated from data/calls
  tests/eval/datasets/rakshak-dataset.json   agents-cli dataset ("call so far" in
                                              one merged turn -> expected decision)
Run: python scripts/build_evalsets.py
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rakshak.audio import SAMPLE_RATE, load_wav, to_wav_bytes  # noqa: E402

SCRIPTS = ROOT / "data" / "scripts"
CALLS = ROOT / "data" / "calls"
EVALS = ROOT / "rakshak" / "evals"

JUDGE = {"judge_model": "gemini-3.8-flash", "num_samples": 1}

SCAM_CONFIG = {
    "criteria": {
        "tool_trajectory_avg_score": {"threshold": 0.75, "match_type": "EXACT", "ignore_args": True},
        "rubric_based_tool_use_quality_v1": {
            "threshold": 0.7,
            "judge_model_options": JUDGE,
            "rubrics": [
                {
                    "rubric_id": "hindi_warning",
                    "rubric_content": {
                        "text_property": "Whenever raise_scam_alert is called, its warning_hindi argument is in Hindi (Devanagari script), at most two short simple sentences, and says why the call is fake or what to do (for example hang up). If raise_scam_alert is not called in this turn, this rubric is satisfied."
                    },
                },
                {
                    "rubric_id": "gujarati_warning",
                    "rubric_content": {
                        "text_property": "Whenever raise_scam_alert is called, its warning_gujarati argument is in Gujarati script and is simple and short. If raise_scam_alert is not called in this turn, this rubric is satisfied."
                    },
                },
                {
                    "rubric_id": "names_red_flags",
                    "rubric_content": {
                        "text_property": "Whenever raise_scam_alert is called, its red_flags argument includes authority_impersonation when the caller has claimed to be police, CBI, a bank, customs or courier official. If raise_scam_alert is not called in this turn, this rubric is satisfied."
                    },
                },
            ],
        },
    }
}

GENUINE_CONFIG = {
    "criteria": {
        "tool_trajectory_avg_score": {"threshold": 1.0, "match_type": "EXACT", "ignore_args": True},
    }
}


def load_scripts() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SCRIPTS.glob("*.json"))]


def line_timing(script: dict) -> list[dict]:
    timing_file = CALLS / f"{script['id']}.timing.json"
    if timing_file.exists():
        return json.loads(timing_file.read_text(encoding="utf-8"))
    # No audio yet: assume ~6s per line so headers still look like a call.
    return [
        {"line": i, "start": i * 6.0, "end": i * 6.0 + 5.5} for i in range(len(script["lines"]))
    ]


def expected_tool(script: dict, line: int) -> str:
    return "raise_scam_alert" if script["alert_line"] == line else "log_call_status"


def build_case(script: dict, audio: bool) -> dict:
    timing = line_timing(script)
    pcm = load_wav(CALLS / f"{script['id']}.wav") if audio else None
    conversation = []
    for t, (speaker, text) in zip(timing, script["lines"], strict=True):
        header = f"[CALL CHUNK {t['line'] + 1} | {t['start']:.1f}s-{t['end']:.1f}s]"
        if audio:
            clip = pcm[int(t["start"] * SAMPLE_RATE) : int(t["end"] * SAMPLE_RATE)]
            parts = [
                {"text": header},
                {
                    "inline_data": {
                        "mime_type": "audio/wav",
                        "data": base64.b64encode(to_wav_bytes(clip)).decode(),
                    }
                },
            ]
        else:
            parts = [{"text": f"{header}\nTRANSCRIPT: {speaker}: {text}"}]
        conversation.append(
            {
                "invocation_id": f"{script['id']}-{t['line']}",
                "user_content": {"role": "user", "parts": parts},
                "intermediate_data": {
                    "tool_uses": [{"name": expected_tool(script, t["line"]), "args": {}}],
                },
            }
        )
    return {
        "eval_id": script["id"],
        "conversation": conversation,
        "session_input": {"app_name": "rakshak", "user_id": "listener", "state": {}},
    }


def write_set(directory: Path, set_id: str, cases: list[dict], config: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{set_id}.test.json"
    eval_set = {"eval_set_id": set_id, "name": set_id, "eval_cases": cases}
    path.write_text(json.dumps(eval_set, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (directory / "test_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def agents_cli_case(script: dict, upto: int, expect: str) -> dict:
    timing = line_timing(script)
    transcript = " ".join(f"{who}: {text}" for who, text in script["lines"][: upto + 1])
    header = f"[CALL CHUNK 1 | {timing[0]['start']:.1f}s-{timing[upto]['end']:.1f}s]"
    return {
        "eval_case_id": f"{script['id']}__upto_line_{upto}",
        "prompt": {"role": "user", "parts": [{"text": f"{header}\nTRANSCRIPT: {transcript}"}]},
        "reference": {"response": {"role": "model", "parts": [{"text": f"EXPECT: {expect}"}]}},
    }


def build_agents_cli_dataset(scripts: list[dict]) -> Path:
    cases = []
    for s in scripts:
        if s["label"] == "scam":
            cases.append(agents_cli_case(s, 0, "log_call_status"))  # greeting only: no alarm yet
            cases.append(agents_cli_case(s, s["alert_line"] + 1, "raise_scam_alert"))
        else:
            cases.append(agents_cli_case(s, len(s["lines"]) - 1, "log_call_status"))
    out = ROOT / "tests" / "eval" / "datasets" / "rakshak-dataset.json"
    out.write_text(json.dumps({"eval_cases": cases}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    scripts = load_scripts()
    for mode in ("transcript", "audio"):
        audio = mode == "audio"
        usable = [s for s in scripts if not audio or (CALLS / f"{s['id']}.timing.json").exists()]
        for label, config in (("scam", SCAM_CONFIG), ("genuine", GENUINE_CONFIG)):
            cases = [build_case(s, audio) for s in usable if s["label"] == label]
            if cases:
                out = write_set(EVALS / mode / label, f"{label}_calls_{mode}", cases, config)
                print(f"{out.relative_to(ROOT)}: {len(cases)} cases")
    out = build_agents_cli_dataset(scripts)
    print(f"{out.relative_to(ROOT)}: agents-cli dataset")


if __name__ == "__main__":
    main()
