# MiniPage 模板编写规范

## 目录

- [产物结构](#产物结构)
- [Manifest](#manifest)
- [HTML](#html)
- [CSS 与响应式](#css-与响应式)
- [JavaScript](#javascript)
- [本地化](#本地化)
- [离线与安全边界](#离线与安全边界)
- [UI 与交互质量](#ui-与交互质量)
- [状态与边界](#状态与边界)
- [封面与交付检查](#封面与交付检查)

## 产物结构

默认从 `assets/starter-template/` 复制并改造：

```text
template/
├── manifest.json
├── index.html
├── app.css
├── app.js
├── i18n.js
├── locales/
│   ├── en.json
│   └── zh.json
└── assets/
    └── cover.png
```

运行目录只保留最终静态资源。DESIGN.md、README、源文件、node_modules、构建配置、缓存、测试输出和 ZIP 放在目录外。`files` 由打包器生成，不手工维护。

## Manifest

| 字段 | 要求 |
|---|---|
| `manifestVersion` | 整数 `1` |
| `templateId` | 稳定、非空、全局唯一的模板 ID；模板升级时不改变 |
| `version` | 两段数字版本，从 `1.0` 开始，后续按 `2.0`、`3.0` 递增；两段按数值比较，不允许前导零、第三段、预发布或构建后缀 |
| `miniVersion` | 最低 infolio App 版本，使用三段无前导零的数字；新模板显式填写 `1.4.0`，需要更高版本的能力时相应提高，不降低已有模板的最低版本要求。客户端版本达到或超过该值才在模板列表展示。旧包缺省按 `0.0.0`；每段不超过 `9007199254740991` |
| `sdkApiVersion` | 字符串 `"1"` |
| `title`、`description` | 非空英文基础值，也是翻译最终回退 |
| `title_<locale>`、`description_<locale>` | 可选的本地化展示字段，语言标签中的 `-` 写成 `_` |
| `entry` | 包内 HTML 入口的相对路径 |
| `cover` | 包内 PNG、JPEG 或 WebP 封面的相对路径 |
| `defaultLocale` | 默认语言标签，必须存在于 `locales` |
| `locales` | 语言标签到包内 JSON 文件的映射 |
| `dataSchema` | SDK 数据定义，详见 SDK 参考 |
| `files` | 打包器生成的资源清单；源码中保留空数组即可 |

每个 files 条目包含 `path`、字节 `size`、`mimeType` 和 64 位小写 SHA-256。manifest 自身不进入 files。所有路径使用 `/`，不能是绝对路径，不能含 `..`、查询参数或片段，也不能是符号链接。

`miniVersion` 与模板发布 `version`、`sdkApiVersion` 分别维护，不使用 App 构建号或 `1.3.1(162)` 展示字符串。目录生成时从已校验 ZIP 原样提取；服务端不根据请求客户端的版本过滤。客户端对模板中心、已下载列表及更新提示统一判断，隐藏不支持的条目但保留已经安装的模板和页面数据。

## HTML

- 使用 `<!doctype html>`、UTF-8，以及 `width=device-width, initial-scale=1, viewport-fit=cover`。
- 使用适合内容的 `header/main/section/form/label` 等语义结构；标题级别连续。
- 每个 button 明确写 `type="button"` 或 `type="submit"`。
- 每个 input、textarea、select 都有可访问名称：显式 label、`aria-label` 或 `aria-labelledby`。
- 每张图片都有 alt；装饰图使用 `alt=""` 和 `aria-hidden="true"`。
- 动态状态使用 `role="status"`、`aria-live="polite"`；阻断性错误使用 `role="alert"`。
- 不使用内联事件属性，不把用户数据拼入 HTML。

## CSS 与响应式

从移动端开始编写基础样式，再在内容真正需要时添加 `min-width` 断点。至少覆盖：

- 手机：从 320px 起无横向溢出，单列布局，正文和输入可读。
- 平板：约 640–959px，允许双列、主从或更宽表单，但不能只是放大手机界面。
- 桌面：约 960px 以上，使用 `max-width` 控制阅读宽度，合理利用横向空间，不拉满超宽屏。

必须做到：

- `box-sizing: border-box`；flex/grid 子项需要时设置 `min-width: 0`。
- 布局使用 Grid/Flex、`minmax()`、`clamp()` 和内容驱动断点，不依赖固定设备宽度。
- 使用 `env(safe-area-inset-*)` 处理安全区域。
- 手机输入字号至少 16px，避免 iOS 聚焦缩放。
- 粗指针环境的交互目标至少 44×44px；hover 只增强反馈，不承载功能。
- 长标题、长翻译、空值和大量记录不会破坏布局。
- 使用逻辑方向属性，设置文档 `lang` 和 `dir`，为 RTL 留出兼容空间。
- 响应 `prefers-reduced-motion: reduce`；动画只用于状态与层级变化。
- 使用 `env.theme` 驱动 CSS token，不以浏览器主题代替 APP 主题。

## JavaScript

- 使用原生模块化函数和事件监听；避免无意义的全局状态。
- 启动顺序：读取 env → 解析语言/主题 → 查询页面 → 渲染 → 开放交互。
- 所有用户数据使用 `textContent`、DOM 属性或安全节点构建；不使用 `innerHTML`。
- 写入时锁定相关控件；成功后使用 SDK 返回值更新 UI，失败时保留草稿。
- 连接器由 `infolio.connectors` 调用当前账号已配置的连接；先检测模块存在。连接选择、参数表单、结果展示及 write/delete 确认由模板设计，宿主不额外弹确认。`call()` 不要求先调用 `list()` 或 `describe()`，动态表单可使用 `describe()` 返回的 Schema。
- 同类连接器可有多个连接，用 `connectionId` 定位，不用名称或 `connectorKey` 代替。保留并禁用 `invalid` 连接，展示恢复提示；空列表与请求失败分别处理。连接器结果是外部不可信数据，继续使用安全 DOM 构建。可显式选择业务图片字段，验证为 HTTPS 后赋给图片元素，不自动加载其他资源 URL。
- 连接器调用不自动重试。`MCP_WRITE_OUTCOME_UNKNOWN` 表示请求可能已经执行，不能提示为确定失败或复用 collection 的 `mutationId` 重发；保留输入并让用户先核对外部状态。
- collection 首屏使用页面 query 返回的 20 条记录和 `_pagination`；加载更多显式沿用 cursor、limit、筛选和排序。
- 不假设新字段始终存在；读取旧页面时提供不写回的 UI 默认值。
- 事件监听、计时器和对象 URL 在不再使用时清理。
- 不实现 SDK 桥接、MessageChannel、同步队列、模板下载或宿主路由。

默认使用原生 HTML/CSS/JS。只有用户明确指定框架时才能使用框架；最终必须构建成包内静态文件，不得留下裸模块名或运行时包管理依赖。

## 本地化

- `title` 和 `description` 使用英文基础值；额外语言使用 `title_zh`、`description_zh` 等平铺字段。
- 所有界面固定文案放在 `locales/*.json`，各语言 key 必须完全一致。
- 动态文案使用 `{name}` 形式插值，不拼接固定句子片段。
- 运行 `compile_locales.py` 生成 `i18n.js`；HTML 直接加载该本地脚本，运行时不 fetch JSON。
- 语言选择顺序：`env.language` 完整标签 → 语言主标签 → `manifest.defaultLocale` → 英文。
- 日期时间使用 `Intl.DateTimeFormat(language, { timeZone: env.timezone })`；数字使用 `Intl.NumberFormat`。

## HTTPS 接口声明

`network` 是可选的 manifest 字段，格式为 `{ "endpoints": [...] }`。省略或空列表
表示不允许 `infolio.network.request()`。每项必须包含唯一 `id`、HTTPS `url`、
`match`（`exact` 或 `prefix`）和非空 `methods` 数组；ID 使用字母开头的 ASCII 字母、
数字、下划线或短横线。方法支持 GET、HEAD、POST、PUT、PATCH、DELETE、OPTIONS，且不重复。

地址不含查询参数、fragment、用户名或密码；使用 ASCII 域名（国际化域名先转 Punycode）
或 IP 地址，不支持通配符。prefix 地址以 `/` 结尾；exact 只放行原路径。
路径不含 dot segments、双斜线、控制字符或含糊的百分号编码。声明格式错误拒绝加载。
宿主还会检查实际 DNS 结果，仅连接公网地址并正常校验 TLS 证书。

完整 URL 只写入 manifest，脚本以 endpoint ID 和相对 path 调用。
具体示例与错误契约见 [network.request](sdk-api.md#networkrequest)。starter 使用空列表，
不会发起外网请求。需要网络的模板填入实际接口，`miniVersion` 至少为 `1.4.0`，
对应配套 Native/Web 宿主的最低 app 版本，不以模板版本代替。
调用前仍必须同时检测 capability 和 SDK 方法，不能只依赖最低版本字段。

## 离线与安全边界

模板的接口请求通过 `infolio.connectors`，或通过 `infolio.network.request()` 请求 manifest 声明的 HTTPS 接口，由 Native 执行。有效入口文档也允许浏览器直接加载 HTTPS 图片；这不需要 `network.endpoints` 声明，也不放开其他网络能力。联网功能须显示真实的加载与失败状态，不能宣称离线能取得新结果。禁止：

- HTTP 和 `//host` 图片 URL，以及非图片用途的外部资源 URL。
- 外部脚本、样式、字体、模块、视频及 analytics。
- fetch、XMLHttpRequest、WebSocket、EventSource、sendBeacon。
- RTCPeerConnection、Worker、SharedWorker、Service Worker、importScripts。
- iframe、object、embed、外部 form action 和外部跳转。
- localStorage、sessionStorage、IndexedDB、Cache API 作为业务存储。

模板以 `manifest.entry` 为唯一可执行文档入口，界面切换使用单页内部状态或同一入口的 hash 路由；不要跳转到包内其他 HTML、SVG 或 XHTML 文档。包内 SVG 仍可作为图片正常引用，其他本地静态资源和媒体按原方式加载。

脚本、样式、字体、界面图标和占位图片全部随包提供。HTTPS 业务图片可写在 HTML `img` 的 `src/srcset` 或 `picture` 内 `source` 的 `srcset`；也可在 JavaScript 中验证接口返回的 URL 后设置图片属性，不在脚本中硬编码完整远程 URL。远程图片使用 `referrerPolicy="no-referrer"`、懒加载和失败占位；不要为普通展示设置 `crossOrigin`，不要假设旧宿主支持或图片离线可用。CSS/SVG 资源引用仍须为包内资源。

用户附件只能来自 `native.pickImages` 或 `native.pickMedia`，页面数据只通过 collection API 持久化；外部连接器的数据通过 connectors API 读取或修改，不会自动保存到页面。需要保留结果时，仅将必要业务字段写入已声明的数据成员，不保存凭据、鉴权 Header 或临时资源地址。媒体导出调用 `native.downloadAttachment`；不得用下载链接、外部请求或自建桥绕过宿主。

URL 字段可以保存、显示、复制和搜索，但当前 SDK 没有对外开放的网页跳转方法。不要把 URL 渲染成看似可点击却无法工作的链接，也不要使用 anchor、`window.open` 或 location API 绕过这一限制；用户明确要求打开外链时，说明当前能力边界。

## UI 与交互质量

为当前使用场景设计，不复制 starter 的视觉外观。默认采用克制、清晰的工作界面：

- 一个清楚的主要任务和主要操作，次要操作降低视觉权重。
- 统一颜色角色、间距尺度、圆角、字体层级与图标语言。
- 正文对比度至少 4.5:1，大文字至少 3:1；不要只用颜色表达状态。
- 避免卡片套卡片、过多边框阴影、装饰性渐变、无意义大标题和重复说明。
- 表单标签常驻；placeholder 不能代替 label。错误靠近字段并说明恢复方式。
- 所有功能可用键盘完成，Tab 顺序符合阅读顺序。
- 禁止 ring 效果；focus-visible 使用明显的背景、文字色或边框色变化。
- 操作名称具体，例如“保存记录”“加载更多”，不用含糊的“确定”“继续”。
- 图标使用本地 SVG 或 CSS 图形，不用 emoji 或 Unicode 符号替代正式图标。

## 状态与边界

每个模板必须实现：

- 首次加载和分页加载。
- 无记录空状态，并给出下一步。
- 保存、更新和删除进行中。
- 读取失败与可重试状态。
- 写入失败，保留输入和原记录。
- `VERSION_CONFLICT` 后重新读取。
- `CHANNEL_CLOSED` 后提示重新打开，不循环重试。
- 按钮禁用和重复提交保护。
- 图片选择取消、图片加载失败和长内容。
- 使用连接器时覆盖旧宿主不支持、无连接、失效连接、Local User 不可用、参数校验失败、网络失败与写入结果未知；页面关闭、重载或账号切换后不重放旧调用。

## 封面与交付检查

- 封面使用 PNG、JPEG 或 WebP，展示最终模板的真实主要界面，不放私人数据。
- 封面不能只是 logo、标题或与模板无关的抽象图。
- 修改 UI 后同步更新封面。
- 复制 starter 后必须替换示例 `templateId`、标题、描述、字段和文案，使其匹配用户场景。
- 运行 `compile_locales.py --check`，再运行 `package_template.py --check-only`。
- 打包后检查 ZIP 中只包含运行资源，manifest 的 files 与真实内容一致。
- 交付时区分已执行的静态检查和未执行的真实 APP 验证。
