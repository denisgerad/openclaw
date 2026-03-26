"""
orchestrator/connectors/web_search.py
──────────────────────────────────────
Tavily web search connector for OpenClaw.

Tavily is optimised for LLM consumption — it returns clean, summarised
snippets rather than raw HTML, which maps cleanly onto ContextBundle.search_results.

Usage:
    searcher = WebSearchConnector()
    results  = searcher.search("latest Python 3.13 release notes")
    # → list of {title, url, summary, score}
"""

import os
from typing import Optional
from tavily import TavilyClient


class WebSearchConnector:
    """
    Thin wrapper around Tavily's search API.
    Keeps search_results in a consistent schema for the orchestrator.
    """

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            raise ValueError(
                "Tavily API key not found.\n"
                "Set TAVILY_API_KEY in your .env file.\n"
                "Get a free key at: https://tavily.com"
            )
        self.client = TavilyClient(api_key=key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",    # "basic" | "advanced"
        include_images: bool = False,
        include_answer: bool = True,    # Tavily's AI-generated direct answer
    ) -> list[dict]:
        """
        Run a web search and return structured results.

        Args:
            query:          Natural language search query.
            max_results:    Number of results to return (1–10).
            search_depth:   "basic" is faster; "advanced" is thorough.
            include_images: Whether to include image URLs in results.
            include_answer: Include Tavily's synthesised answer at top.

        Returns:
            List of dicts with keys: title, url, summary, score, [answer]
        """
        response = self.client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_images=include_images,
            include_answer=include_answer,
        )

        results = []

        # Prepend AI-generated direct answer if available
        if include_answer and response.get("answer"):
            results.append(
                {
                    "type": "direct_answer",
                    "title": "Tavily Direct Answer",
                    "url": "",
                    "summary": response["answer"],
                    "score": 1.0,
                }
            )

        for r in response.get("results", []):
            results.append(
                {
                    "type": "web_result",
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "summary": r.get("content", ""),
                    "score": r.get("score", 0.0),
                }
            )

        return results

    def search_and_summarise(self, query: str) -> str:
        """
        Convenience method: search and return a single flat string summary.
        Useful for injecting into orchestrator prompts.
        """
        results = self.search(query, max_results=3, include_answer=True)
        parts = []
        for r in results:
            if r["type"] == "direct_answer":
                parts.append(f"[Direct Answer]\n{r['summary']}")
            else:
                parts.append(f"[{r['title']}]\n{r['summary']}\nSource: {r['url']}")
        return "\n\n".join(parts)
