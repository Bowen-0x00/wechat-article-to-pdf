import re
import html
import json
import time
from typing import Dict, Any, Optional
import requests

class ArticleExtractor:
    """微信公众号单篇文章元数据提取器"""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.timeout = timeout

    @staticmethod
    def is_captcha_or_invalid(html_content: str, resp_url: str = "") -> bool:
        if "wappoc_appmsgcaptcha" in resp_url or "secitptpage/verify" in html_content:
            return True
        if (
            'id="js_content"' not in html_content
            and "id='js_content'" not in html_content
            and "rich_media_content" not in html_content
            and "picture_page_info_list" not in html_content
            and "window.cgiDataNew" not in html_content
        ):
            return True
        return False

    def extract_from_url(self, url: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        抓取并解析文章元数据
        :param url: 微信文章链接
        :param max_retries: 遇到验证码拦截时的最大重试次数
        :return: 包含 title, nickname, user_name, biz, publish_time, raw_html 等字典
        """
        clean_url = url.strip()
        html_content = ""
        for attempt in range(max_retries):
            resp = self.session.get(clean_url, timeout=self.timeout)
            resp.encoding = "utf-8"
            html_content = resp.text
            if not self.is_captcha_or_invalid(html_content, resp.url):
                break
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
                self.session = requests.Session()
                self.session.trust_env = False
                self.session.headers.update(self.DEFAULT_HEADERS)

        return self.extract_from_html(html_content, clean_url)

    @staticmethod
    def _decode_js_str(val: str) -> str:
        if not val:
            return ""
        s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), val)
        s = s.replace(r'\n', '\n').replace(r'\r', '').replace(r"\'", "'").replace(r'\"', '"')
        return html.unescape(s).strip()
    def extract_from_html(self, html_content: str, url: str = "") -> Dict[str, Any]:
        """
        从 HTML 源码中提取所有公众号和文章元数据
        """
        # 1. 标题
        title = None
        m_title = re.search(r'var\s+msg_title\s*=\s*[\'"]([^\'"]+)[\'"]', html_content)
        if m_title:
            title = m_title.group(1)
        else:
            m_og_title = re.search(r'<meta\s+property=[\'"]og:title[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_content)
            if m_og_title:
                title = m_og_title.group(1)
            else:
                m_tag = re.search(r'<title>([^<]+)</title>', html_content)
                if m_tag:
                    title = m_tag.group(1)

        if title:
            title = html.unescape(title).strip()

        # 2. 公众号昵称 (nickname)
        nickname = None
        m_nick = re.search(r'var\s+nickname\s*=\s*htmlDecode\([\'"]([^\'"]+)[\'"]\)', html_content)
        if m_nick:
            nickname = m_nick.group(1)
        else:
            m_nick_meta = re.search(r'<meta\s+property=[\'"]og:article:author[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_content)
            if m_nick_meta:
                nickname = m_nick_meta.group(1)
            else:
                m_nick_profile = re.search(r'id=[\'"]profile_nickname[\'"][^>]*>([^<]+)<', html_content)
                if m_nick_profile:
                    nickname = m_nick_profile.group(1)
                else:
                    m_nick_cgi = re.search(r'\bnick_name\s*:\s*[\'"]([^\'"]+)[\'"]', html_content)
                    if m_nick_cgi:
                        nickname = self._decode_js_str(m_nick_cgi.group(1))

        if nickname:
            nickname = html.unescape(nickname).strip()

        # 3. 公众号原始 ID (user_name: gh_xxxx)
        user_name = None
        m_username = re.search(r'(?:var\s+user_name\s*=|\buser_name\s*:)\s*[\'"](gh_[^\'"]+)[\'"]', html_content)
        if m_username:
            user_name = m_username.group(1)

        # 4. 公众号唯一标识 __biz
        biz = None
        m_biz = re.search(r'(?:var\s+__biz\s*=|\bbizuin\s*:)\s*[\'"]([^\'"]+)[\'"]', html_content)
        if m_biz:
            biz = m_biz.group(1)
        else:
            # 尝试从 URL 或其他脚本中匹配 __biz
            m_biz_url = re.search(r'__biz=([a-zA-Z0-9+=/]{8,})', url or "")
            if not m_biz_url:
                m_biz_url = re.search(r'__biz=([a-zA-Z0-9+=/]{8,})', html_content)
            if m_biz_url:
                biz = m_biz_url.group(1)

        # 5. 发布时间
        publish_time_str = None
        timestamp = None
        m_time = re.search(r'(?:var\s+ct\s*=|var\s+publish_time\s*=|\bori_create_time\s*:)\s*[\'"]?(\d{9,10})[\'"]?', html_content)
        if m_time:
            timestamp = int(m_time.group(1))
            publish_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        else:
            m_ctime_str = re.search(r'\bcreate_time\s*:\s*[\'"](\d{4}-\d{2}-\d{2}[^\'"]*)[\'"]', html_content)
            if m_ctime_str:
                publish_time_str = m_ctime_str.group(1).strip()

        # 6. 文章作者签名 (Author)
        author = None
        m_author = re.search(r'var\s+author\s*=\s*htmlDecode\([\'"]([^\'"]+)[\'"]\)', html_content)
        if m_author:
            author = html.unescape(m_author.group(1)).strip()

        # 7. 摘要 (digest)
        digest = None
        m_digest = re.search(r'(?:var\s+msg_desc\s*=|\bcontent_noencode\s*:)\s*[\'"]([^\'"]+)[\'"]', html_content)
        if m_digest:
            digest = self._decode_js_str(m_digest.group(1))
        else:
            m_og_desc = re.search(r'<meta\s+property=[\'"]og:description[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_content)
            if m_og_desc:
                digest = self._decode_js_str(m_og_desc.group(1))

        # 8. 话题/合集 ID (TOC album_id)
        album_id = None
        album_url = None
        m_album = re.search(r'album[a-zA-Z0-9_]*[:=][\x27\x22]?(\d{15,})[\x27\x22]?', html_content)
        if not m_album:
            m_album = re.search(r'[\x27\x22]album_id[\x27\x22]\s*:\s*[\x27\x22]?(\d+)[\x27\x22]?', html_content)
        if m_album:
            album_id = m_album.group(1)
            if biz:
                album_url = f"https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum&__biz={biz}&album_id={album_id}"

        return {
            "title": title or "未知标题",
            "nickname": nickname or "未知作者",
            "user_name": user_name or "",
            "biz": biz or "",
            "publish_time": publish_time_str or "",
            "timestamp": timestamp or 0,
            "author": author or "",
            "digest": digest or "",
            "album_id": album_id or "",
            "album_url": album_url or "",
            "url": url,
            "raw_html": html_content,
        }
