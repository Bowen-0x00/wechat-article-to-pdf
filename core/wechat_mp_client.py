import time
import random
import logging
from typing import List, Dict, Any, Optional, Callable
import requests

logger = logging.getLogger(__name__)

class WeChatMPClient:
    """
    微信公众平台接口客户端
    借用微信公众号后台的“图文超链接搜索”功能拉取指定公众号的所有历史文章
    """

    BASE_URL = "https://mp.weixin.qq.com"

    def __init__(self, token: str, cookie: str, delay: float = 2.5):
        self.token = str(token).strip()
        self.cookie = str(cookie).strip()
        self.delay = delay
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": f"{self.BASE_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token={self.token}&lang=zh_CN",
            "Host": "mp.weixin.qq.com",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": self.cookie,
        })

    def is_configured(self) -> bool:
        """检查凭证是否已配置"""
        return bool(self.token and self.cookie)

    def search_account(self, query: str) -> List[Dict[str, Any]]:
        """
        根据公众号名称或微信号搜索公众号，获取其 fakeid (__biz)
        """
        url = f"{self.BASE_URL}/cgi-bin/searchbiz"
        params = {
            "action": "search_biz",
            "begin": 0,
            "count": 5,
            "query": query,
            "token": self.token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": 1,
        }

        resp = self.session.get(url, params=params, timeout=15)
        data = resp.json()

        base_resp = data.get("base_resp", {})
        ret = base_resp.get("ret")
        if ret == 200003 or ret == 200013:
            err_msg = base_resp.get("err_msg", "凭证失效或频率受限")
            raise PermissionError(f"微信公众平台凭证已失效或受限 (code {ret}): {err_msg}。请更新 Token 和 Cookie。")
        elif ret != 0:
            raise RuntimeError(f"搜索公众号失败: {data}")

        return data.get("list", [])

    def fetch_all_articles(
        self,
        fakeid: str,
        max_count: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, List[Dict[str, Any]]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        翻页拉取指定 fakeid 公众号的全部历史文章
        :param fakeid: 公众号唯一标识
        :param max_count: 最大拉取篇数，None 表示拉取全部
        :param progress_callback: 进度回调函数 fn(current, total, article_list)
        :return: 文章列表字典
        """
        url = f"{self.BASE_URL}/cgi-bin/appmsg"
        articles: List[Dict[str, Any]] = []
        begin = 0
        page_size = 5
        total_count = None

        while True:
            params = {
                "action": "list_ex",
                "begin": begin,
                "count": page_size,
                "fakeid": fakeid,
                "type": 9,
                "query": "",
                "need_author_name": 1,
                "token": self.token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": 1,
            }

            resp = self.session.get(url, params=params, timeout=20)
            data = resp.json()

            base_resp = data.get("base_resp", {})
            ret = base_resp.get("ret")
            if ret == 200003:
                raise PermissionError("微信公众平台登录已过期，请重新登录获取 Token 和 Cookie")
            elif ret == 200013:
                raise RuntimeError("微信请求频率受限 (200013)，请增加延迟稍后再试")
            elif ret != 0:
                raise RuntimeError(f"拉取文章列表异常: {data}")

            if total_count is None:
                total_count = data.get("app_msg_cnt", 0)

            app_msg_list = data.get("app_msg_list", [])
            if not app_msg_list:
                break

            for item in app_msg_list:
                create_time = item.get("create_time", 0)
                update_time = item.get("update_time", 0)
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time)) if create_time else ""

                articles.append({
                    "title": item.get("title", "").strip(),
                    "link": item.get("link", "").strip(),
                    "digest": item.get("digest", "").strip(),
                    "create_time": time_str,
                    "timestamp": create_time,
                    "update_time": update_time,
                    "cover": item.get("cover", ""),
                    "aid": item.get("aid", ""),
                    "appmsgid": item.get("appmsgid", ""),
                })

            if progress_callback:
                progress_callback(len(articles), total_count, articles)

            if max_count and len(articles) >= max_count:
                articles = articles[:max_count]
                break

            begin += page_size
            if begin >= total_count:
                break

            # 随机休眠防风控
            sleep_time = self.delay + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)

        return articles
