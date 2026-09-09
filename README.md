# AI 概念学习 Skill 作业仓库

「大数据与人工智能」课程作业：借助 AI 完成 **"创建 Skill → 学习概念 → 核查 → 提交 GitHub"** 的完整闭环。
本仓库用自己设计的项目级 Skill **`concept-mastery`（概念精讲）**，对 **Agent、大模型的上下文、Skill** 三个核心概念进行了结构化学习，并把学习成果与 Skill 本体一起版本化、推送到 GitHub。

---

## 1. 仓库用途

1. 存放我设计的**可复用学习 Skill**（项目级）。
2. 存放由该 Skill 组织生成的**三份概念学习资料 + 一份概念关系说明**。
3. 完整演示一次"用 AI 建仓库、写 Skill、调 Skill、人工核查、提交推送"的真实工作流。

## 2. Skill 存放路径

Skill 位于仓库根目录的项目级技能目录中：

```
.workbuddy/skills/concept-mastery/
└── SKILL.md
```

`SKILL.md` 顶部含 YAML 元数据（`name`、`description` 等），正文详细写明了：适用场景、输入信息、生成步骤、输出结构、资料来源要求、自检要求——**它能接收任意一个新的概念作为学习主题**，并非只为本次三个概念写的一次性提示。

## 3. 如何在 WorkBuddy 中调用它

1. 用 WorkBuddy **打开本仓库根目录**（项目级 Skill 才能被识别）。
2. 在对话框里用自然语言发起请求即可触发，例如：
   - `调用 concept-mastery，学习一下「RAG」这个概念`
   - `用我的概念学习方法，讲讲「Token 与 Context 的区别」`
3. WorkBuddy 会匹配 Skill 的 `description` → 按需加载 `SKILL.md` → 按其中定义的目标/问题/解释/辨析/自测/来源流程，输出一份结构化的学习资料（Markdown 或 HTML），建议存入 `learning-materials/`。

> 说明：本 Skill 是随仓库分发的自定义项目级 Skill，需由使用它的 WorkBuddy 会话正确加载 `.workbuddy/skills/` 下的文件。

## 4. 已生成的学习资料

`learning-materials/` 目录下：

| 文件 | 内容 |
|------|------|
| `agent.html` | Agent 概念精讲（个人解释、核心机制、应用场景、易混淆辨析、自测、可核查来源） |
| `llm-context.html` | 大模型的上下文 / 上下文窗口精讲 |
| `skill.html` | Skill 概念精讲 |
| `concept-relationship.md` | 三概念关系说明（含 Mermaid 图，重点讲"上下文如何影响 Agent、Skill 如何沉淀可复用任务知识"） |

## 5. 我在使用 AI 后做了哪些人工核查与修改

按要求，我没有整段照搬 AI 输出，做了如下人工工作：

1. **重写表达**：概念解释均用我自己的话重述（每份资料均含"我的理解"小节），而非复制 AI 对话原话。
2. **核查资料来源**：对每个参考链接做了可访问性核实（部分经实际访问、部分因站点区域限制改为交叉检索确认），并在资料中如实标注"已核实 / 待核实"；**未编造任何 URL**。资料来源优先选用官方文档（Anthropic、OpenAI）。
3. **统一并校订 Skill 结构**：确认 `SKILL.md` 同时满足"通用（任意概念）+ 本作业三概念"两用，字段齐全（name/description/适用场景/输入/生成步骤/输出/来源要求/自检）。
4. **修正命名与路径**：仓库结构、文件命名（`agent.html`、`llm-context.html`、`skill.html`、`concept-relationship.md`）按作业要求统一。
5. **安全清理**：全仓检查，无 API Key / 密码 / 个人隐私；`.gitignore` 已排除密钥、凭据、本地编辑器与系统配置文件、构建产物等敏感项；提交前用 `git status`/`git diff` 复查待提交内容。

## 6. 目录结构

```
.
├── .gitignore
├── .workbuddy/
│   └── skills/
│       └── concept-mastery/
│           └── SKILL.md          # 项目级 Skill 本体
├── learning-materials/
│   ├── agent.html                # 概念资料：Agent
│   ├── llm-context.html          # 概念资料：大模型的上下文
│   ├── skill.html                # 概念资料：Skill
│   └── concept-relationship.md   # 概念关系说明
└── README.md
```

## 7. 环境与致谢

- 环境：Windows + Git；内容生成/核查使用 AI 助手协助，经人工复核后入库。
- 参考的官方资料见各学习资料的"参考来源"小节。
