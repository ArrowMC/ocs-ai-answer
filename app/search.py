import logging
import re
import asyncio

logger = logging.getLogger(__name__)

# Punctuation and whitespace
_PUNCT_RE = re.compile('[，。、；：""\'\'！？!?\\s\xa0]+')

# Bracket content to strip: （...） or (...)
_BRACKET_RE = re.compile(r'[（(][^)）]*[)）]')

# Common filler words in exam questions
_FILLER_WORDS = {
    '下列', '选项中', '本题考查', '请选择', '单选题', '多选题', '判断题', '填空题',
    '请问', '以下', '选出', '选择', '哪些', '哪个', '那种', '几种', '什么',
}

# Function-word-like characters to split on for phrase segmentation
_SPLIT_CHARS_RE = re.compile(r'[的着了过是在和或与及之为所而]')


def _light_clean(text: str) -> str:
    """Remove bracket content and normalize whitespace."""
    text = _BRACKET_RE.sub('', text)
    text = _PUNCT_RE.sub(' ', text)
    return text.strip()


def _tokenize(text: str) -> list[str]:
    """Split Chinese text into rough word segments."""
    # Split on function characters
    parts = _SPLIT_CHARS_RE.split(text)
    tokens = []
    for p in parts:
        p = p.strip()
        if p:
            tokens.append(p)
    return tokens


def _extract_key_phrases(text: str) -> list[str]:
    """Extract search-worthy phrases from a question."""
    cleaned = _light_clean(text)

    # Remove filler words
    for fw in sorted(_FILLER_WORDS, key=len, reverse=True):
        cleaned = cleaned.replace(fw, ' ')

    # Re-split on punctuation
    segments = [s.strip() for s in _PUNCT_RE.split(cleaned) if s.strip()]
    if not segments:
        segments = [cleaned]

    # For each segment, try tokenizing further
    all_tokens = []
    for seg in segments:
        tokens = _tokenize(seg)
        all_tokens.extend(tokens)

    # Filter: keep tokens >= 2 chars, remove pure numbers/single letters
    phrases = []
    for t in all_tokens:
        t = t.strip()
        if len(t) >= 2 and not re.match(r'^[A-H\d]+$', t):
            phrases.append(t)

    # Deduplicate, limit to 5
    seen = set()
    result = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result[:5]


def _build_queries(phrases: list[str]) -> list[str]:
    """Build search queries from key phrases."""
    queries = []
    # Query 1: all phrases joined
    if len(phrases) >= 2:
        queries.append(' '.join(phrases[:3]))
    # Query 2: top phrase + educational suffix
    if phrases:
        queries.append(f'{phrases[0]} 题库 答案')
    # Query 3: top 2 phrases
    if len(phrases) >= 2:
        queries.append(f'{phrases[0]} {phrases[1]}')
    # Query 4: top phrase alone
    if phrases:
        queries.append(phrases[0])
    return queries


async def _search_single(query: str, max_results: int = 3) -> list[str]:
    """Search a single query, return formatted snippet lines."""
    try:
        def _sync():
            from ddgs import DDGS
            items = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    title = r.get('title', '')
                    body = r.get('body', '')
                    # Skip clearly irrelevant results
                    noise_kw = ['抖音', 'TikTok', '娱乐', '广告', '招聘', '下载',
                                '小说', '漫画', '游戏', '视频', '直播', '购物',
                                '彩票', '股票', '理财', '保险', '加盟']
                    if any(kw in title for kw in noise_kw):
                        continue
                    # Skip if title/body looks like pure social media or commerce
                    if any(kw in body[:80] for kw in ['抖音', 'TikTok', '下载APP']):
                        continue
                    items.append(f'- {title}: {body}')
            return items

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)
    except Exception as e:
        logger.debug("Search failed for '%s': %s", query[:60], e)
        return []


async def search_web(question: str, max_results: int = 5) -> str:
    """Smart web search: extract key concepts, try multiple queries."""
    phrases = _extract_key_phrases(question)
    logger.info("Search: extracted key phrases: %s", phrases)

    if not phrases:
        logger.info("Search: no meaningful phrases found")
        return ""

    queries = _build_queries(phrases)
    logger.info("Search: trying %d queries: %s", len(queries), queries)

    all_items = []
    seen_titles = set()

    for query in queries:
        items = await _search_single(query, max_results=3)
        for item in items:
            key = item[:80]
            if key not in seen_titles:
                seen_titles.add(key)
                all_items.append(item)
        if len(all_items) >= max_results:
            break

    if all_items:
        text = '\n'.join(all_items[:max_results])
        logger.info("Search: %d unique results", len(all_items))
        return text
    else:
        logger.info("Search: no relevant results after %d queries", len(queries))
        return ""
