# 消息审查（message_scrub）

本页说明复读**学习**与做梦**采集/漂流**前如何统一过滤入站消息：命中规则的内容不入库、不参与后续逻辑。**V4 起默认开启审查框架**；**内置严格下流词表默认生效**（`resource/message_scrub/vulgar.txt`，命中即拦），未配置其它词表或远程 API 时仅按内置词表拦截。

多数部署保持默认即可。需要再拦固定说法或接远程审核时，再配 WebUI **通用配置 → 消息审查与入站过滤**。

实现：`pallas/product/message_scrub/`。

## 配置

| 项 | 说明 |
| --- | --- |
| WebUI | **通用配置 → 消息审查与入站过滤** |
| 落盘 | `data/pallas_config/webui.json` |
| 生效 | 保存后 hub 热重载；分片 worker 按磁盘 mtime 自动重读 |
| 启用 | **V4 默认开启**；WebUI「通用配置 → 消息审查」可直接配词表或 API。设 `PALLAS_MESSAGE_SCRUB_ENABLED=false` 可完全关闭 |

### 常用配置键

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `PALLAS_INBOUND_FILTER_SUBSTRINGS` | 空 | 英文逗号分隔关键词，命中即拦 |
| `PALLAS_SCRUB_LEXICON_PATH` | 空 | 本地词表 txt（UTF-8，一行一词） |
| `PALLAS_SCRUB_LEXICON_EXTRA` | 空 | 追加词，逗号分隔 |
| `PALLAS_SCRUB_REVIEW_PROVIDERS` | 自动 | 远程审查顺序：`baidu`、`json_http` 等 |
| `PALLAS_SCRUB_BAIDU_API_KEY` / `SECRET` | 空 | 百度内容审核密钥 |
| `PALLAS_SCRUB_API_URL` | 空 | 自建审查 HTTP 接口 |
| `PALLAS_INBOUND_FILTER_API_FAIL_OPEN` | 放行 | 远程失败时：`1` 放行，`0` 当拦 |

完整字段见 WebUI 或 [`config.py`](https://github.com/PallasBot/Pallas-Bot/blob/main/pallas/product/message_scrub/config.py)。

### 群级追加屏蔽词

除全局词库外，可给单个群追加屏蔽词（WebUI 群配置的 `message_scrub_extra`，或直接编辑 `group_config` 行）：

- **只追加、不替代**：全局关键词、词表文件与内置下流词表照常生效，群词只做叠加。
- **仅群作用**：只在该群命中；私聊或未带群上下文的消息不受影响。
- **受总开关约束**：`PALLAS_MESSAGE_SCRUB_ENABLED=false` 时，群追加词一并失效。
- **生效范围**：保存后**当前进程立即**生效；多进程 / 分片部署其他进程正常约 30 秒由周期快照同步一次。加载失败时保留旧快照，故障期间不保证硬期限。
- 词表上限 200 词、每词 64 字符；写入前会 strip、去空、大小写不敏感去重，超限或非字符串会被拒绝。
- 群内可用 `添加屏蔽词` / `删除屏蔽词` / `查看屏蔽词` 命令增删查看本群词（默认群管/群主，可被控制台「命令权限」覆盖）；也可在 WebUI 群配置的 `message_scrub_extra` 或直接编辑 `group_config` 行维护。
- 命中仅做入站拦截，**不撤回**已发送消息。

### Bot 级追加屏蔽词

除全局与群词外，还可给单个 Bot（`bot_config` 的 `message_scrub_extra`）追加屏蔽词，作用于该 Bot 的**所有群与私聊**：

- **只追加、不替代**：全局关键词、词表文件、内置下流词表与各群词照常生效，Bot 词只做叠加；移除 Bot 词不会削弱全局或群词。
- **按 Bot 隔离**：只在该 Bot 命中，其他 Bot 不受影响；Bot id 与群 id 相同也不会串。
- **私聊管理**：当前 Bot 的绑定号主私聊发 `添加屏蔽词` / `删除屏蔽词` / `查看屏蔽词` 管理本 Bot 词；仅**当前 Bot 号主**可管理，其它 Bot 号主、未绑定超管、群管、ACL 放行与「命令权限」的 everyone 覆盖都不能越过该硬条件。群临时会话（sub_type=group）不能管理。
- **受总开关约束**：`PALLAS_MESSAGE_SCRUB_ENABLED=false` 时，Bot 追加词一并失效。
- **生效范围**：保存后**当前进程立即**生效；多进程 / 分片部署其他进程正常约 30 秒由周期快照同步一次。加载失败时保留旧快照，故障期间不保证硬期限。
- 词表上限 200 词、每词 64 字符；写入前会 strip、去空、大小写不敏感去重，超限或非字符串会被拒绝。
- 命中仅做入站拦截，**不撤回**已发送消息。

## 使用场景

| 目标 | 做法 |
| --- | --- |
| 完全不用审查 | `PALLAS_MESSAGE_SCRUB_ENABLED=false` |
| 拦固定说法 | 配关键词子串 |
| 本地词表 | 准备 txt → 设 `PALLAS_SCRUB_LEXICON_PATH`；改词表内容一般无需重启 |
| 百度审核 | 填 API Key + Secret Key |
| 自建网关 | 设 `PALLAS_SCRUB_API_URL`；约定 `POST` JSON，`blocked: true` 表示拦截 |
| 本地 + 远程 | 可同时启用；顺序由 `PALLAS_SCRUB_REVIEW_PROVIDERS` 控制，默认先百度再自建 |

### 词表文件

- **内置下流词表**：`resource/message_scrub/vulgar.txt`（随发行，187 词）**默认生效**，命中即拦，无需任何配置。
- 用户词表：UTF-8 文本，一行一词；`#` 开头为注释。相对路径相对于 Bot 工作目录，不确定时用绝对路径。大词表易误拦，建议小群试跑。
- 记忆写入防线：除入站审查外，`记住XX` 类教学注入、贬损教学词在记忆/关系笔记写入前另有兜底审查（`vulgar_lexicon.memory_guidance_block_reason`），入站漏网的词也会被拦。

### 远程审查

- **百度**：只需 Key/Secret，Token 自动换取；可选策略 ID、是否拦「疑似」。
- **自建**：Bearer 鉴权可用 `PALLAS_INBOUND_FILTER_API_KEY`；超时默认 2 秒。

## 排障

| 现象 | 处理 |
| --- | --- |
| 正常话被拦 | 缩小词表/关键词；远程「疑似」可关 `BLOCK_SUSPECTED` |
| 改了词表不生效 | 确认路径；或调用 `reload_message_scrub_caches()` |
| 远程总失败 | 查网络与超时；默认 fail-open 会放行 |

## 关联

- [牛牛复读](../../plugins/repeater/README.md)
- [牛牛做梦](../../plugins/dream/README.md)

## 实现

[`pallas/product/message_scrub/`](https://github.com/PallasBot/Pallas-Bot/tree/main/pallas/product/message_scrub/)
