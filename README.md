# FakeGPS v6.0.1 - iPhone 虚拟定位工具

跨平台（macOS + Windows）iPhone 虚拟 GPS 定位工具。免越狱、无需 Xcode，通过 USB 为 iPhone 设置虚拟定位。

![macOS](https://img.shields.io/badge/macOS-FakeGPS.app-blue?logo=apple) ![Windows](https://img.shields.io/badge/Windows-FakeGPS.exe-blue?logo=windows) ![npm](https://img.shields.io/badge/npm-fakegps-red?logo=npm) ![License](https://img.shields.io/badge/license-MIT-green)

## 功能特性

- **虚拟定位**：将 iPhone 定位修改到世界上任意位置
- **暗色 GUI**：基于 pywebview 的深色地图界面，高德瓦片 + Leaflet 渲染
- **命令行模式**：完整的 CLI 交互式 REPL
- **地点搜索**：高德 API 关键词搜索，下拉框选结果
- **GPX 轨迹**：支持 GPX 文件播放，模拟步行/驾车轨迹
- **坐标转换**：自动 GCJ-02（高德）→ WGS-84（GPS）偏移
- **一键恢复**：随时恢复真实 GPS 定位
- **跨平台**：macOS（WebKit）+ Windows（Edge WebView2）

## 下载安装

### 方式一：下载可执行文件（推荐）

前往 [Releases](https://github.com/sixzjd/fakeGPS-for-iPhone/releases/latest) 下载最新版本。

| 平台 | 文件 | 说明 |
|------|------|------|
| macOS | `FakeGPS-macOS.zip` | 解压后双击 `FakeGPS.app` 运行 |
| Windows | `FakeGPS-Windows.zip` | 解压后双击 `FakeGPS.exe` 运行 |

不需要安装 Python 或任何依赖。

### 方式二：npm（macOS CLI 模式）

```bash
npm install -g fakegps
fakegps --cli
```

### 方式三：pip（需要 Python 3.9+）

```bash
pip install fakegps           # 仅 CLI
pip install fakegps[gui]      # 包含 GUI
```

### 方式四：源码运行

```bash
git clone https://github.com/sixzjd/fakeGPS-for-iPhone.git
cd fakeGPS-for-iPhone
pip install -r requirements.txt
python run_gui.py             # GUI 模式
python -m fakegps             # CLI 模式
```

## 环境要求

### iPhone 设置
- 用**数据线**连接（不能只充电的线）
- iPhone 上点**"信任此电脑"**并输入密码
- iOS 16+ 需开启**开发者模式**（设置 → 隐私与安全性 → 开发者模式）

### iOS 17+ 隧道服务

在**另一个终端**运行（保持不要关闭）：

```bash
# macOS
sudo python3 -m pymobiledevice3 remote tunneld

# Windows（以管理员身份运行命令提示符）
python3 -m pymobiledevice3 remote tunneld
```

> GUI 右侧面板有一键复制此命令的按钮。

## 使用方式

### 图形界面

```bash
fakegps --gui
# 或
python run_gui.py
```

- 交互式地图：点击地图选点，点 "Set Location" 即定位
- 高德 API 地点搜索（需配置 Key）
- 设备状态显示、预设地点快捷按钮
- GPX 轨迹播放、一键恢复真实定位

### 命令行

```bash
fakegps --cli               # 交互模式
fakegps tiananmen           # 定位到天安门
fakegps set 39.9 116.3      # 设置坐标
fakegps clear               # 恢复真实定位
fakegps list                # 查看设备
fakegps places              # 查看所有预设地点
```

## 内置地点

| 名称 | 坐标 (WGS-84) | 说明 |
|------|---------------|------|
| tiananmen | 39.90779, 116.39122 | 天安门 |
| guomao | 39.90727, 116.45877 | 国贸CBD |
| wangjing | 39.99271, 116.47673 | 望京SOHO |
| shanghai | 31.24050, 121.48621 | 上海外滩 |
| shenzhen | 22.54600, 114.05790 | 深圳市民中心 |
| paris | 48.8584, 2.2945 | 巴黎埃菲尔铁塔 |
| newyork | 40.7580, -73.9855 | 纽约时代广场 |
| tokyo | 35.6586, 139.7454 | 东京塔 |
| london | 51.5074, -0.1278 | 伦敦大本钟 |

## 搜索配置

搜索功能使用高德 API，需要配置 Key：

1. 访问 https://console.amap.com/dev/key/app 注册账号
2. 创建应用，获取 **Web 服务** API Key
3. 在 GUI 右侧面板 "AMap API Key" 区域输入 Key 并保存

没有 Key 也可以手动输入坐标或点击地图定位。

## Windows 说明

- 需要安装 [Apple Devices](https://apps.microsoft.com/store/detail/apple-devices/9NP83LWLPZ9K)（Apple 设备）
- tunneld 需以管理员身份运行
- 首次运行 exe 可能触发 SmartScreen 警告，点击"仍要运行"即可

## 技术栈

| 组件 | 说明 |
|------|------|
| [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) | iOS 设备通信（USB + tunneld） |
| [pywebview](https://pywebview.flowrl.com/) | 系统原生 WebView（WebKit / Edge WebView2） |
| [Leaflet](https://leafletjs.com/) | 开源地图渲染 |
| [高德地图](https://www.amap.com/) | 地图瓦片 + POI 搜索 |
| [PyInstaller](https://pyinstaller.org/) | 打包为独立可执行文件 |

## 构建

```bash
pip install pyinstaller
pyinstaller fakegps.spec --clean -y
# 产物在 dist/ 目录
```

macOS 产出 `FakeGPS.app`，Windows 产出 `FakeGPS/` 文件夹。

GitHub Actions 会在每次 Release 时自动构建 macOS + Windows 双平台产物并上传。

## 常见问题

**Q: 提示 "No device found"**
A: 检查数据线是否支持数据传输，iPhone 上是否点了"信任此电脑"。

**Q: 提示 "tunneld not running"（iOS 17+）**
A: 在单独终端启动：`sudo python3 -m pymobiledevice3 remote tunneld`

**Q: 设备名称显示 "Unknown"**
A: 某些设备在首次连接时可能未完全配对，尝试先运行一次 `ideviceinfo` 或重新插拔数据线。

**Q: 拔掉数据线后定位恢复了**
A: 正常行为，虚拟定位需要保持 USB 连接。

**Q: Windows SmartScreen 弹窗**
A: 这是 Windows 对未签名应用的正常提醒，点击"更多信息" → "仍要运行"。

## 免责声明

本工具仅供学习和研究使用。使用者应遵守当地法律法规。使用本工具所产生的一切后果由使用者自行承担。

## License

MIT
