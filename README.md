# infolio MiniPage Skill

让 AI Agent 为 infolio 设计、生成、修改和打包 MiniPage 模板，包含 SDK 文档、响应式起始模板、多语言编译和 ZIP 打包脚本。本地功能可离线使用，联网功能与远程图片需要网络。

## 环境要求

- 支持 Agent Skills，且能读写文件、执行命令的 AI 工具。
- Python 3.8 或更高版本；配套脚本仅使用标准库，无需安装 Python 依赖。
- 使用下方安装命令时，需要 Node.js 和 npm。
- 运行生成的模板需要 infolio 1.4.0 或更高版本；具体能力仍以宿主支持为准。

## 安装

下载本仓库的 ZIP，解压后将文件夹命名为 `infolio-minipage-skill`。在该文件夹的父目录运行：

```sh
npx skills add ./infolio-minipage-skill --skill infolio-minipage-skill --global
```

按提示选择要安装到的 Agent。也可以将完整文件夹放入所用 Agent 的技能目录，具体方式见 [skills 安装文档](https://github.com/vercel-labs/skills)。

保留 `SKILL.md`、`agents/`、`references/`、`scripts/` 和 `assets/`，不要只复制 `SKILL.md`。

## 使用

向 Agent 描述需求，例如：

> 使用 infolio-minipage-skill 生成一个阅读记录页面，支持添加书籍、阅读进度和笔记，适配手机与桌面，支持中文和英文。源码输出到技能目录之外，完成静态检查并交付模板 ZIP。

将生成的模板 ZIP 导入 infolio 的 MiniPage 页面使用。页面数据由宿主提供的 `window.infolio` SDK 管理，直接打开 HTML 无法完整运行；静态检查通过后仍需在 app 中验证实际交互。

开发细节见 [技能工作流](SKILL.md)、[模板编写规范](references/template-authoring.md)和 [SDK API](references/sdk-api.md)。

## 使用许可

本仓库采用 [MIT License](LICENSE)。允许使用、修改、分发和商业使用；分发本仓库内容或其重要部分时，须保留版权与许可声明。软件按原样提供，不附带担保。
