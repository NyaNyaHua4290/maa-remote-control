"""用 PyInstaller 打一个单文件 exe：python tools/build_exe.py

产物：dist/maa-remote-control.exe（约 15-25 MB，双击即用，不需要装 Python）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "maa-remote-control"

# uvicorn 的子模块是运行时动态导入的，PyInstaller 静态分析看不到，必须手动列出来
HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 PyInstaller。先执行：")
        print("    python -m pip install -r requirements-build.txt")
        return 1

    separator = ";" if sys.platform.startswith("win") else ":"
    add_data = [
        f"{ROOT / 'src' / 'maa_remote' / 'templates'}{separator}maa_remote/templates",
        f"{ROOT / 'src' / 'maa_remote' / 'static'}{separator}maa_remote/static",
    ]

    dist_dir = ROOT / "dist"
    build_dir = ROOT / "build"

    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        NAME,
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(build_dir),
    ]
    for item in add_data:
        cmd += ["--add-data", item]
    for module in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", module]
    cmd.append(str(ROOT / "tools" / "launcher.py"))

    print("正在打包，第一次会比较慢（1-3 分钟）……")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("打包失败，请查看上面的 PyInstaller 输出。")
        return result.returncode

    target = dist_dir / (NAME + (".exe" if sys.platform.startswith("win") else ""))
    if not target.exists():
        print(f"没有在 {target} 找到产物。")
        return 1

    size_mb = target.stat().st_size / 1024 / 1024
    print()
    print("打包完成：")
    print(f"    {target}  ({size_mb:.1f} MB)")
    print("双击运行即可，数据会放在 exe 同目录的 data 文件夹里。")

    # 顺手清掉中间产物，只留 exe
    shutil.rmtree(build_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
