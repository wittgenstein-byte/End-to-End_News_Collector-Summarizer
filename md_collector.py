import httpx
import os
import time
from pathlib import Path


def fetch_with_jina(url: str, retries: int = 3, delay: float = 2.0) -> str:
    jina_url = f"https://r.jina.ai/{url}"

    for attempt in range(retries):
        response = httpx.get(jina_url, timeout=30.0)

        if response.status_code == 200:
            return response.text
        elif response.status_code == 503:
            wait_time = delay * (attempt + 1)
            print(
                f"503 error, retrying in {wait_time}s... (attempt {attempt + 1}/{retries})"
            )
            time.sleep(wait_time)
        else:
            response.raise_for_status()

    raise Exception(f"Failed after {retries} attempts: 503 Service Unavailable")


def fetch_with_readhtml(url: str) -> str:
    """Fallback: use textise dot iitty"""
    response = httpx.get(f"https://r.jina.ai/http://{url}", timeout=30.0)
    response.raise_for_status()
    return response.text


def collect_markdown_with_jina(url: str, output_dir: str = "collected_md") -> str:
    """
    Fetch markdown content from a URL using r.jina.ai and save it as a .md file.

    Args:
        url: The URL to fetch markdown content from
        output_dir: Directory to save the .md file

    Returns:
        Path to the saved file
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        content = fetch_with_jina(url)
    except Exception as e:
        print(f"r.jina.ai failed: {e}")
        print("Trying fallback...")
        try:
            content = fetch_with_readhtml(url)
        except Exception as e2:
            raise Exception(f"All methods failed. Last error: {e2}")

    filename = url.split("/")[-1]
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


if __name__ == "__main__":
    url = input("Enter URL to collect .md file from: ").strip()

    if not url:
        print("Error: URL cannot be empty")
    else:
        try:
            filepath = collect_markdown_with_jina(url)
            print(f"Successfully saved to: {filepath}")
        except Exception as e:
            print(f"Error: {e}")
