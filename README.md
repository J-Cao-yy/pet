# Betty Pet

一个以 Python/Tkinter 为基础的高自定义桌宠原型。当前支持透明置顶窗口、拖拽、右键菜单、缩放、随机动作、对话气泡和按 manifest 管理动画素材。

## 准备环境

```powershell
conda activate pic
conda env update -f environment.yml
python -m pip install -e .
```

桌宠运行核心依赖是 Pillow；`png_process.py` 需要 OpenCV 和 NumPy，`environment.yml` 已包含。Windows 可用 `python -m tkinter` 检查 Tkinter。

## 运行

```powershell
python main.py
python main.py --check-assets
python -m betty_pet --scale 1.25 --no-random
```

## 目录约定

```text
src/betty_pet/
  config.py       运行配置
  assets.py       素材清单和加载
  model.py        与界面无关的动作状态机
  window.py       Tkinter 窗口和交互
  __main__.py     CLI 入口
assets/           已处理、可直接使用的 PNG 和 manifest.json
input/            原始素材
output/           png_process.py 的处理结果
```

新增动作时，在 `assets/manifest.json` 增加动作名和 PNG 文件列表即可。后续可在此基础上增加设置持久化、换装图层、系统托盘、插件 API 和测试。

项目的当前边界、模块职责以及道具、记忆、情绪、本地大模型、行为调度和动画等扩展路线，见 [项目提炼与扩展路线](docs/PROJECT_DISTILLATION.md)。

素材缩放时会自动将半透明边缘转换为透明/不透明两级，避免 Windows Tkinter 的洋红透明色产生紫红色光晕。
