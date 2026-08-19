"""
ES 集群巡检主入口
支持全量巡检和单集群巡检
"""
import sys
import argparse
import logging
import time
from pathlib import Path

# 设置项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.agent import ESInspectionAgent
from core.es_client import ESClientManager
from core.inspector import ClusterInspector
from core.report_generator import ReportGenerator
from core.llm_factory import LLMFactory


def setup_logging(log_level: str = "INFO"):
    """配置日志"""
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"inspection_{timestamp}.log"

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return str(log_file)


def cmd_inspect(args):
    """执行巡检"""
    log_file = setup_logging(args.log_level)
    logger = logging.getLogger("main")
    logger.info(f"日志文件: {log_file}")
    logger.info(f"LLM 提供商: {args.llm_provider or '默认 (配置文件中 active_provider)'}")

    agent = ESInspectionAgent(llm_provider=args.llm_provider)

    if args.cluster:
        # 单集群巡检
        logger.info(f"执行单集群巡检: {args.cluster}")
        summary = agent.run_cluster_inspection(args.cluster)
        print("\n" + "=" * 60)
        print(f"单集群巡检完成: {args.cluster}")
        print(f"  集群数: {summary.get('total_clusters', 0)}")
        print(f"  成功: {summary.get('success', 0)}")
        print(f"  跳过: {summary.get('skipped', 0)}")
        print(f"  严重问题: {summary.get('total_issues', 0)}")
        print(f"  警告: {summary.get('total_warnings', 0)}")
        print(f"  HTML报告: {summary.get('html_report', 'N/A')}")
        print(f"  Markdown: {summary.get('markdown_report', 'N/A')}")
    else:
        # 全量巡检
        logger.info("执行全量集群巡检")
        summary = agent.run_full_inspection()
        print("\n" + "=" * 60)
        print("巡检完成！汇总:")
        print(f"  集群总数: {summary.get('total_clusters', 0)}")
        print(f"  成功: {summary.get('success', 0)}")
        print(f"  失败: {summary.get('failed', 0)}")
        print(f"  跳过: {summary.get('skipped', 0)}")
        print(f"  严重问题: {summary.get('total_issues', 0)}")
        print(f"  警告: {summary.get('total_warnings', 0)}")
        print(f"  HTML报告: {summary.get('html_report', 'N/A')}")
        print(f"  Markdown: {summary.get('markdown_report', 'N/A')}")
        print("=" * 60)

        if summary.get("llm_analysis"):
            print("\n--- LLM 分析报告 ---")
            print(summary["llm_analysis"])


def cmd_test_connection(args):
    """测试集群连接"""
    setup_logging("DEBUG")
    logger = logging.getLogger("main")
    logger.info("测试所有集群连接...")

    manager = ESClientManager()
    results = manager.connect_all()

    print("\n连接测试结果:")
    print("-" * 60)
    for name, (client, error) in results.items():
        if client:
            # 获取版本信息
            try:
                info = client.info()
                version = info.get("version", {}).get("number", "unknown")
                print(f"  [OK] {name} - 连接成功 (ES版本: {version})")
            except Exception:
                print(f"  [OK] {name} - 连接成功")
        else:
            print(f"  [ERR] {name} - {error}")
    print("-" * 60)
    manager.close_all()


def cmd_list_llm(args):
    """列出可用的 LLM 提供商"""
    factory = LLMFactory()
    providers = factory.list_providers()
    active = factory.get_active_provider()
    print(f"\n当前活跃 LLM: {active}")
    print(f"可用提供商: {', '.join(providers)}")


def cmd_add_cluster(args):
    """添加新集群到配置文件"""
    import yaml
    config_path = project_root / "config" / "clusters.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    new_cluster = {
        "name": args.name,
        "hosts": args.hosts.split(","),
        "port": args.port,
        "scheme": args.scheme,
        "auth": {
            "username": args.username or "db_ops",
            "password": args.password or "Yumchina1234",
        },
        "enabled": True,
        "tags": args.tags.split(",") if args.tags else [],
    }

    config["clusters"].append(new_cluster)

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"[OK] 集群 {args.name} 已添加到配置文件")


def main():
    parser = argparse.ArgumentParser(
        description="ES 集群智能巡检工具 (LangChain Agent)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 全量巡检 (使用默认 LLM)
  python main.py inspect

  # 使用 DeepSeek 进行巡检
  python main.py inspect --llm deepseek

  # 巡检指定集群
  python main.py inspect --cluster cluster-01-3node

  # 测试所有集群连接
  python main.py test-connection

  # 列出可用 LLM
  python main.py list-llm

  # 添加新集群
  python main.py add-cluster --name cluster-16 --hosts "192.168.3.101,192.168.3.102" --port 9200
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # inspect 子命令
    inspect_parser = subparsers.add_parser("inspect", help="执行集群巡检")
    inspect_parser.add_argument("--cluster", "-c", help="指定集群名称 (留空则巡检全部)")
    inspect_parser.add_argument("--llm", "--llm-provider", dest="llm_provider",
                                help="LLM 提供商名称 (如 openai, deepseek, ollama)")
    inspect_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    # test-connection 子命令
    subparsers.add_parser("test-connection", help="测试集群连接")

    # list-llm 子命令
    subparsers.add_parser("list-llm", help="列出可用 LLM 提供商")

    # add-cluster 子命令
    add_parser = subparsers.add_parser("add-cluster", help="添加新集群配置")
    add_parser.add_argument("--name", required=True, help="集群名称")
    add_parser.add_argument("--hosts", required=True, help="节点地址 (逗号分隔)")
    add_parser.add_argument("--port", type=int, default=9200, help="端口 (默认9200)")
    add_parser.add_argument("--scheme", default="http", help="协议 (http/https)")
    add_parser.add_argument("--username", help="用户名 (默认 db_ops)")
    add_parser.add_argument("--password", help="密码 (默认 Yumchina1234)")
    add_parser.add_argument("--tags", help="标签 (逗号分隔)")

    args = parser.parse_args()

    if args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "test-connection":
        cmd_test_connection(args)
    elif args.command == "list-llm":
        cmd_list_llm(args)
    elif args.command == "add-cluster":
        cmd_add_cluster(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()



