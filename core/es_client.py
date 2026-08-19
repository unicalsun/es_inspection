"""
ES 客户端封装模块
处理集群连接、重试、超时，支持连接失败跳过并记录原因
"""
import time
import logging
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from elasticsearch import Elasticsearch, exceptions as es_exceptions

logger = logging.getLogger("es_inspector")


class ESClientManager:
    """ES 集群客户端管理器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "clusters.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.inspection_cfg = self._load_inspection_config()
        self._clients: Dict[str, Elasticsearch] = {}
        self._connection_errors: Dict[str, str] = {}

    def _load_inspection_config(self) -> dict:
        cfg_path = Path(__file__).parent.parent / "config" / "inspection_config.yaml"
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def get_all_clusters(self) -> List[dict]:
        """获取所有启用的集群配置"""
        clusters = self.config.get("clusters", [])
        return [c for c in clusters if c.get("enabled", True)]

    def connect_cluster(self, cluster_cfg: dict) -> Tuple[Optional[Elasticsearch], Optional[str]]:
        """连接单个集群，返回 (client, error_msg)"""
        name = cluster_cfg["name"]
        hosts = cluster_cfg.get("hosts", [])
        port = cluster_cfg.get("port", 9200)
        scheme = cluster_cfg.get("scheme", "http")
        auth = cluster_cfg.get("auth", {})
        timeout = self.inspection_cfg.get("inspection", {}).get("timeout_per_api", 15)

        host_list = [f"{scheme}://{h}:{port}" for h in hosts]

        last_error = None
        for host_url in host_list:
            try:
                es = Elasticsearch(
                    [host_url],
                    http_auth=(auth["username"], auth["password"]) if auth.get("username") else None,
                    timeout=timeout,
                    max_retries=1,
                    retry_on_timeout=False,
                )
                if es.ping():
                    logger.info(f"[{name}] 连接成功: {host_url}")
                    self._clients[name] = es
                    return es, None
                else:
                    last_error = f"ping 失败: {host_url}"
            except Exception as e:
                last_error = f"{host_url} -> {type(e).__name__}: {str(e)[:120]}"

        error_msg = f"集群 {name} 所有节点不可达。最后错误: {last_error}"
        self._connection_errors[name] = error_msg
        logger.warning(f"[{name}] {error_msg}")
        return None, error_msg

    def connect_all(self) -> Dict[str, Tuple[Optional[Elasticsearch], Optional[str]]]:
        """连接所有启用的集群"""
        results = {}
        for cluster_cfg in self.get_all_clusters():
            name = cluster_cfg["name"]
            client, error = self.connect_cluster(cluster_cfg)
            results[name] = (client, error)
        return results

    def get_client(self, cluster_name: str) -> Optional[Elasticsearch]:
        return self._clients.get(cluster_name)

    def get_connection_errors(self) -> Dict[str, str]:
        return self._connection_errors

    def api_call(self, cluster_name: str, endpoint: str, **kwargs) -> Optional[dict]:
        """对指定集群执行 API 调用，带重试，返回 dict 或 None"""
        es = self._clients.get(cluster_name)
        if es is None:
            return None

        retry_count = self.inspection_cfg.get("inspection", {}).get("retry_count", 2)
        retry_delay = self.inspection_cfg.get("inspection", {}).get("retry_delay", 3)

        for attempt in range(retry_count + 1):
            try:
                result = self._do_api_call(es, endpoint, **kwargs)
                return result
            except Exception as e:
                if attempt < retry_count:
                    logger.debug(f"[{cluster_name}] {endpoint} 第{attempt+1}次失败，{retry_delay}s后重试: {e}")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"[{cluster_name}] {endpoint} 最终失败: {type(e).__name__}: {e}")
                    return None
        return None

    def _do_api_call(self, es: Elasticsearch, endpoint: str, **kwargs) -> Optional[dict]:
        """实际执行 API 调用，使用 ES 7.x 原生方法"""

        # --- _cluster/* ---
        if endpoint == "_cluster/health":
            return es.cluster.health()
        elif endpoint == "_cluster/stats":
            return es.cluster.stats()
        elif endpoint == "_cluster/settings":
            return es.cluster.get_settings(include_defaults=True)
        elif endpoint == "_cluster/pending_tasks":
            return es.cluster.pending_tasks()

        # --- _nodes/stats ---
        elif endpoint == "_nodes/stats":
            return es.nodes.stats(metric="_all")
        elif endpoint.startswith("_nodes/stats/"):
            metric = endpoint.replace("_nodes/stats/", "")
            return es.nodes.stats(metric=metric)

        # --- _stats ---
        elif endpoint == "_stats":
            return es.indices.stats()

        # --- _cat/* ---
        elif endpoint == "_cat/allocation?v":
            return self._safe_json(es.cat.allocation(format="json"))
        elif endpoint.startswith("_cat/indices"):
            return self._safe_json(es.cat.indices(format="json", s="index"))
        elif endpoint.startswith("_cat/thread_pool"):
            return self._safe_json(es.cat.thread_pool(format="json", h="node_name,name,active,queue,rejected,completed"))

        else:
            logger.warning(f"[未支持的 endpoint] {endpoint}")
            return None

    @staticmethod
    def _safe_json(data) -> Optional[dict]:
        """安全地将 ES 响应转为 dict/list"""
        if data is None:
            return None
        if isinstance(data, (dict, list)):
            return data
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {"raw": data}
        # bytes
        if isinstance(data, bytes):
            try:
                return json.loads(data.decode("utf-8"))
            except Exception:
                return {"raw": data.decode("utf-8", errors="replace")}
        return {"raw": str(data)}

    def close_all(self):
        """关闭所有连接"""
        for name, es in self._clients.items():
            try:
                es.close()
            except Exception:
                pass
        self._clients.clear()
