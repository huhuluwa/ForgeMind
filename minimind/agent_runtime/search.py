"""Free web search with compact, attributable results."""

from html.parser import HTMLParser
import base64
import json
import os
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from xml.etree import ElementTree
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


try:
    from ddgs import DDGS
except ImportError:
    DDGS = None


TAVILY_ENDPOINT = "https://api.tavily.com/search"
ANYSEARCH_ENDPOINT = "https://api.anysearch.com/v1/search"
DUCKDUCKGO_ENDPOINT = "https://html.duckduckgo.com/html/"
BING_RSS_ENDPOINT = "https://www.bing.com/search"
GITHUB_API = "https://api.github.com"


class _DuckDuckGoResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.capture = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set(attributes.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self.current = {"url": attributes.get("href", ""), "title": [], "snippet": []}
            self.results.append(self.current)
            self.capture = "title"
        elif tag == "a" and "result__snippet" in classes and self.results:
            self.current = self.results[-1]
            self.capture = "snippet"

    def handle_endtag(self, tag):
        if tag == "a":
            self.capture = None

    def handle_data(self, data):
        if self.current is not None and self.capture:
            self.current[self.capture].append(data)


def _target_url(value):
    if value.startswith("//"):
        value = "https:" + value
    parsed = urlsplit(value)
    if parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}:
        value = parse_qs(parsed.query).get("uddg", [""])[0]
        parsed = urlsplit(value)
    return value if parsed.scheme in {"https", "http"} and parsed.hostname else ""


def _search_duckduckgo(query, max_results):
    url = DUCKDUCKGO_ENDPOINT + "?" + urlencode({"q": query})
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        with urlopen(req, timeout=20) as response:
            html = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
    except HTTPError as exc:
        return {"error": f"Web search provider returned HTTP {exc.code}"}
    except (URLError, TimeoutError) as exc:
        return {"error": f"Web search failed: {type(exc).__name__}"}
    parser = _DuckDuckGoResults()
    parser.feed(html)
    sources = []
    for result in parser.results:
        target = _target_url(result["url"])
        title = "".join(result["title"]).strip()
        snippet = "".join(result["snippet"]).strip()
        if not target or not title:
            continue
        sources.append({"title": title[:300], "url": target[:2000],
                        "published_date": None, "snippet": snippet[:2500]})
        if len(sources) >= max_results:
            break
    return {"query": query, "provider": "DuckDuckGo HTML", "sources": sources}


def _search_anysearch(query, max_results):
    payload = json.dumps({"query": query, "max_results": max_results}).encode("utf-8")
    req = Request(ANYSEARCH_ENDPOINT, data=payload, headers={
        "Content-Type": "application/json",
        "X-Anysearch-Client": "skill/3.1.1",
    }, method="POST")
    try:
        with urlopen(req, timeout=30) as response:
            envelope = json.loads(response.read(2_000_000).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"query": query, "provider": "AnySearch", "sources": [],
                "error": f"AnySearch failed: {type(exc).__name__}"}
    data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
    sources = []
    for result in data.get("results", []) if isinstance(data, dict) else []:
        if not isinstance(result, dict):
            continue
        target = _target_url(str(result.get("url") or ""))
        title = str(result.get("title") or "").strip()
        snippet = str(result.get("content") or result.get("snippet") or "").strip()
        if not target or not title:
            continue
        sources.append({"title": title[:300], "url": target[:2000],
                        "published_date": result.get("published_date"),
                        "snippet": snippet[:2500]})
        if len(sources) >= max_results:
            break
    return {"query": query, "provider": "AnySearch", "sources": sources}


def _search_ddgs(query, max_results):
    if DDGS is None:
        return {"query": query, "provider": "DDGS", "sources": [], "error": "ddgs dependency is not installed"}
    try:
        results = DDGS(timeout=20).text(query, max_results=max_results)
    except Exception as exc:
        return {"query": query, "provider": "DDGS metasearch", "sources": [],
                "error": f"DDGS failed: {type(exc).__name__}"}
    sources = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        target = _target_url(str(result.get("href") or result.get("url") or ""))
        title = str(result.get("title") or "").strip()
        snippet = str(result.get("body") or result.get("snippet") or "").strip()
        if not target or not title:
            continue
        sources.append({"title": title[:300], "url": target[:2000],
                        "published_date": result.get("date"), "snippet": snippet[:2500]})
        if len(sources) >= max_results:
            break
    return {"query": query, "provider": "DDGS metasearch", "sources": sources}

def _search_bing_rss(query, max_results):
    url = BING_RSS_ENDPOINT + "?" + urlencode({"format": "rss", "q": query})
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        with urlopen(req, timeout=20) as response:
            root = ElementTree.fromstring(response.read(2_000_000))
    except (HTTPError, URLError, TimeoutError, ElementTree.ParseError) as exc:
        return {"query": query, "provider": "Bing RSS", "sources": [],
                "error": f"Bing RSS failed: {type(exc).__name__}"}
    sources = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        target = _target_url((item.findtext("link") or "").strip())
        snippet = (item.findtext("description") or "").strip()
        if not title or not target:
            continue
        sources.append({"title": title[:300], "url": target[:2000],
                        "published_date": (item.findtext("pubDate") or None),
                        "snippet": snippet[:2500]})
        if len(sources) >= max_results:
            break
    return {"query": query, "provider": "Bing RSS", "sources": sources}


def _search_tavily(query, max_results, api_key):
    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "topic": "general",
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
    }).encode("utf-8")
    req = Request(TAVILY_ENDPOINT, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=20) as response:
            result = json.loads(response.read(2_000_000).decode("utf-8"))
    except HTTPError as exc:
        return {"error": f"Tavily returned HTTP {exc.code}"}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": f"Tavily search failed: {type(exc).__name__}"}
    sources = []
    for item in result.get("results", []):
        url, title, content = item.get("url"), item.get("title"), item.get("content")
        if not (isinstance(url, str) and url.startswith("https://") and isinstance(title, str) and isinstance(content, str)):
            continue
        sources.append({"title": title[:300], "url": url[:2000],
                        "published_date": item.get("published_date"), "snippet": content[:2500]})
    return {"query": query, "provider": "Tavily", "sources": sources}


def _search_github_repo(query, max_results):
    """Read matching public Markdown files from an explicitly named GitHub repo."""
    match = re.search(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?![A-Za-z0-9_.-])", query)
    if not match:
        return None
    owner, repo = match.groups()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ForgeMind-local-agent"}

    def get_json(url, limit=8_000_000):
        request = Request(url, headers=headers)
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read(limit).decode("utf-8"))

    try:
        repository = get_json(f"{GITHUB_API}/repos/{owner}/{repo}", 250_000)
        branch = repository.get("default_branch")
        if not isinstance(branch, str) or not branch:
            return None
        encoded_branch = quote(branch, safe="/")
        tree = get_json(f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{encoded_branch}?recursive=1")
        entries = tree.get("tree", []) if isinstance(tree, dict) else []
        paths = [entry.get("path") for entry in entries if isinstance(entry, dict)
                 and isinstance(entry.get("path"), str) and entry.get("type") == "blob"
                 and entry["path"].casefold().endswith(".md")]
        terms = {term.casefold() for term in re.findall(r"[A-Za-z][A-Za-z0-9-]+", query)
                 if term.casefold() not in {owner.casefold(), repo.casefold(), "github", "skill", "skills", "repo", "repository"}}
        direct_skills = [path for path in paths if any(
            path.casefold() == f"skills/{term}/skill.md" for term in terms
        )]
        candidates = direct_skills or [path for path in paths
                                       if not path.casefold().startswith("systems/")]
        ranked = sorted(candidates, key=lambda path: (
            -sum(term in path.casefold() for term in terms),
            0 if path.casefold().endswith("/skill.md") else 1,
            len(path), path.casefold(),
        ))
        sources = []
        for path in ranked[:max_results]:
            if terms and not any(term in path.casefold() for term in terms):
                continue
            item = get_json(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{quote(path, safe='/')}?ref={quote(branch, safe='/')}",
                1_000_000,
            )
            encoded = item.get("content") if isinstance(item, dict) else None
            if not isinstance(encoded, str):
                continue
            content = base64.b64decode(encoded).decode("utf-8", "replace")
            url = item.get("html_url") or f"https://github.com/{owner}/{repo}/blob/{branch}/{path}"
            sources.append({"title": f"{owner}/{repo}: {path}", "url": url,
                            "published_date": None, "snippet": content[:2500]})
        if sources:
            return {"query": query, "provider": "GitHub public API", "sources": sources}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return None


def search_media(query, media_type, max_results=6):
    """Search public image or video results through the installed DDGS provider."""
    query = str(query).strip()
    if not query or len(query) > 500:
        return {"query": query, "provider": "DDGS", "sources": [],
                "error": "query must contain 1-500 characters"}
    if media_type not in {"image", "video"}:
        return {"query": query, "provider": "DDGS", "sources": [],
                "error": "media_type must be image or video"}
    if DDGS is None:
        return {"query": query, "provider": "DDGS", "sources": [],
                "error": "ddgs dependency is not installed"}
    count = max(1, min(int(max_results), 8))
    search_error = None
    try:
        method = "images" if media_type == "image" else "videos"
        results = getattr(DDGS(timeout=20), method)(query, max_results=count)
    except Exception as exc:
        results = []
        search_error = f"DDGS {media_type} search failed: {type(exc).__name__}"
    sources = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        page = _target_url(str(result.get("url") or result.get("content") or ""))
        media = _target_url(str(result.get("image") or result.get("content") or result.get("url") or ""))
        thumbnail = _target_url(str(result.get("thumbnail") or result.get("image") or ""))
        title = str(result.get("title") or result.get("source") or "").strip()
        if not title or not page:
            continue
        sources.append({
            "title": title[:300], "url": page[:2000], "published_date": None,
            "snippet": str(result.get("description") or result.get("source") or "")[:500],
            "media_type": media_type,
            "media_url": (media or page)[:2000],
            "thumbnail": thumbnail[:2000],
            "width": str(result.get("width") or ""),
            "height": str(result.get("height") or ""),
            "duration": str(result.get("duration") or ""),
        })
        if len(sources) >= count:
            break
    if not sources and media_type == "video":
        fallback = search_web(query + " 视频教程 site:youtube.com/watch OR site:bilibili.com/video", count)
        for item in fallback.get("sources", []):
            page = _target_url(str(item.get("url") or ""))
            host = urlsplit(page).hostname or ""
            if not page or not (host.endswith("youtube.com") or host == "youtu.be" or host.endswith("bilibili.com")):
                continue
            match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", page)
            thumbnail = f"https://i.ytimg.com/vi/{match.group(1)}/hqdefault.jpg" if match else ""
            sources.append({"title": item.get("title", "视频结果"), "url": page,
                            "published_date": item.get("published_date"), "snippet": item.get("snippet", ""),
                            "media_type": "video", "media_url": page, "thumbnail": thumbnail,
                            "width": "", "height": "", "duration": ""})
            if len(sources) >= count:
                break
    fallback_links = False
    if not sources and media_type == "video":
        search_term = query + " 视频"
        sources = [
            {"title": "YouTube 视频搜索：" + query, "url": "https://www.youtube.com/results?" + urlencode({"search_query": search_term}),
             "published_date": None, "snippet": "打开 YouTube 查看匹配视频", "media_type": "video",
             "media_url": "", "thumbnail": "", "width": "", "height": "", "duration": ""},
            {"title": "哔哩哔哩视频搜索：" + query, "url": "https://search.bilibili.com/all?" + urlencode({"keyword": search_term}),
             "published_date": None, "snippet": "打开哔哩哔哩查看匹配视频", "media_type": "video",
             "media_url": "", "thumbnail": "", "width": "", "height": "", "duration": ""},
            {"title": "Bing 视频搜索：" + query, "url": "https://www.bing.com/videos/search?" + urlencode({"q": search_term}),
             "published_date": None, "snippet": "打开 Bing 视频搜索查看结果", "media_type": "video",
             "media_url": "", "thumbnail": "", "width": "", "height": "", "duration": ""},
        ]
        fallback_links = True
    return {"query": query, "provider": "DuckDuckGo media search",
            "sources": sources, "search_page_fallback": fallback_links,
            **({"error": search_error or "没有找到可展示的公开结果"} if not sources else {})}


def search_web(query, max_results=5):
    query = str(query).strip()
    if not query or len(query) > 500:
        return {"error": "query must contain 1-500 characters"}
    try:
        count = max(1, min(int(max_results), 8))
    except (TypeError, ValueError):
        count = 5
    github_result = _search_github_repo(query, count)
    if github_result and github_result.get("sources"):
        return github_result
    api_key = os.environ.get("TAVILY_API_KEY")
    if api_key and os.environ.get("FORGEMIND_TAVILY_FREE_ONLY") == "1":
        result = _search_tavily(query, count, api_key)
        if result.get("sources"):
            return result
    result = _search_ddgs(query, count)
    if result.get("sources"):
        return result
    result = _search_duckduckgo(query, count)
    if result.get("sources"):
        return result
    fallback = _search_bing_rss(query, count)
    if fallback.get("sources"):
        return fallback
    result = _search_anysearch(query, count)
    if result.get("sources"):
        return result
    return result
