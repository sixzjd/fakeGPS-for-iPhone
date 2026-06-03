# FakeGPS v6.0 - iPhone 虚拟定位工具

跨平台（macOS + Windows）iPhone 虚拟 GPS 定位工具。免越狱、无需 Xcode，通过 USB 为 iPhone 设置虚拟定位。

## 功能特性

- **虚拟定位**：将 iPhone 定位修改到世界上任意位置
- **图形界面**：交互式地图，点击选点即定位（高德地图）
- **命令行模式**：完整的 CLI 交互式 REPL
- **地点搜索**：高德 API 搜索，下拉框显示结果
- **GPX 轨迹**：支持 GPX 文件播放，模拟步行/驾车轨迹
- **坐标转换**：自动 GCJ-02（高德）→ WGS-84（GPS）坐标偏移
- **跨平台**：支持 macOS 和 Windows

## 下载安装

### 方式一：下载可执行文件

| 平台 | 下载 | 说明 |
|------|------|------|
| macOS | [FakeGPS.app](../../releases/latest) | 双击即用 |
| Windows | [FakeGPS.exe](../../releases/latest) | 双击即用 |

下载后直接运行，不需要安装 Python 或任何依赖。

### 方式二：npm（macOS CLI 模式）

```bash
npm install -g fakegps
fakegps --cli
```

### 方式三：pip（需要 Python 3.9+）

```bash
# 仅 CLI
pip install fakegps

# 包含 GUI
pip install fakegps[gui]
```

### 方式四：GitHub 源码

```bash
git clone https://github.com/sixzjd/fakeGPS-for-iPhone.git
cd fakeGPS-for-iPhone
pip install -r requirements.txt
pip install PyQt6 PyQt6-WebEngine  # 可选：GUI 模式
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

# Windows（以管理员身份运行）
python3 -m pymobiledevice3 remote tunneld
```

## 使用方式

### 图形界面

```bash
fakegps --gui
# 或
python -m fakegps
```

功能：
- 交互式地图（点击选点即定位）
- 高德 API 地点搜索（需配置 Key）
- 设备状态显示
- 预设地点快捷按钮
- GPX 轨迹播放
- 一键恢复真实定位

### 命令行

```bash
# 交互模式
fakegps --cli

# 直接命令
fakegps tiananmen        # 定位到天安门
fakegps set 39.9 116.3   # 设置坐标
fakegps clear            # 恢复真实定位
fakegps list             # 查看设备
fakegps places           # 查看所有地点
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
3. 在 GUI 右侧面板输入 Key 并保存

没有 Key 也可以手动输入坐标定位。

## Windows 说明

- 需要安装 [Apple Devices](https://apps.microsoft.com/store/detail/apple-devices/9NP83LWLPZ9K)
- tunneld 需以管理员身份运行

## 常见问题

**Q: 提示 "No device found"**
A: 检查数据线是否支持数据传输，iPhone 上是否点了"信任此电脑"。

**Q: 提示 "tunneld not running"（iOS 17+）**
A: 在单独终端启动：`sudo python3 -m pymobiledevice3 remote tunneld`

**Q: 拔掉数据线后定位恢复了**
A: 正常行为，虚拟定位需要保持 USB 连接。

## 免责声明

本工具仅供学习和研究使用。使用者应遵守当地法律法规。使用本工具所产生的一切后果由使用者自行承担。

## License

MIT
