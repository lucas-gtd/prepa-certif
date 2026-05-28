import json
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_microsoft_learn",
            "description": "Search Microsoft Learn for learning paths and documentations related to a specific certification exam.",
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
    },
    {
        "type": "function",
        "function": {
            "name": "search_youtube_videos",
            "description": "Search YouTube for videos related to a certification exam. Returns a list of videos with title, video_id, url, channel and duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, typically the certification code or name followed by keywords like 'tutorial' or 'exam prep'."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of videos to return (1-15)."
                    }
                },
                "required": ["query", "max_results"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_youtube_transcript",
            "description": "Fetch the transcript of a YouTube video. Use this to verify a video's content is actually relevant to the certification before recommending it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "The YouTube video id (the 11-character string after 'v=' in the URL)."
                    },
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Preferred transcript languages in priority order, e.g. ['en', 'fr']."
                    }
                },
                "required": ["video_id", "languages"],
                "additionalProperties": False
            }
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


def search_youtube_videos(query: str, max_results: int = 8) -> dict:
    """Search YouTube without an API key by scraping the search results page.

    Returns a dict with either a list of videos or an error description so the
    agent loop can keep going even when YouTube rate-limits us.
    """
    max_results = max(1, min(int(max_results or 8), 15))
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query, "hl": "en"},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        reason = "rate_limited" if status == 429 else f"http_{status}"
        return {"videos": [], "error": reason}
    except requests.RequestException as exc:
        return {"videos": [], "error": f"request_failed: {exc}"}

    match = re.search(r"var ytInitialData = (\{.*?\});</script>", resp.text)
    if not match:
        return {"videos": [], "error": "no_data"}
    data = json.loads(match.group(1))

    videos: list = []
    seen: set = set()

    def walk(node):
        if len(videos) >= max_results:
            return
        if isinstance(node, dict):
            vr = node.get("videoRenderer")
            if vr and vr.get("videoId") and vr["videoId"] not in seen:
                vid = vr["videoId"]
                seen.add(vid)
                title = "".join(
                    r.get("text", "") for r in vr.get("title", {}).get("runs", [])
                )
                channel = "".join(
                    r.get("text", "")
                    for r in vr.get("ownerText", {}).get("runs", [])
                )
                duration = vr.get("lengthText", {}).get("simpleText", "")
                videos.append({
                    "title": title,
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "channel": channel,
                    "duration": duration,
                })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return {"videos": videos}


def get_youtube_transcript(video_id: str, languages: list[str] | None = None) -> dict:
    languages = languages or ["en"]
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=languages)
    except (TranscriptsDisabled, NoTranscriptFound):
        return {"video_id": video_id, "available": False, "reason": "no_transcript"}
    except VideoUnavailable:
        return {"video_id": video_id, "available": False, "reason": "unavailable"}
    except Exception as exc:
        return {"video_id": video_id, "available": False, "reason": str(exc)}

    text = " ".join(snippet.text for snippet in fetched).strip()
    if len(text) > 6000:
        text = text[:6000] + " ..."
    return {
        "video_id": video_id,
        "available": True,
        "language": fetched.language_code,
        "text": text,
    }


def process_tool_usage(tool_calls, messages):
    for tc in tool_calls:
        name = tc.function.name
        args = json.loads(tc.function.arguments or "{}")
        if name == "search_microsoft_learn":
            output = search_microsoft_learn(args["certification"])
        elif name == "search_youtube_videos":
            output = search_youtube_videos(
                args["query"], args.get("max_results", 8)
            )
        elif name == "get_youtube_transcript":
            output = get_youtube_transcript(
                args["video_id"], args.get("languages") or ["en"]
            )
        else:
            continue
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(output),
        })
