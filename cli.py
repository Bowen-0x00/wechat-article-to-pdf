import os
import sys
import json
import csv
import time
import argparse
from typing import Optional, Dict, Any, List
import yaml

from core.extractor import ArticleExtractor
from core.wechat_mp_client import WeChatMPClient
from core.pdf_converter import WeChatPDFConverter
from core.album_crawler import WeChatAlbumCrawler
from core.wechat_profile_scraper import WeChatProfileScraper

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[警告] 读取配置文件失败: {e}")
        return {}
def save_config(cfg: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

def log_info(msg: str) -> None:
    if HAS_RICH and console:
        console.print(f"[cyan]ℹ {msg}[/cyan]")
    else:
        print(f"[*] {msg}")

def log_success(msg: str) -> None:
    if HAS_RICH and console:
        console.print(f"[bold green]✔ {msg}[/bold green]")
    else:
        print(f"[+] {msg}")

def log_error(msg: str) -> None:
    if HAS_RICH and console:
        console.print(f"[bold red]✘ {msg}[/bold red]")
    else:
        print(f"[-] {msg}")

def cmd_info(args: argparse.Namespace) -> None:
    """解析单篇文章信息"""
    url = args.url.strip()
    log_info(f"正在解析文章元数据: {url}")
    extractor = ArticleExtractor()
    try:
        info = extractor.extract_from_url(url)
    except Exception as e:
        log_error(f"解析文章失败: {e}")
        return

    if HAS_RICH and console:
        table = Table(title="微信文章与公众号元数据", show_header=True, header_style="bold magenta")
        table.add_column("字段", style="dim", width=14)
        table.add_column("值")
        table.add_row("文章标题", info.get("title", ""))
        table.add_row("公众号名称", f"[bold yellow]{info.get('nickname', '')}[/bold yellow]")
        table.add_row("作者签名", info.get("author", "") or "-")
        table.add_row("公众号原始ID", info.get("user_name", "") or "-")
        table.add_row("全局Biz标识", info.get("biz", "") or "-")
        table.add_row("发布时间", info.get("publish_time", "") or "-")
        table.add_row("摘要说明", info.get("digest", "") or "-")
        album_url = info.get("album_url", "")
        table.add_row("所属合集/TOC", f"[bold cyan]{album_url}[/bold cyan]" if album_url else "-")
        console.print(table)
    else:
        print("\n--- 微信文章与公众号元数据 ---")
        for k, v in info.items():
            print(f"{k}: {v}")

def cmd_export_single(args: argparse.Namespace) -> None:
    """将单篇文章直接导出为高质量 PDF"""
    url = args.url.strip()
    cfg = load_config()
    browser_path = args.browser or cfg.get("pdf", {}).get("browser_path")
    raw_out = args.output_dir or cfg.get("pdf", {}).get("output_dir", "output")
    out_dir = raw_out if os.path.isabs(raw_out) else os.path.join(PROJECT_ROOT, raw_out)
    extractor = ArticleExtractor()
    log_info("正在获取文章标题...")
    info = extractor.extract_from_url(url)
    title = info.get("title") or "微信文章"
    nickname = info.get("nickname") or "公众号"
    date_prefix = (info.get("publish_time") or "")[:10]
    if date_prefix:
        date_prefix += "_"

    target_dir = os.path.join(out_dir, WeChatPDFConverter.sanitize_filename(nickname))
    safe_title = WeChatPDFConverter.sanitize_filename(title)
    out_pdf = os.path.join(target_dir, f"{date_prefix}{safe_title}.pdf")

    log_info(f"正在渲染并导出 PDF: {title}")
    converter = WeChatPDFConverter(browser_path=browser_path)
    t0 = time.time()
    try:
        converter.convert_url_to_pdf(url, out_pdf, title=title)
        log_success(f"导出成功! ({round(time.time() - t0, 2)}s)")
        print(f"文件位置: {os.path.abspath(out_pdf)}")
    except Exception as e:
        log_error(f"导出失败: {e}")

def cmd_crawl(args: argparse.Namespace) -> None:
    """
    全量抓取作者历史文章，并支持批量导出 PDF
    """
    target = args.target.strip()
    cfg = load_config()
    mp_cfg = cfg.get("wechat_mp", {})
    token = args.token or mp_cfg.get("token")
    cookie = args.cookie or mp_cfg.get("cookie")

    if not token or not cookie:
        log_error("未检测到微信公众平台后台凭证 (token / cookie)！")
        print("\n[说明] 微信公众号的历史文章列表受严格权限保护。")
        print("要拉取某个作者的【全部历史文章】，最安全、稳定的方式是借用微信公众平台后台的搜索接口。")
        print("请按以下方式配置凭证：")
        print("  1. 浏览器访问 https://mp.weixin.qq.com 并扫码登录（个人免费订阅号即可）")
        print("  2. 在地址栏获取 token 参数，在控制台 Network 中获取 Cookie")
        print("  3. 运行命令配置：python cli.py config --token <你的token> --cookie '<你的cookie>'\n")
        return

    # 1. 判断 target 是文章 URL 还是公众号名称
    nickname = target
    fakeid = None
    if target.startswith("http://") or target.startswith("https://"):
        log_info(f"正在从文章解析作者信息: {target}")
        extractor = ArticleExtractor()
        try:
            info = extractor.extract_from_url(target)
            nickname = info.get("nickname") or ""
            fakeid = info.get("biz")
            log_success(f"解析到公众号: {nickname} (biz: {fakeid})")
        except Exception as e:
            log_error(f"解析文章失败: {e}")
            return

    # 2. 搜索并确认公众号 fakeid
    client = WeChatMPClient(token=token, cookie=cookie)
    log_info(f"正在微信公众平台检索作者: {nickname}")
    try:
        accounts = client.search_account(nickname)
    except Exception as e:
        log_error(f"公众平台接口调用失败: {e}")
        return

    if not accounts:
        log_error(f"公众平台未搜索到相关公众号: {nickname}")
        return

    matched_acc = None
    if fakeid:
        for acc in accounts:
            if acc.get("fakeid") == fakeid:
                matched_acc = acc
                break
    if not matched_acc:
        matched_acc = accounts[0]

    raw_out = args.output_dir or cfg.get("pdf", {}).get("output_dir", "output")
    out_dir = raw_out if os.path.isabs(raw_out) else os.path.join(PROJECT_ROOT, raw_out)

    # 3. 拉取所有文章列表
    out_dir = args.output_dir or cfg.get("pdf", {}).get("output_dir", "output")
    author_dir = os.path.join(out_dir, WeChatPDFConverter.sanitize_filename(actual_nickname))
    os.makedirs(author_dir, exist_ok=True)

    log_info(f"正在拉取 {actual_nickname} 的历史文章列表 (请求间隔防风控)...")

    def on_progress(current: int, total: int, arts: List[Dict[str, Any]]) -> None:
        print(f"[*] 已抓取 {current}/{total} 篇文章...")

    try:
        articles = client.fetch_all_articles(
            fakeid=actual_fakeid,
            max_count=args.max_articles,
            progress_callback=on_progress
        )
    except Exception as e:
        log_error(f"抓取文章列表出错: {e}")
        return

    log_success(f"文章列表获取完毕！共拉取到 {len(articles)} 篇文章。")

    # 保存 JSON 和 CSV
    json_path = os.path.join(author_dir, "articles.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    csv_path = os.path.join(author_dir, "articles.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["create_time", "title", "link", "digest", "aid"])
        writer.writeheader()
        for art in articles:
            writer.writerow({
                "create_time": art.get("create_time", ""),
                "title": art.get("title", ""),
                "link": art.get("link", ""),
                "digest": art.get("digest", ""),
                "aid": art.get("aid", ""),
            })

    log_success(f"文章元数据清单已保存:")
    print(f"  - JSON: {os.path.abspath(json_path)}")
    print(f"  - CSV:  {os.path.abspath(csv_path)}")

    # 4. 批量导出 PDF
    if not args.no_pdf and articles:
        log_info(f"开始批量导出高质量 PDF 到: {author_dir}")
        browser_path = args.browser or cfg.get("pdf", {}).get("browser_path")
        converter = WeChatPDFConverter(browser_path=browser_path)

        def on_pdf_progress(cur: int, tot: int, title: str, success: bool) -> None:
            status_text = "[成功]" if success else "[失败]"
            print(f"[{cur}/{tot}] {status_text} {title}")

        results = converter.batch_convert(
            articles=articles,
            output_dir=author_dir,
            delay=args.pdf_delay or 1.0,
            progress_callback=on_pdf_progress
        )
        log_success(f"批量导出完成！成功: {results['success']}，失败: {results['failed']}")

def cmd_batch_export(args: argparse.Namespace) -> None:
    """根据已有 JSON 列表批量导出 PDF"""
    file_path = args.file.strip()
    if not os.path.exists(file_path):
        log_error(f"文件不存在: {file_path}")
        return

    articles: List[Dict[str, Any]] = []
    if file_path.endswith(".json"):
        with open(file_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
    else:
        # 按行读取 URL
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("http"):
                    articles.append({"link": line, "title": ""})

    if not articles:
        log_error("未从文件中解析到文章数据")
        return

    out_dir = args.output_dir or "output"
    converter = WeChatPDFConverter(browser_path=args.browser)
    log_info(f"开始转换 {len(articles)} 篇文章...")
    results = converter.batch_convert(articles, out_dir, delay=args.pdf_delay or 1.0)
    log_success(f"完成！成功: {results['success']}，失败: {results['failed']}")

def cmd_album(args: argparse.Namespace) -> None:
    """抓取公开的微信公众号合集/专辑中的全部文章并批量转为 PDF"""
    album_url = args.url.strip()
    cfg = load_config()
    crawler = WeChatAlbumCrawler()
    log_info(f"正在拉取合集页面数据: {album_url}")
    try:
        data = crawler.extract_album_articles(album_url)
    except Exception as e:
        log_error(f"解析合集失败: {e}")
        return

    album_title = data.get("album_title") or "微信合集"
    nickname = data.get("nickname") or "公众号"
    all_articles = data.get("articles") or []
    log_success(f"合集解析成功: 《{album_title}》 (作者: {nickname})，共包含 {len(all_articles)} 篇文章！")
    if not all_articles:
        log_error("未在该合集中检索到文章链接")
        return

    raw_out = args.output_dir or cfg.get("pdf", {}).get("output_dir", "output")
    out_dir = raw_out if os.path.isabs(raw_out) else os.path.join(PROJECT_ROOT, raw_out)
    target_dir = os.path.join(out_dir, WeChatPDFConverter.sanitize_filename(nickname), WeChatPDFConverter.sanitize_filename(album_title))
    os.makedirs(target_dir, exist_ok=True)

    # 保存完整清单 JSON 和 CSV
    json_path = os.path.join(target_dir, "articles.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    csv_path = os.path.join(target_dir, "articles.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "title", "link"])
        writer.writeheader()
        for i, art in enumerate(all_articles, 1):
            writer.writerow({"index": i, "title": art.get("title", ""), "link": art.get("link", "")})

    log_success(f"合集文章清单已保存: {os.path.abspath(json_path)}")

    export_articles = all_articles
    if getattr(args, "max_articles", None):
        export_articles = all_articles[:args.max_articles]
    if not args.no_pdf:
        log_info(f"开始批量导出高保真 PDF 到: {target_dir}")
        browser_path = args.browser or cfg.get("pdf", {}).get("browser_path")
        converter = WeChatPDFConverter(browser_path=browser_path)

        def on_pdf_progress(cur: int, tot: int, title: str, success: bool) -> None:
            status_text = "[成功]" if success else "[失败]"
            print(f"[{cur}/{tot}] {status_text} {title}")

        results = converter.batch_convert(
            articles=export_articles,
            output_dir=target_dir,
            delay=args.pdf_delay or 1.0,
            progress_callback=on_pdf_progress
        )
        log_success(f"合集批量导出完成！成功: {results['success']}，失败: {results['failed']}")

def cmd_history(args: argparse.Namespace) -> None:
    """通过电脑微信抓包获得的动态请求全量拉取作者历史所有文章"""
    captured_url = args.url.strip()
    cookie = args.cookie.strip() if args.cookie else ""
    cfg = load_config()

    log_info("正在解析抓包参数并拉取作者历史全量文章...")
    try:
        scraper = WeChatProfileScraper.from_captured_url(captured_url, cookie=cookie, delay=args.delay or 1.5)
        def on_prog(cur: int) -> None:
            print(f"[*] 已抓取 {cur} 篇历史文章...")
        articles = scraper.fetch_all_history(max_articles=args.max_articles, progress_callback=on_prog)
    except Exception as e:
        log_error(f"抓取历史文章失败: {e}")
        return

    log_success(f"成功拉取到 {len(articles)} 篇历史文章！")
    out_dir = args.output_dir or cfg.get("pdf", {}).get("output_dir", "output")
    biz_dir = os.path.join(out_dir, f"biz_{scraper.biz[:12]}")
    os.makedirs(biz_dir, exist_ok=True)

    json_path = os.path.join(biz_dir, "articles.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    log_success(f"清单已保存: {json_path}")

    if not args.no_pdf and articles:
        log_info(f"开始批量导出 PDF...")
        converter = WeChatPDFConverter(browser_path=args.browser)
        converter.batch_convert(articles, biz_dir, delay=args.pdf_delay or 1.0)
        log_success("批量导出完成！")
def cmd_auto(args: argparse.Namespace) -> None:
    """
    全自动终极模式：
    输入任意一篇文章链接（或合集链接），
    自动解析作者，自动嗅探内嵌 TOC / 专栏话题目录并获取全部文章链接，
    逐篇批量导出为独立带序号排版的高质量 PDF！
    """
    url = args.url.strip()
    cfg = load_config()
    raw_out = args.output_dir or cfg.get("pdf", {}).get("output_dir", "output")
    out_dir = raw_out if os.path.isabs(raw_out) else os.path.join(PROJECT_ROOT, raw_out)

    # 1. 如果直接是合集链接
    if "appmsgalbum" in url or "album_id=" in url:
        log_info("检测到输入为公开合集链接，直接进入合集全量导出流程...")
        args.url = url
        cmd_album(args)
        return

    # 2. 单篇文章解析与 TOC 嗅探
    log_info(f"正在深度解析文章元数据并嗅探内嵌 TOC 专栏合集: {url}")
    extractor = ArticleExtractor()
    try:
        info = extractor.extract_from_url(url)
    except Exception as e:
        log_error(f"解析文章失败: {e}")
        return

    title = info.get("title") or "微信文章"
    nickname = info.get("nickname") or "公众号作者"
    album_url = info.get("album_url")

    if album_url:
        log_success(f"✔ 成功在文章中嗅探到内嵌专栏合集 (TOC)！")
        log_info(f"专栏地址: {album_url}")
        log_info(f"作者名称: {nickname}")
        
        # 自动调用合集爬虫全量拉取
        args.url = album_url
        cmd_album(args)
    else:
        log_info(f"该文章未包含内嵌 TOC 专栏，为您单独导出本篇文章为独立 PDF...")
        args.url = url
        cmd_export_single(args)
        print("\n[提示] 该文章没有内嵌 TOC 话题合集。若该作者有专门的专题主页，可将合集链接复制后使用 `python cli.py album <合集链接>` 批量下载。")

def cmd_config(args: argparse.Namespace) -> None:
    """查看或更新配置"""
    cfg = load_config()
    if not cfg:
        cfg = {"wechat_mp": {}, "pdf": {}}

    if args.token is not None:
        cfg.setdefault("wechat_mp", {})["token"] = args.token
    if args.cookie is not None:
        cfg.setdefault("wechat_mp", {})["cookie"] = args.cookie
    if args.browser is not None:
        cfg.setdefault("pdf", {})["browser_path"] = args.browser

    if args.token is not None or args.cookie is not None or args.browser is not None:
        save_config(cfg)
        log_success("配置已成功更新并保存！")

    print("\n--- 当前配置 ---")
    current_token = cfg.get("wechat_mp", {}).get("token") or "(未配置)"
    current_cookie = cfg.get("wechat_mp", {}).get("cookie")
    cookie_display = f"{current_cookie[:25]}... (长度 {len(current_cookie)})" if current_cookie else "(未配置)"
    print(f"微信公众平台 Token:  {current_token}")
    print(f"微信公众平台 Cookie: {cookie_display}")
    print(f"浏览器路径:          {cfg.get('pdf', {}).get('browser_path') or '(自动检测 Chrome/Edge)'}")
    print(f"默认输出目录:        {cfg.get('pdf', {}).get('output_dir', 'output')}")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="微信公众号文章全量抓取与高保真 PDF 导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 0. auto (智能自动嗅探 TOC 专栏合集并全量批量导出)
    p_auto = subparsers.add_parser("auto", help="【推荐】智能模式：输入单篇文章，自动嗅探 TOC 专栏并批量导出整套系列独立 PDF")
    p_auto.add_argument("url", help="微信文章链接（或公开合集链接）")
    p_auto.add_argument("-n", "--max-articles", type=int, default=None, help="最大导出篇数")
    p_auto.add_argument("--no-pdf", action="store_true", help="只拉取文章清单 (JSON/CSV)，不导出 PDF")
    p_auto.add_argument("-o", "--output-dir", help="指定保存根目录")
    p_auto.add_argument("-b", "--browser", help="指定 Chrome/Edge 路径")
    p_auto.add_argument("--pdf-delay", type=float, default=1.0, help="导出单篇 PDF 间隔延迟 (秒)")

    # 1. info
    p_info = subparsers.add_parser("info", help="解析单篇文章元数据（作者/biz/发布时间）")
    p_info.add_argument("url", help="微信文章链接")

    # 2. export-single
    p_single = subparsers.add_parser("export-single", help="将单篇文章导出为高质量 PDF")
    p_single.add_argument("url", help="微信文章链接")
    p_single.add_argument("-o", "--output-dir", help="指定保存目录")
    p_single.add_argument("-b", "--browser", help="指定 Chrome/Edge 路径")

    # 3. crawl
    p_crawl = subparsers.add_parser("crawl", help="抓取作者所有历史文章并批量导出 PDF")
    p_crawl.add_argument("target", help="公众号单篇文章链接，或公众号名称")
    p_crawl.add_argument("-n", "--max-articles", type=int, default=None, help="最大抓取篇数 (默认抓取全部)")
    p_crawl.add_argument("--no-pdf", action="store_true", help="只拉取文章清单 (JSON/CSV)，不导出 PDF")
    p_crawl.add_argument("-o", "--output-dir", help="输出根目录")
    p_crawl.add_argument("-b", "--browser", help="指定 Chrome/Edge 路径")
    p_crawl.add_argument("--pdf-delay", type=float, default=1.0, help="导出单篇 PDF 间隔延迟 (秒)")
    p_crawl.add_argument("--token", help="临时指定微信公众平台 Token")
    p_crawl.add_argument("--cookie", help="临时指定微信公众平台 Cookie")

    # 4. batch-export
    p_batch = subparsers.add_parser("batch-export", help="根据已有的 articles.json 或 URL 列表文件批量导出 PDF")
    p_batch.add_argument("file", help="articles.json 或 url.txt 文件路径")
    p_batch.add_argument("-o", "--output-dir", help="输出目录")
    p_batch.add_argument("-b", "--browser", help="指定 Chrome/Edge 路径")
    p_batch.add_argument("--pdf-delay", type=float, default=1.0, help="导出延迟 (秒)")

    # 5. album
    p_alb = subparsers.add_parser("album", help="抓取公开的微信公众号合集/专辑中的全部文章并批量转为 PDF")
    p_alb.add_argument("url", help="微信合集链接 (包含 appmsgalbum 或 album_id)")
    p_alb.add_argument("-n", "--max-articles", type=int, default=None, help="最大导出篇数 (默认导出全部)")
    p_alb.add_argument("--no-pdf", action="store_true", help="只拉取文章清单 (JSON)，不导出 PDF")
    p_alb.add_argument("-o", "--output-dir", help="输出目录")
    p_alb.add_argument("-b", "--browser", help="指定 Chrome/Edge 路径")
    p_alb.add_argument("--pdf-delay", type=float, default=1.0, help="导出延迟 (秒)")
    # 6. history (基于微信抓包链接全量抓取)
    p_his = subparsers.add_parser("history", help="基于电脑微信抓包获得的请求链接全量拉取历史文章并导出 PDF")
    p_his.add_argument("url", help="抓包到的 profile_ext 请求 URL (含 __biz 和 appmsg_token)")
    p_his.add_argument("--cookie", help="抓包请求中的 Cookie (含 pass_ticket/wap_sid)")
    p_his.add_argument("-n", "--max-articles", type=int, default=None, help="最大抓取篇数")
    p_his.add_argument("--no-pdf", action="store_true", help="只拉取文章清单，不导出 PDF")
    p_his.add_argument("-o", "--output-dir", help="输出目录")
    p_his.add_argument("-b", "--browser", help="指定 Chrome/Edge 路径")
    p_his.add_argument("--delay", type=float, default=1.5, help="请求翻页间隔延迟 (秒)")
    p_his.add_argument("--pdf-delay", type=float, default=1.0, help="导出 PDF 延迟 (秒)")

    # 5. config
    p_cfg = subparsers.add_parser("config", help="查看或设置微信公众平台凭证与浏览器配置")
    p_cfg.add_argument("--token", help="微信公众平台 Token")
    p_cfg.add_argument("--cookie", help="微信公众平台 Cookie")
    p_cfg.add_argument("--browser", help="Chrome / Edge 可执行文件路径")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "auto":
        cmd_auto(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "export-single":
        cmd_export_single(args)
    elif args.command == "crawl":
        cmd_crawl(args)
    elif args.command == "album":
        cmd_album(args)
    elif args.command == "batch-export":
        cmd_batch_export(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "config":
        cmd_config(args)
if __name__ == "__main__":
    main()
