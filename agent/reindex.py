"""
知识库全量重建入口（离线运维脚本）

第一次上线「实体档案」功能、或怀疑向量库与 DB 漂移时，跑一次把存量数据补齐。
增量钩子只覆盖「之后的变动」，存量的 task/project/附件得靠本脚本建索引。

幂等：内部都是「先按 metadata 删旧、再灌新」，重复跑不会堆重复档案，可安全重试。

环境无关：在哪台机器跑就同步哪个环境——config 会按 .env.dev / .env.prod 注入对应的
AGENT_DB_URL（向量库）与 EMBED_HOST（ollama）。所以 dev/prod 命令完全一样：

    uv run python -m agent.reindex            # 全量：实体档案 + 附件正文
    uv run python -m agent.reindex --entities # 只重建实体档案（描述/子任务/评论/附件名）
    uv run python -m agent.reindex --attachments  # 只重建附件正文

每份档案 / 每个附件都要过一次远程 embedding，数百份会跑几分钟，进度会打日志。
"""
import argparse
import sys

from loguru import logger


def main() -> int:
    parser = argparse.ArgumentParser(description="知识库全量重建")
    parser.add_argument("--entities", action="store_true", help="只重建实体档案")
    parser.add_argument("--attachments", action="store_true", help="只重建附件正文")
    args = parser.parse_args()

    # 都不指定 = 两样都做
    do_entities = args.entities or not args.attachments
    do_attachments = args.attachments or not args.entities

    from agent.knowledge import build_knowledge, index_entities, index_attachments

    logger.info("知识库全量重建开始（建表 + 装配 ...）")
    build_knowledge()  # 触发建表 / 装配，失败在这里就暴露

    if do_attachments:
        logger.info("=== 重建附件正文索引 ===")
        stat = index_attachments()
        logger.info("附件正文完成：{}", stat)

    if do_entities:
        logger.info("=== 重建实体档案索引 ===")
        stat = index_entities()
        logger.info("实体档案完成：{}", stat)

    logger.info("知识库全量重建结束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
