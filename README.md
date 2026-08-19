# ES 集群智能巡检系统

基于 LangChain 的 ES 集群自动化巡检工具，支持多 LLM 提供商、可扩展集群配置、自动生成报告。

## 安装依赖

`ash
pip install -r requirements.txt
`

## 快速开始

`ash
# 全量巡检 (所有集群)
python main.py inspect

# 指定 LLM 巡检
python main.py inspect --llm deepseek

# 巡检指定集群
python main.py inspect --cluster standalone

# 测试集群连接
python main.py test-connection

# 查看可用 LLM
python main.py list-llm
`

## 添加新集群

编辑 config/clusters.yaml，在 clusters: 下追加：

`yaml
  - name: "my-cluster"
    hosts: ["192.168.1.101", "192.168.1.102"]
    port: 9200
    scheme: "http"
    auth: {username: "db_ops", password: "xxxx"}
    enabled: true
    tags: ["3node", "生产环境"]
`

或用命令行添加：

`ash
python main.py add-cluster --name my-cluster --hosts "192.168.1.101,192.168.1.102" --port 9200
`

## 配置 LLM

编辑 config/llm_config.yaml：

`yaml
active_provider: "deepseek"    # 修改这里切换 LLM
`

支持的提供商：

| 名称 | 说明 | 环境变量 |
|------|------|---------|
| openai | GPT-4o 等 | OPENAI_API_KEY |
| deepseek | deepseek-chat | DEEPSEEK_API_KEY |
| zhipu | GLM-4 | ZHIPU_API_KEY |
| qwen | 通义千问 | DASHSCOPE_API_KEY |
| ollama | 本地模型 | 无需 |

添加任意 OpenAI 兼容接口：

`yaml
providers:
  my_llm:
    provider: "openai"
    model: "model-name"
    api_key: "your-key"
    base_url: "https://api.example.com/v1"
`

然后设置 ctive_provider: "my_llm"。

## 巡检指标

**集群层** — 健康状态、节点数、分片分配、索引数量

**系统层** — JVM堆(>70%警告/>85%严重)、CPU(>70%/>90%)、磁盘(>75%/>85%)、线程池拒绝

**业务层** — 搜索延迟、索引速率、文档删除比例、业务索引健康

## 报告输出

巡检完成后自动生成到 
eports/ 目录：
- s_inspection_{时间}.html — 完整报告，浏览器打开
- s_inspection_summary_{时间}.md — Markdown 摘要

## 项目结构

```
es_xinjian/
├── config/
│   ├── clusters.yaml          # 集群配置 (可追加)
│   ├── llm_config.yaml        # LLM 配置
│   └── inspection_config.yaml # 巡检指标和阈值
├── core/
│   ├── llm_factory.py         # LLM 工厂
│   ├── es_client.py           # ES 连接管理
│   ├── inspector.py           # 巡检引擎
│   ├── agent.py               # LangChain 智能体
│   └── report_generator.py    # 报告生成
├── reports/                   # 报告目录
├── main.py                    # 入口
└── requirements.txt
```

## ES 账号

- 只读账号: db_ops / xxx （已在每套集群植入）
