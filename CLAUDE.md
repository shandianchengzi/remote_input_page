# Remote Input - Claude Code 工作流

## 开发流程

每次修改代码后，按以下顺序执行：

### 1. 修改代码

编辑 `remote_input.py`。

### 2. 重启服务

```bash
pkill -f "remote_input.py"
python3 remote_input.py --auth --token grey1234567 &
```

确认新进程启动成功：

```bash
ps aux | grep remote_input.py | grep -v grep
```

### 3. 提交并推送

```bash
git add remote_input.py README.md
git commit -m "描述性提交信息"
git push
```
