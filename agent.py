"""Core agent logic, reusable by both the CLI and the desktop GUI."""
from __future__ import annotations

import json
from os import getenv
from typing import Callable, Optional

from dotenv import load_dotenv
from openai import OpenAI

from tools import tools, process_tool_usage

load_dotenv()

StatusCallback = Optional[Callable[[str], None]]


def _client() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=getenv("OPENROUTER_API_KEY"),
    )


def run_certification_agent(cert_name: str, on_status: StatusCallback = None) -> str:
    """Run the prep-agent for `cert_name` and return a markdown answer.

    `on_status` is an optional callback invoked with short human-readable
    progress messages (useful to update a GUI status bar).
    """
    def _say(msg: str) -> None:
        if on_status:
            on_status(msg)

    if not getenv("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "Missing OPENROUTER_API_KEY. Open Settings to add your API key."
        )

    model_id = getenv("MODEL_ID")
    if not model_id:
        raise RuntimeError("Missing MODEL_ID environment variable.")

    client = _client()

    inputs = [
        {
            "role": "system",
            "content": (
                "You help the user prepare for a Microsoft certification exam. "
                "You MUST call search_microsoft_learn to get official learning paths "
                "and documentation, AND call search_youtube_videos to find relevant "
                "video tutorials. You may use get_youtube_transcript to verify that a "
                "video is actually about the certification before recommending it. "
                "Only recommend resources that are clearly relevant."
            ),
        },
        {"role": "user", "content": cert_name},
    ]

    _say("Asking the assistant to plan your study resources...")

    step = 0
    while True:
        step += 1
        response = client.responses.create(
            model=model_id,
            tools=tools,
            input=inputs,
        )

        tool_calls = [item for item in response.output if item.type == "function_call"]
        if not tool_calls:
            break

        names = ", ".join(sorted({c.name for c in tool_calls}))
        _say(f"Step {step}: gathering resources ({names})...")

        for item in tool_calls:
            inputs.append(item)
        process_tool_usage(response, inputs)

    _say("Formatting the final answer...")

    collected = [
        {"call_id": item["call_id"], "output": item["output"]}
        for item in inputs
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]

    response = client.responses.create(
        model=model_id,
        instructions=(
            "Output a clean markdown answer for the user with three sections: "
            "'## Learning Paths', '## Documentation', and '## YouTube Videos'. "
            "For Learning Paths and Documentation, list title + URL. "
            "For YouTube Videos, list title, channel, duration and URL. "
            "Only include items directly relevant to the certification."
        ),
        input=[
            {
                "role": "user",
                "content": (
                    f"Certification: {cert_name}\n\n"
                    f"Tool results (JSON):\n{json.dumps(collected)}"
                ),
            }
        ],
    )

    return response.output_text
