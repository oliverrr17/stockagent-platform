# 股票交易分析平台开发基线

## 1. 文档目的

本文件基于以下三份源文档整理而成，作为项目后续实现、评审、测试和迭代的统一开发基线：

- `D:\stock-trading-analysis\requirements.md`
- `D:\stock-trading-analysis\design.md`
- `D:\stock-trading-analysis\tasks.md`

本基线文档的目标是：

- 统一业务目标、系统边界与术语
- 固化首版技术选型与架构分层
- 明确核心数据模型、模块职责和关键接口
- 将原始任务拆解为可执行的交付阶段
- 固化测试策略、正确性属性和默认验收口径

后续若实现与本基线冲突，应优先更新本基线后再继续开发。

## 2. 项目目标与范围

### 2.1 产品目标

构建一个面向个人投资者的股票交易分析平台，覆盖 A 股与港股两类市场，支持：

- 自动采集交易记录
- 自动维护持仓与成本
- 基于量能、筹码、趋势进行交易复盘
- 抓取持仓相关公告与新闻
- 将重要信息推送给用户

### 2.2 首期范围

首期实现以下闭环能力：

1. A 股交易记录从同花顺侧采集
2. 港股交易记录从汇丰交易确认邮件采集
3. 交易记录统一入库并去重
4. 持仓自动更新，支持手动录入初始持仓
5. 港股基于交易记录计算持仓成本、已实现盈亏、未实现盈亏
6. 对单笔交易生成复盘报告
7. 抓取持仓相关新闻并按规则推送
8. 提供后端 API 和前端页面

### 2.3 非目标

首期不纳入以下内容：

- 实盘下单
- 多用户/多租户复杂权限体系
- 高并发分布式架构优化
- 回测系统
- AI 自动交易决策

## 3. 业务对象与术语

项目核心业务对象如下：

- `Trading_System`：整个平台
- `Trade_Recorder`：交易记录统一接入与存储模块
- `THS_Connector`：A 股交易记录采集连接器
- `Email_Crawler`：汇丰邮件采集与解析模块
- `TradeRecord`：标准交易记录
- `Portfolio` / `Position`：当前持仓
- `PositionEntry`：手动录入的初始持仓
- `Cost_Calculator`：港股成本与盈亏计算模块
- `Review_Engine`：复盘引擎
- `Volume_Analyzer` / `Chip_Analyzer` / `Trend_Analyzer`：三个分析器
- `ReviewReport`：复盘报告
- `News_Crawler`：新闻抓取模块
- `Notification_Service`：通知推送模块
- `NewsItem`：新闻实体
- `NotificationLog`：通知投递记录

## 4. 业务能力基线

### 4.1 交易记录采集

#### A 股

- 用户配置同花顺凭证后，可拉取交易记录
- 系统按日轮询获取新增记录
- 新记录统一转换为标准 `TradeRecord`
- 相同记录重复拉取时必须跳过，不产生重复数据
- 连接失败时记录日志并在下一周期重试

#### 港股

- 用户配置邮箱 IMAP 凭证后，可筛选汇丰交易确认邮件
- 系统按日轮询邮箱中的新邮件
- 解析邮件提取股票代码、名称、方向、价格、数量、交易时间
- 支持中文和英文邮件模板
- 解析失败时记录原始邮件内容并通知用户人工检查
- 重复记录必须跳过

#### 邮件解析器往返能力

- `TradeRecord -> 格式化文本 -> 重新解析` 后应得到语义等价结果

### 4.2 持仓与成本

- 支持手动录入初始持仓
- 录入时验证股票代码有效性
- 买入交易会增加持仓或创建持仓
- 卖出交易会减少持仓
- 数量降为 0 时标记为 `CLEARED`，保留历史
- 区分 A 股与港股
- A 股与港股按各自币种展示盈亏

#### 港股成本盈亏要求

- 采用加权平均成本法
- 成本计算需计入佣金、印花税、交易征费、交收费等费用
- 卖出交易会累计 `Realized_PnL`
- 行情接口用于计算 `Unrealized_PnL`
- 支持查看单只股票的历史交易与逐笔盈亏
- 满足盈亏平衡校验公式

### 4.3 交易复盘

- 用户选择一条交易记录后，系统依次执行：
  - 量能分析
  - 筹码分析
  - 趋势分析
- 最终生成 `ReviewReport`
- 报告至少包含：
  - 三类分析结果
  - 0 到 100 的综合评分
  - 改进建议
- 报告需持久化并关联到交易记录

#### 量能分析

- 获取交易日前后各 20 个交易日的成交量数据
- 计算相对 5/10/20 日均量的比值
- 识别放量、缩量
- 识别量价配合模式

#### 筹码分析

- 获取交易日筹码分布数据
- 计算 90% 筹码价格区间宽度与当前价格比值
- 判定价格位置：套牢区、获利区、密集成交区
- 观察交易日前后筹码变化

#### 趋势分析

- 获取交易日前后各 60 个交易日 K 线
- 计算 MA5、MA10、MA20、MA60
- 计算 MACD、RSI、KDJ
- 识别趋势阶段
- 识别关键支撑位与压力位

### 4.4 新闻与通知

- 按日或按配置周期抓取持仓相关新闻
- A 股优先来源：东方财富、新浪财经
- 港股优先来源：港交所披露易、阿斯达克财经
- 标题 + 来源 去重
- 分类为公告、舆情、研报、行业动态
- 重要新闻触发通知
- 公告类尽量在 5 分钟内推送
- 非交易时段，非紧急新闻可汇总推送
- 推送消息必须包含标题、来源、摘要和原文链接
- 推送失败时 10 分钟后重试，最多 3 次

## 5. 技术架构基线

### 5.1 技术选型

- 后端：`Python + Django 4.2+ + Django REST Framework`
- 异步任务：`Celery + Redis`
- 数据库：`PostgreSQL`
- 前端：`React 18 + TypeScript + Ant Design`
- 图表：`ECharts` 或 `Recharts`
- 邮件解析：Python 内置 `imaplib` + `email`
- 技术指标：`ta-lib` 或 `pandas-ta`
- 认证：`JWT`
- 通知：首选 `Telegram Bot`

### 5.2 架构分层

- 前端层：页面、组件、交互、图表
- API 层：DRF ViewSets / serializers / auth
- 业务逻辑层：交易、持仓、成本、复盘、新闻、通知等 services
- 数据采集层：同花顺连接器、邮件爬虫、新闻爬虫
- 异步任务层：定时轮询、抓取、推送
- 数据层：PostgreSQL、Redis、第三方行情 API

### 5.3 数据流

1. 定时任务触发交易采集
2. 采集结果经 `Trade_Recorder` 标准化和去重后入库
3. 入库后触发持仓更新与港股成本更新
4. 用户发起复盘时，`Review_Engine` 调用三个分析器生成报告
5. 定时任务触发新闻抓取
6. 抓到的新新闻经去重、分类和规则判断后推送

## 6. 默认项目结构

```text
stock_trading/
├── config/
├── trades/
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── tasks.py
│   └── services/
│       ├── ths_connector.py
│       ├── email_crawler.py
│       └── trade_recorder.py
├── portfolio/
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── services/
│       ├── portfolio_manager.py
│       └── cost_calculator.py
├── analysis/
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   └── services/
│       ├── volume_analyzer.py
│       ├── chip_analyzer.py
│       ├── trend_analyzer.py
│       └── review_engine.py
├── news/
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── tasks.py
│   └── services/
│       ├── news_crawler.py
│       └── notification_service.py
├── tests/
│   └── property/
└── frontend/
    └── src/
```

## 7. 数据模型基线

### 7.1 `TradeRecord`

关键字段：

- `stock_code`
- `stock_name`
- `market`: `A_STOCK | HK_STOCK`
- `direction`: `BUY | SELL`
- `price`
- `quantity`
- `commission`
- `stamp_duty`
- `other_fees`
- `trade_time`
- `source`: `THS | HSBC_EMAIL | MANUAL`
- `created_at`

约束：

- 去重唯一键：`stock_code + trade_time + direction + quantity + price`

### 7.2 `Position`

关键字段：

- `stock_code`
- `stock_name`
- `market`
- `quantity`
- `cost_price`
- `weighted_avg_cost`
- `total_invested`
- `realized_pnl`
- `status`: `ACTIVE | CLEARED`
- `created_at`
- `updated_at`

### 7.3 `PositionEntry`

关键字段：

- `stock_code`
- `stock_name`
- `market`
- `quantity`
- `cost_price`
- `entry_time`

### 7.4 `ReviewReport`

关键字段：

- `trade_record`
- `volume_analysis`
- `chip_analysis`
- `trend_analysis`
- `score`
- `suggestions`
- `created_at`

### 7.5 `NewsItem`

关键字段：

- `stock_code`
- `title`
- `source`
- `category`: `ANNOUNCEMENT | SENTIMENT | RESEARCH | INDUSTRY`
- `summary`
- `url`
- `pushed`
- `published_at`
- `created_at`

约束：

- 去重唯一键：`title + source`

### 7.6 `NotificationLog`

关键字段：

- `news_item`
- `channel`: `TELEGRAM | WECHAT | EMAIL`
- `status`: `SUCCESS | FAILED | PENDING`
- `retry_count`
- `sent_at`

## 8. 模块职责基线

### 8.1 `THSConnector`

职责：

- 测试同花顺连接
- 拉取指定时间段交易记录

建议接口：

```python
class THSConnector:
    def __init__(self, config: dict): ...
    def fetch_trade_records(self, start_date, end_date) -> list[dict]: ...
    def test_connection(self) -> bool: ...
```

### 8.2 `EmailCrawler`

职责：

- 连接 IMAP 邮箱
- 拉取汇丰交易确认邮件
- 解析中英文模板
- 输出格式化文本用于人工核验与往返测试

建议接口：

```python
class EmailCrawler:
    def __init__(self, config: dict): ...
    def connect(self) -> None: ...
    def fetch_hsbc_emails(self, since_date) -> list: ...
    def parse_trade_email(self, email) -> object: ...
    def format_trade_record(self, record) -> str: ...
```

### 8.3 `TradeRecorder`

职责：

- 标准化交易记录写入
- 去重判断
- 查询交易记录
- 触发持仓和成本联动更新

### 8.4 `PortfolioManager`

职责：

- 手动录入持仓
- 更新已有持仓
- 应用交易记录变更持仓
- 获取活跃持仓和股票代码列表

### 8.5 `CostCalculator`

职责：

- 计算加权平均成本
- 计算已实现盈亏
- 计算未实现盈亏
- 聚合港股持仓统计
- 提供交易历史与逐笔盈亏视图

### 8.6 `VolumeAnalyzer`

职责：

- 计算量比
- 判断放量、缩量
- 判断量价关系模式

### 8.7 `ChipAnalyzer`

职责：

- 计算筹码集中度
- 判断价格在筹码分布中的位置
- 评估筹码变化趋势

### 8.8 `TrendAnalyzer`

职责：

- 计算均线
- 计算技术指标
- 判断趋势阶段
- 寻找支撑与压力位

### 8.9 `ReviewEngine`

职责：

- 协调三类分析器
- 计算综合评分
- 生成建议
- 持久化复盘报告

### 8.10 `NewsCrawler`

职责：

- 按市场抓取新闻
- 去重
- 分类

### 8.11 `NotificationService`

职责：

- 判断是否推送
- 发送即时推送
- 发送汇总推送
- 判断交易时段

## 9. API 基线

首版 API 以 REST 风格为主。

### 9.1 交易

- `TradeRecordViewSet`
- 支持按 `market`、`direction`、`stock_code` 过滤
- 支持按 `trade_time`、`created_at` 排序

### 9.2 持仓

- `PositionViewSet`
- 提供 `active` action 获取活跃持仓
- 提供手动录入持仓能力

### 9.3 港股统计

- `HKStockStatsViewSet`
- 提供单只股票交易历史查询

### 9.4 复盘

- `ReviewViewSet`
- 提供 `generate` action 触发复盘报告生成

### 9.5 新闻

- `NewsItemViewSet`
- 支持按 `stock_code`、`category` 过滤

## 10. 异步任务基线

默认使用 Celery Beat 驱动。

### 10.1 交易采集任务

- `fetch_ths_trades`
- `fetch_hsbc_email_trades`

默认建议：

- A 股：每日收盘后采集
- 港股邮件：每日傍晚采集

### 10.2 新闻与通知任务

- `crawl_portfolio_news`
- `push_notification`

默认建议：

- 每日 `08:30`、`12:30`、`17:30` 抓取新闻

## 11. 正确性属性基线

以下属性必须在测试中显式覆盖：

1. 交易记录去重幂等性
2. 邮件解析/格式化往返一致性
3. 量能比值与量价模式计算正确性
4. 筹码集中度与价格位置分类正确性
5. 均线与技术指标计算正确性
6. 复盘评分范围不变量
7. 新闻去重不变量
8. 通知消息字段完整性
9. 交易驱动的持仓数量更新正确性
10. 港股加权平均成本计算正确性
11. 港股已实现盈亏计算正确性
12. 港股盈亏平衡恒等式

## 12. 测试策略基线

### 12.1 测试分层

- 单元测试：验证具体规则、边界和错误处理
- 属性测试：验证数学与状态不变量
- 集成测试：验证外部依赖 mock 与服务联动
- API 测试：验证 DRF 端点行为
- 前端测试：验证关键页面与组件

### 12.2 默认测试工具

- Python 测试框架：`pytest`
- 属性测试：`hypothesis`
- Django API 测试：`APITestCase` 或 pytest + DRF 测试工具
- Celery 测试：`CELERY_ALWAYS_EAGER=True`

### 12.3 属性测试约束

- 每个属性测试最少 100 次迭代
- 每个属性测试标注对应 Property 编号
- 失败时应能快速定位到对应需求与模块

### 12.4 重点单元测试

- 中英文邮件模板解析
- 同花顺连接失败处理
- 邮件解析失败通知逻辑
- 支撑位/压力位识别
- 非交易时段新闻汇总推送
- 推送失败重试
- 手动录入初始持仓成本设置
- 股票代码有效性校验

## 13. 错误处理基线

### 13.1 数据采集层

- 外部连接失败时记录日志
- 下一轮询周期自动重试
- 邮件解析失败时保留原始内容
- 单一新闻源失败不阻塞其他来源

### 13.2 业务逻辑层

- 行情数据缺失时允许返回部分分析结果，但必须标明不完整
- 股票代码校验失败应拒绝录入
- 卖出数量超过持仓应拒绝执行

### 13.3 通知层

- 发送失败时自动重试
- 超过上限后写入失败状态，保留人工处理入口

### 13.4 通用原则

- 外部调用默认超时 30 秒
- 数据库关键写操作使用事务
- Celery 任务启用自动重试策略
- 关键操作记录审计日志

## 14. 交付阶段基线

### 阶段 1：基础设施与数据模型

交付内容：

- Django 项目骨架
- 四个后端 app
- 基础配置
- 数据模型与迁移
- 基础 serializers

完成标准：

- 项目可启动
- 数据库迁移可执行

### 阶段 2：交易采集模块

交付内容：

- `TradeRecorder`
- `THSConnector`
- `EmailCrawler`
- 交易采集任务
- 对应单元测试与属性测试

完成标准：

- 交易记录可标准化入库
- 重复记录不会重复创建

### 阶段 3：持仓与成本模块

交付内容：

- `PortfolioManager`
- `CostCalculator`
- 持仓与成本相关测试

完成标准：

- 交易录入后能驱动持仓变化
- 港股成本和盈亏计算通过测试

### 阶段 4：复盘分析模块

交付内容：

- 三个分析器
- `ReviewEngine`
- 报告模型联动
- 分析相关测试

完成标准：

- 可对单笔交易生成复盘报告

### 阶段 5：新闻与通知模块

交付内容：

- `NewsCrawler`
- `NotificationService`
- 新闻和通知任务
- 相关测试

完成标准：

- 可抓取、去重、分类并触发推送

### 阶段 6：后端 API

交付内容：

- trades / portfolio / analysis / news API
- JWT 认证
- API 集成测试

完成标准：

- 前端可通过 API 完成主要业务流转

### 阶段 7：前端

交付内容：

- Dashboard
- 交易记录列表
- 持仓页面
- 复盘页面
- 新闻页面

完成标准：

- 关键页面可用并与后端打通

### 阶段 8：最终联调

交付内容：

- 全量测试
- 端到端主流程验证
- 文档回补

完成标准：

- 所有关键测试通过
- 主流程无阻塞性缺陷

## 15. 实施默认原则

- 先后端基础能力，后前端展示
- 先可测性，后功能扩展
- 先 mock 外部接口，后接真实源
- 先保证去重、幂等、事务性，再追求丰富功能
- 所有新增模块必须附带测试
- 所有需求、模型、接口变更应同步更新本基线

## 16. 下一步建议

按本基线进入实现时，推荐从以下顺序开始：

1. 初始化 Django 项目与 app 结构
2. 落 `TradeRecord`、`Position`、`ReviewReport`、`NewsItem` 等模型
3. 建立基础测试框架
4. 优先实现 `TradeRecorder` 和 `PortfolioManager`

这会最快形成一个可运行、可验证、可继续扩展的骨架。
