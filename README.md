# Remote Input

Ubuntu Wayland 环境下的手机远程输入工具。

手机浏览器打开网页，使用手机输入法（语音/拼音/手写）输入文字，点发送后自动粘贴到电脑当前光标位置。专为 Ubuntu 22+ Wayland 环境设计，不受 GNOME 沙箱限制。

## 仓库内容

```
remote_input_page/
├── remote_input.py    # 主程序（Python 标准库，零第三方依赖）
└── README.md
```

## 环境要求

- Ubuntu 22.04+（Wayland，GNOME 桌面），测试环境：Ubuntu 26.04
- Python 3（系统自带），测试版本：3.14
- 手机和电脑在同一局域网

已测试的依赖版本：
- `ydotool` 1.0.4（注意：1.x 版本使用 `mousemove` 命令，新版 1.1+ 改为 `pointer shift`）
- `wl-clipboard` 2.2.1

## 安装

### 1. 安装系统依赖

```bash
sudo apt install -y wl-clipboard ydotool
```

> **ydotool 版本兼容性**：本脚本自动适配 ydotool 1.x（`mousemove`）和 1.1+（`pointer shift`）两种命令格式。

### 2. 配置用户权限

```bash
sudo usermod -aG input $USER
```

执行后**重新登录**生效。

### 3. 启动 ydotoold 服务

```bash
systemctl --user enable --now ydotool
```

## 使用

### 启动服务

**强烈建议启用认证**，防止同一局域网下其他人误用或滥用：

```bash
# 自动生成随机 token（打印在终端）
python3 remote_input.py --auth

# 或指定自己的 token
python3 remote_input.py --auth --token your_password
```

不加 `--auth` 也可以直接使用，但局域网内任何人都能访问。

查看电脑局域网 IP：

```bash
ip -4 addr show | grep 'inet ' | grep -v '127.0.0.1'
```

### 手机访问

1. 手机连上和电脑同一个 Wi-Fi
2. 浏览器打开 `http://<电脑IP>:8080`
3. 如果启用了认证，先输入 Token 登录
4. 输入文字，点击"发送到电脑"

文字会出现在电脑当前光标位置（终端、浏览器、编辑器均适用）。

### 快捷键按钮

输入框下方提供 4 个快捷键按钮：

| 按键 | 功能 | ydotool 键码 |
|------|------|-------------|
| Enter | 回车 | 28 |
| Back | 退格 | 14 |
| 全选 | Ctrl+A | 29+30 |
| 撤销 | Ctrl+Z | 29+44 |

### 虚拟触摸板 & 鼠标左键

页面下方提供虚拟触摸板区域和左键单击按钮：

- **触摸板区域**：手指在灰色虚线区域内滑动，电脑光标会实时跟随移动。采用 40ms 节流（每秒 25 帧）避免请求风暴
- **左键单击**：红色大按钮，点击即可在电脑光标位置触发一次鼠标左键点击
- **右键单击**：在触摸板区域双指轻触即可触发鼠标右键
- 灵敏度系数默认 1.5 倍，可在 JS 中调整 `moveQueue.dx += dx * 1.5` 的倍数
- 触摸板使用 `touch-action: none` 防止滑动时页面跟随滚动

### 停止服务

终端按 `Ctrl+C`。

## 工作原理

1. 电脑运行 HTTP 服务，监听 8080 端口
2. 手机浏览器打开网页，输入文字
3. 点击发送后，文字通过 HTTP POST 传到电脑
4. 电脑执行 `wl-copy` 将文字写入剪贴板（CLIPBOARD + PRIMARY）
5. `ydotool` 通过 `/dev/uinput` 模拟 Shift+Insert 按键，触发粘贴

关键设计：
- `ydotool` 走内核接口注入按键，不受 Wayland 沙箱限制
- 同时写入 CLIPBOARD 和 PRIMARY 两个剪贴板，确保终端和浏览器都能正确粘贴
- 使用 Shift+Insert 而非 Ctrl+V，兼容终端和图形界面
- 按键事件间加 50ms 延迟，避免系统输入状态机不同步
- 支持快捷键注入（Enter、Backspace、Ctrl+A、Ctrl+z），通过 ydotool 直接模拟按键
- 支持虚拟触摸板：前端 40ms 节流合并坐标偏移，通过 `ydotool mousemove`（1.x）或 `ydotool pointer shift`（1.1+）实现平滑鼠标移动
- 支持鼠标单击：通过 `ydotool click` 模拟左键（`0:1`）或右键（`0:2`）
- 前后端通讯使用 JSON 格式，支持 `text`（文本）、`key`（单键）、`shortcut`（组合键）、`mouse_move`（鼠标移动）、`mouse_click`（鼠标点击）五种类型
- 可选登录认证：挑战-应答机制，token 在浏览器端 SHA-256 哈希后传输，不明文传输

## 常见问题

### 手机打不开网页

- 确认手机和电脑在同一 Wi-Fi
- 检查防火墙：`sudo ufw allow 8080`

### 粘贴没反应

- 检查 ydotoold 是否运行：`systemctl --user status ydotool`
- 确认用户在 input 组：`id -nG $USER | grep input`

### 中文粘贴为空

- 测试剪贴板：`echo "测试" | wl-copy && wl-paste`
- 如果 wl-paste 为空，重启 GNOME Shell（Alt+F2 输入 `r` 回车）

## 贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改
4. 推送到分支：`git push origin feature/your-feature`
5. 创建 Pull Request

如果发现了 Bug 或有功能建议，请先开 Issue 讨论。

## License

MIT
