# 中文部署说明

本文档说明在**当前代码状态**下，如何从零拉起项目，以及如何配置：

- Django 后端
- React 前端
- 同花顺交易接入
- Futu 港股实盘接入
- 每日拉取任务

适用对象：

- 首次拉取仓库的新机器
- 需要联调同花顺或 Futu 的本地环境
- 需要在当前项目基础上快速恢复运行的人

## 1. 环境要求

### 基础依赖

- Git
- Miniconda 或 Anaconda
- Node.js `24.x`
- npm `11.x`

### 可选外部依赖

- Redis
  用于 Celery 异步任务和定时任务
- 同花顺客户端
  用于 A 股交易数据拉取
- Futu OpenD
  用于富途港股实盘订单与费用拉取

## 2. 拉代码

```bash
git clone <你的仓库地址>
cd stockagent-platform
```

## 3. 创建 Python 环境

使用仓库自带的 `environment.yml`：

```bash
conda env create -f environment.yml
conda activate stock-trading-analysis
```

如果环境已经存在，更新它：

```bash
conda env update -f environment.yml --prune
conda activate stock-trading-analysis
```

## 4. 初始化本地配置

复制环境变量模板：

```bash
cp .env.example .env
```

至少需要确认这些基础项：

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
REDIS_URL=redis://127.0.0.1:6379/0
```

## 5. 初始化数据库

当前默认使用 SQLite，本地最简单：

```bash
python stock_trading/manage.py migrate
```

创建管理后台账号：

```bash
python stock_trading/manage.py createsuperuser
```

## 6. 启动后端

```bash
python stock_trading/manage.py runserver
```

默认地址：

- 后端 API: `http://127.0.0.1:8000/`
- Django Admin: `http://127.0.0.1:8000/admin/`

### 6.1 首次登录前必须创建 Django 账户

当前前端不是匿名访问模式，页面数据默认都通过 JWT 调用后端受保护接口。

因此在首次打开前端前，你必须先在本地创建一个 Django 用户：

```bash
python stock_trading/manage.py createsuperuser
```

或者创建普通用户也可以，只要该用户能通过 `/api/auth/token/` 获取 JWT。

如果你没有先创建本地 Django 账户，前端登录页即使填写了用户名和密码，也无法成功换取令牌。

推荐做法：

1. 先执行 `python stock_trading/manage.py createsuperuser`
2. 再启动后端
3. 再启动前端
4. 在登录页填写你刚创建的 Django 用户名和密码
5. 点击“登录并获取令牌”

本地开发时：

- 接口基础地址可以留空
- 不需要手动填写访问令牌或刷新令牌
- 页面会自动调用 `/api/auth/token/` 获取 JWT

## 7. 启动前端

打开第二个终端：

```bash
cd frontend
npm ci
npm run dev
```

默认地址：

- 前端: `http://127.0.0.1:5173/`

## 8. 同花顺账户配置

当前项目中的同花顺接入用于 **A 股交易拉取**。

### 8.1 Windows 模式

这是最传统的模式，依赖同花顺下单客户端和 `easytrader`。

`.env` 中主要配置：

```env
THS_BACKEND=windows_easytrader
THS_EXE_PATH=C:\path\to\xiadan.exe
THS_CLIENT_TYPE=ths
THS_BRIDGE_PYTHON=C:\Users\your-user\AppData\Local\Programs\Python\Python38-32\python.exe
THS_WINDOW_TITLE_KEYWORD=股票交易系统
THS_FETCH_HOUR=16
THS_FETCH_MINUTE=10
```

说明：

- `THS_EXE_PATH`
  指向同花顺下单客户端可执行文件
- `THS_BRIDGE_PYTHON`
  指向能运行同花顺 bridge 的 Python，通常是 Windows 侧 32 位 Python
- `THS_WINDOW_TITLE_KEYWORD`
  用于桌面窗口定位，默认 `股票交易系统`

### 8.2 macOS 本地缓存模式

当前项目也支持通过同花顺 macOS 本地缓存日志重建交易数据。

`.env` 中主要配置：

```env
THS_BACKEND=macos_ths_local
THS_MAC_APP_PATH=/Applications/同花顺.app
THS_MAC_CONTAINER_PATH=~/Library/Containers/cn.com.10jqka.macstock
THS_MAC_LOG_GLOB=Data/Documents/cifox_trade*.log,Data/Library/Caches/HXLogger/TradeRelativeLog/*.log
THS_MAC_REQUIRE_APP_RUNNING=False
THS_FETCH_HOUR=16
THS_FETCH_MINUTE=10
```

说明：

- `THS_MAC_APP_PATH`
  同花顺 macOS App 路径
- `THS_MAC_CONTAINER_PATH`
  同花顺容器目录
- `THS_MAC_LOG_GLOB`
  交易缓存日志定位规则

### 8.3 同花顺联调验证

先执行 dry-run：

```bash
python stock_trading/manage.py fetch_ths_trades_now --dry-run --json
```

如果能看到标准化交易记录，再执行正式落库：

```bash
python stock_trading/manage.py fetch_ths_trades_now
```

同步持仓快照：

```bash
python stock_trading/manage.py sync_ths_positions_now --dry-run
python stock_trading/manage.py sync_ths_positions_now
```

## 9. Futu 账户配置

当前项目中的 Futu 接入用于 **港股实盘账户订单级交易拉取**。

### 9.1 前置条件

你需要准备：

- 一个 **富途港股实盘账户**
- 机器上已安装并启动 **Futu OpenD**
- OpenD 已登录你的富途账户
- 账户里最好有最近 `1-90` 天内的真实成交订单

### 9.2 必填配置

`.env` 中至少配置：

```env
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
FUTU_ACC_ID=123456789
```

推荐同时配置：

```env
FUTU_SECURITY_FIRM=FUTUSECURITIES
FUTU_MARKET=HK
FUTU_FETCH_HOUR=18
FUTU_FETCH_MINUTE=35
```

说明：

- `FUTU_HOST`
  OpenD 地址，通常是 `127.0.0.1`
- `FUTU_PORT`
  OpenD 端口，通常是 `11111`
- `FUTU_ACC_ID`
  富途真实账户 ID，当前代码按它锁定目标账户
- `FUTU_SECURITY_FIRM`
  当前默认建议使用 `FUTUSECURITIES`

### 9.3 如何找到 `FUTU_ACC_ID`

最简单的方法是用 OpenD / `py-futu-api` 查询 `get_acc_list()`。

你也可以在你自己的调试脚本里打印账户列表，确认：

- `acc_id`
- `trd_env=REAL`
- 包含 `HK` 交易权限

### 9.4 富途费用说明

当前代码采用：

- `commission`
- `stamp_duty`
- `other_fees`
- `fee_details`

其中：

- `commission`
  存佣金
- `stamp_duty`
  存印花税
- `other_fees`
  存平台费、交收费、交易费、证监会征费、财汇局征费等其它费用
- `fee_details`
  保留券商原始费用明细

注意：

- 示例费用只能用于说明映射逻辑
- 不同账户套餐、活动、产品类型会导致实际收费不同
- 真实对账时请以 Futu 返回的 `fee_details` 为准

### 9.5 Futu 联调验证

先 dry-run，看能否拉到订单和费用：

```bash
python stock_trading/manage.py fetch_futu_trades_now --dry-run --json
```

如果需要拉更长时间窗口：

```bash
python stock_trading/manage.py fetch_futu_trades_now --dry-run --json --since-days 30
```

如果 dry-run 正常，再正式落库：

```bash
python stock_trading/manage.py fetch_futu_trades_now
```

## 10. 汇丰邮件账户配置

当前项目中的 HSBC 接入用于 **港股邮件交易确认拉取**。

`.env` 中主要配置：

```env
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USERNAME=your-email@example.com
IMAP_PASSWORD=your-app-password
IMAP_MAILBOX=INBOX
IMAP_SENDER_KEYWORD=HSBC@notification.hsbc.com.hk
IMAP_SENDER_FILTERS=HSBC@notification.hsbc.com.hk
IMAP_SUBJECT_INCLUDE_KEYWORDS=全部執行,全部取消
IMAP_SUBJECT_EXCLUDE_KEYWORDS=登入通知,Login Notification
HSBC_FETCH_HOUR=18
HSBC_FETCH_MINUTE=30
```

先验证连接：

```bash
python stock_trading/manage.py fetch_hsbc_email_trades_now --test-connection
```

然后 dry-run：

```bash
python stock_trading/manage.py fetch_hsbc_email_trades_now --dry-run --json
```

## 11. 每日任务与调度

### 11.1 一次性执行全部交易拉取

```bash
python stock_trading/manage.py run_daily_ingestion_now
```

当前会执行：

- THS A 股交易拉取
- HSBC 港股邮件拉取
- Futu 港股订单拉取
- 市场快照刷新

### 11.2 Celery

启动 worker：

```bash
celery -A stock_trading.config worker -l info
```

启动 beat：

```bash
celery -A stock_trading.config beat -l info
```

当前默认定时：

- THS: `16:10`
- HSBC: `18:30`
- Futu: `18:35`
- 新闻摘要: `18:35`

### 11.3 港股交易日判断

当前代码里：

- THS 走 A 股交易日
- HSBC 和 Futu 走港股交易日

如果配置了：

```env
TUSHARE_TOKEN=your-tushare-token
```

则会优先用 Tushare 交易日历。  
如果没有配置，则会退化为“工作日近似判断”，节假日精度会降低。

## 12. 常用验证命令

### 后端检查

```bash
python stock_trading/manage.py check
```

### 核心测试

```bash
python -m pytest stock_trading/trades/tests -v
python -m pytest tests/test_trading_calendar.py -v
```

### 查看当前任务状态 API

登录后访问：

```text
/api/status/operations/
```

### 运行单个操作

可用动作包括：

- `run-ths`
- `run-hsbc`
- `run-futu`
- `run-daily`
- `sync-ths-positions`

## 13. 常见问题

### Futu 拉不到数据

优先检查：

- OpenD 是否已启动
- OpenD 是否已登录
- `FUTU_ACC_ID` 是否正确
- 是否为港股实盘账户
- 最近是否真的有成交订单

### 同花顺拉不到数据

优先检查：

- `THS_BACKEND` 是否和当前机器模式一致
- Windows 模式下 `THS_EXE_PATH` / `THS_BRIDGE_PYTHON` 是否正确
- macOS 模式下容器目录和日志路径是否正确

### 汇丰拉不到邮件

优先检查：

- IMAP 登录是否正常
- 邮箱是否允许第三方客户端 / 应用专用密码
- 发件人过滤是否过窄

## 14. 推荐部署顺序

建议按这个顺序做：

1. 拉代码
2. 创建 Conda 环境
3. 复制 `.env.example` 到 `.env`
4. `migrate`
5. 启动 Django
6. 启动前端
7. 先验证 THS / HSBC / Futu 的 dry-run
8. 再接 Celery 或系统定时任务

这样最容易排查问题，也最不容易把“环境问题”和“账户问题”混在一起。
