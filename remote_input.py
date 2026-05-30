#!/usr/bin/env python3
"""
Remote Input - Ubuntu Wayland 手机远程输入工具

手机浏览器打开后输入文字，点发送即可自动粘贴到电脑当前光标位置。
专为 Ubuntu Wayland 环境设计，不受 GNOME 沙箱限制。

可选参数：
  --auth              启用登录认证（自动生成 token 打印到终端）
  --auth --token XXX  启用登录认证并指定 token
  --port PORT         指定端口（默认 8080）
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
import subprocess, time, os, sys, secrets, hashlib, json

# 全局配置，通过 update() 修改以避免闭包作用域问题
config = {"auth": False, "token_hash": None, "sessions": {}}

INPUT_HTML = """
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

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Login - Remote Input</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #121212; color: white; padding: 20px;
               font-family: -apple-system, sans-serif;
               display: flex; justify-content: center; align-items: center;
               min-height: 100vh; }
        .login-box { width: 100%%; max-width: 360px; }
        h2 { margin-bottom: 15px; font-weight: 400; color: #888; text-align: center; }
        input { width: 100%%; height: 56px; font-size: 18px; padding: 12px;
                background: #1e1e1e; color: white; border: 1px solid #333;
                border-radius: 8px; outline: none; }
        input:focus { border-color: #2563eb; }
        button { width: 100%%; height: 56px; font-size: 20px; margin-top: 12px;
                 background: #2563eb; color: white; border: none;
                 border-radius: 8px; cursor: pointer; }
        button:active { background: #1d4ed8; }
        #msg { margin-top: 10px; color: #f87171; font-size: 14px;
               text-align: center; min-height: 20px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>Remote Input</h2>
        <input id="token" type="password" placeholder="请输入 Token"
               onkeydown="if(event.key==='Enter')login()">
        <button onclick="login()">登录</button>
        <div id="msg"></div>
    </div>
    <script>
        async function sha256(text) {
            const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
            return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
        }
        async function login() {
            const input = document.getElementById('token');
            const msg = document.getElementById('msg');
            const token = input.value.trim();
            if (!token) { msg.textContent = '请输入 Token'; return; }
            const hash = await sha256(token);
            const r = await fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'hash=' + encodeURIComponent(hash)
            });
            if (r.ok) {
                window.location.href = '/';
            } else {
                msg.textContent = 'Token 错误';
                input.value = '';
            }
        }
    </script>
</body>
</html>
"""


def sha256_hex(text):
    return hashlib.sha256(text.encode()).hexdigest()


def get_cookie(self, name):
    cookie = self.headers.get("Cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith(f"{name}="):
            return part.split("=", 1)[1]
    return None


def check_auth(self):
    session_id = get_cookie(self, "session")
    if session_id and sha256_hex(session_id) in config["sessions"]:
        return True
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[LOG] {format % args}")

    def do_GET(self):
        if config["auth"] and not check_auth(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(LOGIN_HTML.encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INPUT_HTML.encode("utf-8"))

    def do_POST(self):
        if self.path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)
            client_hash = params.get("hash", [""])[0]
            if client_hash == config["token_hash"]:
                session_id = secrets.token_hex(32)
                config["sessions"][sha256_hex(session_id)] = True
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie",
                    f"session={session_id}; Path=/; HttpOnly; SameSite=Strict")
                self.end_headers()
            else:
                self.send_response(401)
                self.end_headers()
            return

        if config["auth"] and not check_auth(self):
            self.send_response(403)
            self.end_headers()
            return

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
    port = 8080
    auth_enabled = False
    custom_token = None

    args = sys.argv[1:]
    if "--auth" in args:
        auth_enabled = True
        args.remove("--auth")
    if "--token" in args:
        idx = args.index("--token")
        custom_token = args[idx + 1]
        args.remove("--token")
        args.remove(custom_token)
    if "--port" in args:
        idx = args.index("--port")
        port = int(args[idx + 1])

    if auth_enabled:
        token = custom_token or secrets.token_hex(16)
        config.update(auth=True, token_hash=sha256_hex(token))
        print(f"认证已启用，Token: {token}")
        print(f"手机浏览器打开后需输入此 Token 才能使用")

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"服务已启动，手机访问 http://<你的IP>:{port}")
    server.serve_forever()
