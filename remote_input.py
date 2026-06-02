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
        .header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .term-label { color: #a855f7; font-size: 14px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
        .term-label input { accent-color: #a855f7; }
        textarea { width: 100%; height: 120px; font-size: 16px; padding: 10px; background: #1e1e1e;
                   color: white; border: 1px solid #333; border-radius: 8px; resize: none; touch-action: auto; }
        .btn-group { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 8px; }
        .sub-btn { height: 38px; font-size: 13px; background: #333; color: white; border: none; border-radius: 6px; cursor: pointer; }
        .sub-btn:active { background: #444; }
        .main-btn { width: 100%; height: 46px; font-size: 18px; margin-top: 8px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer; }
        .main-btn:active { background: #1d4ed8; }

        /* 鼠标控制区布局 */
        .mouse-container { display: flex; gap: 8px; margin-top: 15px; height: 180px; }
        .click-btn { width: 56px; height: 100%; background: #dc2626; color: white; border: none; border-radius: 8px;
                     font-size: 14px; font-weight: bold; cursor: pointer; -webkit-tap-highlight-color: transparent; }
        .click-btn:active { background: #b91c1c; }
        .click-btn.right-btn { background: #7c3aed; }
        .click-btn.right-btn:active { background: #6d28d9; }
        .scroll-col { display: flex; flex-direction: column; gap: 4px; width: 40px; height: 100%; }
        .scroll-btn { flex: 1; background: #333; color: white; border: none; border-radius: 6px;
                      font-size: 12px; cursor: pointer; -webkit-tap-highlight-color: transparent; display: flex;
                      justify-content: center; align-items: center; }
        .scroll-btn:active { background: #555; }
        .touchpad { flex: 1; height: 100%; background: #222; border: 2px dashed #444; border-radius: 8px;
                    display: flex; justify-content: center; align-items: center; color: #666; font-size: 13px;
                    position: relative; touch-action: none; text-align: center; padding: 10px;
                    user-select: none; -webkit-user-select: none; }

        .sensitivity-bar { display: flex; align-items: center; gap: 6px; margin-top: 10px; padding: 0 2px; }
        .sensitivity-bar input[type=range] { flex: 1; height: 3px; -webkit-appearance: none; background: #444; border-radius: 2px; outline: none; }
        .sensitivity-bar input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; background: #2563eb; border-radius: 50%; cursor: pointer; }
        .sensitivity-bar span { color: #666; font-size: 11px; min-width: 28px; text-align: right; }
        #status { margin-top: 8px; color: #4ade80; font-size: 13px; min-height: 18px; text-align: center; }
        .help-text { margin-top: 10px; color: #555; font-size: 11px; line-height: 1.6; }
        .help-text b { color: #777; }

        /* 文件上传区域 */
        .file-upload-section { margin-top: 15px; }
        .upload-row { display: flex; gap: 8px; align-items: center; }
        .dir-input {
            flex: 1; height: 38px; font-size: 13px; padding: 0 10px;
            background: #1e1e1e; color: white; border: 1px solid #333;
            border-radius: 6px; outline: none;
        }
        .dir-input:focus { border-color: #2563eb; }
        .dir-input::placeholder { color: #666; }
        .upload-btn {
            height: 38px; padding: 0 16px; font-size: 13px;
            background: #2563eb; color: white; border: none;
            border-radius: 6px; cursor: pointer; white-space: nowrap;
        }
        .upload-btn:active { background: #1d4ed8; }
        .upload-status { margin-top: 6px; color: #4ade80; font-size: 12px; min-height: 16px; }

        /* 统一宽度限制与居中容器 */
        .main-container { width: 100%; margin: 0; }

        /* 键盘模式 */
        .kb-hide { display: none !important; }
        .kb-label { color: #2563eb; font-size: 14px; display: flex; align-items: center; gap: 4px; cursor: pointer; margin-left: 12px; }
        .kb-label input { accent-color: #2563eb; }
        .keyboard { display: none; margin-top: 5px; width: 100%; }
        .keyboard.active { display: block; }
        .kb-row { display: flex; gap: 2px; margin-bottom: 2px; justify-content: space-between; width: 100%; }
        .kb-key {
            min-width: 20px; height: 32px; font-size: 10px;
            background: #333; color: white; border: none; border-radius: 3px;
            cursor: pointer; display: flex; justify-content: center; align-items: center;
            padding: 0 3px; -webkit-tap-highlight-color: transparent;
            flex: 1 1 auto; user-select: none; -webkit-user-select: none;
        }
        .kb-key:active { background: #555; }
        .kb-key.wide { flex: 1.5 1 auto; font-size: 9px; }
        .kb-row:first-child .kb-key { font-size: 7px; min-width: 18px; height: 24px; }
        .kb-key.space { flex: 5 1 auto; }
        .kb-key.shift-active { background: #2563eb; }
        .kb-key.long-press { background: #2563eb; }
        .kb-key.alt-active { background: #2563eb !important; color: white; }
        .touchpad-only {
            margin-top: 10px; display: none !important; flex-direction: row;
            align-items: stretch; gap: 8px; width: 100%; height: 160px;
        }
        .touchpad-only.active { display: flex !important; }
        .numpad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; flex: 0 0 28%; }
        .numpad .kb-key { flex: none; width: 100%; height: 100%; font-size: 12px; }
        .touchpad-only .touchpad { flex: 1; width: auto; height: 100%; }
        .touchpad-col { flex: 1; display: flex; flex-direction: column; gap: 4px; }
        .touchpad-col .touchpad { flex: 1; height: auto; }
        .kb-sens { margin-top: 0; padding: 0 2px; }
    </style>
</head>
<body>
    <div class="header-row">
        <h2>Remote Input</h2>
        <div style="display:flex;align-items:center;">
            <label class="term-label"><input type="checkbox" id="termMode"> 终端模式</label>
            <label class="kb-label"><input type="checkbox" id="kbMode"> 键盘模式</label>
        </div>
    </div>
    <div id="inputArea">
    <textarea id="text" placeholder="在这里输入文字..."></textarea>

    <div class="btn-group">
        <button class="sub-btn" onclick="sendAction('key', '1')">Esc</button>
        <button class="sub-btn" onclick="sendAction('key', '15')">Tab</button>
        <button class="sub-btn" onclick="sendAction('key', '14')">退格</button>
        <button class="sub-btn" onclick="sendAction('mouse_click', 'right')">右键</button>
    </div>
    <div class="btn-group">
        <button class="sub-btn" onclick="sendAction('key', '103')">↑</button>
        <button class="sub-btn" onclick="sendAction('key', '108')">↓</button>
        <button class="sub-btn" onclick="sendAction('key', '105')">←</button>
        <button class="sub-btn" onclick="sendAction('key', '106')">→</button>
    </div>
    <div class="btn-group">
        <button class="sub-btn" onclick="sendAction('shortcut', 'ctrl+z')">撤销</button>
        <button class="sub-btn" onclick="sendAction('shortcut', 'ctrl+a')">全选</button>
        <button class="sub-btn" onclick="sendAction('shortcut', 'ctrl+c')">复制</button>
        <button class="sub-btn" onclick="sendAction('shortcut', 'shift+insert')">粘贴</button>
    </div>

    <button class="main-btn" onclick="sendText()">发送文本到电脑</button>

    <div class="mouse-container">
        <div class="scroll-col">
            <button class="scroll-btn" onclick="sendAction('key', '104')">PgUp</button>
            <button class="scroll-btn" onclick="sendAction('key', '109')">PgDn</button>
        </div>
        <div class="touchpad" id="pad"></div>
        <button class="click-btn right-btn" id="enterBtn">Enter</button>
    </div>

    <div class="sensitivity-bar">
        <span>灵敏</span>
        <input type="range" id="sensitivity" min="0.3" max="5" step="0.1" value="2">
        <span id="sensVal">2.0</span>
    </div>
    </div>

    <div class="main-container">
    <div class="keyboard" id="keyboard">
        <div class="kb-row">
            <button class="kb-key wide" data-code="1">Esc</button>
            <button class="kb-key" data-code="59">F1</button>
            <button class="kb-key" data-code="60">F2</button>
            <button class="kb-key" data-code="61">F3</button>
            <button class="kb-key" data-code="62">F4</button>
            <button class="kb-key" data-code="63">F5</button>
            <button class="kb-key" data-code="64">F6</button>
            <button class="kb-key" data-code="65">F7</button>
            <button class="kb-key" data-code="66">F8</button>
            <button class="kb-key" data-code="67">F9</button>
            <button class="kb-key" data-code="68">F10</button>
            <button class="kb-key" data-code="87">F11</button>
            <button class="kb-key" data-code="88">F12</button>
            <button class="kb-key" data-code="102">Home</button>
            <button class="kb-key" data-code="107">End</button>
            <button class="kb-key" data-code="110">Ins</button>
            <button class="kb-key" data-code="111">Del</button>
        </div>
        <div class="kb-row">
            <button class="kb-key" data-code="41" data-label="`" data-shift="~">`</button>
            <button class="kb-key" data-code="2" data-label="1" data-shift="!">1</button>
            <button class="kb-key" data-code="3" data-label="2" data-shift="@">2</button>
            <button class="kb-key" data-code="4" data-label="3" data-shift="#">3</button>
            <button class="kb-key" data-code="5" data-label="4" data-shift="$">4</button>
            <button class="kb-key" data-code="6" data-label="5" data-shift="%">5</button>
            <button class="kb-key" data-code="7" data-label="6" data-shift="^">6</button>
            <button class="kb-key" data-code="8" data-label="7" data-shift="&amp;">7</button>
            <button class="kb-key" data-code="9" data-label="8" data-shift="*">8</button>
            <button class="kb-key" data-code="10" data-label="9" data-shift="(">9</button>
            <button class="kb-key" data-code="11" data-label="0" data-shift=")">0</button>
            <button class="kb-key" data-code="12" data-label="-" data-shift="_">-</button>
            <button class="kb-key" data-code="13" data-label="=" data-shift="+">=</button>
            <button class="kb-key wide" data-code="14">退格</button>
        </div>
        <div class="kb-row">
            <button class="kb-key wide" data-code="15">Tab</button>
            <button class="kb-key" data-code="16">Q</button>
            <button class="kb-key" data-code="17">W</button>
            <button class="kb-key" data-code="18">E</button>
            <button class="kb-key" data-code="19">R</button>
            <button class="kb-key" data-code="20">T</button>
            <button class="kb-key" data-code="21">Y</button>
            <button class="kb-key" data-code="22">U</button>
            <button class="kb-key" data-code="23">I</button>
            <button class="kb-key" data-code="24">O</button>
            <button class="kb-key" data-code="25">P</button>
            <button class="kb-key" data-code="26" data-label="[" data-shift="{">[</button>
            <button class="kb-key" data-code="27" data-label="]" data-shift="}">]</button>
            <button class="kb-key" data-code="43" data-label="\\" data-shift="|">\</button>
        </div>
        <div class="kb-row">
            <button class="kb-key wide" data-code="58">Caps</button>
            <button class="kb-key" data-code="30">A</button>
            <button class="kb-key" data-code="31">S</button>
            <button class="kb-key" data-code="32">D</button>
            <button class="kb-key" data-code="33">F</button>
            <button class="kb-key" data-code="34">G</button>
            <button class="kb-key" data-code="35">H</button>
            <button class="kb-key" data-code="36">J</button>
            <button class="kb-key" data-code="37">K</button>
            <button class="kb-key" data-code="38">L</button>
            <button class="kb-key" data-code="39" data-label=";" data-shift=":">;</button>
            <button class="kb-key" data-code="40" data-label="'" data-shift="&quot;">'</button>
            <button class="kb-key wide" data-code="28">Enter</button>
        </div>
        <div class="kb-row">
            <button class="kb-key wide" id="shiftKey" data-code="42">Shift</button>
            <button class="kb-key" data-code="44">Z</button>
            <button class="kb-key" data-code="45">X</button>
            <button class="kb-key" data-code="46">C</button>
            <button class="kb-key" data-code="47">V</button>
            <button class="kb-key" data-code="48">B</button>
            <button class="kb-key" data-code="49">N</button>
            <button class="kb-key" data-code="50">M</button>
            <button class="kb-key" data-code="51" data-label="," data-shift="&lt;">,</button>
            <button class="kb-key" data-code="52" data-label="." data-shift="&gt;">.</button>
            <button class="kb-key" data-code="53" data-label="/" data-shift="?">/</button>
            <button class="kb-key" data-code="104">PgUp</button>
            <button class="kb-key" data-code="109">PgDn</button>
        </div>
        <div class="kb-row">
            <button class="kb-key wide" data-code="29">Ctrl</button>
            <button class="kb-key wide" data-code="464">Fn</button>
            <button class="kb-key wide" data-code="125">Win</button>
            <button class="kb-key wide" data-code="56">Alt</button>
            <button class="kb-key space" data-code="57">Space</button>
            <button class="kb-key" data-code="210">PrtSc</button>
            <button class="kb-key" data-code="105">←</button>
            <button class="kb-key" data-code="103">↑</button>
            <button class="kb-key" data-code="108">↓</button>
            <button class="kb-key" data-code="106">→</button>
        </div>
    </div>

    <div class="touchpad-only" id="touchpadOnly">
        <div class="numpad">
            <button class="kb-key" data-code="8">7</button>
            <button class="kb-key" data-code="9">8</button>
            <button class="kb-key" data-code="10">9</button>
            <button class="kb-key" data-code="5">4</button>
            <button class="kb-key" data-code="6">5</button>
            <button class="kb-key" data-code="7">6</button>
            <button class="kb-key" data-code="2">1</button>
            <button class="kb-key" data-code="3">2</button>
            <button class="kb-key" data-code="4">3</button>
            <button class="kb-key" data-code="11">0</button>
            <button class="kb-key" data-code="52">.</button>
            <button class="kb-key" data-code="28">Enter</button>
        </div>
        <div class="touchpad-col">
            <div class="touchpad" id="pad2"></div>
            <div class="sensitivity-bar kb-sens">
                <span>灵敏</span>
                <input type="range" id="sensitivityKb" min="0.3" max="5" step="0.1" value="2">
                <span id="sensValKb">2.0</span>
            </div>
        </div>
    </div>
    </div>

    <div id="status"></div>

    <div class="help-text">
        <b>触摸板</b>：滑动=移动光标，轻触=左键，双击=拖拽模式（再双击退出）<br>
        <b>左键/右键</b>：点击对应按钮 | <b>PgUp/PgDn</b>：翻页<br>
        <b>终端模式</b>：复制/粘贴→Ctrl+Shift+C/V，PgUp/PgDn→Ctrl+Shift+PageUp/Down<br>
        <b>快捷键</b>：退格=退格键，Esc=退出，Tab=制表，↑↓←→=方向键
    </div>

    <div class="file-upload-section">
        <div class="upload-row">
            <input type="text" id="targetDir" placeholder="目标目录（默认: ~/Downloads）" class="dir-input">
            <button class="upload-btn" onclick="document.getElementById('fileInput').click()">上传文件</button>
            <input type="file" id="fileInput" multiple style="display:none" onchange="uploadFiles(this.files)">
        </div>
        <div id="uploadStatus" class="upload-status"></div>
    </div>

    <script>
        let sending = false;

        // 键盘模式切换
        const kbModeCb = document.getElementById('kbMode');
        const inputArea = document.getElementById('inputArea');
        const kbContainer = document.getElementById('keyboard');
        const touchpadOnly = document.getElementById('touchpadOnly');

        kbModeCb.addEventListener('change', () => {
            const active = kbModeCb.checked;
            inputArea.classList.toggle('kb-hide', active);
            kbContainer.classList.toggle('active', active);
            touchpadOnly.classList.toggle('active', active);
            document.activeElement?.blur();
        });

        // Shift 状态管理
        let shiftActive = false;
        const shiftKeyEl = document.getElementById('shiftKey');

        function updateShiftDisplay() {
            document.querySelectorAll('.kb-key[data-shift]').forEach(k => {
                k.textContent = shiftActive ? k.dataset.shift : k.dataset.label;
            });
        }

        shiftKeyEl.addEventListener('touchstart', (e) => {
            e.preventDefault();
            shiftActive = !shiftActive;
            shiftKeyEl.classList.toggle('shift-active', shiftActive);
            updateShiftDisplay();
        });

        // CapsLock 状态管理
        let capsLockActive = false;
        const capsLockKey = document.querySelector('[data-code="58"]');
        capsLockKey.addEventListener('touchstart', (e) => {
            e.preventDefault();
            capsLockActive = !capsLockActive;
            capsLockKey.classList.toggle('shift-active', capsLockActive);
        });

        // Ctrl 组合键状态管理
        let ctrlActive = false;
        const ctrlKeyEl = document.querySelector('[data-code="29"]');
        ctrlKeyEl.addEventListener('touchstart', (e) => {
            e.preventDefault();
            ctrlActive = !ctrlActive;
            ctrlKeyEl.classList.toggle('alt-active', ctrlActive);
        });

        // 字母键 keycode 集合
        const letterCodes = new Set([
            16,17,18,19,20,21,22,23,24,25,
            30,31,32,33,34,35,36,37,38,
            44,45,46,47,48,49,50
        ]);

        // 长按 + 上滑手势检测
        let longPressTimer = null;
        let longPressKey = null;
        const LONG_PRESS_MS = 500;
        let swipeStartX = 0, swipeStartY = 0;
        let swipeActiveKey = null;
        let swipeTriggered = false;
        const SLIDE_UP_THRESHOLD = 30;

        // 键盘按键处理（事件委托，同时绑定全键盘和小键盘）
        function handleKeyTouchStart(e) {
            const key = e.target.closest('.kb-key');
            if (!key) return;
            e.preventDefault();

            const code = parseInt(key.getAttribute('data-code'));
            if (!code) return;
            if (key.id === 'shiftKey' || key.dataset.code === '58' || key.dataset.code === '29') return;

            // 记录触摸起始位置
            const touch = e.touches[0];
            swipeStartX = touch.clientX;
            swipeStartY = touch.clientY;
            swipeActiveKey = key;
            swipeTriggered = false;

            // 视觉反馈
            key.style.background = '#555';

            // 长按检测：有 shift 变体的键
            if (key.dataset.shift) {
                longPressTimer = setTimeout(() => {
                    longPressKey = key;
                    key.classList.add('long-press');
                    key.textContent = key.dataset.shift;
                }, LONG_PRESS_MS);
            }
        }

        function handleKeyTouchMove(e) {
            if (!swipeActiveKey || !swipeActiveKey.dataset.shift) return;
            const touch = e.touches[0];
            const diffY = swipeStartY - touch.clientY; // 向上为正

            if (diffY > SLIDE_UP_THRESHOLD && !swipeTriggered) {
                // 上滑超过阈值，切换到替代字符
                swipeTriggered = true;
                // 取消长按计时器（上滑优先于长按）
                if (longPressTimer) {
                    clearTimeout(longPressTimer);
                    longPressTimer = null;
                }
                // 视觉反馈：显示替代字符并高亮
                swipeActiveKey.classList.add('alt-active');
                swipeActiveKey.textContent = swipeActiveKey.dataset.shift;
            } else if (diffY <= 0 && swipeTriggered) {
                // 滑回原位，取消替代
                swipeTriggered = false;
                swipeActiveKey.classList.remove('alt-active');
                if (!longPressKey) {
                    swipeActiveKey.textContent = swipeActiveKey.dataset.label;
                }
            }
        }

        function handleKeyTouchEnd(e) {
            const key = swipeActiveKey || e.target.closest('.kb-key');
            if (!key) return;

            const code = parseInt(key.getAttribute('data-code'));
            if (!code) return;
            if (key.id === 'shiftKey' || key.dataset.code === '58' || key.dataset.code === '29') return;

            key.style.background = '';

            if (swipeTriggered) {
                // 上滑触发：发送 shifted 键
                key.classList.remove('alt-active');
                key.textContent = key.dataset.label;
                postData({ type: 'key_combo', value: '42,' + code });
            } else if (longPressTimer) {
                // 普通短按（无上滑、无长按）
                clearTimeout(longPressTimer);
                longPressTimer = null;

                if (ctrlActive && shiftActive) {
                    // Ctrl+Shift+key 组合
                    postData({ type: 'key_combo', value: '29,42,' + code });
                    ctrlActive = false;
                    ctrlKeyEl.classList.remove('alt-active');
                    shiftActive = false;
                    shiftKeyEl.classList.remove('shift-active');
                    updateShiftDisplay();
                } else if (ctrlActive) {
                    // Ctrl+key 组合
                    postData({ type: 'key_combo', value: '29,' + code });
                    ctrlActive = false;
                    ctrlKeyEl.classList.remove('alt-active');
                } else if (shiftActive || (capsLockActive && letterCodes.has(code))) {
                    postData({ type: 'key_combo', value: '42,' + code });
                    if (shiftActive) {
                        shiftActive = false;
                        shiftKeyEl.classList.remove('shift-active');
                        updateShiftDisplay();
                    }
                } else {
                    postData({ type: 'key', value: code });
                }
            } else if (longPressKey === key) {
                // 长按触发：发送 shifted 键
                key.classList.remove('long-press');
                key.textContent = key.dataset.label;
                postData({ type: 'key_combo', value: '42,' + code });
                longPressKey = null;
            } else {
                // 普通按键（字母、空格等无上滑字符的键）
                if (ctrlActive && shiftActive) {
                    postData({ type: 'key_combo', value: '29,42,' + code });
                    ctrlActive = false;
                    ctrlKeyEl.classList.remove('alt-active');
                    shiftActive = false;
                    shiftKeyEl.classList.remove('shift-active');
                    updateShiftDisplay();
                } else if (ctrlActive) {
                    postData({ type: 'key_combo', value: '29,' + code });
                    ctrlActive = false;
                    ctrlKeyEl.classList.remove('alt-active');
                } else if (shiftActive) {
                    postData({ type: 'key_combo', value: '42,' + code });
                    shiftActive = false;
                    shiftKeyEl.classList.remove('shift-active');
                    updateShiftDisplay();
                } else {
                    postData({ type: 'key', value: code });
                }
            }

            // 清理状态
            swipeActiveKey = null;
            swipeTriggered = false;
        }

        function handleKeyTouchCancel() {
            if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
            if (longPressKey) {
                longPressKey.classList.remove('long-press');
                longPressKey.textContent = longPressKey.dataset.label;
                longPressKey = null;
            }
            if (swipeActiveKey) {
                swipeActiveKey.classList.remove('alt-active');
                if (swipeActiveKey.dataset.shift) {
                    swipeActiveKey.textContent = swipeActiveKey.dataset.label;
                }
                swipeActiveKey = null;
            }
            swipeTriggered = false;
        }

        kbContainer.addEventListener('touchstart', handleKeyTouchStart, { passive: false });
        kbContainer.addEventListener('touchmove', handleKeyTouchMove, { passive: false });
        kbContainer.addEventListener('touchend', handleKeyTouchEnd, { passive: false });
        kbContainer.addEventListener('touchcancel', handleKeyTouchCancel);

        // 主键盘鼠标事件（桌面端）
        kbContainer.addEventListener('mousedown', (e) => {
            const key = e.target.closest('.kb-key');
            if (!key) return;
            e.preventDefault();
            const code = parseInt(key.getAttribute('data-code'));
            if (!code) return;
            if (key.id === 'shiftKey' || key.dataset.code === '58' || key.dataset.code === '29') {
                // Shift/Caps/Ctrl 点击切换状态
                if (key.id === 'shiftKey') {
                    shiftActive = !shiftActive;
                    shiftKeyEl.classList.toggle('shift-active', shiftActive);
                    updateShiftDisplay();
                } else if (key.dataset.code === '58') {
                    capsLockActive = !capsLockActive;
                    capsLockKey.classList.toggle('shift-active', capsLockActive);
                } else if (key.dataset.code === '29') {
                    ctrlActive = !ctrlActive;
                    ctrlKeyEl.classList.toggle('alt-active', ctrlActive);
                }
                return;
            }
            key.style.background = '#555';
            if (ctrlActive && shiftActive) {
                postData({ type: 'key_combo', value: '29,42,' + code });
                ctrlActive = false;
                ctrlKeyEl.classList.remove('alt-active');
                shiftActive = false;
                shiftKeyEl.classList.remove('shift-active');
                updateShiftDisplay();
            } else if (ctrlActive) {
                postData({ type: 'key_combo', value: '29,' + code });
                ctrlActive = false;
                ctrlKeyEl.classList.remove('alt-active');
            } else if (shiftActive || (capsLockActive && letterCodes.has(code))) {
                postData({ type: 'key_combo', value: '42,' + code });
                if (shiftActive) {
                    shiftActive = false;
                    shiftKeyEl.classList.remove('shift-active');
                    updateShiftDisplay();
                }
            } else {
                postData({ type: 'key', value: code });
            }
        });
        kbContainer.addEventListener('mouseup', (e) => {
            const key = e.target.closest('.kb-key');
            if (key) key.style.background = '';
        });
        // numpad 按键直接绑定事件（不通过 touchpadOnly 委托，避免干扰触摸板）
        document.querySelectorAll('#touchpadOnly .numpad .kb-key').forEach(key => {
            // 触摸事件
            key.addEventListener('touchstart', (e) => {
                e.stopPropagation();
                handleKeyTouchStart(e);
            }, { passive: false });
            key.addEventListener('touchend', (e) => {
                e.stopPropagation();
                handleKeyTouchEnd(e);
            }, { passive: false });
            key.addEventListener('touchcancel', (e) => {
                e.stopPropagation();
                handleKeyTouchCancel(e);
            });
            // 鼠标事件（桌面端）
            key.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const code = parseInt(key.getAttribute('data-code'));
                if (!code) return;
                key.style.background = '#555';
                // 直接发送按键，不依赖触摸板手势
                if (ctrlActive && shiftActive) {
                    postData({ type: 'key_combo', value: '29,42,' + code });
                    ctrlActive = false;
                    ctrlKeyEl.classList.remove('alt-active');
                    shiftActive = false;
                    shiftKeyEl.classList.remove('shift-active');
                    updateShiftDisplay();
                } else if (ctrlActive) {
                    postData({ type: 'key_combo', value: '29,' + code });
                    ctrlActive = false;
                    ctrlKeyEl.classList.remove('alt-active');
                } else if (shiftActive) {
                    postData({ type: 'key_combo', value: '42,' + code });
                    shiftActive = false;
                    shiftKeyEl.classList.remove('shift-active');
                    updateShiftDisplay();
                } else {
                    postData({ type: 'key', value: code });
                }
            });
            key.addEventListener('mouseup', (e) => {
                e.stopPropagation();
                key.style.background = '';
            });
        });

        // 防止键盘长按弹出菜单
        kbContainer.addEventListener('contextmenu', (e) => e.preventDefault());
        touchpadOnly.addEventListener('contextmenu', (e) => e.preventDefault());

        // 1. 基础文本与按键发送（带静默模式，鼠标高频请求不触发状态提示）
        async function postData(payload, quiet=false) {
            payload.term_mode = document.getElementById('termMode').checked;
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

        // 2. 触摸板：单指=移动/轻触单击/双击拖拽
        const sensSlider = document.getElementById('sensitivity');
        const sensVal = document.getElementById('sensVal');
        const sensSliderKb = document.getElementById('sensitivityKb');
        const sensValKb = document.getElementById('sensValKb');
        const TAP_THRESHOLD = 10;
        const DOUBLE_TAP_MS = 200;

        // 从 localStorage 加载保存的灵敏度值
        const savedSensitivity = localStorage.getItem('remote_input_sensitivity');
        if (savedSensitivity) {
            sensSlider.value = savedSensitivity;
            sensVal.textContent = parseFloat(savedSensitivity).toFixed(1);
            sensSliderKb.value = savedSensitivity;
            sensValKb.textContent = parseFloat(savedSensitivity).toFixed(1);
        }

        // 两个灵敏度滑块同步
        function syncSensitivity(source) {
            const value = parseFloat(source.value).toFixed(1);
            localStorage.setItem('remote_input_sensitivity', source.value);
            if (source === sensSlider) {
                sensVal.textContent = value;
                sensSliderKb.value = source.value;
                sensValKb.textContent = value;
            } else {
                sensValKb.textContent = value;
                sensSlider.value = source.value;
                sensVal.textContent = value;
            }
        }
        sensSlider.addEventListener('input', () => syncSensitivity(sensSlider));
        sensSliderKb.addEventListener('input', () => syncSensitivity(sensSliderKb));

        function setupTouchpad(el) {
            let lastX = 0, lastY = 0;
            let totalDx = 0, totalDy = 0;
            let moveQueue = { dx: 0, dy: 0 };
            let moveTimer = null;
            let padState = 'idle';
            let tapTimeout = null;
            let lastTapTime = 0;     // 上次 tap 结束的时间戳，用于兜底检测双击
            let isDragging = false;  // 防止 timeout 在拖拽中误发 click
            let inputType = null; // 'touch' or 'mouse' — 防止混合设备上两端打架

            function padSendMove() {
                let sendX = Math.round(moveQueue.dx);
                let sendY = Math.round(moveQueue.dy);
                if (sendX !== 0 || sendY !== 0) {
                    postData({ type: 'mouse_move', x: sendX, y: sendY }, true);
                }
                moveQueue = { dx: 0, dy: 0 };
                moveTimer = null;
            }

            // 共享的核心逻辑：开始、移动、结束
            function handleStart(cx, cy) {
                lastX = cx;
                lastY = cy;
                totalDx = 0;
                totalDy = 0;
                el.style.background = '#2a2a2a';

                if (padState === 'pending_tap') {
                    // 正常路径：timeout 还没 fires，padState 仍是 pending_tap
                    clearTimeout(tapTimeout);
                    padState = 'dragging';
                    isDragging = true;
                    postData({ type: 'mouse_down', value: 'left' }, true);
                    el.style.background = '#333';
                } else if (padState === 'idle' && lastTapTime &&
                           Date.now() - lastTapTime < DOUBLE_TAP_MS) {
                    // 兜底路径：timeout 已 fires 把 padState 重置为 idle，
                    // 但用户确实在双击时间窗口内，仍然启动拖拽
                    padState = 'dragging';
                    isDragging = true;
                    postData({ type: 'mouse_down', value: 'left' }, true);
                    el.style.background = '#333';
                }
            }

            function handleMove(cx, cy) {
                let dx = cx - lastX;
                let dy = cy - lastY;
                lastX = cx;
                lastY = cy;
                totalDx += Math.abs(dx);
                totalDy += Math.abs(dy);

                moveQueue.dx += dx * parseFloat(sensSlider.value);
                moveQueue.dy += dy * parseFloat(sensSlider.value);
                if (!moveTimer) {
                    moveTimer = setTimeout(padSendMove, 40);
                }
            }

            function handleEnd() {
                let isTap = totalDx < TAP_THRESHOLD && totalDy < TAP_THRESHOLD;

                if (padState === 'dragging') {
                    postData({ type: 'mouse_up', value: 'left' }, true);
                    padState = 'idle';
                    isDragging = false;
                    el.style.background = '#222';
                    return;
                }

                if (isTap && padState === 'idle') {
                    padState = 'pending_tap';
                    lastTapTime = Date.now();
                    tapTimeout = setTimeout(() => {
                        // isDragging 检查：拖拽已启动时 timeout 不应发 click
                        if (padState === 'pending_tap' && !isDragging) {
                            postData({ type: 'mouse_click', value: 'left' }, true);
                            padState = 'idle';
                        }
                    }, DOUBLE_TAP_MS);
                } else if (padState === 'pending_tap') {
                    clearTimeout(tapTimeout);
                    padState = 'idle';
                }

                el.style.background = '#222';
            }

            // === 触摸事件（移动端） ===
            el.addEventListener('touchstart', (e) => {
                inputType = 'touch';
                handleStart(e.touches[0].clientX, e.touches[0].clientY);
            });

            el.addEventListener('touchmove', (e) => {
                if (inputType !== 'touch' || e.touches.length !== 1) return;
                handleMove(e.touches[0].clientX, e.touches[0].clientY);
            });

            el.addEventListener('touchend', () => {
                if (inputType !== 'touch') return;
                handleEnd();
                inputType = null;
            });

            // === 鼠标事件（桌面端） ===
            el.addEventListener('mousedown', (e) => {
                e.preventDefault();
                // 混合设备保护：如果刚触发过 touch，忽略本次 mouse 事件
                if (inputType === 'touch') return;
                inputType = 'mouse';
                handleStart(e.clientX, e.clientY);
            });

            window.addEventListener('mousemove', (e) => {
                if (inputType !== 'mouse') return;
                handleMove(e.clientX, e.clientY);
            });

            window.addEventListener('mouseup', () => {
                if (inputType !== 'mouse') return;
                handleEnd();
                inputType = null;
            });

            el.addEventListener('contextmenu', (e) => e.preventDefault());
        }

        // 初始化两个触摸板
        setupTouchpad(document.getElementById('pad'));
        setupTouchpad(document.getElementById('pad2'));

        // 文件上传功能
        async function uploadFiles(files) {
            const status = document.getElementById('uploadStatus');
            const targetDir = document.getElementById('targetDir').value.trim() || '~/Downloads';

            if (!files || files.length === 0) return;

            status.textContent = '上传中...';
            status.style.color = '#fbbf24';

            const formData = new FormData();
            formData.append('target_dir', targetDir);
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }

            try {
                const r = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await r.json();
                if (r.ok) {
                    status.textContent = result.message || `成功上传 ${files.length} 个文件`;
                    status.style.color = '#4ade80';
                } else {
                    status.textContent = result.error || '上传失败';
                    status.style.color = '#f87171';
                }
            } catch (e) {
                status.textContent = '网络错误';
                status.style.color = '#f87171';
            }

            // 清空文件输入
            document.getElementById('fileInput').value = '';
        }

        // 3. Enter 键（鼠标区域右侧）
        const enterBtn = document.getElementById('enterBtn');
        enterBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            postData({ type: 'key', value: '28' }, true);
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

        # 处理文件上传
        if self.path == '/upload':
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "无效的请求格式"}).encode())
                return

            # 手动解析 multipart 数据（兼容 Python 3.13+，cgi 模块已移除）
            boundary = content_type.split('boundary=')[1].strip()
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            boundary_bytes = boundary.encode()

            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)

            # 按 boundary 分割
            parts = body.split(b'--' + boundary_bytes)
            target_dir = '~/Downloads'
            uploaded_files = []

            for part in parts:
                if not part or part.strip() == b'' or part.strip() == b'--':
                    continue
                # 去掉尾部的 \r\n
                if part.endswith(b'\r\n'):
                    part = part[:-2]

                # 分离 headers 和 body
                header_end = part.find(b'\r\n\r\n')
                if header_end == -1:
                    continue
                headers_raw = part[:header_end].decode('utf-8', errors='replace')
                file_body = part[header_end + 4:]

                # 提取 name 和 filename
                name = None
                filename = None
                for line in headers_raw.split('\r\n'):
                    if 'Content-Disposition:' in line:
                        for token in line.split(';'):
                            token = token.strip()
                            if token.startswith('name='):
                                name = token.split('=', 1)[1].strip('"')
                            if token.startswith('filename='):
                                filename = token.split('=', 1)[1].strip('"')

                if name == 'target_dir' and file_body:
                    target_dir = file_body.decode('utf-8', errors='replace').strip() or '~/Downloads'
                elif name == 'files' and filename:
                    safe_name = os.path.basename(filename)
                    if safe_name:
                        uploaded_files.append((safe_name, file_body))

            # 展开 ~ 路径
            target_dir = os.path.expanduser(target_dir)
            os.makedirs(target_dir, exist_ok=True)

            saved_names = []
            for name, data in uploaded_files:
                filepath = os.path.join(target_dir, name)
                with open(filepath, 'wb') as f:
                    f.write(data)
                saved_names.append(name)

            if saved_names:
                msg = f"成功上传 {len(saved_names)} 个文件到 {target_dir}"
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"message": msg, "files": saved_names}).encode())
            else:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "没有选择文件"}).encode())
            return

        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length).decode("utf-8")

        try:
            data = json.loads(body)
            data_type = data.get("type", "text")
            data_value = data.get("value", "")
            term_mode = data.get("term_mode", False)
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
            if term_mode and data_value == "104":
                # 终端模式: PgUp → Ctrl+Shift+PageUp (29+42+104)
                subprocess.run(["ydotool", "key", "-d", "20", "29:1", "42:1", "104:1", "104:0", "42:0", "29:0"], env=env)
            elif term_mode and data_value == "109":
                # 终端模式: PgDn → Ctrl+Shift+PageDown (29+42+109)
                subprocess.run(["ydotool", "key", "-d", "20", "29:1", "42:1", "109:1", "109:0", "42:0", "29:0"], env=env)
            else:
                subprocess.run(["ydotool", "key", f"{data_value}:1", f"{data_value}:0"], env=env)
        elif data_type == "key_combo" and data_value:
            # 格式: "42,3" 表示按住 42(Shift)，按 3(2)，然后释放
            codes = [int(c.strip()) for c in data_value.split(',')]
            yd_args = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
            subprocess.run(["ydotool", "key", "-d", "20"] + yd_args, env=env)
        elif data_type == "shortcut" and data_value:
            if data_value == "ctrl+a":
                subprocess.run(["ydotool", "key", "-d", "20", "29:1", "30:1", "30:0", "29:0"], env=env)
            elif data_value == "ctrl+z":
                subprocess.run(["ydotool", "key", "-d", "20", "29:1", "44:1", "44:0", "29:0"], env=env)
            elif data_value == "ctrl+c":
                if term_mode:
                    # 终端模式: Ctrl+Shift+C (29+42+46)
                    subprocess.run(["ydotool", "key", "-d", "20", "29:1", "42:1", "46:1", "46:0", "42:0", "29:0"], env=env)
                else:
                    subprocess.run(["ydotool", "key", "-d", "20", "29:1", "46:1", "46:0", "29:0"], env=env)
            elif data_value == "shift+insert":
                if term_mode:
                    # 终端模式: Ctrl+Shift+V (29+42+47)
                    subprocess.run(["ydotool", "key", "-d", "20", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"], env=env)
                else:
                    subprocess.run(["ydotool", "key", "-d", "20", "42:1", "110:1", "110:0", "42:0"], env=env)

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
