# ES 集群智能巡检系统

基于 LangChain 的 ES 集群自动化巡检工具，支持多 LLM、可扩展集群配置、自动生成报告。

## 安装

`ash
pip install -r requirements.txt
`

## 使用

`ash
python main.py inspect                         # 全量巡检
python main.py inspect --llm deepseek          # 指定 LLM
python main.py inspect --cluster standalone    # 巡检指定集群
python main.py test-connection                 # 测试连接
python main.py list-llm                        # 查看可用 LLM
`

## 添加新集群

编辑 config/clusters.yaml，在 clusters: 下追加：

`yaml
  - name: "my-cluster"
    hosts: ["192.168.1.101", "192.168.1.102"]
    port: 9200
    scheme: "http"
    auth: {username: "db_ops", password: "Yumchina1234"}
    enabled: true
    tags: ["3node", "生产环境"]
`

或命令行：python main.py add-cluster --name my-cluster --hosts "ip1,ip2" --port 9200

## 配置 LLM

编辑 config/llm_config.yaml，修改 ctive_provider 字段切换 LLM：

| 名称 | 说明 | 环境变量 |
|------|------|---------|
| openai | GPT-4o | OPENAI_API_KEY |
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

设置 ctive_provider: "my_llm" 即可。

## 巡检指标

| 类别 | 指标 | 阈值 |
|------|------|------|
| 集群 | 健康状态、节点数、分片分配 | red=严重 yellow=警告 |
| JVM | 堆内存使用率 | >70% 警告 / >85% 严重 |
| CPU | 使用率 | >70% 警告 / >90% 严重 |
| 磁盘 | 使用率 | >75% 警告 / >85% 严重 |
| 线程池 | 拒绝计数 | >0 警告 / >100 严重 |
| 业务 | 搜索延迟、索引速率、文档删除率 | 按需配置 |

## 报告

巡检完成后自动生成到 eports/ 目录：
- s_inspection_{时间}.html — 完整报告（浏览器打开）
- s_inspection_summary_{时间}.md — Markdown 摘要

## 项目结构

`
config/
  clusters.yaml          # 集群配置
  llm_config.yaml        # LLM 配置
  inspection_config.yaml # 指标与阈值
core/
  llm_factory.py         # LLM 工厂
  es_client.py           # ES 连接管理
  inspector.py           # 巡检引擎
  agent.py               # LangChain 智能体
  report_generator.py    # 报告生成
reports/                 # 报告输出
main.py                  # 入口
`

## ES 账号

只读：db_ops / Yumchina1234（已植入每套集群）
