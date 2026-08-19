"""
HTML 报告生成模块
将巡检结果生成美观的 HTML 报告
"""
import os
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("es_inspector")


class ReportGenerator:
    """巡检报告生成器"""

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "reports"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(self, all_results: List[dict], summary: dict) -> str:
        """生成完整的 HTML 巡检报告，返回文件路径"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"es_inspection_{timestamp}.html"
        filepath = self.output_dir / filename

        html = self._build_html(all_results, summary)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"报告已生成: {filepath}")
        return str(filepath)

    def _build_html(self, results: List[dict], summary: dict) -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        total = summary.get("total_clusters", len(results))
        success = summary.get("success", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)
        total_issues = summary.get("total_issues", 0)
        total_warnings = summary.get("total_warnings", 0)

        # 概览卡片颜色
        green = "#27ae60" if failed == 0 and skipped == 0 else "#f39c12"
        red = "#e74c3c" if failed > 0 else "#27ae60"
        yellow = "#f39c12" if total_warnings > 0 else "#27ae60"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ES 集群巡检报告 - {ts}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #333; line-height: 1.6; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: white; padding: 30px 40px; }}
.header h1 {{ font-size: 24px; margin-bottom: 8px; }}
.header .subtitle {{ opacity: 0.8; font-size: 14px; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 20px 0; }}
.summary-card {{ background: white; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.summary-card .number {{ font-size: 36px; font-weight: 700; }}
.summary-card .label {{ font-size: 13px; color: #666; margin-top: 4px; }}
.section {{ background: white; border-radius: 12px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow: hidden; }}
.section-title {{ padding: 16px 24px; font-size: 16px; font-weight: 600; border-bottom: 1px solid #eee; background: #fafbfc; }}
.section-body {{ padding: 20px 24px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
th {{ background: #f8f9fa; font-weight: 600; color: #555; }}
tr:hover {{ background: #f8f9fa; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }}
.badge-green {{ background: #d4edda; color: #155724; }}
.badge-yellow {{ background: #fff3cd; color: #856404; }}
.badge-red {{ background: #f8d7da; color: #721c24; }}
.badge-gray {{ background: #e9ecef; color: #495057; }}
.cluster-card {{ border: 1px solid #e8e8e8; border-radius: 10px; margin: 16px 0; overflow: hidden; }}
.cluster-header {{ padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }}
.cluster-header:hover {{ background: #f5f5f5; }}
.cluster-name {{ font-weight: 600; font-size: 15px; }}
.cluster-body {{ padding: 0 20px 20px; }}
.metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 12px 0; }}
.metric-item {{ background: #f8f9fa; border-radius: 8px; padding: 12px; }}
.metric-item .metric-label {{ font-size: 12px; color: #888; }}
.metric-item .metric-value {{ font-size: 18px; font-weight: 600; margin-top: 4px; }}
.issue-list {{ margin: 12px 0; }}
.issue-item {{ padding: 8px 12px; margin: 4px 0; border-radius: 6px; font-size: 13px; }}
.issue-critical {{ background: #f8d7da; border-left: 3px solid #dc3545; }}
.issue-warning {{ background: #fff3cd; border-left: 3px solid #ffc107; }}
.skipped {{ color: #999; font-style: italic; padding: 16px; }}
.node-table {{ margin: 12px 0; }}
.collapsible {{ display: none; }}
.expanded {{ display: block; }}
.toggle-btn {{ background: none; border: 1px solid #ddd; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 12px; }}
.footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
</style>
<script>
function toggleSection(id) {{
    var el = document.getElementById(id);
    el.classList.toggle('expanded');
    el.style.display = el.classList.contains('expanded') ? 'block' : 'none';
}}
</script>
</head>
<body>

<div class="header">
    <h1>🔍 ES 集群巡检报告</h1>
    <div class="subtitle">巡检时间: {ts} | 集群总数: {total} | 生成工具: ES Inspector (LangChain Agent)</div>
</div>

<div class="container">
    <!-- 概览卡片 -->
    <div class="summary-grid">
        <div class="summary-card">
            <div class="number" style="color: #333">{total}</div>
            <div class="label">集群总数</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: {green}">{success}</div>
            <div class="label">巡检成功</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: {red}">{failed}</div>
            <div class="label">巡检失败</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: #999">{skipped}</div>
            <div class="label">已跳过</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: #e74c3c">{total_issues}</div>
            <div class="label">严重问题</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color: #f39c12">{total_warnings}</div>
            <div class="label">警告信息</div>
        </div>
    </div>
"""

        # 各集群详细报告
        for i, result in enumerate(results):
            cid = f"cluster_{i}"
            name = result.get("cluster_name", "unknown")
            status = result.get("status", "unknown")
            issues = result.get("issues", [])
            warnings = result.get("warnings", [])

            status_badge = {
                "success": '<span class="badge badge-green">正常</span>',
                "partial": '<span class="badge badge-yellow">部分完成</span>',
                "skipped": '<span class="badge badge-gray">已跳过</span>',
                "failed": '<span class="badge badge-red">失败</span>',
            }.get(status, f'<span class="badge badge-gray">{status}</span>')

            html += f"""
    <div class="cluster-card">
        <div class="cluster-header" onclick="toggleSection('{cid}')">
            <div>
                <span class="cluster-name">{name}</span>
                {status_badge}
                <span style="margin-left:8px; font-size:12px; color:#999">
                    标签: {', '.join(result.get('cluster_tags', []))} |
                    节点: {len(result.get('hosts', []))} |
                    严重: {len(issues)} | 警告: {len(warnings)}
                </span>
            </div>
            <button class="toggle-btn">展开/收起</button>
        </div>
        <div class="cluster-body collapsible" id="{cid}">
"""
            if status == "skipped":
                html += f'<div class="skipped">⚠️ 跳过原因: {result.get("error", "未知")}</div>\n'
            else:
                # 概览指标
                health = result.get("cluster_health", {})
                biz = result.get("business_metrics", {})
                html += f"""
            <div class="metric-grid">
                <div class="metric-item">
                    <div class="metric-label">集群状态</div>
                    <div class="metric-value">{health.get('status', 'N/A')}</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">节点数</div>
                    <div class="metric-value">{health.get('number_of_nodes', 'N/A')}</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">活跃分片</div>
                    <div class="metric-value">{health.get('active_shards', 'N/A')}</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">文档总数</div>
                    <div class="metric-value">{biz.get('total_doc_count', 'N/A'):,}</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">存储大小</div>
                    <div class="metric-value">{biz.get('total_store_size_gb', 'N/A')} GB</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">索引数量</div>
                    <div class="metric-value">{biz.get('total_indices', 'N/A')}</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">搜索延迟</div>
                    <div class="metric-value">{biz.get('search_latency_ms', 'N/A')} ms</div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">文档删除率</div>
                    <div class="metric-value">{biz.get('doc_deletion_ratio_percent', 'N/A')}%</div>
                </div>
            </div>
"""
                # 问题列表
                if issues:
                    html += '<div class="issue-list"><strong style="color:#e74c3c">🚨 严重问题:</strong>\n'
                    for issue in issues:
                        html += f'<div class="issue-item issue-critical">[{issue.get("category", "")}] {issue.get("message", "")}</div>\n'
                    html += '</div>\n'

                if warnings:
                    html += '<div class="issue-list"><strong style="color:#f39c12">⚠️ 警告:</strong>\n'
                    for w in warnings:
                        html += f'<div class="issue-item issue-warning">[{w.get("category", "")}] {w.get("message", "")}</div>\n'
                    html += '</div>\n'

                # 节点详情表
                node_stats = result.get("node_stats", {}).get("nodes", {})
                if node_stats:
                    html += """
            <div class="node-table">
            <strong>节点详情:</strong>
            <table>
            <tr><th>节点名称</th><th>JVM堆使用率</th><th>CPU</th><th>磁盘使用率</th><th>堆内存</th></tr>
"""
                    for nid, ndata in node_stats.items():
                        nname = ndata.get("name", nid)
                        jvm_pct = self._deep_get(ndata, ["jvm", "mem", "heap_used_percent"], "N/A")
                        cpu_pct = self._deep_get(ndata, ["os", "cpu", "percent"], "N/A")
                        disk_pct = self._deep_get(ndata, ["fs", "total", "used_percent"], "N/A")
                        heap_used = self._deep_get(ndata, ["jvm", "mem", "heap_used_in_bytes"], 0)
                        heap_max = self._deep_get(ndata, ["jvm", "mem", "heap_max_in_bytes"], 0)
                        heap_str = f"{round(heap_used/1024**3, 1)}/{round(heap_max/1024**3, 1)} GB"

                        # 颜色标注
                        def pct_color(v):
                            if isinstance(v, (int, float)):
                                if v > 85: return "color:#e74c3c;font-weight:600"
                                if v > 70: return "color:#f39c12;font-weight:600"
                            return ""

                        html += f"""<tr>
                            <td>{nname}</td>
                            <td style="{pct_color(jvm_pct)}">{jvm_pct}%</td>
                            <td style="{pct_color(cpu_pct)}">{cpu_pct}%</td>
                            <td style="{pct_color(disk_pct)}">{disk_pct}%</td>
                            <td>{heap_str}</td>
                        </tr>\n"""
                    html += "</table></div>\n"

                # 原始数据折叠
                html += f"""
            <details style="margin-top:12px">
                <summary style="cursor:pointer;color:#666;font-size:13px">📦 查看原始巡检数据 (JSON)</summary>
                <pre style="background:#f8f9fa;padding:12px;border-radius:6px;font-size:11px;overflow-x:auto;max-height:400px;overflow-y:auto">{json.dumps(result, ensure_ascii=False, indent=2, default=str)[:8000]}</pre>
            </details>
"""
            html += """
        </div>
    </div>
"""

        html += f"""
    <div class="footer">
        ES 集群巡检报告 | 由 LangChain ES Inspector 自动生成 | {ts}
    </div>
</div>
</body>
</html>"""
        return html

    @staticmethod
    def _deep_get(data, keys, default=None):
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current if current is not None else default

    def generate_markdown_summary(self, all_results: List[dict], summary: dict) -> str:
        """生成 Markdown 格式的摘要报告"""
        ts = time.strftime("%Y%m%d_%H%M%S")
        md_path = self.output_dir / f"es_inspection_summary_{ts}.md"

        lines = [
            f"# ES 集群巡检摘要报告",
            f"",
            f"**巡检时间:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## 概览",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 集群总数 | {summary.get('total_clusters', 0)} |",
            f"| 巡检成功 | {summary.get('success', 0)} |",
            f"| 巡检失败 | {summary.get('failed', 0)} |",
            f"| 已跳过 | {summary.get('skipped', 0)} |",
            f"| 严重问题 | {summary.get('total_issues', 0)} |",
            f"| 警告信息 | {summary.get('total_warnings', 0)} |",
            f"",
            f"## 各集群状态",
            f"",
        ]

        for r in all_results:
            name = r.get("cluster_name", "?")
            status = r.get("status", "?")
            issues = len(r.get("issues", []))
            warnings = len(r.get("warnings", []))
            health_status = r.get("cluster_health", {}).get("status", "N/A")
            lines.append(f"### {name} [{status}]")
            lines.append(f"- 集群状态: {health_status}")
            lines.append(f"- 严重问题: {issues}")
            lines.append(f"- 警告: {warnings}")
            if r.get("error"):
                lines.append(f"- 错误: {r['error']}")
            lines.append("")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"Markdown 摘要已生成: {md_path}")
        return str(md_path)
