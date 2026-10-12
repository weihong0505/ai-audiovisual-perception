import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

# ─────────────────────────────────────────────────────────────────────────
# 夹具缺失守卫
#
# 背景：clip.mp4 / tone.wav 曾被 .gitignore 按"测试大文件"排除（实际仅约 110 KB）。
# 换机器/新克隆后，4 条依赖夹具的测试会以 `assert 0 >= 1`（空列表）失败——
# 排查者会以为业务逻辑坏了，而实际只是文件不在。**这个报错形态是不可接受的。**
#
# 处置：此处集中拦截，把缺文件变成一个**显式 skip + 明确原因**，
# 同时**保留其余测试继续运行**（不中止整个会话，避免丢失信号）。
# 夹具本身已改为随仓库提供。
# ─────────────────────────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).parent / "fixtures"
REQUIRED_FIXTURES = ("clip.mp4", "tone.wav")


def _missing_fixtures() -> set[str]:
    return {n for n in REQUIRED_FIXTURES if not (FIXTURES_DIR / n).exists()}


def _fixtures_used_by(module) -> set[str]:
    """模块级若定义了指向 fixtures/ 的 Path 常量，即认为该模块用到它。"""
    used = set()
    for value in vars(module).values():
        if isinstance(value, Path) and value.parent == FIXTURES_DIR:
            used.add(value.name)
    return used


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    missing = _missing_fixtures()
    if not missing:
        return

    reason = (
        f"缺少测试夹具 {sorted(missing)}（期望位于 {FIXTURES_DIR}）。"
        "它们随仓库提供；若确实丢失，可用 "
        r"python G:\英特尔杯嵌入式AI赛\code\regenerate_fixtures.py 重新生成。"
    )
    skipped = 0
    for item in items:
        module = getattr(item, "module", None)
        if module is None:
            continue
        if _fixtures_used_by(module) & missing:
            item.add_marker(pytest.mark.skip(reason=reason))
            skipped += 1

    if skipped:
        # 大声说出来，别让它淹没在输出里
        print(
            "\n" + "=" * 72 + "\n"
            f"[!] 测试夹具缺失: {sorted(missing)}\n"
            f"    已跳过 {skipped} 条依赖夹具的测试（其余测试照常运行）。\n"
            f"    期望位置: {FIXTURES_DIR}\n"
            "    修复: python "
            r"G:\英特尔杯嵌入式AI赛\code\regenerate_fixtures.py" + "\n"
            + "=" * 72
        )
