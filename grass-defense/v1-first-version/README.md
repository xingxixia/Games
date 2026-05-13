# Grass Defense

这是一个使用 Python 和 pygame 制作的植物塔防小游戏第一版。

## 环境

- Python：3.10
- 当前示例：`pvz_pygame.py`
- 当前示例使用：`pygame`
- 旧版 tkinter 试验文件：`pvz_desktop.py`

## 安装依赖

PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

或者使用 Conda：

```powershell
conda env create -f environment.yml
conda activate gamedev310-local
```

## 运行游戏

```powershell
.\run_pvz.ps1
```

也可以直接运行：

```powershell
python pvz_pygame.py
```

打包后的 `GrassDefense.exe` 可以直接双击游玩。

## AI 测试接口

这个游戏可以导出给模型使用的观测包：

```powershell
python .\pvz_pygame.py --headless --actions .\example_ai_actions.json --simulate 1.0 --export-observation .\ai_observation.png --export-state .\ai_state.json --export-schema .\ai_action_schema.json
```

输出：

- `ai_observation.png`：给视觉模型看的当前游戏画面
- `ai_state.json`：给模型参考的结构化状态
- `ai_action_schema.json`：模型可用动作列表
- `ai_player_interface.md`：给模型/开发者看的玩法和动作说明

打包后的 exe 也支持同样接口，例如：

```powershell
.\GrassDefenseAI.exe --headless --actions .\example_ai_actions.json --simulate 1.0 --export-observation .\ai_observation.png --export-state .\ai_state.json --export-schema .\ai_action_schema.json
```

说明：

- `GrassDefense.exe`：双击游玩的窗口版
- `GrassDefenseAI.exe`：给 AI/脚本测试用的控制台版

## 建议学习路线

1. 先用 `tkinter` 或 `pygame` 学游戏循环、点击输入、碰撞检测、实体状态。
2. 做 3 个小项目：打砖块、塔防、俯视角移动射击。
3. 再考虑 Godot 或 Unity。Unity 更适合 3D、正式发布和 C# 工作流；Godot 更轻，适合 2D 入门。
