# Windows 演练包运行方式

1. 解压到 `C:\skshu\SimpleIntellReportV2_windows_deploy`
2. 用 PowerShell 进入目录
3. 第一次运行：

```powershell
.\run_windows_full_report.ps1 -JobId 06427 -Calmonth 202606 -ReportPeriod 202606 -Name "刘晨"
```

第一次会自动生成 `.env`，先打开 `.env` 填：

```text
SKSHU_BI_API_KEY=真实接口apikey
AI_API_KEY=真实大模型apikey
```

然后再执行同一条命令。PDF 输出在：

```text
Reports\windows_live_strict\{月份}\{工号_姓名}\pdf\full_report.pdf
```

包内不包含 `.env`、历史报告、临时文件、虚拟环境、测试产物。
