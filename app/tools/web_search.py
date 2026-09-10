from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def web_search(
    query: str,
    max_results: int = 5,
) -> list[dict]:

    if not query.strip():

        return []

    if max_results < 1:
        max_results = 1

    max_results = min(max_results, 10)

    url = (
        "https://www.google.com/search?q="
        + quote_plus(query)
    )

    headers = {
        "User-Agent": USER_AGENT
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=10,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        results = []

        for result in soup.select("div.MjjYud"):

            link = result.select_one("a")

            heading = result.select_one("h3")

            if not link or not heading:
                continue

            href = link.get("href")

            if not href:
                continue

            results.append(
                {
                    "title": heading.get_text(
                        strip=True
                    ),
                    "url": href,
                }
            )

            if len(results) >= max_results:
                break

        return results

    except Exception as exc:

        return [
            {
                "error": f"Web search failed: {exc}"
            }
        ]