#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git-push Skill 的推送前侦察脚本（只读，不做任何写入）。

输出四段报告：
  1. 仓库 / 分支 / 远端 / 上游追踪状态
  2. 工作区清单（已暂存、已修改、未跟踪，未跟踪目录会展开到文件级）
  3. 安全扫描（疑似密钥、隐私路径、超大文件、二进制）
  4. 结论与建议的下一步命令

用法：
    python preflight.py [--cwd <repo>] [--max-size-mb 5] [--quiet]

退出码：0 = 通过或仅有提示；1 = 安全扫描命中（应在提交前处理）；2 = 环境/仓库异常。
"""

import argparse
import html as html_mod
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- 输出编码

try:  # Windows 控制台默认 GBK，统一成 UTF-8 以免中文乱码
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

# ---------------------------------------------------------------- 扫描规则

# 路径规则：命中即高危（不该入库）
SENSITIVE_PATH_PATTERNS = [
    (re.compile(r"(^|/)\.env(\.|$)", re.I), "环境变量文件"),
    (re.compile(r"\.(pem|key|p12|pfx|keystore|jks)$", re.I), "密钥/证书文件"),
    (re.compile(r"(^|/)(credentials|secrets?)\.(json|ya?ml|ini|toml)$", re.I), "凭据文件"),
    (re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$"), "SSH 私钥"),
    (re.compile(r"(^|/)\.workbuddy/memory/", re.I), "WorkBuddy 本地记忆（不应入库）"),
    (re.compile(r"(^|/)(\.vscode|\.idea)/"), "编辑器配置"),
    (re.compile(r"(^|/)(Thumbs\.db|\.DS_Store)$", re.I), "系统残留文件"),
    (re.compile(r"(^|/)(node_modules|__pycache__|dist|build)/"), "构建产物/依赖目录"),
]

# 内容规则：命中即高危，必须处理后再提交
SECRET_CONTENT_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "PEM 私钥块"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "GitHub 访问令牌"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "GitHub 细粒度令牌"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API Key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "OpenAI 风格 API Key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS Access Key ID"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "Slack Token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API Key"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "JWT 令牌"),
]

# 赋值式：关键词 + 分隔符 + 疑似真实值
ASSIGN_RE = re.compile(
    r"""(?ix)
    \b(api[_-]?key|apikey|secret|secret[_-]?key|access[_-]?token|auth[_-]?token|
       password|passwd|pwd|private[_-]?key|client[_-]?secret|token)\b
    \s*[:=]\s*
    ["']?(?P<val>[^"'\s,;]{8,})["']?
    """
)
# 值本身就说明"不是真密钥"：占位符、变量引用、从环境/配置读取
SAFE_VALUE_RE = re.compile(
    r"""(?ix)^(
        x{3,}|\*{3,}|<[^>]*>|\$\{?[a-z_][a-z0-9_]*\}?|%[a-z_]+%|
        your[_-]?\w*|my[_-]?\w*|placeholder|todo|none|null|changeme|
        example\w*|redacted|dummy|fake|sample|test\w*|\*+|\.\.\.|
        os\.|sys\.|process\.env|getenv|environ|env\[|dotenv|
        config\.|settings\.|setting\.|app\.config|import\.meta\.env|
        self\.|this\.|request\.|ctx\.|context\.|options\.|params\.
    )"""
)
ENV_READ_RE = re.compile(r"(?i)(os\.environ|os\.getenv|process\.env|getenv\s*\(|environ\[|dotenv|System\.getenv)")

# 个人信息：仅提示，不算高危（学习笔记里出现本人信息很常见）
PII_CONTENT_PATTERNS = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "疑似手机号"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "疑似身份证号"),
]

TEXT_EXT = {
    ".md", ".txt", ".py", ".ipynb", ".js", ".ts", ".jsx", ".tsx", ".json", ".json5",
    ".html", ".htm", ".css", ".scss", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".conf", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".sql", ".java", ".c", ".h",
    ".cpp", ".cs", ".go", ".rs", ".rb", ".php", ".vue", ".svelte", ".xml", ".env",
    ".properties", ".gradle", ".r", ".jl", ".tex", ".markdown", ".text",
}
TEXT_NAMES = {"gitignore", "gitattributes", "dockerfile", "makefile", "license"}
SCAN_MAX_BYTES = 2 * 1024 * 1024  # 单文件扫描上限 2 MB
SNIPPET_LEN = 70

# HTML 代码示例常见包裹标签：只剥这两类，避免把 <a href="真密钥"> 一起剥掉
SPAN_TAG_RE = re.compile(r"</?span\b[^>]*>", re.I)


# ---------------------------------------------------------------- 工具函数


def run_git(args, cwd, keep_raw=False):
    """执行 git 命令，返回 (returncode, stdout, stderr)。

    keep_raw=True 时保持 stdout 原样——处理 porcelain 输出必须用它，
    否则整体 strip 会吃掉首行开头的空格，导致 XY 错位、路径被截。
    """
    try:
        p = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        out = p.stdout or ""
        return p.returncode, (out if keep_raw else out.strip()), (p.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "工作目录不存在，或 git 未安装/不在 PATH 中"
    except NotADirectoryError:
        return 126, "", f"工作目录无效：{cwd}"
    except subprocess.TimeoutExpired:
        return 124, "", "git 命令超时（网络类命令可能被墙或代理异常）"


def git_ok(args, cwd, fallback=""):
    rc, out, _ = run_git(args, cwd)
    return out if rc == 0 else fallback


def parse_porcelain(cwd):
    """解析 `git status --porcelain -uall -z`，返回 ([(xy, path)], error)。

    用 -z 拿到 NUL 分隔的原始输出：既不做 C 风格路径转义（中文路径免转义），
    也不会因为换行/行首空格而被误解析。
    格式：`XY <path>\\0`；重命名/复制为 `XY <new>\\0<old>\\0`。
    """
    rc, out, err = run_git(
        ["-c", "core.quotepath=false", "status", "--porcelain", "-uall", "-z"],
        cwd,
        keep_raw=True,
    )
    if rc != 0:
        return [], err

    tokens = out.split("\0")
    entries = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if len(tok) < 4:  # 最短形如 "?? x"
            i += 1
            continue
        xy, path = tok[:2], tok[3:]
        if xy[0] in ("R", "C") and i + 1 < len(tokens):
            i += 1  # 紧跟的 token 是原路径，跳过
        entries.append((xy, path))
        i += 1
    return entries, ""


def is_text_file(path):
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1].lower()
    if name in TEXT_NAMES or ext in TEXT_EXT:
        return True
    return not ext  # 无扩展名按文本尝试


def read_text(path):
    try:
        if os.path.getsize(path) > SCAN_MAX_BYTES:
            return None
        with open(path, "rb") as f:
            raw = f.read(SCAN_MAX_BYTES)
        if b"\x00" in raw[:4096]:
            return None  # 二进制
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return None


def detag(line):
    """还原 HTML 代码示例的可读形态：剥 span 标签 + 反转义实体。"""
    return html_mod.unescape(SPAN_TAG_RE.sub("", line)).strip()


def scan_line(raw_line):
    """扫描单行，返回 (high_labels, pii_labels)。

    对同一行同时看原始形态与"去标记"形态：只有去标记后仍命中才算高危，
    避免把 HTML 里 <span class="str">"sk-xxx"</span> 这类教学示例误判。
    """
    variants = {raw_line}
    plain = detag(raw_line)
    if plain and plain != raw_line:
        variants.add(plain)

    high, pii = [], []
    for line in variants:
        probe = line[:4000]
        hit = False
        for rx, label in SECRET_CONTENT_PATTERNS:
            if rx.search(probe):
                high.append(label)
                hit = True
                break
        if not hit:
            m = ASSIGN_RE.search(probe)
            if m:
                val = m.group("val").strip().strip("\"'")
                if (
                    not SAFE_VALUE_RE.match(val)
                    and not val.startswith(("${", "$", "%"))
                    and not ENV_READ_RE.search(probe)
                ):
                    high.append("疑似硬编码凭据赋值")
        for rx, label in PII_CONTENT_PATTERNS:
            if rx.search(probe):
                pii.append(label)
                break
    dedup = lambda xs: list(dict.fromkeys(xs))
    return dedup(high), dedup(pii)


def scan_content(text):
    high, pii = [], []
    for i, line in enumerate(text.splitlines(), 1):
        h, p = scan_line(line)
        if h:
            high.append((i, "、".join(h), detag(line)[:SNIPPET_LEN]))
        if p:
            pii.append((i, "、".join(p), detag(line)[:SNIPPET_LEN]))
    return high, pii


def human_size(n):
    val = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if val < 1024 or unit == "GB":
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} GB"


# ---------------------------------------------------------------- 主流程


def main():
    ap = argparse.ArgumentParser(description="推送前只读侦察")
    ap.add_argument("--cwd", default=".", help="仓库路径，默认当前目录")
    ap.add_argument("--max-size-mb", type=float, default=5.0, help="大文件阈值(MB)，默认 5")
    ap.add_argument("--quiet", action="store_true", help="只输出结论段")
    args = ap.parse_args()

    cwd = os.path.abspath(args.cwd)
    if not os.path.isdir(cwd):
        print(f"[异常] 工作目录不存在：{args.cwd}")
        print(f"       实际解析为：{cwd}")
        if os.name == "nt" and args.cwd.startswith("/"):
            print("       提示：/tmp 这类 Git Bash 路径原生 Python 不识别，")
            print("             请先执行 cygpath -w <路径> 转为 Windows 路径再传入。")
        return 2
    max_bytes = int(args.max_size_mb * 1024 * 1024)
    quiet = args.quiet
    blocked = []   # (path, reason) → 退出码 1
    notes = []     # 提示
    next_cmds = []

    def head(title):
        if not quiet:
            print()
            print("=" * 62)
            print(title)
            print("=" * 62)

    def report(reason):
        """记录高危项，按 (路径, 原因) 去重。"""
        if (None, reason) not in blocked:
            blocked.append((None, reason))

    # ---- 1. 仓库状态 ----
    head("1. 仓库 / 分支 / 远端")
    rc, top, err = run_git(["rev-parse", "--show-toplevel"], cwd)
    if rc != 0:
        print(f"[异常] 当前目录不是 Git 仓库：{cwd}")
        print(f"       git 返回：{err}")
        print("       处理：先 git init，或切换到仓库根目录再运行。")
        return 2
    top = top.replace("\\", "/")
    cwd = os.path.abspath(top)
    print(f"仓库根目录 : {top}")

    branch = git_ok(["rev-parse", "--abbrev-ref", "HEAD"], cwd, "(未知)")
    head_hash = git_ok(["rev-parse", "--short", "HEAD"], cwd, "(无提交)")
    subject = git_ok(["log", "-1", "--format=%s"], cwd, "")
    print(f"当前分支   : {branch}")
    print(f"HEAD       : {head_hash}  {subject}".rstrip())

    remotes = git_ok(["remote", "-v"], cwd)
    if not remotes:
        print("[异常] 未配置任何 remote。")
        report("仓库未配置 remote：需要 git remote add origin <仓库URL>")
        next_cmds.append("git remote add origin <仓库URL>")
    else:
        for line in remotes.splitlines():
            print(f"remote     : {line}")

    # 上游追踪状态
    upstream = git_ok(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd, ""
    )
    sb = git_ok(["status", "--short", "--branch"], cwd, "")
    first_line = sb.splitlines()[0] if sb else ""
    gone = "[gone]" in first_line
    configured_upstream = git_ok(["config", f"branch.{branch}.remote"], cwd, "")

    if upstream:
        print(f"上游分支   : {upstream}")
        counts = git_ok(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"], cwd, "")
        if counts:
            behind, ahead = (counts.split() + ["?", "?"])[:2]
            print(f"领先/落后  : ahead {ahead} / behind {behind}")
            if behind not in ("0", "?"):
                notes.append(
                    f"本地落后远端 {behind} 个提交：推送前需先 git fetch && git pull --rebase origin {branch}"
                )
                next_cmds.append(f"git pull --rebase origin {branch}")
            if ahead == "0":
                notes.append("本地没有待推送的新提交")
        else:
            print("[提示] 上游已配置，但无法读取领先/落后数量（可能需要先 git fetch）。")
    elif gone or configured_upstream:
        print(f"上游分支   : origin/{branch} 已失效（[gone]）")
        notes.append(
            f"上游分支不存在：普通 git push 会失败，必须用 git push -u origin {branch} 重建上游"
        )
        next_cmds.append(f"git push -u origin {branch}")
    else:
        print("上游分支   : (未设置)")
        notes.append(f"当前分支没有上游：需 git push -u origin {branch} 建立追踪关系")
        next_cmds.append(f"git push -u origin {branch}")

    # ---- 2. 工作区清单 ----
    head("2. 工作区清单")
    entries, serr = parse_porcelain(cwd)
    if serr:
        print(f"[异常] 无法读取 git status：{serr}")
        return 2

    staged = [p for xy, p in entries if xy[0] not in (" ", "?")]
    modified = [p for xy, p in entries if xy[0] == " " and xy[1] not in (" ", "?")]
    untracked = [p for xy, p in entries if xy.startswith("??")]
    deleted = [
        p for xy, p in entries if "D" in xy
    ]

    def dump(label, items, limit=200):
        print(f"\n{label}（{len(items)}）")
        if not items:
            print("  （无）")
            return
        for p in items[:limit]:
            print(f"  - {p}")
        if len(items) > limit:
            print(f"  ... 其余 {len(items) - limit} 项省略")

    dump("已暂存待提交", staged)
    dump("已修改未暂存", modified)
    dump("未跟踪新文件", untracked)
    if deleted:
        print(f"\n注意：本次涉及 {len(deleted)} 个删除操作，确认是有意删除：")
        for p in deleted[:20]:
            print(f"  - {p}")

    if not entries:
        notes.append("工作区干净，没有可提交的改动")
    elif not staged:
        notes.append("暂存区为空：提交前需先 git add 目标文件（逐项添加，避免 git add -A 盲加）")

    # ---- 3. 安全扫描 ----
    head("3. 安全扫描")
    # 必须覆盖"内容可能变化"的全部文件：已暂存 + 已修改未暂存 + 未跟踪。
    # 只算 staged + untracked 会漏掉"往已入库文件里写入密钥"这种最常见的情形。
    to_commit = list(dict.fromkeys(staged + modified + untracked))
    print(
        f"扫描范围：暂存 {len(staged)} + 已修改 {len(modified)} + 未跟踪 {len(untracked)}，"
        f"去重后 {len(to_commit)} 个文件"
    )

    # 3.1 路径规则
    print("\n路径规则检查：")
    path_hits = 0
    for p in to_commit:
        norm = "/" + p.replace("\\", "/")
        for rx, label in SENSITIVE_PATH_PATTERNS:
            if rx.search(norm):
                blocked.append((p, f"敏感路径：{label}"))
                path_hits += 1
                break
    print(f"  {'! 命中 %d 项，见结论段' % path_hits if path_hits else 'ok 未命中'}")

    # 3.2 逐文件内容扫描
    print("\n逐文件内容检查：")
    if not to_commit:
        print("  （无待提交文件）")
    for p in to_commit:
        abspath = os.path.join(cwd, p.replace("/", os.sep))
        if not os.path.exists(abspath):
            print(f"  -- {p}  → 文件不存在（删除操作，跳过内容扫描）")
            continue
        flags = []
        size = os.path.getsize(abspath)
        if size > max_bytes:
            blocked.append((p, f"超大文件 {human_size(size)} > {args.max_size_mb:g} MB"))
        elif size > max_bytes * 0.4:
            flags.append(f"偏大文件 {human_size(size)}")
        text = read_text(abspath) if is_text_file(p) else None
        if text is None:
            flags.append(f"二进制或超过 {SCAN_MAX_BYTES // 1024 // 1024} MB，未做内容扫描")
        else:
            high, pii = scan_content(text)
            for ln, label, snippet in high:
                blocked.append((p, f"{label}（第 {ln} 行：{snippet}）"))
            for ln, label, snippet in pii[:3]:
                notes.append(f"{p} 第 {ln} 行出现{label}，请确认是否适合公开：{snippet}")
        if flags:
            for f in flags:
                print(f"  ! {p}  → {f}")
        else:
            print(f"  ok {p}")

    # 3.3 gitignore 覆盖检查
    print("\n.gitignore 覆盖检查：")
    need_ignore = []
    for p in untracked:
        norm = "/" + p.replace("\\", "/")
        if re.search(r"(^|/)\.env", norm, re.I) or re.search(r"\.(pem|key|p12|pfx)$", norm, re.I):
            need_ignore.append(p)
    if need_ignore:
        for p in need_ignore:
            print(f"  ! {p} 未被忽略")
            blocked.append((p, "敏感文件未被 .gitignore 覆盖"))
    else:
        print("  ok 未发现明显应被忽略却未忽略的敏感文件")

    # ---- 4. 结论 ----
    head("4. 结论与建议")
    # 去掉占位式记录（无路径）里的重复
    uniq, seen = [], set()
    for item in blocked:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    blocked = uniq

    if blocked:
        print("[结果] 未通过 —— 发现需要在提交前处理的问题：\n")
        for p, why in blocked:
            print(f"  x  {p or '(仓库级)'}\n      {why}")
        print("\n处理方式：")
        print("  1) 不该入库 → 补 .gitignore，并 git rm --cached <file>（保留本地文件）")
        print("  2) 必须入库但含敏感值 → 脱敏为占位符，值改读环境变量")
        print("  3) 疑似已进入历史 → 停止推送，先报告用户，不要自行改写历史\n")
        print("处理完成后重新运行本脚本复检。")
    else:
        print("[结果] 通过 —— 未发现密钥、敏感路径或超大文件问题。")

    if notes:
        print("\n[提示]")
        for n in notes:
            print(f"  - {n}")

    if not blocked:
        print("\n[下一步建议命令]")
        if staged:
            print("  git diff --cached --stat            # 复核改动量")
            print('  git commit -m "type(scope): 中文说明"')
        else:
            print("  git add <目标文件>                  # 逐项添加，先看清再暂存")
        for c in dict.fromkeys(next_cmds):
            print(f"  {c}")
        print("  git ls-remote --heads origin <branch>  # 推送后校验远端哈希")

    print()
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
