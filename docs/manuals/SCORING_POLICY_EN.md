# Paper Morning Scoring Policy

This document explains how Paper Morning decides whether a paper is relevant enough to surface.

It is not a full dump of every runtime prompt. The goal is to document the scoring contract, not freeze every implementation detail.

## 1) Retrieval first, scoring second
Paper Morning does not ask the LLM to rank the entire paper universe.

The pipeline is:
1. generate source-specific queries from research context
2. retrieve candidates from sources such as arXiv and PubMed
3. build a shortlist
4. run listwise LLM reranking on that shortlist

Current shortlist control:
- `LLM_MAX_CANDIDATES` caps the number of papers sent into listwise reranking
- default is `30`

## 2) Search intent layer
Search intent affects retrieval and ranking expectations.

### `whats_new`
- recent papers first
- adaptive window expansion up to the requested horizon
- still expects direct usefulness

### `best_match`
- strongest fit inside the selected horizon
- favors direct overlap and practical reuse

### `discovery`
- broader search for adjacent but reusable work
- allows credible transfer from nearby domains

## 3) Topic relevance modes
Each topic can carry a scoring mode.

### `strict`
- threshold: `7.5`
- precision-first
- adjacent papers can pass, but only with a very strong reuse path

### `balanced`
- threshold: `6.0`
- default mode
- allows clearly reusable methods papers, not only exact topic matches

### `discovery`
- threshold: `5.0`
- broader acceptance for high-upside adjacent work
- still rejects generic buzzword overlap

Source of truth in code:
- `app/scoring_policy.py`

## 4) What the LLM is asked to produce
For each shortlisted paper, the LLM is asked for:
- `relevance_score`
- `relevance_reason`
- `core_point`
- `usefulness`
- `evidence_spans`

`evidence_spans` must be short copied phrases from the title or abstract.

## 5) Evidence-aware gating
Paper Morning uses an extra safety rule:
- if a paper gets score `>= 7.0` but has no evidence spans, it is downgraded

Purpose:
- reduce unsupported score inflation
- make high scores easier to audit later

## 6) Current tradeoff
Paper Morning currently uses listwise reranking over a capped shortlist, instead of many tiny batch calls.

Why:
- better cross-paper calibration
- easier to keep one shared scale

Known tradeoff:
- very long shortlists can degrade consistency
- for now the system uses shortlist capping rather than more complex token-aware chunk orchestration

This is an active design tradeoff, not an accidental omission.

## 7) What is intentionally not promised
The score is not a claim of scientific truth.

It is a ranking signal for:
- practical usefulness
- methodological reuse potential
- relevance to the stated project context

It should be read as a selection tool, not as a paper-quality benchmark.
