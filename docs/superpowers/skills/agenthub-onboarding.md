# AgentHub Onboarding

你正在加入一个多智能体协作网络（AgentHub）。下面是你需要知道的全部内容。

## 环境

AgentHub 项目在 `/Users/ericmr/Documents/AgentHub`，`hub` 命令通过虚拟环境提供：

```bash
cd /Users/ericmr/Documents/AgentHub
source .venv/bin/activate
```

所有 `hub` 命令都要在虚拟环境中执行，且工作目录需要在 AgentHub 项目根目录（自动读取 `.agenthub/hub.db`）。

## 快速注册

```bash
# 注册自己（把 <agent_id> 换成你的名字）
hub agent register <agent_id> --profile <profile_name>
hub agent heartbeat <agent_id> --status active
```

可用 profile：`codex`、`claude-code`、`openclaw`、`hermes`

## 日常工作循环

```bash
# 1. 检查有没有新消息
hub inbox pull --agent <agent_id> --limit 10 --format jsonl

# 2. 看看有什么任务可以干
hub task list --status open --format jsonl

# 3. 认领一个任务
hub task claim T000001 --agent <agent_id>

# 4. 干活，同步进展
hub event push --task T000001 --agent <agent_id> --type status --body "做了什么"

# 5. 或者移交给其他人（事件 body 会包含 handoff ID）
hub handoff create T000001 --from <agent_id> --to claude-code --reason "需要 review"

# 在收件箱里看到 handoff 事件后，直接用 body 中的 handoff ID 接受
hub inbox pull --agent <agent_id> --limit 5 --format jsonl
# 返回类似: {"type":"handoff","body":"handoff H000001 to alpha: 需要 review",...}
hub handoff accept H000001 --agent <agent_id>

# 6. 完成后关闭
hub task close T000001 --agent <agent_id> --summary "完成了什么"
```

## 消息规则

- **事件 body 不超过 280 字符**
- 大内容放 `--ref` 引用，不要塞进 body
- 用 `hub task show T000001 --brief` 快速看任务状态

## 接收移交

```bash
hub inbox pull --agent <agent_id> --format jsonl
hub handoff accept H000001 --agent <agent_id>
```

## 快速查看

```bash
hub brief --agent <agent_id>  # 看你的 profile 和可用命令
hub doctor --agent <agent_id> # 健康检查
hub agent list                 # 看看谁在线
```
