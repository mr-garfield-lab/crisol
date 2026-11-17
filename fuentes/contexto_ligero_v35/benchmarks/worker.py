#!/usr/bin/env python3
"""Un proceso independiente por version/repeticion; no descarga ni ejecuta el corpus."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

sys.dont_write_bytecode = True
TOKENIZER = None
TOKENIZER_INFO = None


def rss_bytes():
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)
    except (ImportError, AttributeError):
        return None


def load_engine(path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("contexto_v3", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["contexto_v3"] = module
    spec.loader.exec_module(module)
    return module


def measure_text(text):
    return {
        "characters": len(text),
        "utf8_bytes": len(text.encode("utf-8")),
        "estimated_tokens": math.ceil(len(text) / 3),
        "estimate_method": "ceil(unicode_characters / 3); no es limite de tokens reales",
        "measured_tokens": len(TOKENIZER.encode(text, add_special_tokens=False).ids) if TOKENIZER else None,
        "tokenizer": TOKENIZER_INFO,
        "measured_tokens_status": "measured: texto solamente, sin plantilla chat ni tokens especiales" if TOKENIZER else
            "unavailable: no tokenizer de modelo y vocabulario local autorizados; sin descargas",
    }


def ranked_symbols(rows):
    result = []
    for item in rows:
        for symbol in item.get("symbols", []):
            pair = (item["path"], symbol["name"])
            if pair not in result:
                result.append(pair)
    return result


def selection_metrics(ranked, relevant):
    ranked = list(dict.fromkeys(tuple(item) for item in ranked))
    truth = {tuple(item) for item in relevant}
    hits5 = [item for item in ranked[:5] if item in truth]
    hits10 = [item for item in ranked[:10] if item in truth]
    reciprocal = next((1 / i for i, item in enumerate(ranked, 1) if item in truth), 0.0)
    hits = truth.intersection(ranked)
    return {"precision_at_5": len(hits5) / 5,
            "precision_at_5_ceiling": min(5, len(truth)) / 5,
            "precision_returned": len(hits) / len(ranked) if ranked else 0.0,
            "recall_returned": len(hits) / len(truth),
            "true_positives_returned": len(hits),
            "recall_at_10": len(set(hits10)) / len(truth),
            "reciprocal_rank": reciprocal,
            "retrieved_symbols": len(ranked),
            "relevant_symbols": len(truth),
            "hits_at_10": [list(item) for item in hits10]}


def packet_metrics(packet_symbols, retrieved_symbols, relevant, dependency_relevant=None):
    """Mismo denominador en ambas versiones; no elimina dependencias para mejorar precisión."""
    shown = set(tuple(item) for item in packet_symbols)
    retrieved = set(tuple(item) for item in retrieved_symbols)
    truth = set(tuple(item) for item in relevant)
    direct = shown.intersection(retrieved)
    added = shown - retrieved
    expected_deps = None if dependency_relevant is None else set(tuple(item) for item in dependency_relevant)
    expected_files = {path for path, _ in truth}
    shown_files = {path for path, _ in shown}
    return {
        'packet_precision': len(shown & truth) / len(shown) if shown else 0.0,
        'packet_recall': len(shown & truth) / len(truth),
        'packet_symbols_count': len(shown),
        'packet_true_positives': len(shown & truth),
        'ranked_packet_precision': len(direct & truth) / len(direct) if direct else 0.0,
        'ranked_packet_count': len(direct),
        'added_not_ranked_count': len(added),
        'added_not_ranked_symbols': [list(item) for item in sorted(added)],
        'known_dependency_recall': None if not expected_deps else len(shown & expected_deps) / len(expected_deps),
        'packet_file_recall': len(shown_files & expected_files) / len(expected_files),
        'role_assignment': 'included_in_ranking = shown intersect retrieved; added = shown minus retrieved. Added symbols are not automatically judged as dependencies or false positives.',
    }


def original_packet_symbols(text, rows):
    """V3.2 imprime cada fichero en una linea y todos sus simbolos en la siguiente."""
    included = []
    for item in rows:
        prefix = item["path"] + " | sha256:"
        if any(line.startswith(prefix) for line in text.splitlines()):
            included.extend((item["path"], sym["name"]) for sym in item.get("symbols", []))
    return included


def validate_oracles(corpus, tasks):
    cache = {}
    for task in tasks:
        for rel, symbol in task["relevant"] + [task["evidence"]]:
            if rel not in cache:
                tree = ast.parse((corpus / rel).read_bytes())
                names = set()
                def walk(node, parent=()):
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            chain = parent + (child.name,)
                            names.add(".".join(chain))
                            walk(child, chain)
                        else:
                            walk(child, parent)
                walk(tree)
                cache[rel] = names
            if symbol not in cache[rel]:
                raise ValueError(f"Oraculo inexistente: {rel}:{symbol}")


def timed(call, repetitions=3):
    durations = []
    value = None
    for _ in range(repetitions):
        start = time.perf_counter()
        value = call()
        durations.append(time.perf_counter() - start)
    return value, {"samples_seconds": durations, "median_seconds": statistics.median(durations)}


def corpus_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, required=True)
    ap.add_argument("--corpus", type=Path, required=True)
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--tokenizer-json", type=Path)
    args = ap.parse_args()
    if args.tokenizer_json:
        from tokenizers import Tokenizer
        global TOKENIZER, TOKENIZER_INFO
        TOKENIZER = Tokenizer.from_file(str(args.tokenizer_json))
        TOKENIZER.no_truncation()
        TOKENIZER.no_padding()
        TOKENIZER_INFO = {"library": "tokenizers", "file": args.tokenizer_json.name,
                          "sha256": hashlib.sha256(args.tokenizer_json.read_bytes()).hexdigest(),
                          "scope": "solo texto; no acredita equivalencia con Claude/Codex"}
    args.output.mkdir(parents=True, exist_ok=False)
    task_spec = json.loads(args.tasks.read_text(encoding="utf-8"))
    tasks = task_spec["tasks"]
    validate_oracles(args.corpus, tasks)
    hashes_before = corpus_hashes(args.corpus)
    engine = load_engine(args.engine)
    start = time.perf_counter()
    db_path = args.output / "index.sqlite3"
    db = engine.connect(db_path)
    connect_seconds = time.perf_counter() - start
    try:
        cold, cold_t = timed(lambda: engine.scan(args.corpus, db), 1)
        cold_rss = rss_bytes()
        warm, warm_t = timed(lambda: engine.scan(args.corpus, db), 1)
        warm_rss = rss_bytes()
        task_results = []
        retrieval = getattr(engine, 'retrieve', engine.search)
        for task in tasks:
            rows, query_t = timed(lambda: retrieval(db, task["query"], task_spec["query_file_limit"]))
            # Todas las versiones reciben idéntico limite y presupuesto.
            if hasattr(engine, "build_packet"):
                details, packet_t = timed(lambda: engine.build_packet(
                    args.corpus, db, task["query"], task_spec["budget_estimated_tokens"], task_spec["query_file_limit"]))
                text = details["text"]
                packet_symbols = ranked_symbols(details["selected"])
            else:
                text, packet_t = timed(lambda: engine.packet(
                    args.corpus, db, task["query"], task_spec["budget_estimated_tokens"], task_spec["query_file_limit"]))
                packet_symbols = original_packet_symbols(text, rows)
            expected = {tuple(item) for item in task["relevant"]}
            packet_recall = len(expected.intersection(packet_symbols)) / len(expected)
            package_metrics = packet_metrics(packet_symbols, ranked_symbols(rows), task['relevant'], task.get('dependency_relevant'))
            path, symbol = task["evidence"]
            snippet_error = None
            try:
                fragment, snippet_t = timed(lambda: engine.snippet(args.corpus, db, path, symbol, 200))
            except (ValueError, OSError) as exc:
                fragment, snippet_t, snippet_error = "", None, str(exc)
            (args.output / (task["id"] + ".packet.txt")).write_text(text, encoding="utf-8")
            (args.output / (task["id"] + ".snippet.txt")).write_text(fragment, encoding="utf-8")
            task_results.append({
                "id": task["id"], "query": task["query"], "relevant": task["relevant"],
                "ranked_symbols": [list(item) for item in ranked_symbols(rows)],
                "selection": selection_metrics(ranked_symbols(rows), task["relevant"]),
                "packet_recall": packet_recall,
                "package_selection": package_metrics,
                "declared_roles_new_engine_only": {
                    'direct': ranked_symbols(details.get('direct_selected', [])),
                    'dependencies': ranked_symbols(details.get('dependency_selected', []))} if hasattr(engine, 'build_packet') else None,
                "retrieval_api": 'retrieve' if hasattr(engine, 'retrieve') else 'search',
                "packet_symbols": [list(item) for item in packet_symbols],
                "packet": measure_text(text),
                "packet_budget_compliant": len(text) <= task_spec["budget_estimated_tokens"] * 3,
                "evidence_requested": task["evidence"],
                "snippet": measure_text(fragment), "snippet_error": snippet_error,
                "packet_plus_same_requested_snippet": measure_text(text + fragment),
                "same_evidence_file_raw": measure_text((args.corpus / path).read_text(encoding="utf-8")),
                "query_timing": query_t, "packet_timing": packet_t, "snippet_timing": snippet_t,
                "peak_process_rss_bytes": rss_bytes(),
            })
        hashes_after = corpus_hashes(args.corpus)
        if hashes_before != hashes_after:
            raise ValueError('El corpus fue modificado durante el benchmark')
        outcome = {
            "version": args.version, "python": platform.python_version(), "platform": platform.platform(),
            "retrieval_api": 'retrieve' if hasattr(engine, 'retrieve') else 'search',
            "metric_scope": "P@5 unchanged; precision_returned = oracle hits / all returned symbols, same formula for both engines; partial oracle may undervalue useful dependencies",
            "engine_sha256": hashlib.sha256(args.engine.read_bytes()).hexdigest(),
            "tasks_sha256": hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
            "connect_seconds": connect_seconds,
            "cold_scan": {"stats": cold, **cold_t, "peak_process_rss_bytes": cold_rss},
            "warm_scan": {"stats": warm, **warm_t, "peak_process_rss_bytes": warm_rss},
            "peak_process_rss_bytes": rss_bytes(),
            "database_bytes": db_path.stat().st_size,
            "tasks": task_results,
            "corpus_unchanged": True,
            "corpus_file_count": len(hashes_before),
            "corpus_manifest_sha256": hashlib.sha256(json.dumps(hashes_before, sort_keys=True).encode()).hexdigest(),
            "llm_answer_accuracy": None,
            "llm_completion_total_tokens": None,
            "rss_scope": "Pico residente de ESTE proceso completo: importaciones, scan, queries y packet; no incremento atribuible a una llamada.",
            "cold_scope": "Base nueva/proceso nuevo. No se vacia cache del SO; no representa disco frio.",
        }
        (args.output / "metrics.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        db.close()


if __name__ == "__main__":
    main()
