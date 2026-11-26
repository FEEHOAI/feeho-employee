---
description: 只读预览 FEEHO 组织与权限 Diff
argument-hint: "<一句要改变的要求>"
---

请按顺序执行，不要自己编造参数或修改合同文件：

1. 运行 `feeho propose . --request "$ARGUMENTS"`，向用户展示只读 Diff、验收影响和下一次执行路径。
2. 明确告诉用户：当前只是预览，员工包没有被修改，Agent 不能自行应用或批准。
3. 如果用户决定应用，请用户在 Agent 外部终端运行输出中的 `feeho configure` 命令。
4. 应用后可运行 `feeho history .`、`feeho diff .` 和 `feeho simulate .` 核对版本与实际执行边界。
5. 涉及发布或其他审批动作时，真人必须在 Agent 外部运行 `feeho approve`。Agent 不得代替真人签发授权。

FEEHO generated command; safe to regenerate with `feeho cc`.
