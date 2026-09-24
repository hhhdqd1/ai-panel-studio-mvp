# AI Panel Studio 提交清单

以下材料可作为邮件附件；请先亲自检查内容和运行效果，再决定发送。项目没有自动发送邮件。

## 文件

1. `AI-Panel-Studio-MVP.zip`：完整源码、数据库初始化逻辑、五条高质量示例数据、README、技术与 API 说明、测试、三张浏览器截图，以及本清单。压缩包不含真实 API Key、运行数据库或依赖目录。
2. `核心Prompt记录.pdf`：六段真实对话摘录，明确标记 SDD、DDD、TDD、E2E 阶段；压缩包内对应 `docs/submission/prompt-log.pdf`，可编辑原件为 `核心Prompt记录.md`。
3. `开发流程与工作流说明.pdf`：一页 A4 的开发过程、典型问题与 AI 协作说明；压缩包内对应 `docs/submission/workflow.pdf`，可编辑原件为 `开发流程与工作流说明.md`。
4. `项目运行说明.md`、三张演示截图及 `真实DeepSeek冒烟记录.md`：供评审快速查看，也已包含在源码压缩包中。

## 仍需你完成

- 将 `codex/ai-panel-studio-mvp` 分支推送到 GitHub 或 Gitee，提供仓库链接，并按题目要求邀请评审账号。当前本地仓库没有配置远程地址，不能把压缩包当作仓库链接。
- 核对邮件收件人、主题、附件和截止时间后亲自发送；不要把 `backend/.env` 或 API Key 附上。

本地演示默认使用假模型：在已安装依赖的源码目录运行 `bash scripts/start-local.sh`，访问 `http://127.0.0.1:5173/`。真实 DeepSeek 冒烟记录只描述已经发生的一次调用，不是对外部事实的核验。
