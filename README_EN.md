# WeChat Article to PDF Exporter

[English Documentation](README_EN.md) | [中文文档](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Chrome / Edge](https://img.shields.io/badge/Browser-Chrome%20%7C%20Edge-brightgreen.svg)](https://www.google.com/chrome/)

A production-grade Python tool for scraping WeChat Official Account articles, intelligently detecting embedded Table of Contents (TOC) series, and batch-exporting them as publication-ready, numbered A4 PDFs.

---

## 🌟 Key Highlights & The Automated Pipeline

Designed specifically for archiving technical WeChat articles, building offline digital books, and high-quality local reading:

1. **Smart TOC Sniffer (`auto` mode)**:
   Input just a single article URL. The tool parses its source, detects any embedded **Table of Contents (TOC)** / topic album tag, and extracts the full series identifier (`album_id`).
2. **Zero-Credential Public Crawling**:
   Leverages WeChat's public album API to paginate and collect the full series catalogue in seconds, requiring zero login credentials, cookies, or tokens.
3. **High-Fidelity Base64 Asset Inlining**:
   Concurrently fetches all article images and encodes them into Base64 Data URIs directly within the HTML, eliminating WeChat's anti-hotlinking (HTTP 403) and lazy-loading blank image issues.
4. **Publication-Ready Numbered PDFs**:
   Invokes local headless Chrome/Edge with custom print styles to strip extraneous UI widgets (QR codes, bottom buttons, ads, tracking scripts) and outputs cleanly numbered A4 PDFs (`01_xxx.pdf`, `02_xxx.pdf`, etc.).

---

## 🚀 Quick Start & 5 Core Scenarios

### Scenario 1: [Recommended] Single Article to Full Series (`auto`)
Encounter any article that belongs to a multi-part series:
```bash
python cli.py auto "https://mp.weixin.qq.com/s/sample_article_id"
```
**Automated Execution:**
- Discovers the author (e.g. `TechArchitecture`) and the series (e.g. `Distributed Systems in Depth`);
- Paginates through all 20+ articles and dumps `articles.json` & `articles.csv`;
- Concurrently renders each article into an ordered, numbered PDF (`01_xxx.pdf` ~ `20_xxx.pdf`).

> 💡 **Graceful Fallback**: If the article does not contain a TOC tag, the tool automatically exports that standalone article as a clean PDF without data loss.

---

### Scenario 2: Public Album / Topic Link (`album`)
If you copied a public topic album URL (containing `appmsgalbum`) directly from desktop WeChat:
```bash
python cli.py album "https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum&__biz=SAMPLE_BIZ==&album_id=1234567890"
```
- Fetches all articles without login and batch-exports them immediately.
- Use `-n 10` to limit exports, or `--no-pdf` to export only JSON/CSV metadata.

---

### Scenario 3: Standalone Article Export (`export-single`)
Quickly archive any individual article for offline research:
```bash
python cli.py export-single "https://mp.weixin.qq.com/s/sample_article_id"
```
Renders a print-ready A4 PDF with intact vector diagrams and code syntax highlighting within seconds.

---

### Scenario 4: URL Text File Batch Export (`batch-export`)
When an author has not created albums or TOC tags:
1. Copy article URLs from the desktop WeChat client;
2. Save them into a plain text file `urls.txt` (one URL per line):
   ```text
   https://mp.weixin.qq.com/s/sample_article_1
   https://mp.weixin.qq.com/s/sample_article_2
   https://mp.weixin.qq.com/s/sample_article_3
   ```
3. Run batch export:
   ```bash
   python cli.py batch-export urls.txt
   ```

---

### Scenario 5: Full Account Historical Archiving (`history`)
Using a network packet inspector (e.g., **Reqable** or **Fiddler**):
Scroll down in the target account profile inside desktop WeChat to capture the `profile_ext` request:
```bash
python cli.py history "CAPTURED_REQUEST_URL" --cookie "CAPTURED_COOKIE"
```
The script takes over pagination to pull down hundreds of historical articles smoothly.

---

## 🛠️ CLI Reference

```text
usage: cli.py [-h] {auto,info,export-single,crawl,batch-export,album,history,config} ...

WeChat Article to PDF Exporter

positional arguments:
  auto          [Recommended] Smart mode: input article, detect TOC, and batch-export numbered PDFs
  info          Inspect metadata of a single article (author, biz, TOC album)
  export-single Convert a single article to a high-fidelity PDF
  album         Crawl a public topic album and batch export all articles to PDFs
  batch-export  Batch convert URLs from articles.json or a txt list
  crawl         Search and crawl using WeChat Official Platform credentials
  history       Paginate full historical stream using captured profile_ext request
  config        View or update credentials and browser configuration
```

### Options
| Option | Description | Example |
| :--- | :--- | :--- |
| `-n, --max-articles` | Max articles to export (default: all) | `-n 10` |
| `--no-pdf` | Save only metadata (JSON/CSV) without generating PDFs | `--no-pdf` |
| `-o, --output-dir` | Custom output directory (default: `output`) | `-o D:/MyBooks` |
| `-b, --browser` | Custom Chrome or Edge executable path | `-b "C:/.../chrome.exe"` |
| `--pdf-delay` | Rate-limit delay between PDF exports in seconds | `--pdf-delay 1.5` |

---

## 📂 Output Directory Structure

Generated PDFs and metadata are organized hierarchically:

```text
output/
├── TechBlog/
│   ├── Distributed_Systems/
│   │   ├── articles.json                          # Full metadata catalog
│   │   ├── articles.csv                           # Spreadsheet catalog
│   │   ├── 01_Architecture_Principles.pdf
│   │   ├── 02_Data_Consistency_at_Scale.pdf
│   │   └── ...                                    # Sequentially numbered
```

---

## ⚙️ Installation & Requirements

1. **Python Environment**: Python 3.8+
   ```bash
   pip install -r requirements.txt
   ```
2. **Browser**: Google Chrome or Microsoft Edge installed on the host machine (no external chromedriver download needed; uses native headless rendering).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
