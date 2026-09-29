import os
import re
import html
import time
import base64
import logging
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Callable
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class WeChatPDFConverter:
    """
    微信公众号文章转高保真 PDF 转换器
    采用 Base64 本地内联渲染技术，破解图片懒加载与防盗链，秒级生成高清 PDF
    """

    COMMON_BROWSER_PATHS = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    CLEAN_CSS = """
    <style>
        /* 微信正文强制可见 */
        #js_content, .rich_media_content, #img-content, body {
            visibility: visible !important;
            opacity: 1 !important;
            display: block !important;
        }

        /* 隐藏非正文无关元素 */
        #js_pc_qr_code, .qr_code_pc, #js_profile_qrcode,
        .rich_media_area_extra, .sns_share, .reward_area,
        .like_comment_wraper, #js_tags, .weui-dialog,
        .rich_media_tool, .profile_container, .article_bottom_share,
        #js_bottom_ad_area, .rich_media_sub_title, .wr_share_wrapper,
        .wx_expand_bottom_btn, #js_cmt_container, .share_media_list {
            display: none !important;
        }

        /* 优化排版与打印 */
        body {
            background-color: #ffffff !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif !important;
            margin: 0 auto !important;
            padding: 10px 15px !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
            max-width: 820px !important;
        }

        .rich_media_content {
            width: 100% !important;
            max-width: 100% !important;
            overflow: visible !important;
        }

        /* 图片防断裂与自适应 */
        img {
            visibility: visible !important;
            opacity: 1 !important;
            max-width: 100% !important;
            height: auto !important;
            page-break-inside: avoid !important;
            break-inside: avoid !important;
            display: block !important;
            margin: 16px auto !important;
        }

        /* 代码块与表格排版 */
        pre, code, table, blockquote {
            page-break-inside: avoid !important;
            break-inside: avoid !important;
        }

        h1, h2, h3, h4, h5, h6 {
            page-break-after: avoid !important;
            break-after: avoid !important;
        }

        @page {
            size: A4;
            margin: 1.2cm 1.0cm;
        }
    </style>
    """

    def __init__(self, browser_path: Optional[str] = None, timeout: int = 35):
        self.browser_path = self._resolve_browser_path(browser_path)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })

    def _resolve_browser_path(self, custom_path: Optional[str]) -> str:
        if custom_path and os.path.exists(custom_path):
            return custom_path
        for p in self.COMMON_BROWSER_PATHS:
            if os.path.exists(p):
                return p
        raise FileNotFoundError(
            "未找到 Chrome 或 Edge 浏览器可执行程序。请安装 Chrome 并在配置中指定 browser_path。"
        )

    @staticmethod
    def sanitize_filename(name: str, max_length: int = 80) -> str:
        """清洗文件名中的 Windows 非法字符"""
        clean = re.sub(r'[\\/*?:"<>|\r\n\t]', "_", name).strip()
        clean = re.sub(r'_+', '_', clean).strip('_')
        if len(clean) > max_length:
            clean = clean[:max_length].rstrip()
        return clean or "untitled"

    def _fetch_single_image_base64(self, img_url: str) -> Optional[str]:
        """下载单个图片并转为 Base64 Data URI"""
        mime = "image/png"
        if "wx_fmt=jpeg" in img_url or "wx_fmt=jpg" in img_url:
            mime = "image/jpeg"
        elif "wx_fmt=gif" in img_url:
            mime = "image/gif"
        elif "wx_fmt=webp" in img_url:
            mime = "image/webp"

        try:
            resp = self.session.get(img_url, headers={"Referer": "https://mp.weixin.qq.com"}, timeout=12)
            if resp.status_code == 200 and resp.content:
                b64 = base64.b64encode(resp.content).decode("ascii")
                return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.warning("下载图片失败: %s - %s", img_url, e)
        return None

    def prepare_clean_html(self, raw_html: str) -> str:
        """
        处理微信 HTML：
        1. 抓取所有图片转 Base64 嵌入（破除防盗链与懒加载）
        2. 清理协议相对 URL，避免 Windows UNC 挂起
        3. 剔除所有无关 JS 与无用 preload
        4. 解除正文 visibility:hidden，注入打印美化 CSS
        """
        # 1. 提取所有图片 URL
        img_urls = list(set(re.findall(r'<img[^>]+data-src=[\x27\x22]([^\x27\x22]+)[\x27\x22]', raw_html)))
        
        # 多线程并发拉取图片
        url_map: Dict[str, str] = {}
        if img_urls:
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(self._fetch_single_image_base64, u): u for u in img_urls}
                for f in as_completed(futures):
                    u = futures[f]
                    try:
                        b64_res = f.result()
                        if b64_res:
                            url_map[u] = b64_res
                    except Exception:
                        pass

        # 2. 替换图片 data-src 为 Base64 src
        def replace_img_tag(match):
            attrs = match.group(1)
            dsrc = match.group(2)
            rest = match.group(3)
            b64_val = url_map.get(dsrc)
            if b64_val:
                return f'<img{attrs}src="{b64_val}"{rest}>'
            return f'<img{attrs}src="{dsrc}"{rest}>'

        processed = re.sub(
            r'<img([^>]+)data-src=[\x27\x22]([^\x27\x22]+)[\x27\x22]([^>]*)>',
            replace_img_tag,
            raw_html,
            flags=re.IGNORECASE
        )

        # 3. 替换掉正文容器内联的 visibility: hidden; opacity: 0;
        processed = re.sub(
            r'style=[\x27\x22][^\x27\x22]*visibility:\s*hidden;?[^\x27\x22]*[\x27\x22]',
            'style="visibility: visible !important; opacity: 1 !important;"',
            processed,
            flags=re.IGNORECASE
        )

        # 4. 去除可能引发 UNC 挂起的相对协议 //
        processed = processed.replace('href="//', 'href="https://').replace('src="//', 'src="https://')

        # 5. 去除所有 <script> 标签
        processed = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', processed, flags=re.IGNORECASE)

        # 6. 使用 BeautifulSoup 清理多余的 modulepreload、dns-prefetch、广告区块
        soup = BeautifulSoup(processed, "html.parser")
        for link in soup.find_all("link"):
            rel = link.get("rel", [])
            if any(r in ["modulepreload", "prefetch", "preload", "dns-prefetch", "preconnect"] for r in rel):
                link.decompose()

        for sel in ["#js_pc_qr_code", ".qr_code_pc", "#js_profile_qrcode", ".rich_media_area_extra"]:
            for el in soup.select(sel):
                el.decompose()

        # 注入 meta referrer 和美化 CSS
        head = soup.find("head")
        meta_ref = soup.new_tag("meta", attrs={"name": "referrer", "content": "no-referrer"})
        css_soup = BeautifulSoup(self.CLEAN_CSS, "html.parser").find("style")
        if head:
            head.insert(0, meta_ref)
            head.append(css_soup)
        else:
            new_head = soup.new_tag("head")
            new_head.append(meta_ref)
            new_head.append(css_soup)
            if soup.html:
                soup.html.insert(0, new_head)

        return str(soup)

    def convert_url_to_pdf(self, url: str, output_path: str, title: Optional[str] = None) -> bool:
        """
        单篇文章 URL 导出为高质量 PDF
        :param url: 文章链接
        :param output_path: 目标 PDF 绝对或相对路径
        :param title: 文章标题（用于日志）
        :return: 是否导出成功
        """
        output_abs = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_abs), exist_ok=True)

        resp = self.session.get(url, timeout=20)
        resp.encoding = "utf-8"
        clean_html = self.prepare_clean_html(resp.text)

        temp_fd, temp_html_path = tempfile.mkstemp(suffix=".html", prefix="wx_clean_")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(clean_html)

            cmd = [
                self.browser_path,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                f"--print-to-pdf={output_abs}",
                temp_html_path
            ]

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=self.timeout
            )
            if not os.path.exists(output_abs) or os.path.getsize(output_abs) == 0:
                err_msg = res.stderr or "未知错误"
                raise RuntimeError(f"PDF 导出失败: {err_msg}")

            return True
        finally:
            if os.path.exists(temp_html_path):
                try:
                    os.remove(temp_html_path)
                except OSError:
                    pass

    def batch_convert(
        self,
        articles: List[Dict[str, Any]],
        output_dir: str,
        delay: float = 1.0,
        progress_callback: Optional[Callable[[int, int, str, bool], None]] = None
    ) -> Dict[str, Any]:
        """
        批量导出文章为 PDF
        :param articles: 文章列表，每项包含 title, link, create_time 等
        :param output_dir: 保存目录
        :param delay: 单篇间隔时间（秒）
        :param progress_callback: fn(current, total, title, success)
        :return: 统计字典 {success: int, failed: int, details: list}
        """
        os.makedirs(output_dir, exist_ok=True)
        success_count: int = 0
        failed_count: int = 0
        details_list: List[Dict[str, Any]] = []
        total = len(articles)

        for idx, item in enumerate(articles, start=1):
            title = str(item.get("title") or f"article_{idx}")
            link = str(item.get("link") or item.get("url") or "")
            if not link:
                continue

            date_prefix = ""
            if "create_time" in item and item["create_time"]:
                date_prefix = item["create_time"][:10] + "_"

            safe_title = self.sanitize_filename(title)
            pdf_filename = f"{idx:02d}_{date_prefix}{safe_title}.pdf"
            target_pdf = os.path.join(output_dir, pdf_filename)

            # 已存在跳过
            if os.path.exists(target_pdf) and os.path.getsize(target_pdf) > 1024:
                success_count += 1
                details_list.append({"title": title, "status": "skipped", "path": target_pdf})
                if progress_callback:
                    progress_callback(idx, total, title, True)
                continue

            try:
                self.convert_url_to_pdf(link, target_pdf, title=title)
                success_count += 1
                details_list.append({"title": title, "status": "success", "path": target_pdf})
                if progress_callback:
                    progress_callback(idx, total, title, True)
            except Exception as e:
                failed_count += 1
                details_list.append({"title": title, "status": "failed", "error": str(e)})
                if progress_callback:
                    progress_callback(idx, total, title, False)

            if delay > 0 and idx < total:
                time.sleep(delay)

        return {"success": success_count, "failed": failed_count, "details": details_list}
