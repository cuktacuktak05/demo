"""Evaluation harness for RAG retrieval methods and threshold calibration.
Measures: Precision@1, Precision@3, Recall@3, MRR, nDCG@3, Latency, and Insufficient Context Accuracy.
"""
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Path configurations
BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BASE_DIR / "evaluation" / "retrieval_dataset.json"
KB_DIR = BASE_DIR / "knowledge_base"
OUTPUT_METRICS_PATH = BASE_DIR / "evaluation" / "retrieval_metrics.csv"


def load_dataset() -> List[Dict[str, Any]]:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def calculate_metrics(
    eval_dataset: List[Dict[str, Any]],
    retriever_func,
    top_k: int = 3,
    threshold: float = 0.0,
) -> Dict[str, Any]:
    """Calculate standard IR metrics and abstention metrics for a retriever."""
    p1_list = []
    p3_list = []
    r3_list = []
    mrr_list = []
    ndcg3_list = []
    latencies = []

    # Abstention confusion matrix:
    # Positive = ground truth is insufficient_context (should reject)
    # Negative = ground truth is relevant (should retrieve)
    tp = 0  # correctly rejected
    fp = 0  # falsely rejected (relevant query got insufficient_context)
    tn = 0  # correctly retrieved
    fn = 0  # falsely retrieved (irrelevant query got non-empty chunks)

    query_details = []

    for item in eval_dataset:
        query = item["query"]
        expected_ids = set(item.get("expected_chunk_ids", []))
        expected_status = item.get("expected_status", "relevant")

        t0 = time.perf_counter()
        retrieved_result = retriever_func(query, top_k=top_k, threshold=threshold)
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        retrieved_ids = [c["chunk_id"] for c in retrieved_result]
        is_empty = len(retrieved_result) == 0

        # Abstention evaluation
        if expected_status == "insufficient_context":
            if is_empty:
                tp += 1
                query_abstain_correct = True
            else:
                fn += 1
                query_abstain_correct = False
        else:
            if is_empty:
                fp += 1
                query_abstain_correct = False
            else:
                tn += 1
                query_abstain_correct = True

        # Ranked retrieval evaluation (only on relevant queries where expected_ids is non-empty)
        if expected_ids:
            # Precision@1
            top1_hit = 1.0 if (retrieved_ids and retrieved_ids[0] in expected_ids) else 0.0
            p1_list.append(top1_hit)

            # Precision@3
            hits_3 = sum(1 for cid in retrieved_ids[:top_k] if cid in expected_ids)
            p3 = hits_3 / top_k
            p3_list.append(p3)

            # Recall@3
            r3 = hits_3 / len(expected_ids)
            r3_list.append(r3)

            # MRR (first relevant rank)
            rr = 0.0
            for rank, cid in enumerate(retrieved_ids[:top_k], start=1):
                if cid in expected_ids:
                    rr = 1.0 / rank
                    break
            mrr_list.append(rr)

            # nDCG@3
            dcg = 0.0
            for rank, cid in enumerate(retrieved_ids[:top_k], start=1):
                rel = 1.0 if cid in expected_ids else 0.0
                dcg += rel / math.log2(rank + 1)

            idcg = 0.0
            ideal_hits = min(top_k, len(expected_ids))
            for rank in range(1, ideal_hits + 1):
                idcg += 1.0 / math.log2(rank + 1)

            ndcg = (dcg / idcg) if idcg > 0 else 0.0
            ndcg3_list.append(ndcg)
        else:
            # For out-of-domain / out-of-KB queries:
            # If retrieved is empty: perfect behavior
            pass

        query_details.append({
            "id": item["id"],
            "query": query,
            "category": item["category"],
            "expected_status": expected_status,
            "expected_ids": list(expected_ids),
            "retrieved_ids": retrieved_ids,
            "retrieved_scores": [round(c.get("score", 0.0), 4) for c in retrieved_result],
            "is_empty": is_empty,
            "latency_ms": round(latency_ms, 2),
            "abstain_correct": query_abstain_correct,
        })

    # Aggregate metrics
    mean_p1 = float(np.mean(p1_list)) if p1_list else 0.0
    mean_p3 = float(np.mean(p3_list)) if p3_list else 0.0
    mean_r3 = float(np.mean(r3_list)) if r3_list else 0.0
    mean_mrr = float(np.mean(mrr_list)) if mrr_list else 0.0
    mean_ndcg3 = float(np.mean(ndcg3_list)) if ndcg3_list else 0.0

    abstain_total = tp + fp + tn + fn
    abstain_accuracy = (tp + tn) / abstain_total if abstain_total > 0 else 0.0
    abstain_precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    abstain_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    abstain_f1 = (
        2 * abstain_precision * abstain_recall / (abstain_precision + abstain_recall)
        if (abstain_precision + abstain_recall) > 0
        else 0.0
    )

    p50_lat = float(np.percentile(latencies, 50))
    p95_lat = float(np.percentile(latencies, 95))
    mean_lat = float(np.mean(latencies))

    return {
        "precision_at_1": round(mean_p1, 4),
        "precision_at_3": round(mean_p3, 4),
        "recall_at_3": round(mean_r3, 4),
        "mrr": round(mean_mrr, 4),
        "ndcg_at_3": round(mean_ndcg3, 4),
        "abstain_accuracy": round(abstain_accuracy, 4),
        "abstain_precision": round(abstain_precision, 4),
        "abstain_recall": round(abstain_recall, 4),
        "abstain_f1": round(abstain_f1, 4),
        "latency_mean_ms": round(mean_lat, 2),
        "latency_p50_ms": round(p50_lat, 2),
        "latency_p95_ms": round(p95_lat, 2),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "query_details": query_details,
    }
