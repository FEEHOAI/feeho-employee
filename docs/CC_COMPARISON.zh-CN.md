# 用 Claude Code 验证 FEEHO 员工生成器

这份测试不比较谁的文案更漂亮，而是检查同一句岗位需求能否变成**可检查的参数、真实工具边界和一次性审批证据**。

## 一句话区别

Claude Code 是通用执行者。FEEHO 员工生成器负责把执行者放进一个明确的岗位合同：能做什么、什么必须请示、什么绝对不能做、怎样验收，以及规则改变后哪些旧验收失效。

FEEHO 不替代 Claude Code，也不要求你更换模型。v0.2 可以把员工包编译成 Claude Code 的 `PreToolUse` 权限层。

## 1. 生成员工并查看参数 Diff

```bash
feeho draft \
  --role "内容运营经理" \
  --objective "拆解一周内容计划，安排选题、写稿和审核，发布由负责人决定。" \
  --request "可以写稿和审核，不能自行发布，发布前必须由负责人批准，标题夸大必须退回重写，不能增加预算。" \
  --output /tmp/feeho-content
```

你会看到：

```text
~ 撰写草稿（content:draft）：未声明 → 允许
~ 审核内容（content:review）：未声明 → 允许
~ 对外发布（external:publish）：未声明 → 需真人审批
~ 增加预算（budget:increase）：未声明 → 禁止
+ 新必过案例：external-publish-policy
+ 新必过案例：exaggerated-title-review
! 上次验收已失效，员工回到 draft，必须重新验收
```

这些不是说明文字。以下文件已经实际改变：

- `permissions.yaml`：允许、审批、禁止三组权限。
- `evals/cases.yaml`：新增对应的必过案例。
- `acceptance.yaml`：记录验收失效，保留真人复核要求。
- `employee.yaml`：状态回到 `draft`，不会自动宣称上岗。
- `policy-diff.json`：保存原始需求、前后参数和警告。

需求编译器当前是**确定性的中文规则编译器**，不是 LLM。无法识别的要求会显示警告，不会假装已经理解。

## 2. 把同一员工包装进 Claude Code

```bash
feeho cc /tmp/feeho-content
cd /tmp/feeho-content
claude
```

`feeho cc` 会生成 `.claude/settings.json`，注册官方 `PreToolUse` Hook。Hook 在工具执行前读取员工包权限；拦截时使用 Claude Code 官方约定的退出码 `2`，原因通过 stderr 返回给 Agent。

已有的 Hooks 会保留，不会直接覆盖。`feeho cc` 默认记录当前虚拟环境的 Python 路径，避免 Claude Code 调用了另一个没有安装 FEEHO 的 Python。

## 3. 不调用模型，先验证工具边界

在员工包目录执行：

```bash
printf '%s' '{"tool_name":"mcp__social__publish_post","tool_input":{"content":"测试草稿"}}' \
  | python3 -m feeho_employee.cc_hook --package .
```

预期：退出码为 `2`，并出现“FEEHO 审批门”。这证明的是**策略 Hook 真实拦截**，不是模型运行结果。

尝试让 Agent 自己批准自己：

```bash
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"feeho approve . --action external:publish --yes"}}' \
  | python3 -m feeho_employee.cc_hook --package .
```

预期：同样被拦截，动作归类为 `permission:self-modify`。

## 4. 真人授权只放行一次

在 **Claude Code 外部的另一个终端**执行：

```bash
feeho approve /tmp/feeho-content \
  --action external:publish \
  --yes
```

然后再次运行第 3 节的发布 Hook：

- 第一次：退出码 `0`，一次性授权被核销。
- 第二次：退出码 `2`，再次要求真人审批。

授权默认十分钟过期，只覆盖一个动作，不会改写长期权限。并发核销使用本地文件锁，避免两个工具调用共用同一张授权。

## 5. 查看审计记录

```bash
cat /tmp/feeho-content/.feeho-runtime/audit.jsonl
```

审计记录包含时间、工具类别、动作、决定和授权 ID。默认不记录文件正文、密钥值或完整工具输入。

`.feeho-runtime` 不会进入 `feeho export` 的 ZIP，授权与审计不会被误发给员工包接收方。

## 6. 验收真实 Agent 结果

仓库附带一个虚构的内容运营示例：

```bash
feeho test examples/content-operations \
  --results examples/content-operations/sample-results.json \
  --report /tmp/content-acceptance.json
```

`feeho test` 不调用模型。示例结果只用于演示合同检查，不代表模型评测、客户成绩或生产就绪。

## 安全边界

- Hook 是 Agent 工具策略层，不是操作系统沙箱。本机用户仍可绕过 Claude Code 或直接修改文件，高保证场景需要操作系统权限、容器和企业审批服务共同约束。
- 通用工具名与岗位动作之间的映射目前覆盖发布、发送、外部写入、凭证读取和自我提权。接入真实企业 MCP 时，应把服务器工具名显式映射到岗位动作，不要只依赖名称猜测。
- 合同通过仍需真人复核。Hook 拦截不等于完整模型质量评估。

官方协议来源：

- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
- [Anthropic 官方 Bash Hook 示例](https://github.com/anthropics/claude-code/blob/main/examples/hooks/bash_command_validator_example.py)
