import re
import json
import time
import urllib.parse
from typing import Dict, Any, List, Optional
import requests

class WeChatProfileScraper:
    """
    微信历史文章全量爬取器 (基于 profile_ext 接口)
    当用户在电脑微信中向下滚动加载公众号历史文章时，
    微信会向腾讯服务器发送 profile_ext?action=getmsg 请求。
    只要提供捕获到的 appmsg_token, key, pass_ticket 与 Cookie，
    本模块即可无限制翻页拉取该公众号过去的全部历史文章！
    """

    BASE_URL = "https://mp.weixin.qq.com/mp/profile_ext"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    }

    def __init__(
        self,
        biz: str,
        appmsg_token: str,
        cookie: str,
        key: str = "",
        pass_ticket: str = "",
        uin: str = "",
        delay: float = 2.0
    ):
        self.biz = biz
        self.appmsg_token = appmsg_token
        self.cookie = cookie
        self.key = key
        self.pass_ticket = pass_ticket
        self.uin = uin
        self.delay = delay
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.session.headers["Cookie"] = self.cookie

    @classmethod
    def from_captured_url(cls, captured_url: str, cookie: str, delay: float = 2.0) -> "WeChatProfileScraper":
        """从抓包捕获到的完整请求 URL 中自动解析参数"""
        parsed = urllib.parse.urlparse(captured_url)
        params = urllib.parse.parse_qs(parsed.query)

        biz = params.get("__biz", [""])[0]
        appmsg_token = params.get("appmsg_token", [""])[0]
        key = params.get("key", [""])[0]
        pass_ticket = params.get("pass_ticket", [""])[0]
        uin = params.get("uin", [""])[0]

        if not biz or not appmsg_token:
            raise ValueError("捕获的 URL 中缺少 __biz 或 appmsg_token 参数！")

        return cls(
            biz=biz,
            appmsg_token=appmsg_token,
            cookie=cookie,
            key=key,
            pass_ticket=pass_ticket,
            uin=uin,
            delay=delay
        )

    def fetch_all_history(
        self,
        max_articles: Optional[int] = None,
        progress_callback: Optional[any] = None
    ) -> List[Dict[str, Any]]:
        """
        翻页拉取该公众号的所有历史文章
        :param max_articles: 最大抓取篇数，None 表示抓取全部
        :param progress_callback: fn(current, total)
        :return: 文章列表
        """
        offset = 0
        count = 10
        all_articles: List[Dict[str, Any]] = []

        while True:
            params = {
                "action": "getmsg",
                "__biz": self.biz,
                "f": "json",
                "offset": offset,
                "count": count,
                "is_ok": 1,
                "scene": 126,
                "uin": self.uin,
                "key": self.key,
                "pass_ticket": self.pass_ticket,
                "wxtoken": "",
                "appmsg_token": self.appmsg_token,
                "x5": 0,
            }

            resp = self.session.get(self.BASE_URL, params=params, timeout=20)
            data = resp.json()

            ret = data.get("ret")
            if ret != 0:
                errmsg = data.get("errmsg", "未知错误")
                raise RuntimeError(f"请求文章列表失败 (ret={ret}): {errmsg}")

            can_msg_continue = data.get("can_msg_continue", 0)
            general_msg_list_raw = data.get("general_msg_list", "{}")
            msg_data = json.loads(general_msg_list_raw)
            msg_list = msg_data.get("list", [])

            if not msg_list:
                break

            for item in msg_list:
                comm_msg_info = item.get("comm_msg_info", {})
                msg_type = comm_msg_info.get("type")
                create_time = comm_msg_info.get("datetime", 0)
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time)) if create_time else ""

                # 图文消息
                if msg_type == 49:
                    app_msg_ext_info = item.get("app_msg_ext_info", {})
                    if app_msg_ext_info:
                        title = app_msg_ext_info.get("title", "")
                        content_url = app_msg_ext_info.get("content_url", "")
                        digest = app_msg_ext_info.get("digest", "")
                        if content_url:
                            # 修复转义
                            clean_link = content_url.replace(r"\/", "/").replace("&amp;", "&")
                            all_articles.append({
                                "title": title.strip(),
                                "link": clean_link,
                                "create_time": time_str,
                                "digest": digest.strip(),
                            })

                        # 多图文子文章
                        multi_items = app_msg_ext_info.get("multi_app_msg_item_list", [])
                        for sub_item in multi_items:
                            sub_title = sub_item.get("title", "")
                            sub_url = sub_item.get("content_url", "")
                            sub_digest = sub_item.get("digest", "")
                            if sub_url:
                                sub_link = sub_url.replace(r"\/", "/").replace("&amp;", "&")
                                all_articles.append({
                                    "title": sub_title.strip(),
                                    "link": sub_link,
                                    "create_time": time_str,
                                    "digest": sub_digest.strip(),
                                })

            if progress_callback:
                progress_callback(len(all_articles))

            if max_articles and len(all_articles) >= max_articles:
                all_articles = all_articles[:max_articles]
                break

            if can_msg_continue != 1:
                break

            offset += count
            time.sleep(self.delay)

        return all_articles
