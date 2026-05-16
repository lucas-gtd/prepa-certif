from openai import OpenAI
from os import getenv
from dotenv import load_dotenv

load_dotenv()

# gets API Key from environment variable OPENROUTER_API_KEY
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=getenv("OPENROUTER_API_KEY"),
)

completion = client.chat.completions.create(
  model="openai/gpt-5-mini",
  # pass extra_body to access OpenRouter-only arguments.
  # extra_body={
    # "models": [
    #   "openai/gpt-4o",
    #   "mistralai/mixtral-8x22b-instruct"
    # ]
  # },
  messages=[
    {
      "role": "user",
      "content": "Say this is a test",
    },
  ],
)

print(completion.choices[0].message.content)
