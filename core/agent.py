"""
LangChain 智能体模块
使用 LangChain Agent 编排巡检流程，利用 LLM 进行分析和建议
"""
import json
import time
import logging
from typing import Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from core.llm_factory import LLMFactory
from core.es_client import ESClientManager
from core.inspector import ClusterInspector
from core.report_generator import ReportGenerator

logger = logging.getLogger("es_inspector")


class ESTools:
    """封装为 LangChain Tool 的 ES 巡检操作"""

    def __init__(self, es_manager: ESClientManager, inspector: ClusterInspector):
        self.es_manager = es_manager
        self.inspector = inspector

    def get_tools(self):
        return [
            self._create_list_clusters_tool(),
            self._create_inspect_cluster_tool(),
            self._create_get_cluster_health_tool(),
            self._create_analyze_issues_tool(),
        ]

    def _create_list_clusters_tool(self):
        @tool
        def list_clusters() -> str:
            """列出所有配置的 ES 集群及其连接状态"""
            clusters = self.es_manager.get_all_clusters()
            result = [{"name": c["name"], "hosts": c.get("hosts", []), "tags": c.get("tags", [])} for c in clusters]
            return json.dumps(result, ensure_ascii=False, indent=2)
        return list_clusters

    def _create_inspect_cluster_tool(self):
        @tool
        def inspect_cluster(cluster_name: str) -> str:
            """对指定的 ES 集群执行全面巡检，返回巡检结果"""
            clusters = self.es_manager.get_all_clusters()
            cluster_cfg = next((c for c in clusters if c["name"] == cluster_name), None)
            if cluster_cfg is None:
                return json.dumps({"error": f"集群 {cluster_name} 未找到"})
            result = self.inspector.inspect_cluster(cluster_name, cluster_cfg)
            summary = {
                "cluster_name": result["cluster_name"],
                "status": result["status"],
                "error": result.get("error"),
                "cluster_health": result.get("cluster_health", {}),
                "business_metrics": result.get("business_metrics", {}),
                "issues": result.get("issues", []),
                "warnings": result.get("warnings", []),
                "node_count": len(result.get("node_stats", {}).get("nodes", {})),
            }
            return json.dumps(summary, ensure_ascii=False, indent=2, default=str)
        return inspect_cluster

    def _create_get_cluster_health_tool(self):
        @tool
        def get_cluster_health(cluster_name: str) -> str:
            """获取指定集群的健康状态摘要"""
            es = self.es_manager.get_client(cluster_name)
            if es is None:
                return json.dumps({"error": f"集群 {cluster_name} 未连接"})
            try:
                health = es.cluster.health()
                return json.dumps({
                    "status": health.get("status"),
                    "number_of_nodes": health.get("number_of_nodes"),
                    "active_shards": health.get("active_shards"),
                    "unassigned_shards": health.get("unassigned_shards"),
                }, indent=2)
            except Exception as e:
                return json.dumps({"error": str(e)})
        return get_cluster_health

    def _create_analyze_issues_tool(self):
        @tool
        def analyze_issues(cluster_results_json: str) -> str:
            """分析多个集群的巡检结果，识别共性问题和风险"""
            try:
                results = json.loads(cluster_results_json)
            except json.JSONDecodeError:
                return "无法解析输入数据"
            all_issues, all_warnings = [], []
            for r in results:
                name = r.get("cluster_name", "?")
                for i in r.get("issues", []):
                    all_issues.append({"cluster": name, **i})
                for w in r.get("warnings", []):
                    all_warnings.append({"cluster": name, **w})
            issue_cats = {}
            for i in all_issues:
                issue_cats.setdefault(i.get("category", "其他"), []).append(i)
            warning_cats = {}
            for w in all_warnings:
                warning_cats.setdefault(w.get("category", "其他"), []).append(w)
            return json.dumps({
                "total_issues": len(all_issues),
                "total_warnings": len(all_warnings),
                "issue_by_category": {k: len(v) for k, v in issue_cats.items()},
                "warning_by_category": {k: len(v) for k, v in warning_cats.items()},
                "top_issue_clusters": list(set(i["cluster"] for i in all_issues)),
            }, ensure_ascii=False, indent=2)
        return analyze_issues


class ESInspectionAgent:
    """基于 LangChain 的 ES 巡检智能体"""

    SYSTEM_PROMPT = """你是一个专业的 Elasticsearch 集群巡检分析助手，隶属于百胜中国(Yum China)的DBA运维团队。

你的职责：
1. 分析 ES 集群的巡检数据，识别潜在风险和问题
2. 针对百胜中国的业务场景（门店搜索、订单查询、菜品菜单、优惠活动等）给出优化建议
3. 评估集群健康度，生成人类可读的巡检报告分析

分析要点：
- 集群健康状态（green/yellow/red）
- JVM 堆内存使用情况（>75% 需关注）
- CPU 和磁盘使用率
- 分片分配状况（未分配分片）
- 线程池拒绝情况
- 搜索延迟和索引速率
- 与百胜业务相关的索引健康（订单、门店、菜品、优惠券等）

请用中文输出分析结果，格式清晰，优先级分明。
"""

    def __init__(self, llm_provider: str = None):
        self.llm_factory = LLMFactory()
        self.llm = self.llm_factory.create_llm(llm_provider)
        self.es_manager = ESClientManager()
        self.inspector = ClusterInspector(self.es_manager)
        self.report_generator = ReportGenerator()
        self.tools = ESTools(self.es_manager, self.inspector)

    def run_full_inspection(self) -> dict:
        """全量巡检: 连接所有集群 -> 逐个巡检 -> LLM分析 -> 生成报告"""
        logger.info("=" * 60)
        logger.info("开始 ES 集群全面巡检")
        logger.info("=" * 60)

        # Step 1: 连接
        connections = self.es_manager.connect_all()
        connected = sum(1 for c, e in connections.values() if c is not None)
        failed_conn = sum(1 for c, e in connections.values() if c is None)
        logger.info(f"连接结果: 成功 {connected}, 失败 {failed_conn}")

        # Step 2: 逐集群巡检
        all_results = []
        for cluster_cfg in self.es_manager.get_all_clusters():
            name = cluster_cfg["name"]
            logger.info(f"  巡检: {name}...")
            result = self.inspector.inspect_cluster(name, cluster_cfg)
            all_results.append(result)

        # Step 3: 汇总
        summary = self._build_summary(all_results)
        logger.info(f"巡检汇总: {json.dumps(summary, ensure_ascii=False)}")

        # Step 4: LLM 分析
        logger.info("LLM 分析巡检结果...")
        llm_analysis = self._llm_analyze(all_results, summary)

        # Step 5: 生成报告
        logger.info("生成巡检报告...")
        html_path = self.report_generator.generate_report(all_results, summary)
        md_path = self.report_generator.generate_markdown_summary(all_results, summary)

        summary["llm_analysis"] = llm_analysis
        summary["html_report"] = html_path
        summary["markdown_report"] = md_path

        self.es_manager.close_all()
        logger.info(f"巡检完成！HTML: {html_path}  |  Markdown: {md_path}")
        return summary

    def run_cluster_inspection(self, cluster_name: str) -> dict:
        """对单个集群执行巡检 (仅连接指定集群，生成报告)"""
        logger.info(f"单集群巡检: {cluster_name}")

        # 找到集群配置
        clusters = self.es_manager.get_all_clusters()
        cluster_cfg = next((c for c in clusters if c["name"] == cluster_name), None)
        if cluster_cfg is None:
            return {"error": f"集群 {cluster_name} 未在配置文件中找到"}

        # 只连接目标集群
        client, error = self.es_manager.connect_cluster(cluster_cfg)
        if client is None:
            result = {
                "cluster_name": cluster_name,
                "status": "skipped",
                "error": error,
                "cluster_tags": cluster_cfg.get("tags", []),
                "hosts": cluster_cfg.get("hosts", []),
                "inspection_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "cluster_health": {}, "cluster_stats": {}, "node_stats": {},
                "indices_stats": {}, "shard_info": {}, "system_metrics": {},
                "business_metrics": {}, "issues": [], "warnings": [],
            }
            all_results = [result]
            summary = self._build_summary(all_results)
        else:
            # 执行巡检
            result = self.inspector.inspect_cluster(cluster_name, cluster_cfg)
            all_results = [result]
            summary = self._build_summary(all_results)

        # 生成报告 (单集群也生成)
        html_path = self.report_generator.generate_report(all_results, summary)
        md_path = self.report_generator.generate_markdown_summary(all_results, summary)
        summary["html_report"] = html_path
        summary["markdown_report"] = md_path

        self.es_manager.close_all()
        logger.info(f"报告已生成: {html_path}")
        return summary

    def _build_summary(self, all_results: List[dict]) -> dict:
        return {
            "total_clusters": len(all_results),
            "success": sum(1 for r in all_results if r["status"] == "success"),
            "partial": sum(1 for r in all_results if r["status"] == "partial"),
            "failed": sum(1 for r in all_results if r["status"] == "failed"),
            "skipped": sum(1 for r in all_results if r["status"] == "skipped"),
            "total_issues": sum(len(r.get("issues", [])) for r in all_results),
            "total_warnings": sum(len(r.get("warnings", [])) for r in all_results),
        }

    def _llm_analyze(self, all_results: List[dict], summary: dict) -> str:
        try:
            entries = []
            for r in all_results:
                name = r.get("cluster_name", "?")
                status = r.get("status", "?")
                health = r.get("cluster_health", {})
                biz = r.get("business_metrics", {})
                issues = r.get("issues", [])
                warnings = r.get("warnings", [])
                entry = f"集群: {name}\n  状态: {status}\n"
                if status == "skipped":
                    entry += f"  跳过原因: {r.get('error', '未知')}\n"
                else:
                    entry += f"  健康: {health.get('status', 'N/A')}  节点: {health.get('number_of_nodes', 'N/A')}\n"
                    entry += f"  文档: {biz.get('total_doc_count', 'N/A')}  存储: {biz.get('total_store_size_gb', 'N/A')}GB\n"
                    entry += f"  搜索延迟: {biz.get('search_latency_ms', 'N/A')}ms\n"
                    entry += f"  严重: {len(issues)}  警告: {len(warnings)}\n"
                    for i in issues:
                        entry += f"    [{i.get('severity')}] {i.get('message')}\n"
                    for w in warnings:
                        entry += f"    [warn] {w.get('message')}\n"
                entries.append(entry)

            prompt = f"""请分析以下 ES 集群巡检结果，给出整体评估和建议。

巡检汇总:
- 集群总数: {summary.get('total_clusters', 0)}
- 成功: {summary.get('success', 0)}
- 失败/跳过: {summary.get('failed', 0) + summary.get('skipped', 0)}
- 严重问题: {summary.get('total_issues', 0)}
- 警告: {summary.get('total_warnings', 0)}

各集群详情:
{chr(10).join(entries)}

请提供:
1. 整体健康评估（一段话总结）
2. 关键风险点（按优先级排序）
3. 针对百胜中国业务（门店搜索、订单查询、菜品菜单、优惠活动）的优化建议
4. 后续行动建议

请用中文回答，格式清晰。"""

            messages = [
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            error_msg = f"LLM 分析失败: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            return error_msg
