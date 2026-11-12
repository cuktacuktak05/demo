"""Benchmark and threshold calibration script for Session 2 RAG evaluation.
Evaluates:
- Method A: TF-IDF
- Method B: BM25
- Method C: Dense Embedding (Multilingual MiniLM)
- Method D: Hybrid (BM25 + Dense Embedding with RRF)

Calculates P@1, P@3, R@3, MRR, nDCG@3, Latency, and Insufficient Context Accuracy.
Finds optimal threshold for each method.
Outputs evaluation/retrieval_metrics.csv.
"""
import csv
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.rag import (
    retrieve_tfidf,
    retrieve_bm25,
    retrieve_embedding,
    retrieve_hybrid,
    load_documents,
    CALIBRATED_THRESHOLDS,
)

DATASET_PATH = BASE_DIR / "evaluation" / "retrieval_dataset.json"
OUTPUT_METRICS_PATH = BASE_DIR / "evaluation" / "retrieval_metrics.csv"


def load_dataset() -> List[Dict[str, Any]]:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def calculate_metrics_for_method(
    eval_dataset: List[Dict[str, Any]],
    retriever_func,
    method_name: str,
    top_k: int = 3,
    threshold: Optional[float] = None,
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
        "method": method_name,
        "threshold": threshold,
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


def main():
    dataset = load_dataset()
    docs = load_documents()
    print(f"Loaded {len(docs)} KB chunks and {len(dataset)} evaluation queries.")

    method_configs = [
        ("TF-IDF (Baseline)", retrieve_tfidf, [0.10, 0.15, 0.20, 0.25], 0.20),
        ("BM25", retrieve_bm25, [3.0, 5.0, 7.0, 10.0], 5.0),
        ("Embedding (Semantic)", retrieve_embedding, [0.35, 0.40, 0.45, 0.50], 0.45),
        ("Hybrid (BM25+Dense)", retrieve_hybrid, [0.020, 0.025, 0.028, 0.030], 0.028),
    ]

    best_results = []
    print("\n" + "=" * 90)
    print("CALIBRATING RETRIEVAL THRESHOLDS")
    print("=" * 90)

    for name, retriever, thresholds, default_t in method_configs:
        print(f"\n--- {name} ---")
        best_f1 = -1.0
        best_res = None
        for t in thresholds:
            res = calculate_metrics_for_method(dataset, retriever, name, top_k=3, threshold=t)
            score_comb = res["abstain_f1"] * 0.5 + res["ndcg_at_3"] * 0.5
            print(
                f"  Thresh={t:6.3f} | P@1={res['precision_at_1']:.3f} | R@3={res['recall_at_3']:.3f} | "
                f"nDCG@3={res['ndcg_at_3']:.3f} | Abstain_Acc={res['abstain_accuracy']:.3f} | "
                f"Abstain_F1={res['abstain_f1']:.3f} (TP={res['tp']}, FP={res['fp']}, TN={res['tn']}, FN={res['fn']})"
            )
            if score_comb > best_f1:
                best_f1 = score_comb
                best_res = res
        best_results.append(best_res)

    # Save benchmark table
    headers = [
        "Method", "Calibrated_Threshold", "Precision@1", "Precision@3", "Recall@3", "MRR", "nDCG@3",
        "Abstain_Accuracy", "Abstain_Precision", "Abstain_Recall", "Abstain_F1",
        "Latency_Mean_ms", "Latency_P50_ms", "Latency_P95_ms"
    ]

    csv_rows = []
    print("\n" + "=" * 120)
    print("FINAL RETRIEVAL BENCHMARK COMPARISON TABLE")
    print("=" * 120)
    print(f"{headers[0]:<22} | {headers[1]:<10} | {headers[2]:<5} | {headers[3]:<5} | {headers[4]:<5} | {headers[5]:<5} | {headers[6]:<7} | {headers[7]:<11} | {headers[8]:<9} | {headers[9]:<9} | {headers[10]:<10} | {headers[11]:<10} | {headers[12]:<10} | {headers[13]:<10}")
    print("-" * 150)

    for r in best_results:
        row = [
            r["method"],
            str(r["threshold"]),
            r["precision_at_1"],
            r["precision_at_3"],
            r["recall_at_3"],
            r["mrr"],
            r["ndcg_at_3"],
            r["abstain_accuracy"],
            r["abstain_precision"],
            r["abstain_recall"],
            r["abstain_f1"],
            r["latency_mean_ms"],
            r["latency_p50_ms"],
            r["latency_p95_ms"],
        ]
        csv_rows.append(row)
        print(
            f"{r['method']:<22} | {str(r['threshold']):<10} | {r['precision_at_1']:<5.3f} | {r['precision_at_3']:<5.3f} | "
            f"{r['recall_at_3']:<5.3f} | {r['mrr']:<5.3f} | {r['ndcg_at_3']:<7.3f} | "
            f"{r['abstain_accuracy']:<11.3f} | {r['abstain_precision']:<9.3f} | {r['abstain_recall']:<9.3f} | "
            f"{r['abstain_f1']:<10.3f} | {r['latency_mean_ms']:<10.2f} | {r['latency_p50_ms']:<10.2f} | "
            f"{r['latency_p95_ms']:<10.2f}"
        )

    with open(OUTPUT_METRICS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(csv_rows)

    print(f"\nSaved metrics CSV to: {OUTPUT_METRICS_PATH}")


if __name__ == "__main__":
    main()
