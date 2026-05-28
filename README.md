# FakeGPS v6.0 - iPhone 虚拟定位工具

跨平台（macOS + Windows）iPhone 虚拟 GPS 定位工具。免越狱、无需 Xcode，通过 USB 为 iPhone 设置虚拟定位。

## 功能特性

- **虚拟定位**：将 iPhone 定位修改到世界上任意位置
- **图形界面**：交互式地图，点击选点即设定（PyQt6 + Leaflet）
- **命令行模式**：完整的 CLI 交互式 REPL
- **地图选点**：高德地图点击选点，自动坐标转换
- **自定义地点**：添加常用位置为快捷命令
- **轨迹模拟**：支持 GPX 文件播放，模拟步行/驾车轨迹
- **坐标转换**：自动 GCJ-02（高德）→ WGS-84（GPS）坐标偏移
- **跨平台**：支持 macOS 和 Windows

## 环境要求

- Python 3.9+
- iPhone 通过 USB 连接（iOS 17+ 需要 tunneld）
- 图形界面模式（可选）：PyQt6 + PyQt6-WebEngine

## 安装

### pip（推荐）

```bash
# 仅命令行模式
pip install fakegps

# 包含图形界面
pip install fakegps[gui]
```

### 手动安装

```bash
git clone https://github.com/sixzjd/fakeGPS-for-iPhone.git
cd fakeGPS-for-iPhone
pip install -r requirements.txt

# 可选：安装图形界面
pip install PyQt6 PyQt6-WebEngine
```

## 快速开始

### 1. 启动隧道服务（iOS 17+ 必须）

在**另一个终端窗口**运行（保持不要关闭）：

```bash
# macOS
sudo python3 -m pymobiledevice3 remote tunneld

# Windows（以管理员身份运行）
python3 -m pymobiledevice3 remote tunneld
```

### 2. 图形界面模式（推荐）

```bash
fakegps --gui
# 或
python -m fakegps
```

图形界面功能：
- 交互式地图（点击选点）
- 设备状态显示
- 预设地点快捷按钮
- 手动输入坐标
- GPX 轨迹播放
- 一键恢复真实定位

### 3. 命令行模式

```bash
# 交互式 REPL
fakegps --cli
# 或
python -m fakegps --cli

# 直接执行命令
fakegps tiananmen        # 定位到天安门
fakegps set 39.9 116.3   # 设置坐标
fakegps clear            # 恢复真实定位
fakegps list             # 查看已连接设备
fakegps places           # 查看所有地点
fakegps play route.gpx   # 播放 GPX 轨迹
```

### 4. CLI 交互模式

```
fakegps> tiananmen           # 定位到天安门
fakegps> /set 39.9 116.3    # 设置坐标
fakegps> /map               # 打开图形界面
fakegps> /clear             # 恢复真实定位
fakegps> /places            # 查看所有地点
fakegps> /add myhome 39.9 116.3  # 添加自定义地点
fakegps> /remove myhome     # 删除自定义地点
fakegps> /play route.gpx    # 播放 GPX 轨迹
fakegps> /exit              # 退出
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

## 自定义地点管理

```bash
# 添加（坐标为高德坐标，自动转换为 WGS-84）
fakegps add myhome 39.9 116.3

# 使用
fakegps myhome

# 查看所有地点
fakegps places

# 删除
fakegps remove myhome
```

自定义地点保存在 `~/.fakegps_places`（JSON 格式）。

## 坐标系说明

中国境内地图存在坐标偏移问题：
- **高德/腾讯地图**：使用 GCJ-02 坐标系（有偏移）
- **iPhone GPS**：使用 WGS-84 坐标系（真实坐标）

本工具自动判断：
- **中国境内**：高德坐标 (GCJ-02) 自动转换为 GPS 坐标 (WGS-84)
- **中国境外**：直接使用原始坐标，无需转换

## Windows 说明

- 需要安装 [iTunes](https://www.apple.com/itunes/) 或 Microsoft Store 的 [Apple Devices](https://apps.microsoft.com/store/detail/apple-devices/9NP83LWLPZ9K) 以支持 USB 设备通信
- tunneld 需以管理员身份运行
- 图形界面需要安装 PyQt6：`pip install PyQt6 PyQt6-WebEngine`

## 常见问题

**Q: 提示 "No device found"（未找到设备）**
A: 用数据线连接 iPhone，在手机上点击"信任此电脑"并输入密码。

**Q: 提示 "tunneld not running"（iOS 17+）**
A: 在单独的终端窗口启动隧道服务：
```bash
# macOS
sudo python3 -m pymobiledevice3 remote tunneld
# Windows（以管理员身份运行）
python3 -m pymobiledevice3 remote tunneld
```

**Q: 定位不准确，有几百米偏差**
A: 确保使用 v6.0+ 版本，已包含坐标转换功能。

**Q: 拔掉数据线后定位恢复了**
A: 正常行为，虚拟定位需要保持 USB 连接。重启 iPhone 也会恢复真实定位。

## npm 包

https://www.npmjs.com/package/fakegps

## 免责声明

本工具仅供学习和研究使用。使用者应遵守当地法律法规，不得将其用于任何违法违规用途。使用本工具所产生的一切后果由使用者自行承担。

## License

MIT
