"""ADK evals (AgentEvaluator) over the transcript and audio evalsets. Needs credentials.

Equivalent CLI: adk eval rakshak rakshak/evals/transcript/scam/scam_calls_transcript.test.json \
    --config_file_path rakshak/evals/transcript/scam/test_config.json
"""

from pathlib import Path

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "rakshak" / "evals"

pytestmark = pytest.mark.live

SETS = [
    d
    for d in (
        EVALS / "transcript" / "scam",
        EVALS / "transcript" / "genuine",
        EVALS / "audio" / "scam",
        EVALS / "audio" / "genuine",
    )
    if any(d.glob("*.test.json"))
]


@pytest.mark.parametrize("eval_dir", SETS, ids=lambda d: f"{d.parent.name}-{d.name}")
async def test_adk_evalset(eval_dir):
    await AgentEvaluator.evaluate(
        agent_module="rakshak",
        eval_dataset_file_path_or_dir=str(eval_dir),
        num_runs=1,
    )
