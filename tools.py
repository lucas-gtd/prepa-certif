import json
import requests

tools = [
    {
        "type": "function",
        "name": "search_microsoft_learn",
        "description": "Search Microsoft Learn for learning paths and documentations related to a specific certification exam.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "certification": {
                    "type": "string",
                    "description": "The certification exam code or name, e.g. 'AZ-900'"
                }
            },
            "required": ["certification"],
            "additionalProperties": False
        }
    }
]


def search_microsoft_learn(certification: str) -> list:
    results = []

    for category in ("Training", "Documentation"):
        resp = requests.get(
            "https://learn.microsoft.com/api/search/",
            params={
                "search": certification,
                "locale": "en-us",
                "$filter": f"category eq '{category}'",
                "$top": 10,
            },
            timeout=10,
        ).json()

        for item in resp.get("results", []):
            results.append({
                "type": category,
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description", ""),
            })

    return results


def fetch_certifications() -> list[str]:
    resp = requests.get(
        "https://learn.microsoft.com/api/catalog/",
        params={"type": "certifications", "locale": "en-us"},
        timeout=15,
    ).json()
    certs = resp.get("certifications", [])
    return sorted(set(c.get("title") for c in certs if c.get("title")))


def process_tool_usage(response, input_list):
    for item in response.output:
        if item.type == "function_call":
            if item.name == "search_microsoft_learn":
                certification = json.loads(item.arguments)["certification"]
                results = search_microsoft_learn(certification)
                input_list.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(results),
                })
