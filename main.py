from openai import OpenAI
from os import getenv
import json
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from InquirerPy import inquirer

from tools import tools, process_tool_usage, fetch_certifications

load_dotenv()

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=getenv("GITHUB_TOKEN"),
)

console = Console()

with console.status("[bold yellow]Loading certifications...[/bold yellow]", spinner="dots"):
    cert_choices = fetch_certifications()

console.print()
cert_name = inquirer.fuzzy(
    message="Select a certification:",
    choices=cert_choices,
    mandatory=True,
).execute()

console.print()

messages = [
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
        )
    },
    {
        "role": "user",
        "content": cert_name
    }
]

with console.status("[bold green]Working[/bold green]", spinner="dots"):
    while True:
        response = client.chat.completions.create(
            model=getenv('MODEL_ID'),
            tools=tools,
            messages=messages,
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        assistant_msg = {
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

        process_tool_usage(tool_calls, messages)

    # Aggregate every tool result the agent collected and ask the model
    # for a clean, standalone formatted answer.
    collected = [
        {"tool_call_id": m["tool_call_id"], "output": m["content"]}
        for m in messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]

    response = client.chat.completions.create(
        model=getenv('MODEL_ID'),
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

final_text = response.choices[0].message.content or ""

console.print()
console.print(Panel(
    Markdown(final_text),
    title=f"[bold green]Results for {cert_name}[/bold green]",
    border_style="green",
    padding=(1, 2),
))
