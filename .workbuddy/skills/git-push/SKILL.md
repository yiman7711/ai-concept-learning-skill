---
name: git-push
description: "「一键推送」——把当前本地仓库的改动走完一整套 Git 流程并推送到远端：侦察 → 敏感信息/大文件扫描 → 精细暂存 → 规范提交 → 同步远端 → 推送 → 校验汇报。适用于用户说「推送到 GitHub」「提交并推送」「git commit 一下」「把改动传上去」「同步到远端」「发布到仓库」等场景；也适用于提交前自检（只看不做改动）。本项目默认远端为 git@github.com:yiman7711/ai-concept-learning-skill.git，主分支 main，SSH 密钥 ~/.ssh/id_ed25519。"
version: 1.0.0
agent_created: true
---

# git-push · 本地仓库推送闭环

把"把改好的东西传上 GitHub"从一串容易出错的散装命令，变成一个**有检查点、可中断、可回溯**的标准流程。
核心立场：**宁可停下来问，也不要盲推**。推送是不可逆的外部动作，一次误提交密钥或大文件，清理成本远高于多确认一句。

## 触发场景

- "把改动推送到 GitHub / 同步到远端"
- "提交一下 / commit 并 push / 帮我发布这版"
- "提交前先帮我看看有没有问题"（只跑第 1–2 步，产出报告，不做任何写入）
- 上一次推送失败（认证、分支、冲突、非快进）需要诊断并续推

## 硬性红线（任何情况下不破）

1. **绝不** `git add -A` / `git add .` 而不先看清单——必须逐项确认后再加。
2. **绝不**提交疑似密钥、令牌、密码、私钥、含个人信息的文件。扫描命中即**停止**，先处理再继续。
3. **绝不** `git push --force` / `-f`，除非用户明确点名要求，且已说明后果并二次确认。优先 `--force-with-lease`。
4. **绝不**加 `--no-verify` 跳过钩子、`--no-gpg-sign` 绕过签名；钩子失败要排查根因。
5. **绝不**把 token / 密码写进 remote URL、`.git/config`、脚本或提交信息。认证走 SSH 密钥或系统凭据管理器。
6. **绝不**在推送结果未确认前就向用户宣称"已推送成功"——必须以远端校验输出为准。

## 本项目默认环境

| 项 | 值 |
|----|----|
| 仓库根 | `C:\Users\zuliy\Documents\大数据与人工智能-本地备份` |
| remote `origin` | `git@github.com:yiman7711/ai-concept-learning-skill.git`（SSH） |
| 主分支 | `main` |
| SSH 私钥 | `~/.ssh/id_ed25519` |
| 提交身份 | `yiman7711` / `yiman7711@users.noreply.github.com` |
| 已忽略 | `.workbuddy/memory/`、密钥/凭据、构建产物、压缩包（见 `.gitignore`） |
| 项目级 Skill 位置 | `.workbuddy/skills/<skill-name>/SKILL.md`（**入库，随仓库分发**） |

## 执行流程

### 第 0 步 · 对齐意图

确认三件事，缺一就问用户（不要猜）：

1. **推送范围**：全部改动，还是只推某个目录/某几个文件？
2. **提交粒度**：一个提交打包，还是按主题拆成多个提交？
3. **是否只做自检**：用户若只是"看看有没有问题"，跑完第 1–2 步就交付报告，**不要写入**。

另外，**工作区里已存在的删除与重命名必须单独确认**——它们往往不是本次任务产生的（例如某个已入库的 Skill 文件在工作区被删了，而仓库里还有）。这类改动可能是有意重构，也可能是误操作，**不要顺手带进本次提交**。先问：恢复它，还是确认删除并提交？

### 第 1 步 · 侦察（只读）

```bash
cd "<repo-root>"
python .workbuddy/skills/git-push/scripts/preflight.py
```

脚本输出：仓库/分支/远端/上游追踪状态、暂存与未跟踪清单、敏感信息与超大文件扫描结果、以及**下一步建议的推送命令**。

Windows 下注意：脚本用原生 Python 运行，**不认 Git Bash 的 `/tmp/xxx` 这类路径**（会报"工作目录无效"）。传入路径前先转换：

```bash
python .workbuddy/skills/git-push/scripts/preflight.py --cwd "$(cygpath -w /tmp/xxx)"
```

常用参数：`--max-size-mb 5` 调整大文件阈值，`--quiet` 只看结论段。

若环境没有可用的 Python，退化为手工只读命令：
```bash
git rev-parse --show-toplevel
git status --short --branch
git remote -v
git log --oneline -5
git diff --stat            # 未暂存
git diff --cached --stat   # 已暂存
```

**判读要点**

- `## main...origin/main [gone]` → 远端上游分支已不存在（改名或重建过仓库）。必须用 `git push -u origin main` **重建上游**，普通 `git push` 会直接报错。
- `ahead N` → 有本地提交待推；`behind N` → 远端有本地没有的提交，先同步再推。
- 未跟踪文件数量异常多 → 检查是不是误把临时目录/产物放进来了，必要时补 `.gitignore`。

### 第 2 步 · 安全闸门（**必须通过才可继续**）

1. 逐条查看待提交内容：
   - 已暂存：`git diff --cached`
   - 未跟踪：`git diff --no-index /dev/null <file>` 或直接读文件开头
2. 检查四项：
   - **密钥/凭据**：`.env`、`*.pem`、`*.key`、含 `token`/`secret`/`password` 的文件，或源码里硬编码的 `sk-`、`ghp_`、`AKIA`、`BEGIN ... PRIVATE KEY`。
   - **个人信息**：真实姓名、手机号、身份证号、住址、他人截图（课程作业场景尤其要留意学号/姓名）。
   - **大文件**：单文件 > 5 MB 或二进制/模型权重/数据集，确认是否该走 `.gitignore` 或 Git LFS。
   - **隐私路径**：`.workbuddy/memory/`、编辑器与系统配置（`.vscode/`、`.idea/`、`Thumbs.db`、`.DS_Store`）。
3. 命中处理（按优先级）：
   - 能用 `.gitignore` 兜住的 → 补规则，用 `git rm --cached <file>` 从索引移除（**保留本地文件**）。
   - 必须入库但含敏感值 → 脱敏成占位符（如 `sk-xxxx`），值改放环境变量。
   - 疑似已提交进历史 → 停止推送，告知用户，由用户决定是否清理历史。**不要**自行改写历史。
4. 闸门通过后，记一句"扫描通过"再进下一步。

### 第 3 步 · 精细暂存

按需逐项加，避免整仓盲加：

```bash
git add <path1> <path2>
git status --short          # 复核：新增/修改是否符合预期
git diff --cached --stat    # 复核：改动量是否符合预期
```

- 中文/空格路径统一加引号：`git add "learning-materials/ai-01-bigdata.md"`。
- 路径显示被转义（`\346\225\260...`）时执行一次 `git config core.quotepath false`。
- 明确不想提交的文件：若只是本次不要，用 `git add` 精确选；若长期不要，加 `.gitignore`。

### 第 4 步 · 规范提交

提交信息格式（Conventional Commits + 中文描述，需能一眼看出改了什么）：

```
<type>(<scope>): <中文一句话说明>
```

- `type`：`feat` 新功能 / `fix` 修错 / `docs` 文档 / `chore` 杂务（依赖、配置、gitignore）/ `refactor` 重构 / `style` 排版 / `test` 测试 / `release` 版本。
- `scope` 可省略，建议用模块名，如 `feat(git-push): 新增推送闭环 Skill`。
- 正文（可选）说明**为什么**改，不重复罗列改了哪些文件。
- 禁止模糊信息：`update`、`修改`、`提交`、`fix bug`、`asdf`。

```bash
git commit -m "feat(git-push): 新增本地仓库推送闭环 Skill" -m "覆盖侦察、敏感信息扫描、暂存、提交、同步、推送与校验七个检查点。"
```

多行信息在 Git Bash 里用多个 `-m` 或 heredoc，避免换行被吞：

```bash
git commit -F - <<'EOF'
feat(git-push): 新增本地仓库推送闭环 Skill

覆盖侦察、敏感信息扫描、暂存、提交、同步、推送与校验。
EOF
```

提交前最后的自查：`git status` 是否还有本该一起提交的改动；敏感文件确认不在其中。

### 第 5 步 · 同步远端（防非快进被拒）

```bash
git fetch origin
git status --short --branch    # 看 behind
```

- `behind 0` → 直接进第 6 步。
- `behind N` → 先整合再推，优先变基保持线性：
  ```bash
  git pull --rebase origin main
  ```
  有冲突 → **停下来**，把冲突文件路径和冲突片段交给用户确认处理方式，不要盲选一侧。
- 上游 `[gone]` → 跳过 pull，直接进第 6 步并用 `-u` 重建。

### 第 6 步 · 推送

```bash
# 常规
git push

# 首次推送 / 上游 [gone] / 新分支
git push -u origin main

# 远端刚被改写过、已确认需要覆盖（仅在用户明确要求时）
git push --force-with-lease origin main
```

阻塞处理：SSH 认证失败、连接超时、非快进被拒、钩子拒绝等，见 `references/troubleshooting.md`（内含 Windows + Git Bash 场景的具体处置）。

### 第 7 步 · 校验与汇报

```bash
git status --short --branch        # 应显示 up to date / 无待推送
git log --oneline -3
git rev-parse HEAD                 # 本地完整哈希
git ls-remote --heads origin main  # 远端哈希，确认真写进去了
git rev-list --left-right --count origin/main...HEAD   # 期望 0  0
```

`git ls-remote` 返回的哈希必须与本地 `HEAD` **完全一致**，且领先/落后为 `0 0`，才算推送完成。

向用户汇报时**必须包含**：

1. 提交哈希与提交信息（`git log -1 --format='%h %s'`）
2. 本次提交的文件清单（`git show --stat --oneline HEAD`）
3. 目标远端与分支，以及远端最新哈希（来自 `git ls-remote`，不是本地推测）
4. 敏感信息扫描结论（通过 / 已处理哪些）
5. 若中途停下或降级处理，明确说明停在哪、原因、下一步

汇报要如实：本地 `git push` 成功 ≠ 远端确有该提交，以第 7 步的远端校验为准。

## 失败与中断处理

| 现象 | 定位 | 处置 |
|------|------|------|
| `Permission denied (publickey)` | SSH 或密钥未加载 | 见 troubleshooting §1 |
| `Could not resolve host` / 超时 | 网络或代理 | 见 troubleshooting §2 |
| `! [rejected] ... non-fast-forward` | 远端有新提交 | 见 troubleshooting §3 |
| `fatal: The current branch main has no upstream branch` / `[gone]` | 上游丢失 | `git push -u origin main` |
| `pre-commit hook failed` | 钩子校验未过 | 修根因；**不**用 `--no-verify` |
| 提交后才发现误提交密钥 | 历史污染 | 停止推送，报告用户，由用户决策 |
| `LF will be replaced by CRLF` | Windows 换行 | 警告可忽略；全仓统一可加 `.gitattributes` |

详细命令与判定见 `references/troubleshooting.md`。

## 收尾清单

- [ ] 敏感扫描通过（或已处理并说明）
- [ ] 暂存内容与用户意图一致，无多余文件
- [ ] 提交信息符合规范，粒度合理
- [ ] 已 fetch，无 behind 未整合
- [ ] 上游正常，`git status` 无待推送
- [ ] `git ls-remote` 确认远端哈希已更新
- [ ] 已向用户汇报哈希、文件清单、远端与分支
