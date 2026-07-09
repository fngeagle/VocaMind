"""启动静态前端页面（默认 http://localhost:8080）。"""
from __future__ import annotations

import argparse
import http.server
import os
import socketserver


def main() -> None:
    parser = argparse.ArgumentParser(description="VocaMind 前端静态服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    root = os.path.join(os.path.dirname(__file__), "..", "frontend")
    os.chdir(os.path.abspath(root))

    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"前端已启动: http://{args.host}:{args.port}")
        print("请确保后端已运行: python main.py")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
