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

- Ubuntu 22.04+（Wayland，GNOME 桌面）
- Python 3（系统自带）
- 手机和电脑在同一局域网

## 安装

### 1. 安装系统依赖

```bash
sudo apt install -y wl-clipboard ydotool
```

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
- 可选登录认证：token 在浏览器端 SHA-256 哈希后传输，不明文传输

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
