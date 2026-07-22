# FakeGPS v6.2.5 - iPhone 虚拟定位工具 | iOS GPS 模拟器

跨平台（macOS + Windows）iPhone 虚拟 GPS 定位工具。免越狱、无需 Xcode，通过 USB 为 iPhone 设置虚拟定位。

![macOS](https://img.shields.io/badge/macOS-FakeGPS.app-blue?logo=apple) ![Windows](https://img.shields.io/badge/Windows-FakeGPS.exe-blue?logo=windows) ![npm](https://img.shields.io/badge/npm-fakegps-red?logo=npm) ![License](https://img.shields.io/badge/license-MIT-green)
> **关键词**：iPhone 虚拟定位、iOS GPS 模拟器、免越狱改定位、fakegps、虚拟定位工具、macOS 虚拟定位、Windows 虚拟定位、GPX 轨迹模拟

## 功能特性

- **虚拟定位**：将 iPhone 定位修改到世界上任意位置
- **简约 GUI**：基于 pywebview 的黑白地图界面，高德瓦片 + Leaflet 渲染
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

> **Windows 用户注意**：FakeGPS 启动时会自动解除下载文件的锁定标记。如果弹出 SmartScreen 警告，点“更多信息” → “仍要运行”。程序启动时会请求一次管理员权限，用于 iOS 17+ 的 tunneld 隧道服务。

### 方式二：官网下载（推荐）

前往 [www.sixzjd.sbs](https://www.sixzjd.sbs) 下载 macOS 或 Windows 版本。

### 方式三：npm（macOS CLI 模式）

```bash
npm install -g fakegps
fakegps --cli
```

### 方式四：pip（需要 Python 3.9+）

```bash
pip install fakegps           # 仅 CLI
pip install fakegps[gui]      # 包含 GUI
```

### 方式五：源码运行

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

## 使用方式

> **先配置高德 AMap API Key（地点搜索必需）**
>
> 1. 打开 [高德开放平台控制台](https://console.amap.com/dev/key/app) 并注册/登录。
> 2. 创建应用，添加 **Web 服务** Key，复制 Key。
> 3. 打开 FakeGPS，在右侧 **AMap API Key** 输入并保存。
>
> 没有 Key 仍可直接点击地图或输入经纬度进行定位。

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

### fakeGPS 是什么？
fakeGPS 是一款跨平台（macOS + Windows）iPhone 虚拟定位工具，可以通过 USB 将 iPhone 的 GPS 定位修改到世界上任意位置。免越狱、无需 Xcode，支持 GUI 地图交互和 CLI 命令行两种模式。

### 使用 fakeGPS 需要越狱吗？
完全不需要。fakeGPS 基于 pymobiledevice3 协议与 iPhone 通信，不需要在 iPhone 上安装任何 App 或进行越狱操作。

### fakeGPS 支持哪些 iOS 版本？
支持 iOS 16 及以上版本。iOS 17+ 的 tunneld 隧道服务由 GUI 自动启动，首次启动时按系统提示授权即可。

### 如何安装 fakeGPS？
推荐从 [GitHub Releases](https://github.com/sixzjd/fakeGPS-for-iPhone/releases/latest) 下载可执行文件，解压即用。也支持 npm（`npm install -g fakegps`）、pip（`pip install fakegps`）和源码运行。

### 支持哪些城市的地标？
内置天安门、国贸CBD、望京SOHO、上海外滩、深圳市民中心、巴黎埃菲尔铁塔、纽约时代广场、东京塔、伦敦大本钟等 9 个全球地标，还支持自定义添加。


## 免责声明

本工具仅供学习和研究使用。使用者应遵守当地法律法规。使用本工具所产生的一切后果由使用者自行承担。

## License

MIT
