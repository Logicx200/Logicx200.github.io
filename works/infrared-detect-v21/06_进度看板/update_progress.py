#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红外仿真项目进度看板 · progress.json 命令行更新工具

特性：
  * 原子写入（临时文件 + os.replace），避免页面读到半截 JSON；
  * 写操作使用同目录 .lock 文件串行化，避免并发写互相覆盖；
  * 读取时保留文件中所有既有字段，只修改命令行指定的字段；
  * 自动刷新 meta.updated_at 为本地当前时间；
  * 支持 --set / --overall / --log / --milestone / --meta；
  * 默认操作本脚本同目录的 progress.json。

示例：
  python update_progress.py --set extract 25 running "字段映射表整理中"
  python update_progress.py --overall 8 --log "参数解析推进到 25%" --level info
  python update_progress.py --milestone "2026-11-06 18:00" "PDF 终稿交付" "完成校对" --milestone-done
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

__version__ = "1.0.0"
DEFAULT_FILE = Path(__file__).resolve().with_name("progress.json")
STATUS_CHOICES = ("pending", "running", "done", "blocked")
LEVEL_CHOICES = ("info", "warn", "done")
LOCK_TIMEOUT_SECONDS = 6.0
STALE_LOCK_SECONDS = 45.0


class ToolError(Exception):
    """可预期的命令行错误，统一打印为中文提示。"""


# ---------------------------------------------------------------------------
# 通用读写
# ---------------------------------------------------------------------------


def configure_stdio() -> None:
    """统一使用 UTF-8 输出，避免 Windows 管道默认 GBK 导致中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def load_progress(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ToolError(f"文件不存在：{path}")
    if not path.is_file():
        raise ToolError(f"不是普通文件：{path}")

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"无法读取文件：{path}（{exc}）") from exc
    except UnicodeDecodeError as exc:
        raise ToolError(f"progress.json 不是 UTF-8 文本：{path}（{exc}）") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(
            f"progress.json 不是合法 JSON：第 {exc.lineno} 行第 {exc.colno} 列（{exc.msg}）"
        ) from exc

    if not isinstance(data, dict):
        raise ToolError("progress.json 的根节点必须是 JSON 对象")
    if not isinstance(data.get("meta"), dict):
        raise ToolError("progress.json 缺少 meta 对象，已中止写入以保护现有文件")
    if not isinstance(data.get("workstreams"), list):
        raise ToolError("progress.json 缺少 workstreams 数组，已中止写入以保护现有文件")
    return data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    """同目录临时文件写完后原子替换目标，失败时清理临时文件。"""
    directory = path.parent
    if not directory.exists():
        raise ToolError(f"目标目录不存在：{directory}")

    tmp_path = directory / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        last_error: OSError | None = None
        for attempt in range(4):
            try:
                os.replace(tmp_path, path)
                return
            except OSError as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.05 * (attempt + 1))
        raise ToolError(f"原子替换失败：{path}（{last_error}）")
    finally:
        with contextlib.suppress(FileNotFoundError, OSError):
            if tmp_path.exists():
                tmp_path.unlink()


@contextlib.contextmanager
def file_lock(target: Path) -> Iterator[None]:
    """
    基于 O_CREAT | O_EXCL 的轻量级同目录锁。
    仅用于保护本工具自身的“读-改-写”过程；过期锁会在超时后清理。
    """
    lock_path = target.with_name(target.name + ".lock")
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd: int | None = None

    while fd is None:
        try:
            fd = os.open(os.fspath(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, f"pid={os.getpid()} time={datetime.now().isoformat()}\n".encode("utf-8"))
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > STALE_LOCK_SECONDS:
                with contextlib.suppress(OSError):
                    lock_path.unlink()
                continue
            if time.monotonic() >= deadline:
                raise ToolError(
                    f"另一个更新进程正在写入（锁文件：{lock_path.name}）。"
                    "请等待几秒后重试；若确认无进程占用，可手动删除该锁文件。"
                )
            time.sleep(0.05)
        except OSError as exc:
            raise ToolError(f"无法创建锁文件：{lock_path}（{exc}）") from exc

    try:
        yield
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(FileNotFoundError, OSError):
            lock_path.unlink()


# ---------------------------------------------------------------------------
# 参数解析辅助
# ---------------------------------------------------------------------------


def parse_percent(raw: str, what: str = "percent") -> int | float:
    try:
        value = float(str(raw).strip().rstrip("%"))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{what} 必须是 0–100 的数字，收到：{raw!r}") from exc
    if not (0.0 <= value <= 100.0):
        raise ToolError(f"{what} 必须在 0–100 之间，收到：{raw!r}")
    return int(value) if value.is_integer() else round(value, 2)


def parse_set_args(values: list[str]) -> tuple[str, int | float, str, str | None]:
    if len(values) < 3:
        raise ToolError(
            "--set 至少需要 3 个参数：ID PERCENT STATUS [NOTE]；"
            "例如 --set extract 25 running \"字段映射表整理中\""
        )
    workstream_id = values[0].strip()
    if not workstream_id:
        raise ToolError("--set 的工作流 ID 不能为空")
    percent = parse_percent(values[1], f"{workstream_id} 的 percent")
    status = values[2].strip().lower()
    if status not in STATUS_CHOICES:
        raise ToolError(f"status 必须是 {' / '.join(STATUS_CHOICES)} 之一，收到：{values[2]!r}")
    note = " ".join(values[3:]).strip() if len(values) > 3 else None
    return workstream_id, percent, status, note


def parse_overall_args(values: list[str]) -> tuple[int | float, str | None]:
    percent = parse_percent(values[0], "overall.percent")
    label = " ".join(values[1:]).strip() if len(values) > 1 else None
    return percent, (label or None)


def parse_milestone_args(values: list[str]) -> tuple[str, str, str]:
    """
    兼容两种写法：
      --milestone "2026-11-06 18:00" "PDF 终稿交付" "详情"
      --milestone 2026-11-06 18:00 "PDF 终稿交付" "详情"
    """
    if len(values) < 2:
        raise ToolError(
            "--milestone 至少需要 2 个参数：时间 标题 [详情]；"
            "例如 --milestone \"2026-11-06 18:00\" \"PDF 终稿交付\" \"完成校对\""
        )

    first = values[0].strip()
    if (
        len(values) >= 3
        and len(first) == 10
        and first[4] == "-"
        and first[7] == "-"
        and ":" in values[1]
        and " " not in values[1].strip()
    ):
        milestone_time = f"{first} {values[1].strip()}"
        title = values[2].strip()
        detail = " ".join(values[3:]).strip()
    else:
        milestone_time = first
        title = values[1].strip()
        detail = " ".join(values[2:]).strip()

    if not milestone_time:
        raise ToolError("里程碑时间不能为空")
    if not title:
        raise ToolError("里程碑标题不能为空")
    return milestone_time, title, detail


def ensure_list_field(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if value is None:
        value = []
        data[key] = value
    if not isinstance(value, list):
        raise ToolError(f"progress.json 中的 {key} 必须是数组")
    return value


def ensure_dict_field(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        value = {}
        data[key] = value
    if not isinstance(value, dict):
        raise ToolError(f"progress.json 中的 {key} 必须是对象")
    return value


# ---------------------------------------------------------------------------
# 应用变更
# ---------------------------------------------------------------------------


def apply_changes(data: dict[str, Any], args: argparse.Namespace) -> list[str]:
    changes: list[str] = []
    meta = ensure_dict_field(data, "meta")
    workstreams = data["workstreams"]

    # --set（可重复）
    if args.set:
        id_to_workstream: dict[str, dict[str, Any]] = {}
        for item in workstreams:
            if isinstance(item, dict) and item.get("id") is not None:
                id_to_workstream[str(item["id"])] = item

        for raw_values in args.set:
            workstream_id, percent, status, note = parse_set_args(raw_values)
            target = id_to_workstream.get(workstream_id)
            if target is None:
                available = ", ".join(id_to_workstream.keys()) or "（无）"
                raise ToolError(
                    f"未找到工作流 ID：{workstream_id!r}。可用 ID：{available}"
                )
            target["percent"] = percent
            target["status"] = status
            if note is not None:
                target["note"] = note

            note_part = f"；备注：{note}" if note is not None else "；备注保持不变"
            changes.append(
                f"工作流 {workstream_id} → {percent}% / {status}{note_part}"
            )

    # --overall
    if args.overall is not None:
        percent, label = parse_overall_args(args.overall)
        overall = ensure_dict_field(data, "overall")
        overall["percent"] = percent
        if label is not None:
            overall["label"] = label
        changes.append(
            f"总体进度 → {percent}%"
            + (f"（{label}）" if label is not None else "（标签保持不变）")
        )

    # --meta KEY VALUE（可重复）
    if args.meta:
        for key, value in args.meta:
            key = key.strip()
            if not key:
                raise ToolError("--meta 的键不能为空")
            meta[key] = value
            changes.append(f"meta.{key} = {value}")

    # --milestone（可重复）
    if args.milestone:
        milestones = ensure_list_field(data, "milestones")
        for raw_values in args.milestone:
            milestone_time, title, detail = parse_milestone_args(raw_values)
            existing = next(
                (
                    item
                    for item in milestones
                    if isinstance(item, dict) and str(item.get("title", "")).strip() == title
                ),
                None,
            )
            if existing is not None:
                existing["time"] = milestone_time
                if detail:
                    existing["detail"] = detail
                if args.milestone_done:
                    existing["done"] = True
                elif "done" not in existing:
                    existing["done"] = False
                action = "更新"
            else:
                new_item: dict[str, Any] = {
                    "time": milestone_time,
                    "title": title,
                    "detail": detail,
                    "done": bool(args.milestone_done),
                }
                milestones.append(new_item)
                action = "新增"
            changes.append(f"{action}里程碑：{milestone_time} · {title}")

    # --log（可重复，时间统一取本次执行时间）
    if args.log:
        logs = ensure_list_field(data, "log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for text in args.log:
            text = text.strip()
            if not text:
                raise ToolError("--log 的内容不能为空")
            logs.append({"time": timestamp, "level": args.level, "text": text})
            changes.append(f"日志 +1（{args.level}）：{text}")

    # 自动更新写入时间；放在所有 meta 操作之后，避免被 --meta updated_at 覆盖
    meta["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return changes


# ---------------------------------------------------------------------------
# 展示 / 输出
# ---------------------------------------------------------------------------


def summarize(data: dict[str, Any]) -> str:
    meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
    overall = data.get("overall", {}) if isinstance(data.get("overall"), dict) else {}
    workstreams = data.get("workstreams", []) if isinstance(data.get("workstreams"), list) else []
    milestones = data.get("milestones", []) if isinstance(data.get("milestones"), list) else []
    logs = data.get("log", []) if isinstance(data.get("log"), list) else []

    counts = {key: 0 for key in STATUS_CHOICES}
    for item in workstreams:
        if isinstance(item, dict):
            status = str(item.get("status", "pending")).lower()
            counts[status if status in counts else "pending"] += 1
    done_ms = sum(1 for item in milestones if isinstance(item, dict) and item.get("done"))

    lines = [
        f"项目：{meta.get('project', '—')}",
        f"版本：{meta.get('version', '—')}    更新：{meta.get('updated_at', '—')}",
        f"总体：{overall.get('percent', '—')}% · {overall.get('label', '—')}",
        f"阶段：{meta.get('stage', '—')}    预计完成：{meta.get('eta', '—')}",
        f"工作流：{len(workstreams)} 条（进行中 {counts['running']} / 已完成 {counts['done']} / 受阻 {counts['blocked']} / 待启动 {counts['pending']}）",
    ]
    for item in workstreams:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"  - [{item.get('status', 'pending'):>8}] {item.get('percent', 0):>5}%  "
            f"{item.get('name', item.get('id', '未命名'))}  @{item.get('owner', '未分配')}"
        )
    lines.append(f"里程碑：{done_ms}/{len(milestones)} 已完成")
    lines.append(f"日志：{len(logs)} 条")
    for item in logs[-3:][::-1]:
        if isinstance(item, dict):
            lines.append(
                f"  - {item.get('time', '—')} [{item.get('level', 'info')}] {item.get('text', '')}"
            )
    return "\n".join(lines)


def print_result(path: Path, changes: list[str], data: dict[str, Any], dry_run: bool) -> None:
    prefix = "[dry-run] 未写入" if dry_run else "已写入"
    print(f"{prefix}：{path}")
    if changes:
        print("本次变更：")
        for change in changes:
            print(f"  • {change}")
    meta = data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}
    overall = data.get("overall", {}) if isinstance(data.get("overall"), dict) else {}
    print(
        f"当前：总体 {overall.get('percent', '—')}% · "
        f"阶段 {meta.get('stage', '—')} · 更新时间 {meta.get('updated_at', '—')}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="update_progress.py",
        description="更新进度看板数据文件 progress.json（安全原子写入、保留既有字段）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  python update_progress.py --set extract 20 running "正在整理字段映射"
  python update_progress.py --overall 8 "参数解析阶段"
  python update_progress.py --log "参数解析完成" --level done
  python update_progress.py --milestone "2026-11-03 18:00" "参数解析完成" "产出参数映射表" --milestone-done
  python update_progress.py --meta stage "模型接入与工况扩充" --meta eta "2026-11-06 18:00"
  python update_progress.py --show
""",
    )
    parser.add_argument(
        "--file",
        default=str(DEFAULT_FILE),
        help=f"progress.json 路径（默认：{DEFAULT_FILE}）",
    )
    parser.add_argument(
        "--set",
        nargs="+",
        action="append",
        metavar="ID PERCENT STATUS [NOTE]",
        help="更新工作流：ID PERCENT STATUS [NOTE]；STATUS 可选 pending/running/done/blocked；可重复",
    )
    parser.add_argument(
        "--overall",
        nargs="+",
        metavar="PERCENT [LABEL]",
        help="更新总体进度，例如 --overall 8 \"参数解析阶段\"；省略 LABEL 时保留原标签",
    )
    parser.add_argument(
        "--log",
        action="append",
        metavar="TEXT",
        help="追加一条实时日志，可重复；日志级别由 --level 指定",
    )
    parser.add_argument(
        "--level",
        choices=LEVEL_CHOICES,
        default="info",
        help="日志级别：info / warn / done（默认 info）",
    )
    parser.add_argument(
        "--milestone",
        nargs="+",
        action="append",
        metavar="TIME TITLE [DETAIL]",
        help="新增或按标题更新里程碑；可重复；加 --milestone-done 表示已完成",
    )
    parser.add_argument(
        "--milestone-done",
        action="store_true",
        help="将 --milestone 指定的里程碑标记为已完成",
    )
    parser.add_argument(
        "--meta",
        nargs=2,
        action="append",
        metavar=("KEY", "VALUE"),
        help="更新 meta 字段，例如 --meta stage \"正式报告撰写\"；可重复",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="只读显示当前进度摘要，不修改文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="解析并应用变更到内存，但输出预览而不写文件",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def has_mutations(args: argparse.Namespace) -> bool:
    return bool(args.set or args.overall is not None or args.log or args.milestone or args.meta)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.milestone_done and not args.milestone:
        parser.error("--milestone-done 必须与 --milestone 一起使用")
    if not has_mutations(args) and not args.show:
        parser.print_help()
        print("\n提示：使用 --show 查看当前进度。")
        return 0

    path = Path(args.file).expanduser()
    try:
        path = path.resolve()
        if args.show and not has_mutations(args):
            data = load_progress(path)
            print(f"文件：{path}\n")
            print(summarize(data))
            return 0

        if args.dry_run:
            data = load_progress(path)
            changes = apply_changes(data, args)
            print_result(path, changes, data, dry_run=True)
            return 0

        with file_lock(path):
            data = load_progress(path)
            changes = apply_changes(data, args)
            atomic_write(path, data)

        print_result(path, changes, data, dry_run=False)
        if args.show:
            print("\n" + summarize(data))
        return 0
    except ToolError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
