#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes 配置体检 / 备份 / 还原

用法（默认就是体检）：
    hermes-config-doctor.cmd                 # = check
    hermes-config-doctor.cmd check
    hermes-config-doctor.cmd backup          # 存一份带时间戳的备份（留最近 20 份）
    hermes-config-doctor.cmd list            # 列出备份，逐份标好坏
    hermes-config-doctor.cmd restore --latest-good

体检覆盖 10 项指标，每项给出 OK / 警告 / 失败 三态和一句人话，
失败项直接给修法。任何一项 FAIL 时退出码为 1，方便以后挂到计划任务里。
"""

import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import unicodedata

HERMES_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
CONFIG = os.path.join(HERMES_DIR, "config.yaml")
AUTH = os.path.join(HERMES_DIR, "auth.json")
BACKUP_DIR = os.path.join(HERMES_DIR, "config-backups")
KEEP_BACKUPS = 20

OK, WARN, FAIL, SKIP = "OK", "警告", "失败", "跳过"
ICON = {OK: "[ OK ]", WARN: "[警告]", FAIL: "[失败]", SKIP: "[跳过]"}


# ---------- 显示对齐（中文字符按两格算） ----------
def width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s, n):
    return s + " " * max(0, n - width(s))


def ts():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def when(path):
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")


# ---------- 体检 ----------
class Report:
    def __init__(self):
        self.rows = []

    def add(self, no, name, level, detail, fix=""):
        self.rows.append((no, name, level, detail, fix))

    def summary(self):
        n_ok = sum(1 for r in self.rows if r[2] == OK)
        n_warn = sum(1 for r in self.rows if r[2] == WARN)
        n_fail = sum(1 for r in self.rows if r[2] == FAIL)
        n_skip = sum(1 for r in self.rows if r[2] == SKIP)
        return n_ok, n_warn, n_fail, n_skip

    def render(self, config_path):
        print()
        print("Hermes 配置体检   " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        print("配置文件：" + config_path)
        print("-" * 78)
        name_w = max(width(r[1]) for r in self.rows) + 2
        for no, name, level, detail, fix in sorted(self.rows, key=lambda r: r[0]):
            print("%-4s %s %s %s" % ("[%d]" % no, pad(name, name_w), ICON[level], detail))
            if level in (WARN, FAIL) and fix:
                print(" " * 8 + "↳ 怎么修：" + fix)
        n_ok, n_warn, n_fail, n_skip = self.summary()
        print("-" * 78)
        verdict = "配置可用" if n_fail == 0 else "配置有问题，Hermes 可能起不来"
        print("结论：%d 项检查 → %d 通过 / %d 警告 / %d 失败 / %d 跳过 —— %s"
              % (n_ok + n_warn + n_fail + n_skip, n_ok, n_warn, n_fail, n_skip, verdict))
        if n_fail:
            print("提示：直接跑 `hermes-config-doctor.cmd restore --latest-good` 可从最近一份好备份还原。")
        print()
        return n_fail


def check_backups(rep):
    """第 9 项：备份目录里有没有一份近期、能解析的备份。"""
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "config-*.yaml")), reverse=True)
    if not backups:
        rep.add(9, "配置备份", WARN, "一份都没有", "跑一次 `hermes-config-doctor.cmd backup`")
        return
    newest = backups[0]
    age_h = (datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(newest))).total_seconds() / 3600
    ok_parse = True
    try:
        import yaml
        ok_parse = isinstance(yaml.safe_load(open(newest, "rb").read().decode("utf-8-sig")), dict)
    except Exception:
        ok_parse = False
    level = OK if (ok_parse and age_h <= 24 * 14) else WARN
    rep.add(9, "配置备份", level,
            "%d 份，最新 %s（%.0f 小时前，%s）" % (len(backups), os.path.basename(newest), age_h,
                                                "可解析" if ok_parse else "已损坏"),
            "改配置前先 backup，坏了才有得还原")


def run_check(config_path):
    rep = Report()

    # 1 文件存在
    if not os.path.isfile(config_path):
        rep.add(1, "配置文件存在", FAIL, "找不到 " + config_path, "确认 Hermes 装好、路径正确")
        rep.render(config_path)
        return rep
    size = os.path.getsize(config_path)
    rep.add(1, "配置文件存在", OK if size > 500 else WARN,
            "%s 字节，最后修改 %s" % (format(size, ","), when(config_path)),
            "文件异常小，检查是不是被截断了")

    raw = open(config_path, "rb").read()
    text = raw.decode("utf-8-sig", "replace")

    # 2 YAML 语法
    data = None
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            rep.add(2, "YAML 语法", OK, "解析通过，顶层是 mapping")
        else:
            rep.add(2, "YAML 语法", FAIL, "顶层不是 mapping（拿到 %s）" % type(data).__name__,
                    "文件结构被改坏了，用 restore 还原最近的备份")
    except Exception as e:
        rep.add(2, "YAML 语法", FAIL, "解析失败：" + str(e).splitlines()[0][:70],
                "最常见是缩进/少了个引号；跑 restore --latest-good")

    # 3 编码与换行
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    lone_cr = raw.count(b"\r") - crlf
    level = OK if (lone_lf == 0 and lone_cr == 0) else WARN
    rep.add(3, "编码与换行", level,
            "%s · CRLF %d 行 · 孤立LF %d / 孤立CR %d" % ("带BOM" if has_bom else "无BOM", crlf, lone_lf, lone_cr),
            "混用换行会让某些读取路径出奇怪报错，统一成 CRLF")

    # 语法坏了，后面的结构检查都无从判断：标"跳过"，别让人误以为没问题
    if data is None:
        for no, name in ((4, "默认模型字段"), (5, "自定义 provider"), (6, "模型与服务商对齐"),
                         (7, "Hermes 自检"), (8, "凭据池"), (10, "风险项")):
            rep.add(no, name, SKIP, "无法判断：先修第 2 项 YAML 语法")
        check_backups(rep)
        return rep

    # 4 必填字段
    model = (data or {}).get("model") or {}
    need = ["default", "provider", "base_url", "api_key"]
    missing = [k for k in need if not (isinstance(model, dict) and model.get(k))]
    if missing:
        rep.add(4, "默认模型字段", FAIL, "缺：" + "、".join("model." + m for m in missing),
                "缺 model.api_key 就直接不通；补全后跑 check")
    else:
        rep.add(4, "默认模型字段", OK, "%s @ %s" % (model["default"], model["provider"]))

    # 5 provider 列表
    provs = (data or {}).get("custom_providers") or []
    provs = [p for p in provs if isinstance(p, dict)]
    if not provs:
        rep.add(5, "自定义 provider", WARN, "一个都没有（只用内置厂商时正常）")
    else:
        bad = [p.get("name") or "?" for p in provs if not p.get("api_key") or not p.get("base_url")]
        models_n = sum(len(p.get("models") or {}) for p in provs)
        detail = "%d 个：%s · 共 %d 个模型" % (len(provs), "、".join(p.get("name", "?") for p in provs), models_n)
        rep.add(5, "自定义 provider", FAIL if bad else OK,
                detail + ("；缺 key/base_url：" + "、".join(bad) if bad else ""),
                "缺 api_key 的那条永远不会通，补上或删掉")

    # 6 一致性
    if provs and model.get("provider"):
        hit = next((p for p in provs if p.get("name") == model.get("provider")), None)
        if hit is None:
            rep.add(6, "模型与服务商对齐", FAIL, "model.provider=%s 不在自定义 provider 列表里" % model.get("provider"),
                    "改成列表里存在的名字，或把这个 provider 加回来")
        else:
            diffs = []
            if (hit.get("base_url") or "").rstrip("/") != (model.get("base_url") or "").rstrip("/"):
                diffs.append("base_url 不一致")
            if hit.get("api_key") != model.get("api_key"):
                diffs.append("api_key 不一致（等于绕过了这个 provider）")
            rep.add(6, "模型与服务商对齐", WARN if diffs else OK,
                    "；".join(diffs) if diffs else "base_url 与 api_key 都和 %s 一致" % hit.get("name"),
                    "把 model.* 改成与 provider 条目同一份值，否则池子的 key 轮换用不上")
    else:
        rep.add(6, "模型与服务商对齐", WARN, "缺 provider 信息，未比对", "先补 model.provider")

    # 7 hermes 自己认不认
    if os.path.abspath(config_path) != os.path.abspath(CONFIG):
        rep.add(7, "Hermes 自检", OK, "跳过（这次分析的是外部文件，不跑自检）")
    else:
        try:
            r = subprocess.run(["hermes", "config", "check"], capture_output=True, text=True, timeout=90, shell=True)
            out = (r.stdout or "") + (r.stderr or "")
            ver = next((l.strip() for l in out.splitlines() if "Config version" in l), "")
            bad = "error" in out.lower() or "formatting error" in out.lower()
            rep.add(7, "Hermes 自检", FAIL if (bad or r.returncode != 0) else OK,
                    (ver or "无版本信息") + "，退出码 %s" % r.returncode,
                    "Hermes 自检不过=真的起不来，先 restore 备份")
        except Exception as e:
            rep.add(7, "Hermes 自检", WARN, "调用失败：" + str(e)[:60], "手动跑 hermes config check")

    # 8 凭据池
    pool_rows = []
    if not os.path.isfile(AUTH):
        rep.add(8, "凭据池", WARN, "没有 auth.json（只用 config 里的 key）", "正常，如果你没配多 key 池")
    else:
        try:
            auth = json.load(open(AUTH, encoding="utf-8"))
            pool = auth.get("credential_pool") or {}
            target = "custom:%s" % model.get("provider") if model.get("provider") else None
            entries = pool.get(target) or []
            for e in entries:
                label = e.get("label") or e.get("id") or "?"
                has = bool(e.get("access_token")) or str(e.get("source", "")).startswith("config:")
                st = e.get("last_status") or ""
                code = e.get("last_error_code")
                state = "可用" if (has and st != "exhausted") else ("已耗尽%s" % ("(%s)" % code if code else "") if st == "exhausted" else "空条目")
                pool_rows.append("%s=%s" % (label, state))
            exhausted = sum(1 for e in entries if e.get("last_status") == "exhausted")
            empty = sum(1 for e in entries if not e.get("access_token") and not str(e.get("source", "")).startswith("config:"))
            lvl = FAIL if (not entries or empty == len(entries)) else (WARN if exhausted else OK)
            detail = "%s 共 %d 把：%s" % (target, len(entries), "、".join(pool_rows)) if entries else "没有 %s 的条目（provider 名对不上池子）" % (target or "当前 provider")
            rep.add(8, "凭据池", lvl, detail,
                    ("pool 里没有这个 provider 的条目 —— 先核对 model.provider 拼写，再 hermes auth add 加一把"
                     if not entries else
                     "池子全空/全耗尽=没有备用钥匙；hermes auth add 加一把，或 hermes auth reset 清耗尽标记"))
        except Exception as e:
            rep.add(8, "凭据池", WARN, "auth.json 读不了：" + str(e)[:60], "文件可能损坏，先备份再排查")

    # 9 备份
    check_backups(rep)

    # 10 风险项
    risks = []
    seen = {}
    for p in provs:
        k = p.get("api_key") or ""
        if k and not k.startswith("http") and len(k) < 20:
            risks.append("%s 的 api_key 只有 %d 位，像占位符" % (p.get("name"), len(k)))
        if k:
            seen[k] = seen.get(k, 0) + 1
        bu = p.get("base_url") or ""
        if bu and not bu.startswith("https://"):
            risks.append("%s 的 base_url 不是 https" % p.get("name"))
    dup = [v for v in seen.values() if v > 1]
    if dup:
        risks.append("%d 组 provider 用了同一把 key（等于没有冗余）" % len(dup))
    rep.add(10, "风险项", WARN if risks else OK,
            "；".join(risks) if risks else "没发现占位符 key / 明文 http / key 复用",
            "按提示逐条处理；key 复用请换成不同账号的 key")

    return rep


# ---------- 备份 / 列表 / 还原 ----------
def cmd_backup(config_path=CONFIG):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, "config-%s.yaml" % ts())
    shutil.copyfile(config_path, dst)
    print("已备份 → %s（%s 字节）" % (dst, format(os.path.getsize(dst), ",")))
    olds = sorted(glob.glob(os.path.join(BACKUP_DIR, "config-*.yaml")))
    for f in olds[:-KEEP_BACKUPS]:
        os.remove(f)
        print("清理旧备份：%s" % os.path.basename(f))
    return 0


def parse_ok(path):
    try:
        import yaml
        return isinstance(yaml.safe_load(open(path, "rb").read().decode("utf-8-sig")), dict)
    except Exception:
        return False


def cmd_list():
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, "config-*.yaml")), reverse=True)
    if not files:
        print("还没有备份。跑一次： hermes-config-doctor.cmd backup")
        return 0
    print()
    print("%-34s %10s  %-6s %s" % ("备份文件", "大小", "状态", "改于"))
    print("-" * 74)
    for f in files:
        print("%-34s %10s  %-6s %s" % (os.path.basename(f), format(os.path.getsize(f), ","),
                                       "正常" if parse_ok(f) else "损坏", when(f)))
    print()
    return 0


def cmd_restore(target="--latest-good", config_path=CONFIG):
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, "config-*.yaml")), reverse=True)
    if not files:
        print("没有可用备份。")
        return 1
    if target and target != "--latest-good":
        files = [f for f in files if os.path.basename(f) == target]
        if not files:
            print("找不到备份：%s（用 list 看有哪些）" % target)
            return 1
    for f in files:
        if not parse_ok(f):
            print("跳过损坏的备份：%s" % os.path.basename(f))
            continue
        broken = os.path.join(HERMES_DIR, "config-broken-%s.yaml" % ts())
        shutil.copyfile(config_path, broken)
        shutil.copyfile(f, config_path)
        print("已还原：%s" % os.path.basename(f))
        print("坏文件留档：%s" % os.path.basename(broken))
        return run_check(config_path).render(config_path)
    print("没有一份能解析的备份，无法自动还原。")
    return 1


def main():
    args = [a for a in sys.argv[1:]]
    config_path = CONFIG
    if "--config" in args:
        i = args.index("--config")
        config_path = args[i + 1]
        del args[i:i + 2]
    cmd = args[0] if args else "check"
    if cmd in ("check", "体检"):
        return run_check(config_path).render(config_path)
    if cmd == "backup":
        return cmd_backup(config_path)
    if cmd == "list":
        return cmd_list()
    if cmd == "restore":
        return cmd_restore(args[1] if len(args) > 1 else "--latest-good", config_path)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
