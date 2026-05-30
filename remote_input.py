#!/usr/bin/env python3
"""
Remote Input - Ubuntu Wayland 手机远程输入工具 (全功能版：含虚拟触摸板)

手机浏览器打开后输入文字，点发送即可自动粘贴到电脑当前光标位置。
专为 Ubuntu Wayland 环境设计，不受 GNOME 沙箱限制。
支持虚拟触摸板（鼠标移动）和左键单击。

可选参数：
  --auth              启用登录认证（自动生成 token 打印到终端）
  --auth --token XXX  启用登录认证并指定 token
  --port PORT         指定端口（默认 8080）
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess, time, os, sys, secrets, hashlib, json

config = {"auth": False, "token_raw": None, "sessions": {}, "nonces": {}}

INPUT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>Remote Input</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; touch-action: pan-x pan-y; }
        body { background: #121212; color: white; padding: 15px; font-family: -apple-system, sans-serif; -webkit-user-select: none; }
        h2 { margin-bottom: 10px; font-weight: 400; color: #888; font-size: 18px; }
        textarea { width: 100%; height: 120px; font-size: 16px; padding: 10px; background: #1e1e1e;
                   color: white; border: 1px solid #333; border-radius: 8px; resize: none; touch-action: auto; }
        .btn-group { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 8px; }
        .sub-btn { height: 38px; font-size: 13px; background: #333; color: white; border: none; border-radius: 6px; cursor: pointer; }
        .sub-btn:active { background: #444; }
        .main-btn { width: 100%; height: 46px; font-size: 18px; margin-top: 8px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer; }
        .main-btn:active { background: #1d4ed8; }

        /* 鼠标控制区布局 */
        .mouse-container { display: flex; gap: 10px; margin-top: 15px; height: 180px; }
        .click-btn { width: 60px; height: 100%; background: #dc2626; color: white; border: none; border-radius: 8px;
                     font-size: 14px; font-weight: bold; cursor: pointer; -webkit-tap-highlight-color: transparent; }
        .click-btn:active { background: #b91c1c; }
        .click-btn.right-btn { background: #7c3aed; }
        .click-btn.right-btn:active { background: #6d28d9; }
        .touchpad { flex: 1; height: 100%; background: #222; border: 2px dashed #444; border-radius: 8px;
                    display: flex; justify-content: center; align-items: center; color: #666; font-size: 13px;
                    position: relative; touch-action: none; text-align: center; padding: 10px; }

        #status { margin-top: 8px; color: #4ade80; font-size: 13px; min-height: 18px; text-align: center; }
    </style>
</head>
<body>
    <h2>Remote Input</h2>
    <textarea id="text" placeholder="在这里输入文字..."></textarea>

    <div class="btn-group">
        <button class="sub-btn" onclick="sendAction('key', '28')">Enter</button>
        <button class="sub-btn" onclick="sendAction('key', '14')">Back</button>
        <button class="sub-btn" onclick="sendAction('shortcut', 'ctrl+a')">全选</button>
        <button class="sub-btn" onclick="sendAction('shortcut', 'ctrl+z')">撤销</button>
    </div>
    <div class="btn-group">
        <button class="sub-btn" onclick="sendAction('key', '103')">↑</button>
        <button class="sub-btn" onclick="sendAction('key', '108')">↓</button>
        <button class="sub-btn" onclick="sendAction('key', '105')">←</button>
        <button class="sub-btn" onclick="sendAction('key', '106')">→</button>
    </div>

    <button class="main-btn" onclick="sendText()">发送文本到电脑</button>

    <div class="mouse-container">
        <button class="click-btn" id="leftClickBtn">左键</button>
        <div class="touchpad" id="pad">滑动控制鼠标指针</div>
        <button class="click-btn right-btn" id="rightClickBtn">右键</button>
    </div>

    <div id="status"></div>

    <script>
        let sending = false;

        // 1. 基础文本与按键发送（带静默模式，鼠标高频请求不触发状态提示）
        async function postData(payload, quiet=false) {
            if (sending && !quiet) return;
            if (!quiet) sending = true;
            const s = document.getElementById('status');
            try {
                const r = await fetch('/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!r.ok && r.status === 403) {
                    window.location.href = '/';
                }
            } catch(e) { if(!quiet) s.textContent = '网络错误'; }
            finally { if(!quiet) sending = false; }
        }

        function sendText() {
            const t = document.getElementById('text');
            if (t.value.trim() === '') return;
            postData({ type: 'text', value: t.value });
            t.value = '';
        }

        function sendAction(type, value) {
            postData({ type: type, value: value });
        }

        // 2. 触摸板核心逻辑：轻触=左键，长按拖动=按住拖拽
        const pad = document.getElementById('pad');
        let lastX = 0, lastY = 0;
        let totalDx = 0, totalDy = 0;
        let touchStartTime = 0;
        let isHolding = false;       // 长按已触发，按键已按下
        let holdSent = false;        // 已发送 mouse_down
        let moveQueue = { dx: 0, dy: 0 };
        let timer = null;
        const HOLD_DELAY = 300;     // 长按阈值 300ms
        const TAP_THRESHOLD = 10;   // 轻触移动容忍像素

        pad.addEventListener('touchstart', (e) => {
            const touch = e.touches[0];
            lastX = touch.clientX;
            lastY = touch.clientY;
            totalDx = 0;
            totalDy = 0;
            touchStartTime = Date.now();
            isHolding = false;
            holdSent = false;
            pad.style.background = '#2a2a2a';
        });

        pad.addEventListener('touchmove', (e) => {
            if (e.touches.length !== 1) return;
            const touch = e.touches[0];
            let dx = touch.clientX - lastX;
            let dy = touch.clientY - lastY;
            lastX = touch.clientX;
            lastY = touch.clientY;
            totalDx += Math.abs(dx);
            totalDy += Math.abs(dy);

            // 如果移动距离超过阈值且还没进入长按状态，取消长按检测
            if (!isHolding && (totalDx > TAP_THRESHOLD || totalDy > TAP_THRESHOLD)) {
                // 移动距离已经够大，如果还没到长按时间，说明是快速滑动，不触发拖拽
                // 但如果已经超过长按时间，进入拖拽
            }

            // 已经超过长按时间，发送 mouse_down 并开始拖拽
            if (!holdSent && Date.now() - touchStartTime >= HOLD_DELAY) {
                isHolding = true;
                holdSent = true;
                postData({ type: 'mouse_down', value: 'left' }, true);
                pad.style.background = '#333';
            }

            // 灵敏度系数 1.5 倍
            moveQueue.dx += dx * 1.5;
            moveQueue.dy += dy * 1.5;

            // 节流：40ms 周期打包发送
            if (!timer) {
                timer = setTimeout(() => {
                    let sendX = Math.round(moveQueue.dx);
                    let sendY = Math.round(moveQueue.dy);
                    if (sendX !== 0 || sendY !== 0) {
                        postData({ type: 'mouse_move', x: sendX, y: sendY }, true);
                    }
                    moveQueue = { dx: 0, dy: 0 };
                    timer = null;
                }, 40);
            }
        });

        pad.addEventListener('touchend', (e) => {
            let elapsed = Date.now() - touchStartTime;

            if (holdSent) {
                // 拖拽结束，释放按键
                postData({ type: 'mouse_up', value: 'left' }, true);
            } else if (elapsed < HOLD_DELAY && totalDx < TAP_THRESHOLD && totalDy < TAP_THRESHOLD) {
                // 轻触 = 左键单击
                postData({ type: 'mouse_click', value: 'left' }, true);
            }

            isHolding = false;
            holdSent = false;
            pad.style.background = '#222';
        });

        // 3. 左键单击
        const leftBtn = document.getElementById('leftClickBtn');
        leftBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            postData({ type: 'mouse_click', value: 'left' }, true);
        });

        // 4. 右键单击
        const rightBtn = document.getElementById('rightClickBtn');
        rightBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            postData({ type: 'mouse_click', value: 'right' }, true);
        });
    </script>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <title>Login - Remote Input</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #121212; color: white; padding: 20px; font-family: -apple-system, sans-serif;
               display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .login-box { width: 100%%; max-width: 360px; }
        h2 { margin-bottom: 15px; font-weight: 400; color: #888; text-align: center; }
        input { width: 100%%; height: 56px; font-size: 18px; padding: 12px; background: #1e1e1e; color: white; border: 1px solid #333; border-radius: 8px; outline: none; }
        input:focus { border-color: #2563eb; }
        button { width: 100%%; height: 56px; font-size: 20px; margin-top: 12px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer; }
        button:active { background: #1d4ed8; }
        #msg { margin-top: 10px; color: #f87171; font-size: 14px; text-align: center; min-height: 20px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>Remote Input</h2>
        <input id="token" type="password" placeholder="请输入 Token" onkeydown="if(event.key==='Enter')login()">
        <button onclick="login()">登录</button>
        <div id="msg"></div>
    </div>
    <script>
        function safeSha256(s) {
            var chrsz = 8, hexcase = 0;
            function safe_add(x, y) { var lsw = (x & 0xFFFF) + (y & 0xFFFF), msw = (x >> 16) + (y >> 16) + (lsw >> 16); return (msw << 16) | (lsw & 0xFFFF); }
            function S(X, n) { return (X >>> n) | (X << (32 - n)); }
            function R(X, n) { return (X >>> n); }
            function Ch(x, y, z) { return ((x & y) ^ (~x & z)); }
            function Maj(x, y, z) { return ((x & y) ^ (x & z) ^ (y & z)); }
            function Sigma0256(x) { return (S(x, 2) ^ S(x, 13) ^ S(x, 22)); }
            function Sigma1256(x) { return (S(x, 6) ^ S(x, 11) ^ S(x, 25)); }
            function gamma0256(x) { return (S(x, 7) ^ S(x, 18) ^ R(x, 3)); }
            function gamma1256(x) { return (S(x, 17) ^ S(x, 19) ^ R(x, 10)); }
            function core_sha256(m, l) {
                var K = [0x428A2F98,0x71374491,0xB5C0FBCF,0xE9B5DBA5,0x3956C25B,0x59F111F1,0x923F82A4,0xAB1C5ED5,0xD807AA98,0x12835B01,0x243185BE,0x550C7DC3,0x72BE5D74,0x80DEB1FE,0x9BDC06A7,0xC19BF174,0xE49B69C1,0xEFBE4786,0x0FC19DC6,0x240CA1CC,0x2DE92C6F,0x4A7484AA,0x5CB0A9DC,0x76F988DA,0x983E5152,0xA831C66D,0xB00327C8,0xBF597FC7,0xC6E00BF3,0xD5A79147,0x6CA6351,0x14292967,0x27B70A85,0x2E1B2138,0x4D2C6DFC,0x53380D13,0x650A7354,0x766A0ABB,0x81C2C92E,0x92722C85,0xA2BFE8A1,0xA81A664B,0xC24B8B70,0xC76C51A3,0xD192E819,0xD6990624,0xF40E3585,0x106AA070,0x19A4C116,0x1E376C08,0x2748774C,0x34B0BCB5,0x391C0CB3,0x4ED8AA4A,0x5B9CCA4F,0x682E6FF3,0x748F82EE,0x78A5636F,0x84C87814,0x8CC70208,0x90BEFFFA,0xA4506CEB,0xBEF9A3F7,0xC67178F2];
                var HASH = [0x6A09E667,0xBB67AE85,0x3C6EF372,0xA54FF53A,0x510E527F,0x9B05688C,0x1F83D9AB,0x5BE0CD19];
                var W = new Array(64); var a, b, c, d, e, f, g, h, i, j; var T1, T2; m[l >> 5] |= 0x80 << (24 - l % 32); m[((l + 64 >> 9) << 4) + 15] = l;
                for (var i = 0; i < m.length; i += 16) {
                    a = HASH[0]; b = HASH[1]; c = HASH[2]; d = HASH[3]; e = HASH[4]; f = HASH[5]; g = HASH[6]; h = HASH[7];
                    for (var j = 0; j < 64; j++) {
                        if (j < 16) W[j] = m[j + i];
                        else W[j] = safe_add(safe_add(safe_add(gamma1256(W[j - 2]), W[j - 7]), gamma0256(W[j - 15])), W[j - 16]);
                        T1 = safe_add(safe_add(safe_add(safe_add(h, Sigma1256(e)), Ch(e, f, g)), K[j]), W[j]); T2 = safe_add(Sigma0256(a), Maj(a, b, c));
                        h = g; g = f; f = e; e = safe_add(d, T1); d = c; c = b; b = a; a = safe_add(T1, T2);
                    }
                    HASH[0] = safe_add(a, HASH[0]); HASH[1] = safe_add(b, HASH[1]); HASH[2] = safe_add(c, HASH[2]); HASH[3] = safe_add(d, HASH[3]); HASH[4] = safe_add(e, HASH[4]); HASH[5] = safe_add(f, HASH[5]); HASH[6] = safe_add(g, HASH[6]); HASH[7] = safe_add(h, HASH[7]);
                } return HASH;
            }
            function str2binb(str) { var bin = Array(); var mask = (1 << chrsz) - 1; for (var i = 0; i < str.length * chrsz; i += chrsz) bin[i >> 5] |= (str.charCodeAt(i / chrsz) & mask) << (24 - i % 32); return bin; }
            function binb2hex(binarray) { var hex_tab = hexcase ? "0123456789ABCDEF" : "0123456789abcdef"; var str = ""; for (var i = 0; i < binarray.length * 4; i++) { str += hex_tab.charAt((binarray[i >> 2] >> ((3 - i % 4) * 8 + 4)) & 0xF) + hex_tab.charAt((binarray[i >> 2] >> ((3 - i % 4) * 8)) & 0xF); } return str; }
            return binb2hex(core_sha256(str2binb(unescape(encodeURIComponent(s))), unescape(encodeURIComponent(s)).length * chrsz));
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
                const clientHash = safeSha256(nonce + token);
                const r = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ hash: clientHash })
                });
                if (r.ok) {
                    window.location.href = '/';
                } else {
                    msg.textContent = 'Token 错误';
                    input.value = '';
                }
            } catch(e) { msg.textContent = '请求失败，请检查网络'; }
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
        # 鼠标高频移动请求很多，过滤掉日志，保持终端清爽
        if "mouse_move" in format or "mouse_click" in format:
            return
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
            try:
                data = json.loads(body)
                client_hash = data.get("hash", "")
            except:
                self.send_response(400)
                self.end_headers()
                return

            now = time.time()
            config["nonces"] = {k: v for k, v in config["nonces"].items() if v > now}

            login_success = False
            matched_nonce = None
            for nonce in config["nonces"].keys():
                expected_hash = hashlib.sha256((nonce + config["token_raw"]).encode()).hexdigest()
                if client_hash.lower() == expected_hash.lower():
                    login_success = True
                    matched_nonce = nonce
                    break

            if login_success:
                config["nonces"].pop(matched_nonce, None)
                session_id = secrets.token_hex(32)
                config["sessions"][sha256_hex(session_id)] = True
                self.send_response(200)
                self.send_header("Set-Cookie", f"session={session_id}; Path=/; HttpOnly; SameSite=Strict")
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
        body = self.rfile.read(length).decode("utf-8")

        try:
            data = json.loads(body)
            data_type = data.get("type", "text")
            data_value = data.get("value", "")
        except:
            data_type = "text"
            data_value = body

        env = os.environ.copy()
        env["DISPLAY"] = ":0"

        if data_type == "mouse_move":
            mx = data.get("x", 0)
            my = data.get("y", 0)
            subprocess.run(["ydotool", "mousemove", "-x", str(mx), "-y", str(my)], env=env)
        elif data_type == "mouse_click":
            click_val = data.get("value", "left")
            key_code = "0xC1" if click_val == "right" else "0xC0"
            subprocess.run(["ydotool", "click", key_code], env=env)
        elif data_type == "mouse_down":
            click_val = data.get("value", "left")
            # 0x40=down base, 0x00=left, 0x01=right
            key_code = "0x41" if click_val == "right" else "0x40"
            subprocess.run(["ydotool", "click", key_code], env=env)
        elif data_type == "mouse_up":
            click_val = data.get("value", "left")
            # 0x80=up base, 0x00=left, 0x01=right
            key_code = "0x81" if click_val == "right" else "0x80"
            subprocess.run(["ydotool", "click", key_code], env=env)
        elif data_type == "text" and data_value:
            subprocess.run(["wl-copy"], input=data_value.encode("utf-8"), env=env)
            subprocess.run(["wl-copy", "-p"], input=data_value.encode("utf-8"), env=env)
            time.sleep(0.15)
            subprocess.run(["ydotool", "key", "-d", "50", "42:1", "110:1", "110:0", "42:0"], env=env)
        elif data_type == "key" and data_value:
            subprocess.run(["ydotool", "key", f"{data_value}:1", f"{data_value}:0"], env=env)
        elif data_type == "shortcut" and data_value:
            if data_value == "ctrl+a":
                subprocess.run(["ydotool", "key", "-d", "20", "29:1", "30:1", "30:0", "29:0"], env=env)
            elif data_value == "ctrl+z":
                subprocess.run(["ydotool", "key", "-d", "20", "29:1", "44:1", "44:0", "29:0"], env=env)

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

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"服务已启动，端口: {port}")
    server.serve_forever()
