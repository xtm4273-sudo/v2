# SimpleIntellReportV2 二期项目地图

本项目按一期的思路整理：代码归代码，规范归规范，正式报告归正式报告，测试和临时产物单独放。

## 文件夹功能

| 文件夹 | 大白话 | 专业说明 |
| --- | --- | --- |
| `Data/` | 管数据怎么拿、怎么检查、怎么变干净 | 接口请求、数据校验、清洗契约、样例数据 |
| `ReportGenerator/` | 管每一章报告怎么生成 | 章节 generator、renderer、AI writer、报告管理 |
| `ReportWrapping/` | 管报告怎么包装成最终样式 | HTML/PDF 包装、排版和模板能力 |
| `AnaModel/` | 管大模型怎么调用 | 模型客户端与调用封装 |
| `RuntimeSupport/` | 管运行时辅助能力 | 配置、错误处理、运行记录等公共支撑 |
| `Logger/` | 管日志 | 日志封装与输出 |
| `Tools/` | 管可复用小工具 | 绘图、分析工具或外部工具封装 |
| `guidelines/` | 管每章该怎么写 | 章节写作规则、分析口径、提示词素材 |
| `DevelopmentDocs/` | 管开发过程说明 | 接口文档、缺失数据清单、阶段性方案和约定 |
| `tests/` | 管代码能不能跑对 | 自动化测试用例 |
| `Reports/` | 管正式报告产物 | 对外交付或准生产报告输出 |
| `test_output/` | 管测试跑出来的东西 | 测试报告、验证报告、渲染样例 |
| `tmp/` | 管临时中间文件 | PDF 渲染图、docx 拆解文本等临时缓存 |
| `archive/` | 管历史和多余产物 | 归档旧输出、临时渲染、手工测试报告，保留原路径结构 |

## 当前归档口径

- 正式报告留在 `Reports/`。
- mock、realtest、comment rules、AI action reserved 等验证报告放到 `test_output/report_validation/`。
- 临时拆解、渲染缓存放到 `tmp/`。
- 多余或阶段性产物统一归档到 `archive/{日期}_cleanup/`，并补充 `manifest.md` 说明移动范围。
- `.DS_Store`、`__pycache__`、`.pytest_cache`、`.venv` 不作为项目内容维护。

更细的规则见 `DevelopmentDocs/文件管理手册.md`。

## 环境依赖

运行报告生成脚本：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

本地开发和跑测试：

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest
```

依赖分层：

- `requirements.txt`：报告生成运行依赖，包括接口/AI、HTML/PDF 渲染和 PDF 合并。
- `requirements-dev.txt`：在运行依赖基础上增加测试依赖。

## 完整报告 AI 文案

完整报告默认强制使用一次大模型调用，同时生成第 3、4、5、7 章行动指南和第 8 章综合总结。任一输出未通过结构、数字或事实校验时，不生成正式 PDF。

本地配置写入项目根目录 `.env`，服务器使用环境变量或 Secret 注入：

```text
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
AI_API_KEY=填写真实密钥
AI_REQUIRED=true
```

真实密钥不得写入源码、`.env.example`、报告或日志。

## 二期整本报告整合

可以用 `compile_phase2_report.py` 将二期 1-8 章整合成一份报告包。脚本会把每章 Markdown 复制到整合目录的 `chapters/` 下，方便单章修改；外层会生成整本 `integrated_report.md`、`integrated_report.html`、`integrated_report.pdf`。

```bash
python compile_phase2_report.py --job-id 86002542 --calmonth 202606
```

修改某章后，直接编辑：

```text
Reports/integrated_report_86002542_202606/chapters/chapter2_final_report.md
```

然后重新编译整本报告：

```bash
python compile_phase2_report.py --job-id 86002542 --calmonth 202606 --from-chapters
```

如果只想保留每章原始 PDF 版式并拼成一本，可使用：

```bash
python compile_phase2_report.py --job-id 86002542 --calmonth 202606 --from-chapters --pdf-mode merge
```
