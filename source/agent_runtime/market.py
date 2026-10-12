import re
from urllib.parse import quote
from urllib.request import Request, urlopen

_STOPWORDS = (
    "请问", "告诉我", "帮我", "给我", "我想看", "我想知道", "想看", "想知道",
    "股市", "A股", "中国股票市场", "中国", "主要指数", "主要", "三大指数", "大盘", "市场",
    "查一下", "查下", "查询", "搜索", "联网", "看看", "看下", "今天", "今日",
    "现在", "目前", "实时", "截至", "最新", "的", "股票代码", "股票", "股价",
    "个股", "这只", "该股", "涨跌幅", "涨跌", "上涨", "下跌", "行情", "走势",
    "情况", "信息", "数据", "多少", "如何", "怎么样", "是多少", "是多少点", "价格", "点位", "呢", "吗", "它", "那只", "这家公司",
    "给我看", "介绍", "表现", "今日行情", "当前", "我", "那", "这",
)
_BROAD = re.compile(r"股市|A股|大盘|主要指数|三大指数|中国股票市场", re.I)
_INDEXES = {
    "上证指数": ("s_sh000001", "上证指数"),
    "沪指": ("s_sh000001", "上证指数"),
    "深证成指": ("s_sz399001", "深证成指"),
    "深成指": ("s_sz399001", "深证成指"),
    "创业板指": ("s_sz399006", "创业板指"),
    "创业板指数": ("s_sz399006", "创业板指"),
}

def is_specific_index_request(query):
    return any(name in query for name in _INDEXES)

def stock_search_term(query):
    code = re.search(r"(?<!\d)(\d{6})(?!\d)", query)
    if code:
        return code.group(1)
    value = query
    for word in sorted(_STOPWORDS, key=len, reverse=True):
        value = value.replace(word, "")
    value = re.sub(r"[\s，。！？、,.!?：:；;（）()【】\[\]的和与及]+", "", value)
    value = re.sub(r"(今天|今日|现在|目前|实时|最新|涨跌|行情|股价|股票|数据|信息|如何|怎么样|多少|点位|表现|建议|推荐|好吗|呢|吗)+$", "", value)
    return value[:30].strip()

def classify_stock_request(query):
    if re.search(r"建议|推荐|投资|理财|学习|入门", query) and not re.search(
            r"股价|涨跌|现价|代码|多少|今天|今日|实时|最新", query):
        return None
    code = re.search(r"(?<!\d)(\d{6})(?!\d)", query)
    if code:
        return {"kind": "stock", "query": code.group(1), "code": code.group(1)}
    if is_specific_index_request(query):
        name = next((label for label in _INDEXES if label in query), "上证指数")
        symbol, canonical = _INDEXES[name]
        return {"kind": "index", "symbol": symbol, "name": canonical}
    term = stock_search_term(query)
    if _BROAD.search(query) and not term:
        return {"kind": "broad"}
    has_quote_intent = bool(re.search(
        r"股票|股价|个股|涨跌|行情|走势|证券|代码|今天|今日|实时|目前|最新|涨多少|跌多少|(?:那|这|它).{0,10}呢",
        query, re.I))
    if term and has_quote_intent and not _BROAD.fullmatch(term):
        return {"kind": "stock", "query": term}
    if re.search(r"股票|股价|个股|证券|涨跌|行情", query) and not term:
        return {"kind": "need_target"}
    if _BROAD.search(query):
        return {"kind": "broad"}
    return None

def _get(url, referer):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 ForgeMind local assistant",
                                    "Referer": referer, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urlopen(request, timeout=9) as response:
        return response.read(200_000).decode("gbk", "replace")

def resolve_stock(query):
    code = re.search(r"(?<!\d)(\d{6})(?!\d)", query)
    term = code.group(1) if code else str(query).strip()
    if not term:
        return []
    url = "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key=" + quote(term)
    text = _get(url, "https://finance.sina.com.cn/")
    match = re.search(r'var suggestvalue="([^"]*)"', text)
    if not match or not match.group(1):
        return []
    results = []
    for row in match.group(1).split(";"):
        fields = row.split(",")
        if len(fields) < 4 or fields[1] != "11":
            continue
        name, code, symbol = fields[0].strip(), fields[2].strip(), fields[3].strip()
        if re.fullmatch(r"\d{6}", code) and re.fullmatch(r"(?:sh|sz|bj)\d{6}", symbol):
            item = {"name": name, "code": code, "symbol": symbol}
            if item not in results:
                results.append(item)
    if len(results) > 1:
        exact = [item for item in results if item["name"] == term or item["code"] == term]
        if len(exact) == 1:
            return exact
    return results[:5]

def fetch_stock_quote(stock):
    symbol = stock["symbol"]
    if not re.fullmatch(r"(?:sh|sz)\d{6}", symbol):
        return None
    sina_url = "https://hq.sinajs.cn/list=" + symbol
    tencent_url = "https://qt.gtimg.cn/q=" + symbol
    sina_text = _get(sina_url, "https://finance.sina.com.cn/")
    tencent_text = _get(tencent_url, "https://gu.qq.com/")
    sina_match = re.search(r"var hq_str_" + re.escape(symbol) + r'="([^"]*)"', sina_text)
    tencent_match = re.search(r"v_" + re.escape(symbol) + r'="([^"]*)"', tencent_text)
    if not sina_match or not tencent_match:
        return None
    s = sina_match.group(1).split(",")
    t = tencent_match.group(1).split("~")
    if len(s) < 4 or len(t) < 5:
        return None
    try:
        price, previous = float(s[3]), float(s[2])
        other_price, other_previous = float(t[3]), float(t[4])
    except ValueError:
        return None
    change, percent = price - previous, (price / previous - 1) * 100 if previous else 0.0
    resolved_name = s[0].strip()
    if resolved_name and not re.fullmatch(r"(?:sh|sz|bj)?\d{6}", resolved_name, re.I):
        stock["name"] = resolved_name
    if abs(price - other_price) > max(0.05, price * 0.0001):
        return None
    if abs(change - (other_price - other_previous)) > max(0.05, price * 0.0001):
        return None
    return {
        "name": stock["name"], "code": stock["code"], "symbol": symbol,
        "price": price, "change": change, "percent": percent,
        "sina_url": sina_url, "tencent_url": tencent_url,
    }

def format_stock_quote(stock, quote_data, queried_at):
    if not quote_data:
        return f"我找到“{stock['name']}”（{stock['code']}），但新浪与腾讯行情暂时无法相互核对，所以不显示未经核实的涨跌数字。"
    return (
        f"{stock['name']}（{stock['code']}）最新可得行情（查询时间：{queried_at}）\n\n"
        f"- 现价：{quote_data['price']:,.2f}\n"
        f"- 涨跌：{quote_data['change']:+,.2f}（{quote_data['percent']:+.2f}%）\n\n"
        "新浪与腾讯公开行情接口的现价已交叉核对。数据可能延迟，请以交易所或券商页面为准。"
    )
