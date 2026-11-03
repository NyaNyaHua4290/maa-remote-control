"""用 PyInstaller 打包 Windows 版本。

默认打成「文件夹版」（dist/maa-remote-control/ 里有 exe 和 _internal）：
启动快、不需要解压到临时目录，也不会被杀毒软件的临时目录拦截挡住。

加 --onefile 可以打成单文件 exe，但部分机器（安全软件、受限的 TEMP）会报
"Could not create temporary directory!"，所以单文件只作为备选。

用法：
    python tools/build_exe.py            # 文件夹版（推荐）
    python tools/build_exe.py --onefile  # 单文件版
"""

from __future__ import annotations

import argparse
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


def build(onefile: bool) -> int:
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
        "--onefile" if onefile else "--onedir",
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

    suffix = ".exe" if sys.platform.startswith("win") else ""
    target = dist_dir / f"{NAME}{suffix}" if onefile else dist_dir / NAME / f"{NAME}{suffix}"
    if not target.exists():
        print(f"没有在 {target} 找到产物。")
        return 1

    size_mb = target.stat().st_size / 1024 / 1024
    print()
    print("打包完成：")
    if onefile:
        print(f"    {target}  ({size_mb:.1f} MB)")
        print("双击运行即可，数据会放在 exe 同目录的 data 文件夹里。")
    else:
        print(f"    {target}  ({size_mb:.1f} MB，依赖在旁边的 _internal 目录里)")
        print("整个 dist\\maa-remote-control 文件夹一起拷走，双击里面的 exe 运行。")

    # 顺手清掉中间产物
    shutil.rmtree(build_dir, ignore_errors=True)
    return 0


def _configure_console() -> None:
    """Windows CI 的默认代码页可能是 cp1252，直接打印中文会抛 UnicodeEncodeError。

    不强制改成 UTF-8（中文 Windows 控制台是 cp936，会乱码），只把编码不了的字符替换掉。
    """

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _configure_console()

    parser = argparse.ArgumentParser(description="打包 MAA 远程控制的 Windows 可执行文件")
    parser.add_argument("--onefile", action="store_true", help="打成单文件 exe（默认是文件夹版）")
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 PyInstaller。先执行：")
        print("    python -m pip install -r requirements-build.txt")
        return 1

    return build(args.onefile)


if __name__ == "__main__":
    raise SystemExit(main())
