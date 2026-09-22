# infolio MiniPage SDK API

## 目录

- [运行环境](#运行环境)
- [公共类型](#公共类型)
- [env.get](#envget)
- [template.checkForUpdates / template.update](#template)
- [native.pickImages](#nativepickimages)
- [native.pickMedia](#nativepickmedia)
- [native.downloadAttachment](#nativedownloadattachment)
- [network.request](#networkrequest)
- [connectors](#connectors)
- [collection.query](#collectionquery)
- [collection.create](#collectioncreate)
- [collection.update](#collectionupdate)
- [collection.delete](#collectiondelete)
- [筛选、排序和分页](#筛选排序和分页)
- [错误、并发与重试](#错误并发与重试)
- [dataSchema](#dataschema)
- [模板更新兼容性](#模板更新兼容性)

## 运行环境

宿主在模板脚本之前注入冻结的 `window.infolio`：

```ts
interface Window {
  infolio: {
    env: { get(): Promise<MinipageEnv> }
    template?: {
      checkForUpdates(cache?: boolean): Promise<TemplateUpdateCheck | false>
      update(): Promise<TemplateUpdateResult>
    }
    native: {
      pickImages(input?: { maxCount?: number }): Promise<Attachment[]>
      pickMedia?(input?: { maxCount?: number }): Promise<Attachment[]>
      downloadAttachment?(input: { assetId: string }): Promise<{ saved: boolean }>
    }
    network?: { request(input: NetworkRequest): Promise<NetworkResponse> }
    connectors?: {
      list(input?: { connectorKey?: string }): Promise<{ connections: ConnectorConnection[] }>
      describe(input: ConnectorToolTarget): Promise<ConnectorToolDescription>
      call(input: ConnectorToolTarget & { arguments?: Record<string, JsonValue> }): Promise<ConnectorCallResult>
    }
    collection: {
      query(input?: PageQuery): Promise<PageQueryResult>
      query(input: RecordQuery): Promise<RecordQueryResult>
      create(input: RecordCreate): Promise<{ record: CollectionRecord }>
      update(input: PageUpdate | RecordUpdate): Promise<{ page: MinipagePage } | { record: CollectionRecord }>
      delete(input: RecordDelete): Promise<RecordDeleteResult>
    }
  }
}
```

所有方法都是异步方法，并在 MessageChannel 建立后执行。模板只消费 SDK，不实现注入、握手、Flutter action 或消息协议。

`collection` 和 `native.pickImages/pickMedia` 的公开参数不包含 `pageId`；外层宿主根据当前 iframe 绑定的页面自动传递页面 ID，模板不能选择其他页面。为兼容历史模板，参数对象中遗留的 `pageId` 会被静默忽略，无论其值是什么都只操作当前页面；新模板不再传入该字段。`env.pageId` 与返回结果中的页面 ID 保留为只读信息。

页面自动绑定需要配套的 Native 和 Web 消息分发宿主一起交付。更新后的宿主兼容历史模板传入 `pageId`；新模板省略 `pageId` 不代表能兼容尚未更新的旧宿主。

模板运行在 `sandbox="allow-scripts"` iframe 中。宿主 CSP 禁止网络连接、子 frame、Worker、object、外部表单和外部资源。只有当前加载的 `manifest.entry` 作为可执行文档入口并注入 SDK；其他资源作为文档打开时不允许执行脚本。页面导航仅允许宿主认可的活动入口（可带 query/hash）：可取得来源框架时限定同一加载，否则使用当前 WebView 控制器的活动入口允许列表。模板界面切换使用自身入口的单页内部状态或 hash 路由，不依赖跨入口导航。包内图片、SVG、样式、字体和媒体仍按资源加载。

`connectors` 是 SDK `1` 的增量能力；旧宿主可能没有该模块，调用前检查 `window.infolio.connectors`。它通过 Native 调用已配置连接，不开放 iframe 直接联网或读取凭据。

`network` 是 SDK `1` 的增量能力。只有 `env.capabilities?.network === true` 且
`typeof window.infolio.network?.request === 'function'` 时才可调用；Native 与 Web
Host 必须一起支持。旧宿主保持原有功能，模板使用现有国际化文案提示能力不可用。

## network.request

地址只能在 manifest 的 `network.endpoints` 中声明。以下声明允许 `/v1/items/`
目录及其下级路径上的 GET、POST，查询参数可以变化：

```json
{
  "network": {
    "endpoints": [
      {
        "id": "items",
        "url": "https://api.example.com/v1/items/",
        "match": "prefix",
        "methods": ["GET", "POST"]
      }
    ]
  }
}
```

```js
const env = await window.infolio.env.get();
if (env.capabilities?.network === true &&
    typeof window.infolio.network?.request === 'function') {
  const response = await window.infolio.network.request({
    endpoint: 'items',
    path: '123',
    method: 'GET',
    query: { language: env.language }
  });
  // Check response.status, then interpret response.body in the template.
}
```

- `endpoint` 是声明中唯一的 ID；不传完整 URL 或权限列表。
- `path` 默认空字符串；只允许相对路径。`exact` 声明只能使用空 path；`prefix`
  声明必须以 `/` 结尾，空 path 请求声明地址。禁止绝对路径、冒号、上级/当前目录、
  双斜线、编码分隔符及重复百分号编码；宿主拼接后再次匹配 HTTPS、主机、端口和路径。
- `method` 默认 GET，必须在该 endpoint 的 methods 中。GET/HEAD 不接受 body。
- query、headers 的值均为字符串；body 是调用方序列化后的文本，例如
  `JSON.stringify(data)`，相应 Content-Type 由调用方提供。
- Authorization 可显式传入；宿主不注入 infolio 登录态或连接器凭据，不共享 Cookie。
  Host、Content-Length、Connection、Cookie、Origin、Referer、Accept-Encoding、
  Expect、代理及其他传输相关头由宿主管理，禁止模板覆盖。
- 返回原始 HTTP 状态、响应头列表及解码后的文本。4xx/5xx 不抛 SDK 错误，
  不校验业务 JSON 或自动修改响应。支持 UTF-8、ASCII、Latin-1；未声明 charset 默认 UTF-8。
- 不跟随重定向：3xx 连同 Location 返回，后续请求仍须显式选择 manifest 中的接口。
- 总超时 30 秒，请求体最多 1 MiB UTF-8 字节，解压后响应体最多 5 MiB，
  每个活动页面最多 6 个并发请求。仅支持公网 HTTPS 的完整 JSON/文本响应；没有文件或流接口。
- SDK 错误码包括 `NETWORK_NOT_ALLOWED`、`NETWORK_INPUT_INVALID`、`NETWORK_BUSY`、
  `NETWORK_TIMEOUT`、`NETWORK_REQUEST_TOO_LARGE`、`NETWORK_RESPONSE_TOO_LARGE`、
  `NETWORK_ENCODING_UNSUPPORTED`、`NETWORK_FAILED`、`CHANNEL_CLOSED`。
- 写请求发出后未取得完整结果，或等待写入结果时 SDK 通道关闭，返回
  `NETWORK_WRITE_OUTCOME_UNKNOWN`，`error.details.outcomeUnknown` 为 true，cause 为原因。
  不自动重试；先核实外部服务的结果。GET、HEAD、OPTIONS 按读取处理。
- 页面关闭、账号切换会取消请求；普通重载/模板更新先等待请求完成或超时。
  旧页面只使用旧包的权限，重载后使用新包的权限。修改返回的 env.manifest 不会改变授权。
- `connectors.call()` 保留独立的绑定和权限机制，不受此白名单影响。

## 公共类型

```ts
type NetworkMethod = 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS'
interface NetworkRequest {
  endpoint: string
  path?: string
  method?: NetworkMethod
  query?: Record<string, string>
  headers?: Record<string, string>
  body?: string
}
interface NetworkResponse {
  status: number
  headers: Record<string, string[]>
  body: string
}

type JsonValue = null | string | number | boolean | JsonValue[] | { [key: string]: JsonValue }

interface MinipageEnv {
  pageId: string
  manifest: TemplateManifest
  language: string
  theme: 'light' | 'dark'
  timezone: string
  utcOffsetMinutes: number
  app: { name: 'infolio'; version: string; platform: string }
  userProfile: { nickname: string; avatarUrl: string | null }
  sdkApiVersion: '1'
  capabilities?: { pickMedia: boolean; downloadAttachment: boolean; templateUpdates?: boolean; network?: boolean }
}

interface TemplateUpdateCheck {
  templateId: string
  currentVersion: string
  latestVersion: string | null
  updateAvailable: boolean
}

interface TemplateUpdateResult {
  templateId: string
  previousVersion: string
  version: string
  updated: boolean
}

interface Attachment {
  id: string
  name: string
  size: number
  mimeType: string
  url: string
}

interface CollectionRecord {
  id: string
  values: Record<string, JsonValue>
  createdAt: string
  updatedAt: string
  version: string
}

interface MinipagePage {
  id: string
  sourceId: string
  uid: string
  pid?: string
  type: 'minipage'
  templateId: string
  ctime: string
  utime: string
  pined: boolean
  revision: number
  readVersionToken: string
  is_embedded_owned: boolean
  owner_page_id?: string | null
  content: {
    titleConfig: { title: string; title_icon?: string | null }
    data: Record<string, JsonValue | CollectionRecord[]>
    _pagination?: Record<string, Pagination>
  }
  external: Record<string, JsonValue> | null
  text_content: string | null
  content_snapshot: null
}

interface Pagination {
  limit: number
  total: number
  nextCursor: string | null
}

type FieldType = 'text' | 'url' | 'number' | 'boolean' | 'date' | 'attachment' | 'json'

interface FieldDefinition {
  key: string
  type: FieldType
  required?: boolean
  default?: JsonValue
  labelKey?: string
  options?: { dateFormat: 'date' | 'datetime' }
}

interface PageQuery { fieldKey?: never }
interface PageQueryResult { page: MinipagePage }
```

日期时间字符串由宿主返回 ISO 8601 值。`version` 是记录并发控制令牌，不要解析或自行生成。

## `env.get()`

```js
const env = await window.infolio.env.get()
```

无参数，返回 `MinipageEnv`。

- `pageId`：当前页面实例 ID，仅供只读识别；数据与媒体调用由宿主自动绑定当前页面，不将它传回 SDK。
- `manifest`：当前运行包的完整 manifest；可包含 `miniVersion`（如 `1.3.1`），供客户端决定模板列表是否展示，旧包缺省按 `0.0.0`。
- `language`：infolio 当前语言，如 `zh`、`en-US`。使用完整语言标签、语言主标签、`manifest.defaultLocale` 的顺序选择翻译。
- `theme`：当前主题。把它写到根节点的 `data-theme`，由 CSS token 响应。
- `timezone`：IANA 时区，如 `Asia/Shanghai`。日期时间显示传给 `Intl.DateTimeFormat`。
- `utcOffsetMinutes`：当前时刻相对 UTC 的分钟偏移，只作为无法使用 IANA 时区时的回退。
- `app`：宿主名称、版本和平台。
- `userProfile`：当前账号的只读昵称和头像。`avatarUrl` 只会是宿主生成的 `data:image/*` 或 `null`；不得把它写入用户数据或假设它永久不变。
- `sdkApiVersion`：当前为字符串 `"1"`。
- `capabilities`：实际 Web 消息分发宿主声明的增量能力；旧宿主可能不返回。调用新方法需同时满足对应字段为 `true` 且所属模块下存在该方法，避免只更新原生 SDK、未更新 Web 资源时误判支持。`pickMedia`、`downloadAttachment` 对应 `native` 方法，`templateUpdates` 对应 `template` 的两个方法。

重新调用可获得最新语言、主题、时区和账号资料；同次加载中的 manifest 不变。

## `template`

检查并更新当前 MiniPage 使用的共享模板。`checkForUpdates(cache?: boolean)` 可选择是否使用缓存，`update()` 无参数；宿主根据当前 iframe 的加载上下文确定账号和模板，不接受 `templateId`、`pageId`、下载 URL 或本地路径。检查和下载由 Native 访问可信模板中心，不开放 iframe 联网，也不更新 infolio App。

这是 SDK `1` 的增量能力。调用前须同时确认 `env.capabilities.templateUpdates === true`、`template.checkForUpdates` 和 `template.update` 两个方法存在；旧宿主保留页面原有功能，可提示升级 App。只有原生和 Web 宿主均支持时才可用，导入新的模板 ZIP 不会补齐宿主能力。

### `template.checkForUpdates(cache?)`

```js
const status = await window.infolio.template.checkForUpdates()
// false 或 { templateId, currentVersion, latestVersion, updateAvailable }
if (status !== false && status.updateAvailable) {
  // 可展示模板更新入口。
}

// 用户主动刷新检查结果时，跳过缓存并重新查询。
const freshStatus = await window.infolio.template.checkForUpdates(false)
```

返回 `TemplateUpdateCheck | false`，仅查询，不安装或刷新页面。宿主先检查当前页面（`sys.page.minipage`）的 `minipageSource`，只有线上模板来源 `online_template` 才继续检查；本地导入、本地 Agent 或缺失来源直接返回布尔 `false`，在读取缓存和请求模板中心之前结束，调用 `checkForUpdates(false)` 时也一样。判断依据是当前页面来源，不是共享模板记录的来源。

线上模板来源页面返回 `TemplateUpdateCheck`：

- `currentVersion` 是当前 iframe 实际运行包的版本，与本次加载的 `env.manifest.version` 一致。
- `latestVersion` 是可信模板中心当前可用且与宿主兼容的版本；模板未上架，或没有满足当前 App `miniVersion`、manifest 与 SDK 支持条件的条目时为 `null`。
- `updateAvailable` 表示该兼容版本是否高于 `currentVersion`。模板版本按两段非负整数 `major.minor` 比较，例如 `1.10` 高于 `1.9`，不按字符串排序；不接受三段版本或预发布后缀。

线上模板来源页面的 `cache` 默认 `true`。`checkForUpdates()` 与 `checkForUpdates(true)` 复用 12 小时内的成功结果，命中时不请求模板中心；`checkForUpdates(false)` 强制重新查询，成功后更新缓存。缓存由 Native 本地持久保存，可跨 iframe 重载和 App 重启复用，但仅在账号、模板中心 Region、模板 ID、App 版本和当前运行包内容哈希均一致时命中。有效期从成功请求完成时计算，读取缓存不延长有效期；没有新版或 `latestVersion: null` 的成功结果也会缓存。

网络、目录或其他查询错误通过 Promise 拒绝返回，不能把失败展示为“已是最新版本”。失败不缓存，强制查询失败也不覆盖之前的成功缓存，本次调用仍返回错误。检查结果可能来自缓存，是最近一次成功查询时的快照；`update()` 始终即时查询，不受该缓存影响，也不依赖之前的检查结果。

### `template.update()`

```js
const result = await window.infolio.template.update()
// { templateId, previousVersion, version, updated }
```

返回 `TemplateUpdateResult`。`previousVersion` 是调用页面原先运行的版本，`version` 是更新操作完成后使用的版本。宿主复用共享模板安装流程，完成包完整性、清单及数据 schema 兼容校验后启用新版，保留所有页面标题、配置、记录和附件。不降级，不提供历史版本选择或回退。

当前运行包已是可用目标包时返回 `updated: false`，页面不刷新。`updated` 比较的是目标包与当前 iframe 包的内容哈希；如果本设备已经安装了比当前 iframe 更新的包，可直接切换到该包，返回 `updated: true`，包括模板中心未返回新版、但其他页面或同步已更新本地共享包的情况。

`updated: true` 后宿主自动刷新本设备已挂载且引用同一模板的页面。当前调用在刷新前收到结果，但不要依赖旧 iframe 的 JavaScript 状态继续运行；更新前应先通过 collection 保存未持久化编辑。其他设备沿用既有同步流程更新。失败时 Promise 拒绝，保留尚未被替换的旧包并恢复页面调用，不重置用户数据。

下面示例用于用户点击“立即更新”的处理逻辑；`persistPendingEdits` 由模板实现，负责通过 collection 保存草稿，展示文案由模板自身的语言资源维护：

```js
async function updateCurrentTemplate(persistPendingEdits) {
  const sdk = window.infolio
  const env = await sdk.env.get()
  if (
    env.capabilities?.templateUpdates !== true ||
    typeof sdk.template?.checkForUpdates !== 'function' ||
    typeof sdk.template?.update !== 'function'
  ) {
    return { supported: false }
  }

  const status = await sdk.template.checkForUpdates(false)
  if (status === false || !status.updateAvailable) return { supported: true, status }

  await persistPendingEdits()
  const result = await sdk.template.update()
  // updated 为 true 时宿主即将刷新，勿再发起依赖旧页面状态的操作。
  return { supported: true, status, result }
}
```

更新期间禁用更新入口，避免重复提交。检查与更新失败均应保留当前页面并显示本地化错误，不在 `catch` 中返回“无更新”，也不自动循环重试。

## `native.pickImages()`

```js
const images = await window.infolio.native.pickImages({
  maxCount: 6,
})
```

| 参数 | 必填 | 说明 |
|---|---:|---|
| `maxCount` | 否 | 正整数。限制本次最多返回的图片数量；`1` 使用单选，省略时保持宿主默认多选行为 |

为当前 MiniPage 选择并导入图片，返回 `Attachment[]`。用户取消选择时返回空数组，不抛错。

附件 `url` 是宿主管理的稳定相对 URL，可直接赋给 `<img src>`。保存附件时保留返回对象的全部字段；不要拼接资产 URL、保存设备绝对路径或用取消返回的空数组覆盖已有附件。

## `native.pickMedia()`

```js
const media = await window.infolio.native.pickMedia({
  maxCount: 24,
})
```

选择图片和视频，按选择器返回的顺序返回 `Attachment[]`，取消返回空数组。参数与 `pickImages` 相同，始终导入当前页面；省略 `maxCount` 默认最多 24 项。

手机使用系统混合媒体选择器，桌面使用文件选择器。附件继续由 MiniPage 管理、保存和同步。根据 `mimeType` 的 `image/` 或 `video/` 前缀区分显示方式；稳定相对 URL 可用于 `<img>` 或 `<video playsinline controls>`。视频可播放的编码由所在设备决定，不提供转码。

图片和视频可以混存在同一个 attachment 字段中，顺序由数组保存，无须增加字段或改变旧 schema。封面、头像等仅接受图片的场景继续使用 `pickImages`。

## `native.downloadAttachment()`

```js
const { saved } = await window.infolio.native.downloadAttachment({ assetId: attachment.id })
```

仅导出当前 MiniPage 拥有的指定图片或视频。宿主解析附件真实文件名、类型和内容，不接受模板传入文件路径或下载 URL。手机保存到系统相册，桌面弹出文件保存对话框。成功返回 `{ saved: true }`；用户取消返回 `{ saved: false }`，不能将取消提示为保存成功。

系统权限拒绝、格式不支持和保存失败通过 Promise 拒绝返回错误。模板应保留当前预览，并在预览内显示可理解的本地化反馈。导出不修改记录，也不触发新的同步。

两个方法是 SDK `1` 的增量能力，旧宿主可能没有提供。调用前同时检测 `env.capabilities` 对应字段及方法是否存在；缺少任一条件或收到不支持方法的响应时，保留原图片浏览/选择能力，并提示更新应用。不要把所有 `VALIDATION_FAILED` 都当成宿主过旧。部署时需同时交付配套 Flutter 宿主和 Web 消息分发更新，单独导入 ZIP 不能补齐宿主能力。

## `connectors`

调用用户在 infolio 设置中已配置的内置或“自定义连接器”。自定义连接器可选 API 或远程 MCP：API 由 Native 包装成唯一的 `request` 工具；MCP 在用户保存配置 JSON 时自动发现并保存全部工具。两者使用相同的 `list/describe/call`，模板不需要实现 HTTP 鉴权或 MCP 协议。

配置、鉴权和测试在 App 设置中完成。自定义连接器首版使用 HTTPS 和静态鉴权，不支持通用 OAuth、stdio/本地命令或脚本，不提供外部可访问的 MCP Endpoint。MCP 支持 Streamable HTTP 的 JSON/SSE 与旧 HTTP + SSE；由 Native 处理 `2026-07-28` 以及 `2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05` 的协议差异。API 保存不会调用业务接口，只有显式成功测试才更新验证时间。

```ts
interface ConnectorToolSummary {
  name: string
  summary: Record<string, string> // 目录提供的语言标签到说明的映射
  operationKind: 'read' | 'write' | 'delete'
}

interface ConnectorConnection {
  connectionId: string
  connectorKey: string
  name: string
  status: 'active' | 'invalid'
  lastErrorCode?: string | null
  tools: ConnectorToolSummary[]
}

interface ConnectorToolTarget {
  connectionId: string
  toolName: string
}

interface ConnectorToolDescription extends ConnectorToolTarget {
  summary: Record<string, string>
  operationKind: 'read' | 'write' | 'delete'
  inputSchema: Record<string, JsonValue>
  outputSchema?: Record<string, JsonValue>
}

interface ConnectorCallResult {
  content: Array<{ type: string; [key: string]: JsonValue }>
  structuredContent?: JsonValue
  isError?: boolean
  [key: string]: JsonValue | undefined
}
```

### `connectors.list`

```js
const { connections } = await infolio.connectors.list({
  connectorKey: 'google-search-console',
});
```

省略参数或 `connectorKey` 时列出当前账号已配置的连接和工具摘要，返回 `{ connections: [] }` 表示没有匹配连接。宿主已按连接器 `miniVersion` 与当前 App 版本筛选目录，模板无需重复判断。保留 `invalid` 状态以便显示和禁用，不把失效连接当作未配置。目录不可见或连接器已不可用时不能据连接记录绕过目录调用工具。内置目录仍保留管理员可见性；普通登录用户也可看到并使用自己的自定义连接器。配置与工具快照属于当前账号；本地用户或缺少运行能力时返回 `MCP_RUNTIME_UNAVAILABLE`，不伪造空列表。

同一种内置连接器可以有多个连接；每个自定义连接拥有独立稳定的 `connectorKey`，`connectionId` 是后续调用的连接标识，`name` 只用于展示。修改名称不会改变 API 的 `request` 工具名。不要按显示名称自动匹配连接，也不要依赖示例中的 Key 查找用户的自定义连接。模板按 `env.language` 从 `summary` 选择说明，缺失时回退到英文。SDK 不提供新增、授权、重命名或删除连接的方法，也不提供宿主连接选择弹窗。

### `connectors.describe`

```js
const description = await infolio.connectors.describe({ connectionId, toolName });
```

返回目录说明、操作类型与经验证的输入/输出 Schema；没有输出 Schema 时省略 `outputSchema`。模板可据此设计参数输入和 write/delete 确认。Native 解析目录、取得运行凭据，并校验已保存的 API 参数 Schema 或远程 MCP Schema；配置、凭据和目录 Revision 变化会使旧快照失效，远程 Schema 变化需用户在设置中重新保存 MCP JSON 以刷新工具。模板不能覆盖工具类型、Endpoint、Header 或允许列表；调用前无需先调用 `list()`。

### `connectors.call`

```js
const result = await infolio.connectors.call({
  connectionId,
  toolName,
  arguments: toolArguments,
});
```

`arguments` 可省略，默认为 `{}`；提供时必须为 JSON 对象。不要求模板预先调用 `list()` 或 `describe()`；每次执行由 Native 完成连接、目录和凭据版本校验、工具解析及参数 Schema 校验。返回脱敏后的 MCP 结果对象，保留 `content`、可选 `structuredContent`、`isError` 等协议结果字段；自定义 API 及内置 JSON API 的 `structuredContent` 为 `{ status, body }`，`body` 可以是 JSON、文本或空响应的 `null`，远程 MCP 的 `structuredContent` 可以是任意受传输大小边界约束的 JSON 值，不按 outputSchema 校验。不包装成 Agent 的执行回执，也不自动写入 collection。结果及 Schema 都是外部数据，按不可信输入渲染；`resource`、`resource_link` 和返回的 URL 不会自动加载。

GSC 上游 HTTP 403 只表示当前网站或请求没有权限，不会使整条连接失效；模板应在对应资源旁显示提示，让其他资源继续加载。上游 HTTP 429 或 Google quota/limit 错误表示请求受到配额或频率限制，提示稍后手动重试，不当作授权失效。连接列表中的 `lastErrorCode` 可辅助区分已失效连接的原因，旧宿主可能不提供；不要仅凭 `status: invalid` 断言 Token 过期。

模板自行设计连接选择、参数输入、结果展示及 write/delete 确认；宿主不额外弹确认。SDK 不自动重试工具调用，也不接受 collection 的 `mutationId`。一旦 write/delete 请求可能已发出而无法确认结果，Promise 拒绝并返回 `MCP_WRITE_OUTCOME_UNKNOWN`，`details.retryable` 为 `false`。这不能解释为写入失败，需先核对外部状态再决定后续动作。收到上游 HTTP/JSON-RPC/工具错误时 `call()` 同样 resolve，保留 `isError: true` 与完整脱敏错误内容；模板根据结果自行决定展示和后续动作，不能只以 Promise resolve 判断业务成功。

调用绑定当前页面加载和账号。页面关闭、重载或账号切换会取消关联请求，旧结果不会送到新页面；取消不能撤销已发出的远端写入。模板更新时宿主停止接收旧页面新调用并等待已接受调用结束，不自动重放。

Apple 报表工具返回 `{ reports: [{ date, status, body }] }`，body 是解压后的供应商范围原始 TSV 或原始错误响应。调用方解析 TSV、按 App ID/SKU 筛选与汇总，不再向报表工具传 appId。404 不代表零活动；缺币种等业务数据由调用方处理。内置结果最大 32 MiB，自定义 API/MCP 仍为 256 KiB，超限明确失败。

### 页面调用示例

以下函数接入模板自己渲染的连接列表、参数表单与状态区；`ui.*` 由模板实现，其固定文案全部从 `locales/*.json` 取值。工具名和参数必须来自实际目录与 Schema，不硬编码不存在的写工具。

```js
async function loadConnections(ui) {
  if (!window.infolio.connectors) {
    ui.showError('connectors_upgrade_required');
    return [];
  }
  try {
    const { connections } = await infolio.connectors.list();
    ui.showConnections(connections); // 展示名称和状态，禁用 invalid
    return connections;
  } catch (error) {
    ui.showConnectorError(error.code, error.details);
    return [];
  }
}

async function submitTool(connectionId, toolName, toolArguments, ui) {
  if (!window.infolio.connectors) {
    ui.showError('connectors_upgrade_required');
    return;
  }
  ui.setBusy(true);
  try {
    const target = { connectionId, toolName };
    const description = await infolio.connectors.describe(target);
    if (description.operationKind !== 'read' &&
        !await ui.confirmWrite(description, toolArguments)) return;
    const result = await infolio.connectors.call({
      ...target,
      arguments: toolArguments,
    });
    ui.showResult(result);
  } catch (error) {
    if (error.code === 'MCP_WRITE_OUTCOME_UNKNOWN') {
      ui.showError('connectors_check_external_state');
    } else {
      ui.showConnectorError(error.code, error.details);
    }
    // 保留参数输入；不自动重试。
  } finally {
    ui.setBusy(false);
  }
}
```

### 自定义 API 调用示例

假定用户已在 App 设置中创建 API 连接：URL 为 `https://api.example.com/items/{{itemId}}`，方法 GET，并声明必填字符串参数 `itemId`。新 API 默认按写入类型处理，不根据 HTTP 方法推断只读，模板应遵循 `describe()` 返回的操作类型。接口凭据由 Native 加密保存，不写入模板。先用 `list()` 显示当前账号的连接，由用户选择其连接 ID，再沿用上面的 `submitTool`：

```js
// 模板的连接选择界面；不能默认使用列表第一条。
await loadConnections(ui);

// 用户提交参数表单后，selectedConnectionId 来自该选择界面。
await submitTool(selectedConnectionId, 'request', {
  itemId: formValues.itemId,
}, ui);
```

上述 `submitTool` 仍通过 `connectors.describe()` 核对操作类型并取得 Schema，再通过 `connectors.call()` 调用。成功结果示例：

```json
{
  "content": [{ "type": "text", "text": "{\"status\":200,\"body\":{\"id\":\"item-123\"}}" }],
  "structuredContent": { "status": 200, "body": { "id": "item-123" } },
  "isError": false,
  "resultType": "complete"
}
```

调用自定义 MCP 时，把 `request` 换成用户所选连接的实际工具名，参数来自 `describe().inputSchema`；不向 SDK 传入连接 Endpoint、鉴权 Header 或 Token；工具业务参数仍以实际 Schema 为准。SDK 不限制自定义目录只有 24 个工具，模板应支持正常滚动/选择全部返回项；超出宿主大小上限则明确报错，不截断成成功结果。

接口地址、鉴权、映射或 Schema 更新后，旧调用可能返回版本冲突；重新取得连接与说明，让用户核对参数，不自动重试业务请求。只有真实 App 中从页面到 Native 再到自有 API/MCP 的调用成功，才算设备验证；TypeScript、资源检查和测试替身通过不能代替该验证。

## `collection.query()`

### 查询页面和首批记录

```js
const { page } = await window.infolio.collection.query()
const preferences = page.content.data.preferences ?? {}
const records = page.content.data.records ?? []
const pagination = page.content._pagination?.records
```

无参数调用，也可传入空对象。返回 `{ page: MinipagePage }`。所有 JSON 成员完整返回；唯一 collection 的前 20 条记录放在 `content.data[collectionKey]`，对应分页信息放在 `_pagination[collectionKey]`。`_pagination` 只读且不持久化。

### 查询 collection

```ts
interface RecordQuery {
  fieldKey: string
  recordId?: string
  selectFieldIds?: string[]
  filters?: FilterGroup | FilterCondition
  sorts?: Array<{ fieldId: string; direction: 'asc' | 'desc' }>
  search?: string
  searchFieldIds?: string[]
  limit?: number
  cursor?: string
  includeSchema?: boolean
}

interface RecordQueryResult {
  records: CollectionRecord[]
  nextCursor: string | null
  total: number
  schema?: { fields: FieldDefinition[] }
}
```

`fieldKey` 是 collection 根成员名，不是记录字段名或点路径。默认 `limit` 为 50，允许 1–500。若接续页面首批结果，沿用其 `limit: 20` 和 `nextCursor`。

SDK 没有聚合查询。计数、合计和图表若只基于当前已加载记录，必须在界面明确说明；需要全量结果时应逐页加载到 `nextCursor === null`，并避免在大数据集上阻塞界面。

指定 `recordId` 时返回零或一条记录，不得同时传 filters、sorts、search、searchFieldIds、limit 或 cursor。`selectFieldIds` 可包含业务字段和只读 `_ctime`、`_utime`。

## `collection.create()`

```ts
interface RecordCreate {
  fieldKey: string
  values: Record<string, JsonValue>
  mutationId?: string
}
```

```js
const { record } = await window.infolio.collection.create({
  fieldKey: 'records',
  values: { title: 'First item', done: false },
})
```

返回 `{ record: CollectionRecord }`。缺失字段会在创建时应用 manifest 中的字段默认值；显式传入的 `0`、`false`、空数组、空对象或 `null` 不触发默认值，并仍需满足字段类型和 required 约束。不能写 `_` 开头的宿主字段。

## `collection.update()`

### 更新页面 JSON 成员

```ts
interface PageUpdate {
  values: Record<string, JsonValue>
  mutationId?: string
}
```

```js
const { page } = await window.infolio.collection.update({
  values: { preferences: { compact: true } },
})
```

不传 `fieldKey` 时，`values` 必须是非空对象，键必须是 manifest 声明的 JSON 根成员。每个对象或数组作为一个完整值替换，不递归合并；未传成员保持不变；不能用这种模式更新 collection。

### 更新记录

```ts
interface RecordUpdate {
  fieldKey: string
  recordId: string
  values: Record<string, JsonValue>
  expectedVersion?: string
  mutationId?: string
}
```

返回 `{ record: CollectionRecord }`。`values` 是非空补丁；未传字段保持不变。优先传最近一次读取到的 `record.version` 作为 `expectedVersion`。

## `collection.delete()`

```ts
interface RecordDelete {
  fieldKey: string
  recordId: string
  expectedVersion?: string
  mutationId?: string
}

interface RecordDeleteResult {
  pageId: string
  fieldKey: string
  recordId: string
  deleted: true
}
```

仅在用户明确触发删除后调用。优先传最近一次读取到的 `version`。此方法只删除记录，不删除 MiniPage。

## 筛选、排序和分页

```ts
interface FilterGroup {
  conjunction: 'and' | 'or'
  conditions: Array<FilterGroup | FilterCondition>
}

interface FilterCondition {
  fieldId: string
  operator:
    | 'equals' | 'notEquals'
    | 'greaterThan' | 'greaterThanOrEqual'
    | 'lessThan' | 'lessThanOrEqual'
    | 'contains' | 'notContains' | 'startsWith' | 'endsWith'
    | 'in' | 'notIn' | 'between'
    | 'isEmpty' | 'isNotEmpty'
  value?: JsonValue
}
```

- 筛选树最多 12 层，每组最多 100 个条件。
- `isEmpty/isNotEmpty` 不传 value，适用于所有字段。
- JSON 与 attachment 只支持空值判断，不支持内容筛选或排序。
- 文本和 URL 支持 equals、notEquals、contains、notContains、startsWith、endsWith、in、notIn。
- number 和 date 还支持大小比较与 between；between 的 value 是两个元素。
- boolean 支持 equals、in、notIn 和空值判断。
- `in/notIn` 的 value 是 1–500 个同类型值。
- `search` 非空时必须同时传非空 `searchFieldIds`，且字段只能是 text 或 URL。
- sorts 最多 3 项；默认按 `_ctime` 升序，最终总以记录 ID 升序稳定排序。
- cursor 与页面、集合、字段选择、筛选、搜索、排序和 limit 绑定。改变任一条件时丢弃旧 cursor，从第一页重新查询。

## 错误、并发与重试

SDK Promise 拒绝时错误对象至少包含 `code` 和 `message`。

| code | 含义与处理 |
|---|---|
| `NOT_FOUND` | 页面、记录或资源不存在；停止重试并重新读取或返回上一级 |
| `DATA_NOT_READY` | 模板、schema 或同步数据尚未就绪；保留界面状态并允许稍后重试 |
| `VALIDATION_FAILED` | 参数或字段值不符合契约；定位输入并提示用户修正 |
| `VERSION_CONFLICT` | 记录已变化；重新查询后让用户基于新值继续 |
| `CHANNEL_CLOSED` | 页面通道关闭；提示重新打开页面，不自动循环重试 |
| `MEDIA_UNSUPPORTED` | 文件不是支持的图片或视频；保留草稿并提示选择其他文件 |
| `PERMISSION_DENIED` | 系统相册权限被拒绝；保留预览并提示检查系统权限 |
| `MEDIA_SAVE_FAILED` | 系统保存失败或无法保存该媒体格式；允许用户稍后重试 |
| `MCP_RUNTIME_UNAVAILABLE` | 本地账号或远程运行条件不满足；连接器方法不可用，保留页面本地功能 |
| `MCP_CONNECTION_INACTIVE` | 连接已失效；保留连接展示，提示用户在应用设置中恢复授权 |
| `MCP_CONNECTION_NOT_FOUND` / `MCP_CONNECTOR_NOT_FOUND` / `MCP_TOOL_NOT_ALLOWED` | 指定连接、连接器或工具不可用；重新加载目录并停止旧调用 |
| `MCP_ARGUMENTS_INVALID` | 连接器参数不符合 Schema；保留输入并修正 |
| `MCP_TOOL_REPORTED_ERROR` | 只读工具报告执行错误；通过模板的本地化错误界面展示 |
| `MCP_TOOL_SCHEMA_CHANGED` / `MCP_CREDENTIAL_REVISION_CONFLICT` / `MCP_CATALOG_REVISION_CONFLICT` | 工具或授权版本已变化；重新读取说明，让用户重新核对参数和写入意图 |
| `MCP_WRITE_OUTCOME_UNKNOWN` | 外部写入可能已发生；`details.retryable` 为 `false`，先核对外部状态，不自动重试 |

只有 collection 的 create、update、delete 支持 `mutationId`。SDK 省略时自动生成；如果模板为这些操作提供失败或超时后的“重试”，重试必须复用原 `mutationId`。超时不代表操作未提交，成功只表示本地提交，不表示远端同步完成。连接器调用不继承这一幂等保证。

写入期间禁用相关控件，防止重复提交。失败时保留表单和未保存输入；冲突必须重新读取，不能用旧版本盲目覆盖。

## `dataSchema`

```json
{
  "dataSchema": {
    "preferences": {
      "type": "json",
      "default": { "compact": false }
    },
    "records": {
      "type": "collection",
      "version": 1,
      "fields": [
        { "key": "title", "type": "text", "required": true },
        { "key": "done", "type": "boolean", "default": false },
        { "key": "photos", "type": "attachment", "default": [] }
      ]
    }
  }
}
```

- 根成员名和字段 key 以字母开头，只含字母、数字、下划线；不使用点路径。
- 允许多个 `type: "json"` 根成员，必须且只能有一个 `type: "collection"` 根成员。
- JSON 成员只允许 `type` 与可选 `default`；对象和数组整体保存在该成员中。
- collection 必须包含正整数 version 与 fields，不能有 default。
- 字段类型：`text`、`url`、`number`、`boolean`、`date`、`attachment`、`json`。
- 字段可包含 `required`、`default`、`labelKey`；只有 date 可包含 `options.dateFormat`，值为 `date` 或 `datetime`。
- date 使用 `YYYY-MM-DD`；datetime 使用带时区的 ISO 8601。number 必须有限。attachment 必须是 SDK 返回的描述数组。
- 宿主增加只读 `_ctime`、`_utime`；模板不得声明或写入 `_` 前缀字段。
- 所有需要写入的 JSON 成员和记录字段必须提前声明。

## 模板更新兼容性

保持 `templateId`、根成员名、collection 名、字段 key 和字段类型稳定。允许新增 JSON 成员、增加非必填记录字段、调整显示标签和合法默认值；记录定义变化时递增 collection version。

不要删除字段、改名、收紧 required、改变类型或在页面加载时回填默认值。旧页面可能缺少后来新增的值，UI 必须提供不写回的显示回退。
