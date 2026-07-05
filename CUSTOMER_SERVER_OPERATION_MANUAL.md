# 三棵树智能经营分析报告部署与操作手册

## 1. 交付包说明

交付压缩包用于部署到客户服务器，包内包含：

- 报告生成源码：`Data/`、`ReportAI/`、`ReportGenerator/`、`ReportWrapping/`、`RuntimeSupport/` 等。
- 运行脚本：`run_server_full_report.sh`、`run_windows_full_report.ps1`、`run_full_report_strict.py`、`run_chapter*.py`。
- 依赖清单：`requirements.txt`。
- 配置模板：`.env.example`。
- 本操作手册：`CUSTOMER_SERVER_OPERATION_MANUAL.md`。

交付包不包含 `.env`、真实密钥、历史报告、临时文件、虚拟环境、测试缓存和开发用产物。

## 2. 服务器要求

- Python 3.11 或以上。
- 可访问三棵树 BI 接口地址。
- 可访问大模型接口地址，默认配置为 DeepSeek OpenAI-compatible API。
- Linux/macOS 服务器需要 `bash`、`unzip`。
- Windows 服务器需要 PowerShell 和 Python 启动器 `py`。

## 3. Linux/macOS 首次部署

把压缩包上传到服务器，例如 `/opt/skshu/`，然后执行：

```bash
cd /opt/skshu
unzip SimpleIntellReportV2_customer_server_*.zip
cd SimpleIntellReportV2_customer_server
chmod +x run_server_full_report.sh run_chapter.sh
./run_server_full_report.sh 06427 202606 202605 刘晨
```

首次执行会自动生成 `.env` 并停止。编辑 `.env`：

```text
SKSHU_BI_API_KEY=真实接口apikey
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
AI_API_KEY=真实大模型apikey
AI_REQUIRED=true
```

保存后重新执行：

```bash
./run_server_full_report.sh 06427 202606 202605 刘晨
```

## 4. Windows 首次部署

解压到例如 `C:\skshu\SimpleIntellReportV2_customer_server`，用 PowerShell 进入目录：

```powershell
cd C:\skshu\SimpleIntellReportV2_customer_server
.\run_windows_full_report.ps1 -JobId 06427 -Calmonth 202606 -ReportPeriod 202605 -Name "刘晨"
```

首次执行会生成 `.env` 并停止。填写 `.env` 后，重新执行同一条命令。

## 5. 生成完整报告

Linux/macOS 推荐命令：

```bash
./run_server_full_report.sh <工号> <取数月份YYYYMM> <报告截止月份YYYYMM> <姓名>
```

示例：

```bash
./run_server_full_report.sh 06427 202606 202605 刘晨
```

Windows 推荐命令：

```powershell
.\run_windows_full_report.ps1 -JobId 06427 -Calmonth 202606 -ReportPeriod 202605 -Name "刘晨"
```

输出目录：

```text
Reports/server_live_strict/{取数月份}/{工号_姓名}/
```

重点文件：

- `pdf/{姓名}_{生成日期}.pdf`：最终 PDF，目录下只保留这一份 PDF，例如 `刘晨_20260630.pdf`。
- `html/full_report.html`：最终 HTML。
- `markdown/full_report.md`：最终 Markdown。
- `diagnostics.json`：诊断日志。
- `raw/`：接口原始响应。
- `cleaned/`：清洗后的中间数据。

## 6. 生成单章报告

Linux/macOS：

```bash
./run_chapter.sh 3 06427 202606
./run_chapter.sh all 06427 202606
```

也可以显式传入接口 key：

```bash
./run_chapter.sh 3 06427 202606 --api-key 真实接口apikey
```

单章输出默认在 `Reports/chapter*_api_*` 目录下。

## 7. 常见问题

缺少接口 key：

- 检查 `.env` 是否存在。
- 检查 `SKSHU_BI_API_KEY` 是否已填写真实值。

缺少大模型 key：

- 检查 `AI_API_KEY` 是否已填写真实值。
- 如果客户环境使用其他 OpenAI-compatible 服务，调整 `AI_BASE_URL` 和 `AI_MODEL`。

Playwright/Chromium 安装失败：

- 确认服务器可以访问 Playwright 下载源。
- 必要时让运维预装 Chromium，并按服务器策略开放执行权限。

接口门禁失败：

- 查看命令行输出里的 `module X` 错误。
- 查看对应报告目录下的 `raw/module_X.json` 和 `diagnostics.json`。
- 如果是字段缺失或空数组，应先确认接口返回是否符合约定。

报告月份显示不对：

- `Calmonth` 是接口取数月份。
- `ReportPeriod` 是报告展示截止月份。例如取 `202606` 接口、报告展示 1-5 月，则 `ReportPeriod=202605`。

## 8. 日常维护

- `.env` 不要上传、不要发给外部人员。
- 定期清理 `Reports/` 下的历史报告，避免磁盘占满。
- 升级代码前先备份 `.env` 和需要保留的报告结果。
- 新版本部署后先用一个已知工号跑通完整报告，再批量生成。
