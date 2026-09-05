# Water Meter Barcode Reader

[![CI](https://github.com/icenturyw/water-meter-barcode-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/icenturyw/water-meter-barcode-reader/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

> 水表表号批量识别工具：从手机拍摄的水表照片中批量解码条码表号，集中复核异常，并导出 Excel / CSV。

这是一个面向 Windows 的本地离线桌面工具。程序使用 ZXing-C++ 解码照片中的条码，通过“纯数字、固定长度、固定前缀”等规则筛选表号，并把未识别、多码、规则不符和重复记录集中交给人工复核。

整个识别过程在本机完成，不需要上传照片，也不会修改、移动或删除原图。

## 功能特点

- 批量选择照片文件夹，也可追加单张或多张照片
- 支持 JPG、JPEG、PNG、BMP、TIFF、WebP
- 自动处理 EXIF 方向
- 支持 ZXing-C++ 可解码的一维码和二维码，水表场景主要使用 Code 128
- 可配置表号规则：纯数字、精确位数、固定前缀
- 自动区分“自动通过、待复核、未识别、人工确认”
- 对普通识别失败的照片尝试灰度化、对比度增强、锐化、放大和小角度纠偏
- v1.0.1 增加困难照片兜底：局部切片、背景归一化和细角度纠偏
- 困难图像只有在同一候选结果被重复解码后才自动接受，优先降低误识别风险
- 在原图预览中显示条码区域，支持人工修改和确认
- 标记跨照片重复表号，不静默删除重复项
- 导出 XLSX 或 UTF-8-SIG CSV
- XLSX 中表号按文本保存，保留前导零
- 导出的 XLSX 同时包含“全部结果”和“待复核及异常”两个工作表

## 适用场景

- 水表到货验收
- 批量表号采集
- 换表施工前后表号整理
- 箱号 / 批次与表号对应关系整理
- 从现场照片快速生成表号 Excel 清单

本项目当前只负责**条码表号解码**，不识别液晶屏读数，也不使用 OCR 自动读取条码下方的印刷数字。

## 运行环境

- Windows x64
- Python 3.11–3.13 x64
- Python 安装需包含 Tcl/Tk

主要依赖：

- `zxing-cpp`：条码解码
- `Pillow`：图片读取和预处理
- `openpyxl`：XLSX 导出
- `tkinter`：桌面 GUI
- `PyInstaller`：Windows 发行包构建

## 本地开发

创建虚拟环境：

```powershell
py -3.13 -m venv .venv
```

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动程序：

```powershell
.\.venv\Scripts\python.exe app.py
```

## 命令行自检

可以直接识别一张图片并输出 JSON，便于排查某张照片是否能够被正常解码：

```powershell
.\.venv\Scripts\python.exe app.py --self-test "D:\照片\水表001.jpg" --length 14
```

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖：

- Code 128 正常解码
- 前导零保留
- 表号规则校验
- 倾斜照片识别
- 困难图像兜底
- 中文路径和子目录扫描
- 重复表号标记
- XLSX 文本格式导出

## 构建 Windows 发行包

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

构建脚本会生成两个版本：

```text
dist\
├── onedir\
│   └── 水表表号批量识别工具\
└── onefile\
    └── 水表表号批量识别工具.exe
```

- `onedir`：目录版，启动更快、兼容性更稳，建议作为默认发行包
- `onefile`：单文件版，方便分发，但每次启动需要临时解包

两个版本均会捆绑 Python、Tk、条码库和 Excel 库，目标电脑无需安装 Python，也无需联网。

构建脚本还会自动收集主要第三方依赖许可证，并随发行包分发。

## 使用流程

1. 将手机拍摄的水表照片按批次或箱号保存到电脑
2. 打开程序，填写批次 / 箱号
3. 选择照片文件夹
4. 根据实际表号设置位数、前缀等规则
5. 点击“开始识别”
6. 使用“只看异常”集中处理待复核、未识别和重复记录
7. 人工确认或修改异常表号
8. 导出 Excel / CSV

详细拍照规范和现场操作说明见 [`使用说明.txt`](使用说明.txt)。

## 拍照建议

- 推荐一表一图
- 条码必须完整入镜，并保留左右空白
- 条码区域尽量占照片宽度 60% 以上
- 拍照前点按条码区域完成对焦
- 尽量正对条码拍摄，减少透视和旋转
- 避免强反光、阴影、污渍和手抖
- 尽量传输原图，不要使用经过聊天软件压缩的图片

图像增强可以改善部分轻度倾斜、对比度不足或轻微模糊的照片，但无法恢复已经丢失的条纹细节。正式批量使用前建议先用 20–50 张现场照片验收识别效果。

## 项目结构

```text
.
├── app.py                    # Tkinter GUI、任务调度和交互逻辑
├── core.py                   # 条码识别、规则校验、重复检测和导出
├── tests/
│   └── test_core.py          # 核心功能自动化测试
├── build.ps1                 # PyInstaller Windows 构建脚本
├── requirements.txt          # 固定版本依赖
├── THIRD_PARTY_NOTICES.txt   # 第三方组件说明
├── 使用说明.txt               # 面向最终用户的操作手册
└── README.md
```

## 隐私与数据安全

- 不上传照片或表号
- 不依赖云端 OCR / API
- 不自动修改、移动、重命名或删除原照片
- 用户需要自行保管原照片和导出的 Excel / CSV

## 已知限制

- 当前不直接支持 HEIC / HEIF，建议先转为 JPG
- 当前不识别水表液晶屏读数
- 当前不做印刷数字 OCR 校验
- 严重失焦、手抖、过曝、反光或条码残缺的照片仍需要重拍
- 默认表号规则为 14 位纯数字，实际项目规则不同时需要在界面中调整

## 版本

当前版本：`v1.0.1`

版本变化见 [`CHANGELOG.md`](CHANGELOG.md)。

## License

当前仓库暂未声明开源许可证。在正式公开发布前，请根据代码归属和使用范围选择合适的许可证。

