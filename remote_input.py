#!/usr/bin/env python3
"""
Remote Input - Ubuntu Wayland 手机远程输入工具

手机浏览器打开后输入文字，点发送即可自动粘贴到电脑当前光标位置。
专为 Ubuntu Wayland 环境设计，不受 GNOME 沙箱限制。
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess, time, os

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Remote Input</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #121212; color: white; padding: 20px;
               font-family: -apple-system, sans-serif; }
        h2 { margin-bottom: 15px; font-weight: 400; color: #888; }
        textarea { width: 100%; height: 200px; font-size: 18px;
                   padding: 12px; background: #1e1e1e; color: white;
                   border: 1px solid #333; border-radius: 8px;
                   resize: vertical; }
        button { width: 100%; height: 56px; font-size: 20px;
                 margin-top: 12px; background: #2563eb; color: white;
                 border: none; border-radius: 8px; cursor: pointer; }
        button:active { background: #1d4ed8; }
        #status { margin-top: 10px; color: #4ade80; font-size: 14px;
                  min-height: 20px; }
    </style>
</head>
<body>
    <h2>Remote Input</h2>
    <textarea id="text" placeholder="在这里输入..."></textarea>
    <button onclick="send()">发送到电脑</button>
    <div id="status"></div>
    <script>
        let sending = false;
        function send() {
            if (sending) return;
            const t = document.getElementById('text');
            const s = document.getElementById('status');
            if (t.value.trim() === '') return;
            sending = true;
            fetch('/', { method: 'POST', body: t.value })
                .then(r => {
                    s.textContent = '已发送!';
                    t.value = '';
                    sending = false;
                    setTimeout(() => s.textContent = '', 2000);
                })
                .catch(() => { s.textContent = '发送失败'; sending = false; });
        }
    </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[LOG] {format % args}")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        text = self.rfile.read(length).decode("utf-8")
        if text:
            env = os.environ.copy()
            env["DISPLAY"] = ":0"
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), env=env)
            subprocess.run(["wl-copy", "-p"], input=text.encode("utf-8"), env=env)
            time.sleep(0.15)
            subprocess.run(["ydotool", "key", "-d", "50",
                           "42:1", "110:1", "110:0", "42:0"], env=env)
        self.send_response(200)
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("服务已启动，手机访问 http://<你的IP>:8080")
    server.serve_forever()
