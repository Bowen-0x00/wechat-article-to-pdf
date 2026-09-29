# WeChat Article to PDF Exporter (微信公众号文章转高保真 PDF 导出工具)

[中文文档](README.md) | [English Documentation](README_EN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Chrome / Edge](https://img.shields.io/badge/Browser-Chrome%20%7C%20Edge-brightgreen.svg)](https://www.google.com/chrome/)

微信公众号文章全量抓取、TOC 专栏智能嗅探与高保真独立 PDF 批量导出工具。

---

## 🌟 核心亮点与全自动流水线 (Auto Mode)

本工具专为解决**微信公众号技术文章存档、专栏电子书制作与批量离线阅读**而设计：

1. **智能深度嗅探 (Smart TOC Sniffer)**：
   只需输入任意一篇文章的链接，工具自动逆向分析文章源码，智能识别内嵌的 **TOC 专栏目录（Table of Contents）** 和公开合集 ID（`album_id`）。
2. **免登录公网全量翻页 (Zero-Credential Crawl)**：
   针对公开合集与专栏目录，直接走微信公开 API 翻页，无需任何账号密码、Cookie 或 Token，秒级拉取整套系列所有文章清单。
3. **高保真 Base64 资产内联 (High-Fidelity Offline Engine)**：
   采用多线程并发下载文章内所有高清图片并转为 Base64 Data URI 内嵌于 HTML 中，彻底破解微信图床的防盗链 403 限制与 `data-src` 懒加载空白问题。
4. **出版级独立 PDF 批量生成 (Numbered A4 PDFs)**：
   调用本地 Chrome / Edge 原生无头渲染引擎，注入专用打印样式表清洗无用杂音（广告、点赞赞赏、二维码、底栏推荐），自动按阅读顺序编号输出独立 A4 PDF（如 `01_xxx.pdf`、`02_xxx.pdf`）。

---

## 🚀 极速上手与五大使用场景

### 场景 1：【智能模式】输入单篇文章，全自动拉取整套专栏并导出独立 PDF
平时在微信中看到某篇属于某个专题或专栏的技术文章：
```bash
python cli.py auto "https://mp.weixin.qq.com/s/sample_article_id"
```
**自动执行效果：**
- 自动解析出文章作者（如 `架构笔记`），并自动嗅探出所属专栏（如 `《深入浅出分布式系统》`）；
- 自动分页拉取专栏内全部 20+ 篇文章清单存入 `articles.json` 和 `articles.csv`；
- 逐篇自动渲染导出带序号前缀的独立 PDF（`01_xxx.pdf` ~ `20_xxx.pdf`）。

> 💡 **智能回退**：若文章未包含专栏目录，工具会自动导出该单篇 PDF，不漏掉任何内容。

---

### 场景 2：直接输入公开合集/专辑（Album）链接
若已在电脑版微信中复制了某个公众号的话题合集链接（包含 `appmsgalbum` 的 URL）：
```bash
python cli.py album "https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum&__biz=SAMPLE_BIZ==&album_id=1234567890"
```
- 无需登录，公网直接秒级拉取整套合集清单并自动批量导出 PDF。
- 可加 `-n` 参数限制篇数（如 `-n 10`），或加 `--no-pdf` 仅保存元数据清单。

---

### 场景 3：单篇随手导出（离线研读）
平时看到任意一篇独立优质长文想要本地归档：
```bash
python cli.py export-single "https://mp.weixin.qq.com/s/sample_article_id"
```
约 5~8 秒内即可在 `output/{公众号名}/` 目录下生成包含全部高清流程图和代码高亮的独立 A4 PDF。

---

### 场景 4：批量链接文本导出（无合集时的利器）
若目标作者既没有主页合集，文章也没有内嵌 TOC 标签：
1. 在电脑微信公众号主页的文章列表中，右键复制文章链接；
2. 新建文本文件 `urls.txt`，每行粘贴一个链接：
   ```text
   https://mp.weixin.qq.com/s/sample_article_1
   https://mp.weixin.qq.com/s/sample_article_2
   https://mp.weixin.qq.com/s/sample_article_3
   ```
3. 执行批量导出：
   ```bash
   python cli.py batch-export urls.txt
   ```
   工具将自动并发下载、顺序编号并逐篇导出。

---

### 场景 5：通过抓包 URL 全量回溯历史（一次性抓取几百篇）
利用抓包工具（如 **Reqable** / **Fiddler**）：
在电脑微信公众号主页点击文章并向下滚动一次，捕获发出的 `profile_ext` 请求链接：
```bash
python cli.py history "抓包捕获到的完整请求URL" --cookie "抓包捕获到的Cookie"
```
程序将自动接管翻页，以平稳频率拉取该号过去的全部历史文章清单并批量导出。

---

## 🛠️ CLI 命令行手册

```text
usage: cli.py [-h] {auto,info,export-single,crawl,batch-export,album,history,config} ...

微信公众号文章全量抓取与高保真 PDF 导出工具

positional arguments:
  auto          【推荐】智能模式：输入单篇文章，自动嗅探 TOC 专栏并批量导出整套系列独立 PDF
  info          解析单篇文章元数据（作者/biz/所属合集等）
  export-single 将单篇文章导出为高质量 PDF
  album         抓取公开的微信公众号合集/专辑中的全部文章并批量转为 PDF
  batch-export  根据已有的 articles.json 或 URL 列表文本文件批量导出 PDF
  crawl         基于公众号后台凭证检索爬取
  history       基于电脑微信抓包获得的请求链接全量拉取历史所有文章
  config        查看或设置全局凭证与浏览器路径
```

### 常用参数说明
| 参数 | 说明 | 示例 |
| :--- | :--- | :--- |
| `-n, --max-articles` | 限制最大导出篇数（默认全量导出） | `-n 10` |
| `--no-pdf` | 只拉取保存文章元数据清单 (JSON/CSV)，暂不生成 PDF | `--no-pdf` |
| `-o, --output-dir` | 自定义保存目录（默认为 `output`） | `-o D:/MyBooks` |
| `-b, --browser` | 指定 Chrome 或 Edge 浏览器的执行路径 | `-b "C:/.../chrome.exe"` |
| `--pdf-delay` | 单篇 PDF 导出防风控间隔延迟（秒，默认 1.0） | `--pdf-delay 1.5` |

---

## 📂 生成的目录与文件规范

执行导出后，文件按规范清晰分层存放：

```text
output/
├── 示例公众号/
│   ├── 分布式系统设计全解/
│   │   ├── articles.json                          # 该专栏完整元数据清单
│   │   ├── articles.csv                           # Excel 可读表格清单
│   │   ├── 01_架构设计核心原则.pdf
│   │   ├── 02_高并发场景下的数据一致性.pdf
│   │   └── ...                                    # 全部按阅读顺序编号排列
```

---

## ⚙️ 安装与环境要求

1. **Python 环境**：Python 3.8+
   ```bash
   pip install -r requirements.txt
   ```
2. **系统浏览器**：系统已安装 Google Chrome 或 Microsoft Edge（无需配置 Chromedriver，工具直接调用原生无头渲染）。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
