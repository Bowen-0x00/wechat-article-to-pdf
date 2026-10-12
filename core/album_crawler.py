import re
import html
import time
import urllib.parse
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

class WeChatAlbumCrawler:
    """
    微信公众号话题/合集 (Album / Topic) 全量解析器
    微信合集页面为完全公开的 Web 页面，无需登录后台凭证，即可无限制全量翻页抓取合集内的所有文章！
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.timeout = timeout

    def extract_album_articles(self, album_url: str) -> Dict[str, Any]:
        """
        从合集链接中解析合集标题、公众号信息及全部文章列表（自动翻页拉取完整专辑）
        :param album_url: 合集链接
        :return: {album_title, nickname, biz, album_id, articles: [{title, link, msgid, itemidx, create_time}]}
        """
        clean_url = album_url.strip()
        resp = self.session.get(clean_url, timeout=self.timeout)
        resp.encoding = "utf-8"
        content = resp.text

        soup = BeautifulSoup(content, "html.parser")

        # 1. 提取元数据
        album_title = ""
        m_js_title = re.search(r'title:\s*[\'"]([^\'"]+)[\'"]', content)
        if m_js_title:
            album_title = html.unescape(m_js_title.group(1)).strip()
        else:
            m_title = soup.find(class_=re.compile(r"album__title")) or soup.find("title")
            if m_title:
                album_title = m_title.get_text(strip=True)
        nickname = ""
        m_nick = soup.find(class_=re.compile(r"album__author"))
        if m_nick:
            nickname = m_nick.get_text(strip=True)

        # 提取 biz 与 album_id
        parsed = urllib.parse.urlparse(clean_url)
        params = urllib.parse.parse_qs(parsed.query)
        biz = params.get("__biz", [""])[0]
        album_id = params.get("album_id", [""])[0]

        if not biz:
            m_biz = re.search(r'__biz=([a-zA-Z0-9+=/]+)', content)
            if m_biz:
                biz = m_biz.group(1)

        if not album_id:
            m_aid = re.search(r'album_id=([0-9]+)', content)
            if m_aid:
                album_id = m_aid.group(1)

        # 2. 从第一页 HTML 提取首批文章
        articles: List[Dict[str, Any]] = []
        last_msgid = ""
        last_itemidx = "1"

        # 尝试匹配第一页嵌入的 cgiData.article_list
        item_blocks = re.findall(
            r'title:\s*[\x27\x22]([^\x27\x22]+)[\x27\x22][\s\S]*?url:\s*[\x27\x22]([^\x27\x22]+)[\x27\x22][\s\S]*?msgid:\s*[\x27\x22](\d+)[\x27\x22][\s\S]*?itemidx:\s*[\x27\x22](\d+)[\x27\x22]',
            content
        )

        if item_blocks:
            for title, raw_url, msgid, itemidx in item_blocks:
                link = html.unescape(raw_url).replace("http://", "https://")
                articles.append({
                    "title": html.unescape(title).strip(),
                    "link": link,
                    "msgid": msgid,
                    "itemidx": itemidx
                })
                last_msgid = msgid
                last_itemidx = itemidx
        else:
            # 备用 DOM 解析
            items = soup.find_all("li", class_=re.compile(r"album__list-item"))
            for it in items:
                title = it.get("data-title") or (it.find(class_=re.compile(r"title")).get_text(strip=True) if it.find(class_=re.compile(r"title")) else "")
                link = it.get("data-link") or ""
                msgid = it.get("data-msgid") or ""
                if link and not link.startswith("http"):
                    link = "https://mp.weixin.qq.com" + link
                if title:
                    articles.append({
                        "title": html.unescape(title).strip(),
                        "link": link,
                        "msgid": msgid,
                        "itemidx": "1"
                    })
                    if msgid:
                        last_msgid = msgid

        # 检查第一页的 continue_flag
        has_more = False
        m_continue = re.search(r'continue_flag\s*:\s*[\x27\x22]?(\d+)[\x27\x22]?', content)
        if m_continue and m_continue.group(1) == "1":
            has_more = True

        # 3. 如果还有更多，循环调用官方公开翻页 API
        page_num = 1
        while has_more and last_msgid and biz and album_id:
            page_num += 1
            api_url = "https://mp.weixin.qq.com/mp/appmsgalbum"
            req_params = {
                "action": "getalbum",
                "__biz": biz,
                "album_id": album_id,
                "count": "10",
                "begin_msgid": last_msgid,
                "begin_itemidx": last_itemidx,
                "f": "json"
            }

            try:
                r = self.session.get(api_url, params=req_params, timeout=self.timeout)
                data = r.json()
                if data.get("base_resp", {}).get("ret") != 0:
                    break

                getalbum_resp = data.get("getalbum_resp", {})
                new_items = getalbum_resp.get("article_list", [])
                if not new_items:
                    break

                for it in new_items:
                    t = it.get("title", "")
                    u = html.unescape(it.get("url", "")).replace("http://", "https://")
                    mid = it.get("msgid", "")
                    idx = it.get("itemidx", "1")
                    articles.append({
                        "title": t.strip(),
                        "link": u,
                        "msgid": mid,
                        "itemidx": idx
                    })
                    last_msgid = mid
                    last_itemidx = idx

                has_more = bool(getalbum_resp.get("continue_flag") == 1)
                time.sleep(0.5)  # 优雅微延迟
            except Exception:
                break

        # 去重
        seen_links = set()
        dedup_articles = []
        for art in articles:
            l = art["link"]
            if l not in seen_links:
                seen_links.add(l)
                dedup_articles.append(art)

        if not album_title and dedup_articles:
            album_title = f"微信专题_{album_id}"

        return {
            "album_title": album_title,
            "nickname": nickname or "微信公众号",
            "biz": biz,
            "album_id": album_id,
            "articles": dedup_articles
        }
