# git-push 排障参考

按现象查表。原则不变：**能停下确认的，就不要强行绕过**。

## §1 SSH 认证失败

现象：

```
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

排查顺序：

```bash
# 1) 密钥是否存在（本项目用 ed25519）
ls -l ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub

# 2) 详细握手日志，看用了哪把密钥、被怎么拒绝
ssh -vT git@github.com

# 3) 只测指定密钥
ssh -i ~/.ssh/id_ed25519 -T git@github.com
```

- 输出 `Hi <username>! You've successfully authenticated` → 密钥可用，问题在 remote URL 或代理。
- 输出 `Permission denied (publickey)` 且已尝试正确密钥 → 公钥未添加到 GitHub。让用户到
  GitHub → Settings → SSH and GPG keys 添加 `~/.ssh/id_ed25519.pub` 内容（**只贴 `.pub`**）。
- 报 `UNPROTECTED PRIVATE KEY FILE` / `bad permissions` → 权限过宽：

  ```bash
  chmod 600 ~/.ssh/id_ed25519
  ```

- 报 `Host key verification failed` → 首次连接，确认指纹后：

  ```bash
  ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
  ```

- remote 仍是 HTTPS 形式 → 换成 SSH：

  ```bash
  git remote set-url origin git@github.com:<user>/<repo>.git
  ```

**不要**把 token 拼进 URL（`https://<token>@github.com/...`）——会明文留在 `.git/config` 里。

## §2 网络 / 代理

现象：`Could not resolve host`、`Failed to connect ... port 22`、`Connection timed out`。

```bash
ping -n 2 github.com            # Windows
ssh -T git@github.com           # 测 22 端口
ssh -T -p 443 git@ssh.github.com  # 测 443 端口（22 被墙时的替代）
```

22 端口不通、443 可通时，写 `~/.ssh/config`：

```
Host github.com
  HostName ssh.github.com
  Port 443
  User git
  IdentityFile ~/.ssh/id_ed25519
```

代理环境下（有 http(s) 代理但 SSH 不走代理）：

```bash
git config --get http.proxy
git config --get https.proxy
# 必要时：
# git config --global http.proxy http://127.0.0.1:<port>
# 取消：
# git config --global --unset http.proxy
```

注意：`git config --global` 会改全局配置，属于本地环境的持久改动，执行前先告知用户。

## §3 非快进被拒

现象：

```
! [rejected]  main -> main (non-fast-forward)
hint: Updates were rejected because the remote contains work that you do not have locally.
```

含义：远端有本地没有的提交（可能在网页上改过，或另一台机器推过）。

```bash
git fetch origin
git log --oneline HEAD..origin/main    # 远端独有的提交
git log --oneline origin/main..HEAD    # 本地独有的提交
```

- 历史可线性整合 → `git pull --rebase origin main`，解决冲突后再 `git push`。
- 冲突处理：`git status` 列出冲突文件，逐个人工确认保留哪一侧，`git add <file>` 后
  `git rebase --continue`。**不确定就停下问用户**，不要盲选 ours/theirs。
- 想放弃变基回到原状：`git rebase --abort`。
- 确认远端内容确实要丢弃（**仅在用户明确要求时**）：
  `git push --force-with-lease origin main`。

## §4 上游分支丢失

现象：

```
fatal: The current branch main has no upstream branch.
```
或 `git status -sb` 显示 `## main...origin/main [gone]`。

原因：远端分支被删除/改名，或仓库被重建。

```bash
git fetch origin --prune           # 清理本地失效的远端追踪引用
git branch -vv                     # 确认当前分支与上游
git push -u origin main            # 重建上游并推送
```

若 `git branch -vv` 显示上游指向一个已不存在的名字，先解除再重设：

```bash
git branch --unset-upstream
git push -u origin main
```

## §5 提交被钩子拦截

现象：`pre-commit` / `commit-msg` / `pre-push` 失败。

- 读完整报错，**修根因**（常见：格式检查、密钥扫描钩子命中、lint 失败）。
- 不要在用户未明确要求时使用 `--no-verify` —— 这会把本该拦下的问题放行。
- 钩子报"文件被修改"（如 formatter 自动改写了文件）→ 把改写后的结果重新 `git add` 再提交。
- 确实需要绕过时：向用户说明被跳过的检查内容与风险，取得明确同意后再执行。

## §6 中文路径与换行

- 路径显示成 `\346\225\260...`：`git config core.quotepath false`
- `LF will be replaced by CRLF`：仅是 Windows 换行提示，可忽略；要全仓统一则加
  `.gitattributes`：

  ```
  * text=auto eol=lf
  *.ps1 text eol=crlf
  *.bat text eol=crlf
  ```

- 中文文件名/内容乱码：在 Git Bash 中确认 `git config --get i18n.commitEncoding`、
  `locale`；提交信息统一用 UTF-8 编写。

## §7 大文件被拒

现象：`remote: error: File ... is 123.45 MB; this exceeds GitHub's file size limit of 100.00 MB`
或 `GH001: Large files detected`。

```bash
git rm --cached <big-file>          # 从索引移除，保留本地文件
echo "<pattern>" >> .gitignore
git commit --amend                  # 若该文件在最近一次未推送的提交里
```

- 文件已在**已推送的历史**里 → 需要 `git filter-repo` 类工具重写历史 + 强推，风险高，
  **必须由用户决策**，不要自行执行。
- 大文件确实要版本化 → 改用 Git LFS（需用户确认后再装）。

## §8 结果校验（每次推送后必做）

```bash
git status --short --branch             # 期望：nothing to commit / up to date
git log --oneline -3
git show --stat --oneline HEAD          # 本次提交包含哪些文件
git ls-remote --heads origin main        # 远端真实哈希，与本地 HEAD 对比
git rev-parse HEAD                       # 本地完整哈希
```

只有当 `git ls-remote` 返回的哈希与本地 `HEAD` 一致（或本地 HEAD 是其祖先时符合预期，
即确实已包含本地提交）才算推送完成。仅凭本地 `git push` 的输出不足以判定。

## §9 侦察脚本本身的常见问题

`scripts/preflight.py` 退出码即结论：`0` 通过（可能带提示）、`1` 安全扫描命中、`2` 环境或仓库异常。

| 现象 | 原因 | 处置 |
|------|------|------|
| `[异常] 工作目录不存在` + 提示 `cygpath` | 传了 Git Bash 风格路径（`/tmp/xxx`），原生 Python 不识别 | 用 `--cwd "$(cygpath -w /tmp/xxx)"`，或直接 `cd` 到仓库再不带参数运行 |
| 首行路径少一个字符（如 `.workbuddy` 显示成 `workbuddy`） | 历史版本整体 `strip()` 吃掉了首行行首空格 | 已修：改用 `git status --porcelain -uall -z` + 保留原始输出。若复现，说明脚本被改回按行切分了 |
| 未跟踪的**目录**没有被逐个扫描 | porcelain 默认会把整个未跟踪目录折叠成 `dir/` 一项 | 已修：加 `-uall` 展开到文件级 |
| HTML 代码示例、`os.environ["X"]` 被误判为硬编码凭据 | 教学示例里的 `sk-xxx` 或读环境变量的写法命中规则 | 脚本已做去标签 + 环境变量白名单；**仍命中时按真密钥处理**——文件里确实存在完整密钥字符串就无法自动区分真假，交由人工确认或脱敏 |
| 中文路径显示为 `\346\225\260...` | `core.quotepath` 转义 | `git config core.quotepath false`（脚本内部已强制关闭） |
| 报 `超大文件` 但文件其实不大 | 该文件处于未跟踪目录中，或被重复计入 | 用 `--max-size-mb` 调整阈值；确认是否需要补 `.gitignore` |

