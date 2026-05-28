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
        )
    },
    {
        "role": "user",
        "content": cert_name
    }
]

with console.status("[bold green]Working[/bold green]", spinner="dots"):
    while True:
        response = client.responses.create(
            model=getenv('MODEL_ID'),
            tools=tools,
            input=inputs,
        )

        tool_calls = [item for item in response.output if item.type == "function_call"]
        if not tool_calls:
            break

        for item in tool_calls:
            inputs.append(item)
        process_tool_usage(response, inputs)

    # Aggregate every tool result the agent collected and ask the model
    # for a clean, standalone formatted answer.
    collected = [
        {"call_id": item["call_id"], "output": item["output"]}
        for item in inputs
        if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]

    response = client.responses.create(
        model=getenv('MODEL_ID'),
        instructions=(
            "Output a clean markdown answer for the user with three sections: "
            "'## Learning Paths', '## Documentation', and '## YouTube Videos'. "
            "For Learning Paths and Documentation, list title + URL. "
            "For YouTube Videos, list title, channel, duration and URL. "
            "Only include items directly relevant to the certification."
        ),
        input=[{
            "role": "user",
            "content": (
                f"Certification: {cert_name}\n\n"
                f"Tool results (JSON):\n{json.dumps(collected)}"
            )
        }],
    )

console.print()
console.print(Panel(
    Markdown(response.output_text),
    title=f"[bold green]Results for {cert_name}[/bold green]",
    border_style="green",
    padding=(1, 2),
))
