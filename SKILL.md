---
name: infolio-minipage-skill
description: 为 infolio 设计、生成、修改和打包离线 MiniPage 模板。用于把用户场景实现为响应式 HTML/CSS/JavaScript、manifest、dataSchema 和多语言资源；适用于新建模板、维护已有模板、调用 window.infolio SDK、检查移动端/平板/桌面端适配、排除外部网络依赖并生成 ZIP。不要用于修改 infolio 宿主、服务端或发布模板。
---

# infolio MiniPage 模板开发

生成能在 infolio MiniPage 沙箱中离线运行的模板。默认使用原生 HTML、CSS 和 JavaScript；只有用户明确要求时才使用框架，并把依赖全部构建进静态产物。

## 工作流

1. 明确页面用途、核心数据、主要操作、语言、视觉偏好和输出目录。信息足够时直接实现，不追问技术细节。
2. 创建新模板时复制 `assets/starter-template/` 到输出目录；维护已有模板时先读取其 `manifest.json`、HTML、CSS、JavaScript 和语言资源。不要在本 skill 目录内生成用户模板。
3. 设计数据前完整读取 [SDK API](references/sdk-api.md)。先确定 `dataSchema`，再写界面；持续增长的数据使用 collection，偏好和小型结构使用 json。
4. 写代码前完整读取 [模板编写规范](references/template-authoring.md)。生成移动优先、同时适配平板和桌面的离线页面；不得调用外部网络或依赖外部运行时资源。
5. 所有固定文案写入 `locales/*.json`，再运行：

   ```sh
   python3 <skill-root>/scripts/compile_locales.py <template-dir>
   ```

6. 完成 HTML、CSS、JavaScript、manifest 和真实界面封面后，先静态检查：

   ```sh
   python3 <skill-root>/scripts/package_template.py <template-dir> --check-only
   ```

7. 修复全部错误，再把 ZIP 输出到模板目录外：

   ```sh
   python3 <skill-root>/scripts/package_template.py <template-dir> <output.zip>
   ```

   已存在的 ZIP 仅在明确需要替换时使用 `--force`。

## 必须遵守

- 只调用 `window.infolio.env.get`、`template.checkForUpdates`、`template.update`、`native.pickImages/pickMedia/downloadAttachment`、`collection.query/create/update/delete` 和 `connectors.list/describe/call`；不实现或复制宿主桥接。新增媒体方法、模板更新及 `connectors` 须检测宿主支持，旧宿主保留可用功能并提示升级。`env.userProfile` 只用于当前账号资料的只读展示回退，不持久化其中的 data URL。
- 模板更新接口仅操作当前 iframe 对应的共享模板；须同时检测 `env.capabilities.templateUpdates === true` 与两个方法存在，不传入模板 ID 或下载 URL。`checkForUpdates(cache?: boolean)` 返回 `Promise<TemplateUpdateCheck | false>`：仅当前页面 `minipageSource` 为 `online_template` 时查询，共享模板来源不参与判断；本地导入、本地 Agent 或缺失来源在读取缓存和请求网络前直接返回 `false`，调用方先判断 `status === false` 再访问结果字段。线上页面默认复用 12 小时成功结果缓存，传 `false` 强制查询并刷新成功缓存；`update()` 无参数且始终即时查询。更新前通过 collection 保存未持久化编辑；成功启用新版后宿主会刷新本设备同模板页面。检查失败不能当作无更新或覆盖成功缓存，更新失败保留页面和用户输入。
- 连接器仅经 SDK 调用当前账号已配置的连接，以 `connectionId` 区分同类连接器的不同账号。模板自行设计连接选择、参数输入、结果展示和 write/delete 确认；宿主不额外弹确认。不收集凭据、不创建连接、不直接请求服务商，也不自动重试连接器写入。收到 `MCP_WRITE_OUTCOME_UNKNOWN` 时保留输入并提示先核对外部状态，不视为写入失败。
- `collection` 与 `native.pickImages/pickMedia` 不传 `pageId`，只操作当前 iframe 对应页面；外层宿主自动绑定当前页面 ID。历史模板仍传 `pageId` 时会被忽略，不改变操作目标。`collection.query()` 无参数读取当前页面；`env.pageId` 和结果里的页面 ID 仅作为只读信息。
- 用户数据只经 SDK 持久化；禁止 localStorage、sessionStorage、IndexedDB 和自建数据库。
- HTTPS 接口地址仅在 manifest 的 `network.endpoints` 中声明，通过 `infolio.network.request()` 以 endpoint ID 调用；同时检查 `env.capabilities.network` 和方法存在。默认空列表禁止请求，路径前缀及方法必须显式声明，写请求结果未知时不得自动重试。详见 `references/sdk-api.md` 的 network.request。
- 运行源码不得包含 HTTP/HTTPS 资源 URL、CDN、远程字体、远程图片、fetch、XHR、WebSocket、Worker、iframe 或外部跳转。
- 使用 `env.language`、`env.theme`、`env.timezone`；不要使用浏览器语言代替 APP 语言。
- 保留已有 `templateId` 和既有字段；兼容更新不得删除、改名或改变已有字段类型。
- 必须覆盖加载、空数据、保存中、失败、禁用、分页和版本冲突状态；写入失败时保留用户输入。
- 移动端触控目标至少 44×44px；平板和桌面端必须重新排布而不是简单缩放。
- 不添加 ring 效果。键盘焦点使用背景色、文字色或边框色反馈。
- 不声称未执行的检查已经通过。默认交付源码、静态检查结果和 ZIP；不生成 catalog、不上传、不发布，除非用户另行明确要求。

## 交付

交付模板源码目录和 ZIP，并简要列出：页面用途、数据成员、主要交互、支持语言、实际执行的检查，以及仍需用户提供或确认的真实内容。
