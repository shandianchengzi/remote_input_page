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
config = {"auth": False, "token_raw": None, "sessions": {}, "nonces": {}}

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
        function pureSha256(str) {
            function rotr(n, x) { return (x >>> n) | (x << (32 - n)); }
            const k = [
                0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
                0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
                0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
                0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
                0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
                0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
                0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
                0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
            ];
            let h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
            let words = [];
            let ascii = unescape(encodeURIComponent(str));
            for (let i = 0; i < ascii.length; i++) words[i >> 2] |= ascii.charCodeAt(i) << (24 - (i % 4) * 8);
            let bits = ascii.length * 8;
            words[bits >> 5] |= 0x80 << (24 - (bits % 32));
            words[(((bits + 64) >> 9) << 4) + 15] = bits;
            for (let i = 0; i < words.length; i += 16) {
                let w = words.slice(i, i + 16);
                let a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],_h=h[7];
                for (let j = 0; j < 64; j++) {
                    if (j >= 16) {
                        w[j] = (rotr(17,w[j-2])^rotr(19,w[j-2])^(w[j-2]>>>10))+w[j-7]+
                               (rotr(7,w[j-15])^rotr(18,w[j-15])^(w[j-15]>>>3))+w[j-16];
                    }
                    let t1=_h+(rotr(6,e)^rotr(11,e)^rotr(25,e))+((e&f)^(~e&g))+k[j]+(w[j]|0);
                    let t2=(rotr(2,a)^rotr(13,a)^rotr(22,a))+((a&b)^(a&c)^(b&c));
                    _h=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;
                }
                h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=_h;
            }
            return h.map(v=>('00000000'+(v>>>0).toString(16)).slice(-8)).join('');
        }

        async function login() {
            const input = document.getElementById('token');
            const msg = document.getElementById('msg');
            const token = input.value.trim();
            if (!token) { msg.textContent = '请输入 Token'; return; }
            try {
                const resNonce = await fetch('/login?get_nonce=1');
                if (!resNonce.ok) { msg.textContent = '服务器错误'; return; }
                const { nonce } = await resNonce.json();
                const clientHash = pureSha256(nonce + token);
                const r = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'hash=' + encodeURIComponent(clientHash)
                });
                if (r.ok) {
                    window.location.href = '/';
                } else {
                    msg.textContent = 'Token 错误';
                    input.value = '';
                }
            } catch(e) {
                msg.textContent = '请求失败，请检查网络';
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
        if config["auth"] and self.path.startswith("/login?get_nonce=1"):
            nonce = secrets.token_hex(16)
            config["nonces"][nonce] = time.time() + 60.0
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"nonce": nonce}).encode("utf-8"))
            return

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

            now = time.time()
            config["nonces"] = {k: v for k, v in config["nonces"].items() if v > now}

            login_success = False
            matched_nonce = None
            for nonce in config["nonces"].keys():
                expected_hash = hashlib.sha256((nonce + config["token_raw"]).encode()).hexdigest()
                if client_hash == expected_hash:
                    login_success = True
                    matched_nonce = nonce
                    break

            if login_success:
                config["nonces"].pop(matched_nonce, None)
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
        config.update(auth=True, token_raw=token)
        print(f"认证已启用，Token: {token}")
        print(f"手机浏览器打开后需输入此 Token 才能使用")

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"服务已启动，手机访问 http://<你的IP>:{port}")
    server.serve_forever()
