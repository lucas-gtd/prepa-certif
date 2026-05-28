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
        base_url="https://models.github.ai/inference",
        api_key=getenv("GITHUB_TOKEN"),
    )


def run_certification_agent(cert_name: str, on_status: StatusCallback = None) -> str:
    """Run the prep-agent for `cert_name` and return a markdown answer.

    `on_status` is an optional callback invoked with short human-readable
    progress messages (useful to update a GUI status bar).
    """
    def _say(msg: str) -> None:
        if on_status:
            on_status(msg)

    if not getenv("GITHUB_TOKEN"):
        raise RuntimeError(
            "Missing GITHUB_TOKEN. Open Settings to add your GitHub token."
        )

    model_id = getenv("MODEL_ID")
    if not model_id:
        raise RuntimeError("Missing MODEL_ID environment variable.")

    client = _client()

    messages: list = [
        {
            "role": "system",
            "content": (
                "You help the user prepare for a Microsoft certification exam. "
                "You MUST call search_microsoft_learn to get official learning paths "
                "and documentation, AND call search_youtube_videos to find relevant "
                "video tutorials. You may use get_youtube_transcript to verify that a "
                "video is actually about the certification before recommending it. "
                "Only recommend resources that are clearly relevant. "
                "If search_youtube_videos returns an error (e.g. 'rate_limited') or "
                "no videos, DO NOT retry it; continue with the Microsoft Learn results "
                "only and produce the final answer."
            ),
        },
        {"role": "user", "content": cert_name},
    ]

    _say("Asking the assistant to plan your study resources...")

    step = 0
    while True:
        step += 1
        response = client.chat.completions.create(
            model=model_id,
            tools=tools,
            messages=messages,
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        assistant_msg: dict = {
            "role": "assistant",
            "content": message.content or "",
        }
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        if not tool_calls:
            break

        names = ", ".join(sorted({c.function.name for c in tool_calls}))
        _say(f"Step {step}: gathering resources ({names})...")

        process_tool_usage(tool_calls, messages)

    _say("Formatting the final answer...")

    collected = [
        {"tool_call_id": m["tool_call_id"], "output": m["content"]}
        for m in messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": (
                    "Output a clean markdown answer for the user with three sections: "
                    "'## Learning Paths', '## Documentation', and '## YouTube Videos'. "
                    "For Learning Paths and Documentation, list title + URL. "
                    "For YouTube Videos, list title, channel, duration and URL. "
                    "Only include items directly relevant to the certification. "
                    "If the YouTube tool returned an error or no videos, still emit "
                    "the '## YouTube Videos' section with a short note explaining "
                    "that no video results are available (e.g. rate limited)."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Certification: {cert_name}\n\n"
                    f"Tool results (JSON):\n{json.dumps(collected)}"
                ),
            },
        ],
    )

    return response.choices[0].message.content or ""
