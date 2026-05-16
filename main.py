from openai import OpenAI
from os import getenv
from dotenv import load_dotenv

from tools import tools, process_tool_usage

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=getenv("OPENROUTER_API_KEY"),
)

prompt = input('Give the certification name: ')

inputs = [
    {
        "role": "system",
        "content": "You are an assistant that ONLY give the user a list of Microsoft learning paths for his choosen certification exam."
    },
    {
        "role": "user",
        "content": prompt
    }
]

response = client.responses.create(
    model="openai/gpt-5-mini",
    tools=tools,
    input=inputs,
)

inputs += response.output

process_tool_usage(response, inputs)

response = client.responses.create(
    model="openai/gpt-5-mini",
    instructions=(
        "Based on the search results, output a clean numbered list of Microsoft Learn "
        "learning paths and documentation pages relevant to the certification. "
        "For each item include: the title and the URL. Group them under '## Learning Paths' "
        "and '## Documentation'. Only include items directly related to the certification."
    ),
    input=inputs,
)

print(response.output_text)
