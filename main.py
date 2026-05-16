from openai import OpenAI
from os import getenv
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from InquirerPy import inquirer

from tools import tools, process_tool_usage, fetch_certifications

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=getenv("OPENROUTER_API_KEY"),
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
        "content": "You are an assistant that ONLY give the user a list of Microsoft learning paths for his chosen certification exam."
    },
    {
        "role": "user",
        "content": cert_name
    }
]

with console.status("[bold green]Working[/bold green]", spinner="dots"):
    response = client.responses.create(
        model=getenv('MODEL_ID'),
        tools=tools,
        input=inputs,
    )

    for item in response.output:
        if item.type == "function_call":
            inputs.append(item)

    process_tool_usage(response, inputs)

    # Extract the raw search results and build a clean, standalone request
    # so the final call never sees the first call's reasoning text.
    search_results = next(
        (item["output"] for item in inputs
         if isinstance(item, dict) and item.get("type") == "function_call_output"),
        "[]"
    )

    response = client.responses.create(
        model=getenv('MODEL_ID'),
        instructions=(
            "Output a clean numbered list of Microsoft Learn learning paths and documentation "
            "pages relevant to the certification. For each item include: the title and the URL. "
            "Group them under '## Learning Paths' and '## Documentation'. "
            "Only include items directly related to the certification."
        ),
        input=[{
            "role": "user",
            "content": f"Certification: {cert_name}\n\nSearch results (JSON):\n{search_results}"
        }],
    )

console.print()
console.print(Panel(
    Markdown(response.output_text),
    title=f"[bold green]Results for {cert_name}[/bold green]",
    border_style="green",
    padding=(1, 2),
))
