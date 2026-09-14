---
type: index
created: '2026-09-15'
updated: '2026-09-15'
title: 索引
---

# 索引

共 15 个页面。

## 总览
- [[总览]] — 
- [[约定]] — 

## 素材（6）
- [[LLM Wiki 的核心是让模型维护一个持久化的 markdown 知识库。知识编译只做一次，之后每次查询都复用已经整理]] — LLM Wiki 的核心是让模型维护一个持久化的 markdown 知识库。知识编译只做一次，之后每次查询都复用已经整理好的页面，而不是重新做向量检索。Karpathy 认为维护成本才是知识库失败的根本原因。 · 引用 1 个素材
- [[Large language model - Wikipedia]] — A large language model (LLM) is an AI model (typically a neural network)) trained on a vast amount of text for natural… · 引用 1 个素材
- [[RAG 的工程复杂度来自哪里]] — RAG 系统的复杂度主要来自三块：分块策略、嵌入模型、向量数据库运维。 分块粒度太小会丢失上下文，太大会稀释语义。嵌入模型换了就要全量重建索引。 相比之下 LLM Wiki 的复杂度几乎为零，代价是每次查询要消耗更多 token 去读页面… · 引用 1 个素材
- [[Retrieval-augmented generation - Wikipedia]] — Retrieval-augmented generation (RAG) is a technique that enables large language models (LLMs) to retrieve and… · 引用 1 个素材
- [[为什么 LLM Wiki 比 RAG 更适合个人知识库]] — RAG 的做法是把文档切块、做向量嵌入，查询时召回最相似的片段再交给模型生成答案。 问题是每次查询模型都在从头重新发现知识，没有任何积累。 LLM Wiki 换了个思路：让模型增量维护一个持久化的 markdown 知识库。 新素材进来时… · 引用 1 个素材
- [[知识编译与增量维护的取舍]] — 知识编译与增量维护的取舍。LLM Wiki 的代价是每次查询都要读页面，好处是知识会复利增长。向量检索每次都要重新召回，无法积累。 · 引用 1 个素材

## 概念（9）
- [[Google]] — 聚合自 2 篇素材
- [[LLM Wiki]] — 聚合自 4 篇素材
- [[Retrieval]] — 聚合自 2 篇素材
- [[向量]] — 聚合自 4 篇素材
- [[嵌入]] — 聚合自 2 篇素材
- [[查询]] — 聚合自 4 篇素材
- [[模型]] — 聚合自 3 篇素材
- [[知识]] — 聚合自 3 篇素材
- [[维护]] — 聚合自 3 篇素材
