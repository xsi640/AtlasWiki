---
title: RAG 的工程复杂度来自哪里
source_type: text
captured_at: '2026-09-15 00:34:05'
origin: manual
detected_type: text
---

# RAG 的工程复杂度来自哪里

RAG 系统的复杂度主要来自三块：分块策略、嵌入模型、向量数据库运维。
分块粒度太小会丢失上下文，太大会稀释语义。嵌入模型换了就要全量重建索引。

相比之下 LLM Wiki 的复杂度几乎为零，代价是每次查询要消耗更多 token 去读页面。
在中等规模（约 100 篇素材）时，LLM Wiki 的索引加摘要已经足够让模型高效定位信息。
