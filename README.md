# dsh-pdf2md

[English](README.en.md) | 中文

把 PDF、Word、PPT、Excel、HTML 转成 Markdown 或纯文本；**遇到扫描件会拒绝，而不是吐一个空文件。**

A DSH skill that converts documents to Markdown or plain text — and tells the
truth about what the conversion could not do.

## 为什么做这个

现成的转换库（`pymupdf`、`markitdown`）都很好，但它们不解决"该在什么时候用哪个"，
也不会阻止你踩最贵的一个坑：

> 扫描版 PDF 没有文字层，提取出来是空的。工具会老老实实写出一个 0 字节的 `.md`，
> 下游拿着一份空文件，照样生成一段自信的胡说。

这个 skill 的核心不是转换，是**边界**：

- `probe` 先判断有没有文字层，只读、极快
- 扫描件 → `convert` 退出码 **2**，**不写任何文件**，并说明下一步选项
- `--format txt` 永远输出纯文本，不会把 Markdown 伪装成 `.txt`

## 安装

### 作为 DSH 插件（推荐）

```bash
dsh plugin --profile web add dsh-pdf2md
```

桌面客户端把 profile 名换成你的（默认 `desktop`）：

```bash
dsh plugin --profile desktop add dsh-pdf2md
```

`dsh plugin add` 会把包装进 profile，**并自动登记到 `dsh.profile.bundles`**（实测：全新 profile 一条命令，bundles 就多出这一项）。重启 DSH 后，技能清单里出现 `pdf2md`。

不用 `dsh` 命令的话，也可以 `pnpm add dsh-pdf2md`，再手动把包名加进 profile `package.json` 的 `dsh.profile.bundles`。

### Python 依赖（必须）

`scripts/pdf2md.py` 需要 Python 3.10+ 和以下库：

```bash
<python> -m pip install -r skills/pdf2md/requirements.txt
# 国内建议加镜像
<python> -m pip install -r skills/pdf2md/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

用 `doctor` 验证：

```bash
<python> skills/pdf2md/scripts/pdf2md.py doctor
```

找不到合适的解释器时，按顺序试：`$PDF2MD_PYTHON` → 工作区 `.venv/Scripts/python.exe`
→ `.venv/bin/python` → `python3` → `python`，第一个通过 `doctor` 的就能用。

## 用法

```bash
# 1. 先探（只读）
python scripts/pdf2md.py probe report.pdf

# 2. 再转
python scripts/pdf2md.py convert report.pdf --out ./out
python scripts/pdf2md.py convert report.pdf --engine structure --pages 1-6
python scripts/pdf2md.py convert ./docs --format txt --tables-csv
```

| 参数 | 作用 |
|---|---|
| `--out DIR` | 输出目录，默认与源文件同目录 |
| `--engine auto\|structure\|text` | 引擎，见下表 |
| `--format md\|txt` | `txt` 永远是纯文本 |
| `--pages 1-3,7` | PDF 页码范围 |
| `--tables-csv` | 同时把检测到的表格导出成 CSV |

### 两个引擎

| | `structure` | `text` |
|---|---|---|
| 库 | pymupdf4llm | markitdown |
| 保留标题层级 | **是** | 否 |
| 格式 | 仅 PDF | PDF/DOCX/PPTX/XLSX/HTML 等 |
| 适合 | 要读、要引用的文档 | 喂给模型、混合格式 |

实测（24 页中文公文）：

- `structure` 取 6 页 → 3 708 字符，10 个标题行
- `text` 取全本 → 18 831 字符，0 个标题行

两者不是"谁更好"，是回答不同的问题。

## 质量边界

**别承诺做不到的事。** 详见 [`skills/pdf2md/references/quality.md`](skills/pdf2md/references/quality.md)：

- 合并单元格：内容在，分组丢失
- 双栏排版：可能串行
- 公式：变成 Unicode 碎片，不是 LaTeX
- 扫描件：什么都没有，需要先 OCR

## 沙箱提示

子进程常被限制在工作区内写文件，即使外层 shell 不受限。若在工作区外写入报
`PermissionError`，不是 skill 坏了 —— 把输出放进工作区即可。

## 开发

```bash
python -m pytest tests -q          # 12 个测试，测试数据在运行时生成
node --check lib/startup.js        # 插件语法
npm pack --dry-run                 # 看会发布哪些文件
```

CI 在 Python 3.10 / 3.12 / 3.13 和 Node 20 上跑同样三项检查。

## 发布

```bash
npm publish --access public
```

发布前请替换 `package.json` 里的 `author` / `repository` 字段（当前未填写）。

## 许可

MIT。转换库各自的许可证独立：`pymupdf` 为 AGPL-3.0，`markitdown` 为 MIT —— 若你
分发本 skill，请注意 `pymupdf` 的 AGPL 传染性。
