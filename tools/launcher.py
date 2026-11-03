"""Windows 直接运行入口。

两种用法：

- 打包后的 exe：双击 `maa-remote-control.exe` 即可，会自动挑端口、打开浏览器。
- 源码方式：`python tools/launcher.py`（需要先装好依赖）。

环境和 Docker 部署完全一致，数据默认放在“程序所在目录/data”。
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import traceback
import webbrowser

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PORT_SCAN_RANGE = 20


def _configure_console() -> None:
    """避免中文在部分 Windows 控制台里报编码错误。

    不强制改成 UTF-8：中文 Windows 的控制台是 cp936，强行输出 UTF-8 字节会变成乱码。
    只把无法编码的字符替换掉，保证不会因为编码异常直接崩掉。
    """

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _find_free_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + PORT_SCAN_RANGE):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(
        f"端口 {preferred}-{preferred + PORT_SCAN_RANGE - 1} 都被占用了，"
        "请用环境变量 MAA_REMOTE_PORT 指定一个空闲端口。"
    )


def _pause_if_frozen() -> None:
    if getattr(sys, "frozen", False):
        try:
            input("\n按回车键退出…")
        except (EOFError, KeyboardInterrupt):
            pass


def main() -> int:
    _configure_console()

    host = os.getenv("MAA_REMOTE_HOST", DEFAULT_HOST)
    preferred_port = int(os.getenv("MAA_REMOTE_PORT", str(DEFAULT_PORT)))
    port = _find_free_port(host, preferred_port)

    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{port}"

    # 必须在 import maa_remote 之前设置，配置是在模块导入时读取的
    os.environ.setdefault("MAA_REMOTE_PUBLIC_BASE_URL", url)

    from maa_remote.config import settings
    from maa_remote.main import app

    print("=" * 64)
    print("  MAA 远程控制已启动")
    print(f"  网页地址：{url}")
    print(f"  数据目录：{settings.data_dir}")
    print()
    print("  在 MAA「设置 → 远程控制」里填：")
    print(f"    获取任务端点：{url}/maa/getTask")
    print(f"    汇报任务端点：{url}/maa/reportStatus")
    print("    用户标识符：注册后到网页的「配置指引」里复制")
    print()
    print("  关闭这个窗口或按 Ctrl+C 即可停止服务。")
    print("=" * 64)

    if os.getenv("MAA_REMOTE_NO_BROWSER", "") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=settings.log_level.lower())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    except SystemExit:
        raise
    except Exception:  # pragma: no cover - 双击运行时让人看清报错
        traceback.print_exc()
        _pause_if_frozen()
        raise SystemExit(1) from None
