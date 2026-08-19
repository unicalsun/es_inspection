"""
巡检指标采集模块
对每个集群执行全量指标采集，返回结构化数据
"""
import time
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from core.es_client import ESClientManager

logger = logging.getLogger("es_inspector")


class ClusterInspector:
    """单集群巡检器"""

    def __init__(self, es_manager: ESClientManager):
        self.es_manager = es_manager
        cfg_path = Path(__file__).parent.parent / "config" / "inspection_config.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            self.inspection_config = yaml.safe_load(f)

    def inspect_cluster(self, cluster_name: str, cluster_cfg: dict) -> dict:
        """
        对单个集群执行完整巡检
        返回结构化的巡检结果字典
        """
        result = {
            "cluster_name": cluster_name,
            "cluster_tags": cluster_cfg.get("tags", []),
            "hosts": cluster_cfg.get("hosts", []),
            "inspection_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "success",
            "error": None,
            "cluster_health": {},
            "cluster_stats": {},
            "node_stats": {},
            "indices_stats": {},
            "shard_info": {},
            "system_metrics": {},
            "business_metrics": {},
            "issues": [],
            "warnings": [],
        }

        es = self.es_manager.get_client(cluster_name)
        if es is None:
            result["status"] = "skipped"
            errors = self.es_manager.get_connection_errors()
            result["error"] = errors.get(cluster_name, "未知连接错误")
            return result

        start_time = time.time()

        try:
            # 1. 集群健康
            result["cluster_health"] = self._collect_cluster_health(cluster_name)
            self._check_health_issues(result)

            # 2. 集群统计
            result["cluster_stats"] = self._collect_cluster_stats(cluster_name)

            # 3. 节点统计 (含系统指标)
            result["node_stats"] = self._collect_node_stats(cluster_name)
            self._check_node_issues(result)

            # 4. 索引统计
            result["indices_stats"] = self._collect_indices_stats(cluster_name)
            self._check_index_issues(result)

            # 5. 分片信息
            result["shard_info"] = self._collect_shard_info(cluster_name)
            self._check_shard_issues(result)

            # 6. 系统层指标
            result["system_metrics"] = self._collect_system_metrics(cluster_name)
            self._check_system_issues(result)

            # 7. 百胜业务层指标
            result["business_metrics"] = self._collect_business_metrics(cluster_name, result)

            # 8. 线程池状态
            result["thread_pool_stats"] = self._collect_thread_pool_stats(cluster_name)
            self._check_thread_pool_issues(result)

        except Exception as e:
            result["status"] = "partial"
            result["error"] = f"巡检过程异常: {type(e).__name__}: {str(e)}"
            logger.error(f"[{cluster_name}] 巡检异常: {e}", exc_info=True)

        elapsed = round(time.time() - start_time, 2)
        result["inspection_duration_seconds"] = elapsed
        logger.info(f"[{cluster_name}] 巡检完成，耗时 {elapsed}s，发现 {len(result['issues'])} 个问题，{len(result['warnings'])} 个警告")

        return result

    def _call_api(self, cluster_name: str, endpoint: str, **kwargs) -> Optional[dict]:
        return self.es_manager.api_call(cluster_name, endpoint, **kwargs)

    # ==================== 数据采集 ====================

    def _collect_cluster_health(self, cluster_name: str) -> dict:
        data = self._call_api(cluster_name, "_cluster/health")
        return data or {}

    def _collect_cluster_stats(self, cluster_name: str) -> dict:
        data = self._call_api(cluster_name, "_cluster/stats")
        return data or {}

    def _collect_node_stats(self, cluster_name: str) -> dict:
        data = self._call_api(cluster_name, "_nodes/stats")
        return data or {}

    def _collect_indices_stats(self, cluster_name: str) -> dict:
        data = self._call_api(cluster_name, "_stats")
        return data or {}

    def _collect_shard_info(self, cluster_name: str) -> dict:
        data = self._call_api(cluster_name, "_cat/allocation?v")
        return {"allocation": data or []}

    def _collect_system_metrics(self, cluster_name: str) -> dict:
        metrics = {}
        # JVM
        jvm_data = self._call_api(cluster_name, "_nodes/stats/jvm")
        metrics["jvm"] = jvm_data
        # OS
        os_data = self._call_api(cluster_name, "_nodes/stats/os")
        metrics["os"] = os_data
        # FS
        fs_data = self._call_api(cluster_name, "_nodes/stats/fs")
        metrics["fs"] = fs_data
        return metrics

    def _collect_business_metrics(self, cluster_name: str, result: dict) -> dict:
        """百胜中国业务层指标"""
        biz = {}
        # 搜索延迟
        search_stats = result.get("indices_stats", {})
        total_search = self._deep_get(search_stats, ["_all", "total", "search"], {})
        query_total = total_search.get("query_total", 0)
        query_time = total_search.get("query_time_in_millis", 0)
        biz["search_latency_ms"] = round(query_time / max(query_total, 1), 3)
        biz["search_total_queries"] = query_total

        # 索引速率
        total_indexing = self._deep_get(search_stats, ["_all", "total", "indexing"], {})
        index_total = total_indexing.get("index_total", 0)
        index_time = total_indexing.get("index_time_in_millis", 0)
        biz["indexing_rate_docs_per_sec"] = round(index_total / max(index_time, 1) * 1000, 2)

        # 文档删除比例
        total_docs = self._deep_get(search_stats, ["_all", "total", "docs"], {})
        doc_count = total_docs.get("count", 0)
        doc_deleted = total_docs.get("deleted", 0)
        biz["doc_deletion_ratio_percent"] = round(doc_deleted / max(doc_count, 1) * 100, 2)
        biz["total_doc_count"] = doc_count
        biz["total_doc_deleted"] = doc_deleted

        # 索引数量
        cluster_stats = result.get("cluster_stats", {})
        biz["total_indices"] = self._deep_get(cluster_stats, ["indices", "count"], 0)

        # 存储大小
        biz["total_store_size_bytes"] = self._deep_get(cluster_stats, ["indices", "store", "size_in_bytes"], 0)
        biz["total_store_size_gb"] = round(biz["total_store_size_bytes"] / (1024**3), 2)

        return biz

    def _collect_thread_pool_stats(self, cluster_name: str) -> dict:
        data = self._call_api(cluster_name, "_cat/thread_pool?v")
        return {"pools": data or []}

    # ==================== 问题检查 ====================

    def _check_health_issues(self, result: dict):
        health = result.get("cluster_health", {})
        status = health.get("status", "unknown")
        if status == "red":
            result["issues"].append({
                "severity": "critical",
                "category": "集群健康",
                "message": "集群状态为 RED，存在未分配的主分片，数据可能丢失或不可用",
                "value": status,
            })
        elif status == "yellow":
            result["warnings"].append({
                "severity": "warning",
                "category": "集群健康",
                "message": "集群状态为 YELLOW，存在未分配的副本分片",
                "value": status,
            })

        relocating = health.get("relocating_shards", 0)
        if relocating > 5:
            result["warnings"].append({
                "severity": "warning",
                "category": "分片迁移",
                "message": f"有 {relocating} 个分片正在迁移，可能影响性能",
                "value": relocating,
            })

        initializing = health.get("initializing_shards", 0)
        if initializing > 0:
            result["warnings"].append({
                "severity": "warning",
                "category": "分片初始化",
                "message": f"有 {initializing} 个分片正在初始化",
                "value": initializing,
            })

    def _check_node_issues(self, result: dict):
        node_stats = result.get("node_stats", {})
        nodes = node_stats.get("nodes", {})
        thresholds = self.inspection_config.get("system_metrics", {})

        for node_id, node_data in nodes.items():
            node_name = node_data.get("name", node_id)

            # JVM 堆使用
            jvm_mem = self._deep_get(node_data, ["jvm", "mem"], {})
            heap_percent = jvm_mem.get("heap_used_percent", 0)
            if heap_percent > 85:
                result["issues"].append({
                    "severity": "critical",
                    "category": "JVM内存",
                    "message": f"节点 {node_name} JVM堆使用率 {heap_percent}% 超过85%阈值",
                    "value": heap_percent,
                    "node": node_name,
                })
            elif heap_percent > 70:
                result["warnings"].append({
                    "severity": "warning",
                    "category": "JVM内存",
                    "message": f"节点 {node_name} JVM堆使用率 {heap_percent}% 超过70%预警线",
                    "value": heap_percent,
                    "node": node_name,
                })

            # CPU
            os_stats = self._deep_get(node_data, ["os", "cpu"], {})
            cpu_percent = os_stats.get("percent", 0)
            if cpu_percent > 90:
                result["issues"].append({
                    "severity": "critical",
                    "category": "CPU",
                    "message": f"节点 {node_name} CPU使用率 {cpu_percent}% 超过90%阈值",
                    "value": cpu_percent,
                    "node": node_name,
                })
            elif cpu_percent > 70:
                result["warnings"].append({
                    "severity": "warning",
                    "category": "CPU",
                    "message": f"节点 {node_name} CPU使用率 {cpu_percent}% 超过70%预警线",
                    "value": cpu_percent,
                    "node": node_name,
                })

            # 磁盘
            fs_stats = self._deep_get(node_data, ["fs", "total"], {})
            disk_percent = fs_stats.get("used_percent", 0)
            if disk_percent > 85:
                result["issues"].append({
                    "severity": "critical",
                    "category": "磁盘",
                    "message": f"节点 {node_name} 磁盘使用率 {disk_percent}% 超过85%阈值",
                    "value": disk_percent,
                    "node": node_name,
                })
            elif disk_percent > 75:
                result["warnings"].append({
                    "severity": "warning",
                    "category": "磁盘",
                    "message": f"节点 {node_name} 磁盘使用率 {disk_percent}% 超过75%预警线",
                    "value": disk_percent,
                    "node": node_name,
                })

            # 线程池拒绝
            thread_pools = self._deep_get(node_data, ["thread_pool"], {})
            for pool_name, pool_data in thread_pools.items():
                rejected = pool_data.get("rejected", 0)
                if rejected > 100:
                    result["issues"].append({
                        "severity": "critical",
                        "category": "线程池",
                        "message": f"节点 {node_name} {pool_name} 线程池拒绝 {rejected} 次",
                        "value": rejected,
                        "node": node_name,
                    })
                elif rejected > 0:
                    result["warnings"].append({
                        "severity": "warning",
                        "category": "线程池",
                        "message": f"节点 {node_name} {pool_name} 线程池拒绝 {rejected} 次",
                        "value": rejected,
                        "node": node_name,
                    })

    def _check_index_issues(self, result: dict):
        indices_stats = result.get("indices_stats", {})
        indices = indices_stats.get("indices", {})
        for idx_name, idx_data in indices.items():
            # 检查大量删除的索引
            docs = idx_data.get("total", {}).get("docs", {})
            deleted = docs.get("deleted", 0)
            count = docs.get("count", 0)
            if count > 0 and deleted / max(count, 1) > 0.5:
                result["warnings"].append({
                    "severity": "warning",
                    "category": "索引数据",
                    "message": f"索引 {idx_name} 删除比例 {round(deleted/max(count,1)*100, 1)}% 较高",
                    "value": f"{deleted}/{count}",
                })

    def _check_shard_issues(self, result: dict):
        health = result.get("cluster_health", {})
        unassigned = health.get("unassigned_shards", 0)
        if unassigned > 0:
            result["issues"].append({
                "severity": "critical" if unassigned > 5 else "warning",
                "category": "分片分配",
                "message": f"有 {unassigned} 个未分配分片",
                "value": unassigned,
            })

    def _check_system_issues(self, result: dict):
        # 从 node_stats 中已检查，这里做额外的汇总检查
        pass

    def _check_thread_pool_issues(self, result: dict):
        tp_stats = result.get("thread_pool_stats", {}).get("pools", [])
        if isinstance(tp_stats, list):
            for pool in tp_stats:
                if isinstance(pool, dict):
                    rejected = pool.get("rejected", 0)
                    if isinstance(rejected, (int, float)) and rejected > 0:
                        result["warnings"].append({
                            "severity": "warning",
                            "category": "线程池",
                            "message": f"节点 {pool.get('node_name', '?')} 线程池 {pool.get('name', '?')} 有 {rejected} 次拒绝",
                            "value": rejected,
                        })

    # ==================== 工具方法 ====================

    @staticmethod
    def _deep_get(data: dict, keys: list, default=None):
        """安全的深层字典取值"""
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current if current is not None else default
