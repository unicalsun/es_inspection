# ES 集群智能巡检系统 - Agent 上下文

## 项目概述

基于 LangChain 的 Elasticsearch 集群巡检工具，用于百胜中国(Yum China)内网环境下的 ES 集群自动化巡检。
- 10套 3节点集群 (master/data/coordinating 混部)
- 5套 10节点集群 (3master + 6data + 2coordinating)
- 巡检指标覆盖: 集群层 + 系统层 + 百胜业务层
- LLM 可配置，不局限于 OpenAI

## 技术栈

- **Python 3.11** (C:\Python311\python.exe)
- **LangChain 1.3.14** + langchain-openai 1.3.5 + langchain-deepseek 1.1.0
- **Elasticsearch 7.10.1** (elasticsearch-py)
- **PyYAML** 配置管理
- **HTML/Markdown** 报告生成

## 项目结构

`
es_xinjian/
├── config/
│   ├── clusters.yaml          # ES 集群配置 (可追加新集群)
│   ├── llm_config.yaml        # LLM 提供商配置 (支持多LLM切换)
│   └── inspection_config.yaml # 巡检指标定义与阈值
├── core/
│   ├── __init__.py
│   ├── llm_factory.py         # LLM 工厂: 根据配置创建 LLM 实例
│   ├── es_client.py           # ES 客户端: 连接管理/重试/超时/失败跳过
│   ├── inspector.py           # 巡检引擎: 三层指标采集 + 问题检测
│   ├── agent.py               # LangChain 智能体: Tool + LLM 分析编排
│   └── report_generator.py    # 报告生成: HTML(交互式) + Markdown
├── reports/                   # 巡检报告输出 (按时间戳命名)
├── logs/                      # 运行日志
├── main.py                    # CLI 主入口
├── requirements.txt           # 依赖清单
└── README.md                  # 项目说明
`

## 核心模块说明

### llm_factory.py - LLM 工厂
- 读取 config/llm_config.yaml 中的 ctive_provider 字段确定使用哪个 LLM
- 支持环境变量引用: ${OPENAI_API_KEY} 格式
- 所有提供商最终都通过 ChatOpenAI 创建实例 (含 Ollama/DeepSeek/智谱/千问等)
- 自定义 LLM: 在 providers 下新增一个 openai 兼容配置即可

### es_client.py - ES 客户端管理
- ESClientManager: 管理多集群连接
- connect_cluster(): 逐节点尝试连接，返回 (client, error_msg) 元组
- connect_all(): 批量连接所有启用的集群
- pi_call(): 带重试的 API 调用，失败返回 None
- 连接失败的集群会被跳过，原因记录在 _connection_errors 字典中

### inspector.py - 巡检引擎
- ClusterInspector: 单集群巡检器
- inspect_cluster(): 执行完整巡检，返回结构化结果字典
- 采集指标: 集群健康/统计/节点统计/索引统计/分片/系统/JVM/CPU/磁盘/线程池
- 问题检测: 自动检查阈值，写入 issues (严重) 和 warnings (警告) 列表
- 百胜业务指标: 搜索延迟/索引速率/文档删除比例/索引数量

### agent.py - LangChain 智能体
- ESInspectionAgent: 核心智能体类
- 4个 LangChain Tool: list_clusters / inspect_cluster / get_cluster_health / analyze_issues
- un_full_inspection(): 全量巡检流程 (连接->巡检->LLM分析->报告)
- un_cluster_inspection(): 单集群巡检
- LLM 分析: 将巡检数据发送给 LLM，生成整体评估+风险点+业务优化建议

### report_generator.py - 报告生成
- ReportGenerator: HTML + Markdown 双格式报告
- HTML 报告: 概览卡片 + 各集群折叠详情 + 节点表格 + 原始JSON
- Markdown 摘要: 概览表格 + 各集群状态
- 报告文件名格式: s_inspection_{timestamp}.html

## 配置文件

### config/clusters.yaml - 集群配置
`yaml
clusters:
  - name: "cluster-01-3node"
    hosts: ["192.168.1.101", "192.168.1.102", "192.168.1.103"]
    port: 9200
    scheme: "http"
    auth:
      username: "db_ops"
      password: "Yumchina1234"
    enabled: true
    tags: ["3node", "生产环境"]
`
- 追加新集群: 在列表末尾添加，或使用 python main.py add-cluster
- 已配置 15 套集群 (10套3节点 + 5套10节点)

### config/llm_config.yaml - LLM 配置
`yaml
active_provider: "deepseek"
providers:
  openai: { provider: "openai", model: "gpt-4o", api_key: "" }
  deepseek: { provider: "deepseek", model: "deepseek-chat", api_key: "", base_url: "https://api.deepseek.com" }
  zhipu: { provider: "zhipu", model: "glm-4", ... }
  qwen: { provider: "qwen", model: "qwen-plus", ... }
  ollama: { provider: "openai", model: "qwen2.5:14b", base_url: "http://localhost:11434/v1" }
  custom_openai: { ... }
`
- 切换 LLM: 修改 ctive_provider 或运行时 --llm 参数
- 添加新 LLM: 在 providers 下新增 openai 兼容配置

### config/inspection_config.yaml - 巡检配置
- cluster_metrics: 集群层指标 (health/stats/shards/settings)
- yumchina_business_metrics: 百胜业务指标 (搜索延迟/菜单索引/优惠活动等)
- system_metrics: 系统层指标 (JVM/CPU/磁盘/内存/线程池/Segment)
- eport: 报告输出配置
- inspection: 超时/重试/并行度配置

## CLI 命令

`ash
# 全量巡检
python main.py inspect

# 指定 LLM 巡检
python main.py inspect --llm deepseek

# 巡检指定集群
python main.py inspect --cluster cluster-01-3node

# 测试所有集群连接
python main.py test-connection

# 列出可用 LLM
python main.py list-llm

# 添加新集群
python main.py add-cluster --name cluster-16 --hosts "10.0.0.1,10.0.0.2" --port 9200
`

## 巡检阈值

| 指标 | 警告 (Warning) | 严重 (Critical) |
|------|---------------|----------------|
| JVM 堆使用率 | > 70% | > 85% |
| CPU 使用率 | > 70% | > 90% |
| 磁盘使用率 | > 75% | > 85% |
| 线程池拒绝 | > 0 | > 100 |
| 未分配分片 | > 0 | > 5 |
| 文档删除比例 | > 20% | > 50% |
| 搜索延迟 | > 50ms | > 200ms |

## ES 凭据

- 只读账号: db_ops / Yumchina1234
- 每套集群均已植入该账号
- 配置在 clusters.yaml 的 auth 字段中

## 维护指南

### 追加新集群
1. 编辑 config/clusters.yaml 在 clusters 列表末尾追加
2. 或运行 python main.py add-cluster --name xxx --hosts "ip1,ip2" --port 9200

### 切换/添加 LLM
1. 编辑 config/llm_config.yaml 修改 ctive_provider
2. 或运行时指定 python main.py inspect --llm xxx
3. 添加新 LLM: 在 providers 下新增配置，provider 字段填 openai (兼容接口)

### 调整巡检指标
编辑 config/inspection_config.yaml，可修改:
- 阈值 (thresholds)
- 新增/删除检查项
- 调整超时和重试参数

### 查看报告
报告输出在 eports/ 目录:
- HTML: 浏览器打开，包含交互式展开/收起
- Markdown: 文本摘要
- 日志: logs/inspection_{timestamp}.log

## 常见开发场景

1. **新增巡检指标**: 在 inspection_config.yaml 添加指标定义，在 inspector.py 的 inspect_cluster() 中添加采集逻辑
2. **新增 LLM 提供商**: 在 llm_config.yaml providers 下添加配置，llm_factory.py 的 create_llm() 中添加对应 case
3. **修改报告格式**: 编辑 eport_generator.py 的 _build_html() 方法
4. **调整告警阈值**: 编辑 inspection_config.yaml 中的 thresholds 字段
