#!/usr/bin/env python3
"""
Phase 5 Performance Benchmark

Compares performance before and after Phase 5 optimizations:
- Query caching
- Parallel execution
- Error handling
- SimpleGraph (vs NetworkX)
"""

import time
import json
from pathlib import Path
from typing import List

# Import both versions for comparison
from test_search import LocalEmbeddingSearch
from hybrid_retrieval import HybridRetrieval
from hybrid_retrieval_enhanced import EnhancedHybridRetrieval


def benchmark_search_system(search_system, queries: List[str], n_results: int = 5):
    """
    Benchmark a search system with test queries.

    Args:
        search_system: Search system instance
        queries: List of test queries
        n_results: Number of results per query

    Returns:
        Performance metrics
    """
    times = []

    for query in queries:
        start = time.time()

        if hasattr(search_system, 'hybrid_search'):
            results = search_system.hybrid_search(query, n_results=n_results)
        else:
            results = search_system.search(query, n_results=n_results)

        elapsed = (time.time() - start) * 1000  # Convert to ms
        times.append(elapsed)

    avg_time = sum(times) / len(times) if times else 0
    min_time = min(times) if times else 0
    max_time = max(times) if times else 0

    return {
        'avg_ms': round(avg_time, 2),
        'min_ms': round(min_time, 2),
        'max_ms': round(max_time, 2),
        'total_queries': len(queries)
    }


def run_comprehensive_benchmark():
    """Run comprehensive benchmark comparing all systems."""
    print("=" * 80)
    print("PHASE 5 PERFORMANCE BENCHMARK")
    print("=" * 80)
    print()

    # Test queries (mix of different types)
    test_queries = [
        "How do I control animation speed?",
        "audio visualization with FFT",
        "3D camera controls",
        "particle system effects",
        "noise patterns and generation",
        "rendering with materials and lighting",
        "MIDI control and OSC networking",
        "video playback and movie files",
        "data table operations",
        "geometry deformation techniques",
    ]

    print(f"Test queries: {len(test_queries)}")
    print()

    # Benchmark 1: Basic Vector Search (LocalEmbeddingSearch)
    print("-" * 80)
    print("1. BASIC VECTOR SEARCH (Baseline)")
    print("-" * 80)
    print("Loading...")
    basic_search = LocalEmbeddingSearch()
    print("Benchmarking...")
    basic_stats = benchmark_search_system(basic_search, test_queries)
    print(f"  Average: {basic_stats['avg_ms']} ms")
    print(f"  Min: {basic_stats['min_ms']} ms")
    print(f"  Max: {basic_stats['max_ms']} ms")
    print()

    # Benchmark 2: Hybrid Search (with NetworkX - if working)
    print("-" * 80)
    print("2. HYBRID SEARCH (Vector + Graph)")
    print("-" * 80)
    print("Loading...")
    try:
        hybrid_search = HybridRetrieval()
        print("Benchmarking...")
        hybrid_stats = benchmark_search_system(hybrid_search, test_queries)
        print(f"  Average: {hybrid_stats['avg_ms']} ms")
        print(f"  Min: {hybrid_stats['min_ms']} ms")
        print(f"  Max: {hybrid_stats['max_ms']} ms")

        improvement = ((basic_stats['avg_ms'] - hybrid_stats['avg_ms']) / basic_stats['avg_ms']) * 100
        print(f"  Improvement: {improvement:+.1f}%")
    except Exception as e:
        print(f"  Error: {e}")
        print("  Skipping hybrid search benchmark")
        hybrid_stats = None
    print()

    # Benchmark 3: Enhanced Hybrid Search (Phase 5 - no cache)
    print("-" * 80)
    print("3. ENHANCED HYBRID SEARCH (Phase 5 - No Cache)")
    print("-" * 80)
    print("Loading...")
    enhanced_search_nocache = EnhancedHybridRetrieval(enable_cache=False)
    print("Benchmarking...")
    enhanced_nocache_stats = benchmark_search_system(enhanced_search_nocache, test_queries)
    print(f"  Average: {enhanced_nocache_stats['avg_ms']} ms")
    print(f"  Min: {enhanced_nocache_stats['min_ms']} ms")
    print(f"  Max: {enhanced_nocache_stats['max_ms']} ms")

    improvement = ((basic_stats['avg_ms'] - enhanced_nocache_stats['avg_ms']) / basic_stats['avg_ms']) * 100
    print(f"  Improvement vs Baseline: {improvement:+.1f}%")
    print()

    # Benchmark 4: Enhanced Hybrid Search (Phase 5 - With Cache)
    print("-" * 80)
    print("4. ENHANCED HYBRID SEARCH (Phase 5 - With Cache)")
    print("-" * 80)
    print("Loading...")
    enhanced_search = EnhancedHybridRetrieval(enable_cache=True)

    # Clear cache first
    if enhanced_search.cache:
        enhanced_search.cache.clear()

    # First pass - populate cache
    print("First pass (cache population)...")
    first_pass_stats = benchmark_search_system(enhanced_search, test_queries)
    print(f"  Average: {first_pass_stats['avg_ms']} ms")

    # Second pass - cache hits
    print("Second pass (cache hits)...")
    second_pass_stats = benchmark_search_system(enhanced_search, test_queries)
    print(f"  Average: {second_pass_stats['avg_ms']} ms")
    print(f"  Min: {second_pass_stats['min_ms']} ms")
    print(f"  Max: {second_pass_stats['max_ms']} ms")

    # Get performance stats
    perf_stats = enhanced_search.get_performance_stats()
    print(f"  Cache hit rate: {perf_stats['cache_hit_rate']}")

    cache_speedup = ((first_pass_stats['avg_ms'] - second_pass_stats['avg_ms']) / first_pass_stats['avg_ms']) * 100
    print(f"  Cache speedup: {cache_speedup:.1f}%")

    overall_improvement = ((basic_stats['avg_ms'] - second_pass_stats['avg_ms']) / basic_stats['avg_ms']) * 100
    print(f"  Improvement vs Baseline: {overall_improvement:+.1f}%")
    print()

    # Summary
    print("=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print()

    summary_data = [
        ("Basic Vector Search (Baseline)", basic_stats['avg_ms'], "0%"),
    ]

    if hybrid_stats:
        hybrid_improvement = ((basic_stats['avg_ms'] - hybrid_stats['avg_ms']) / basic_stats['avg_ms']) * 100
        summary_data.append(
            ("Hybrid Search (Vector + Graph)", hybrid_stats['avg_ms'], f"{hybrid_improvement:+.1f}%")
        )

    enhanced_improvement = ((basic_stats['avg_ms'] - enhanced_nocache_stats['avg_ms']) / basic_stats['avg_ms']) * 100
    summary_data.append(
        ("Enhanced (No Cache)", enhanced_nocache_stats['avg_ms'], f"{enhanced_improvement:+.1f}%")
    )

    overall_improvement = ((basic_stats['avg_ms'] - second_pass_stats['avg_ms']) / basic_stats['avg_ms']) * 100
    summary_data.append(
        ("Enhanced (With Cache)", second_pass_stats['avg_ms'], f"{overall_improvement:+.1f}%")
    )

    # Print table
    print(f"{'System':<35} {'Avg Time (ms)':<15} {'Improvement':<15}")
    print("-" * 80)
    for system, avg_time, improvement in summary_data:
        print(f"{system:<35} {avg_time:<15.2f} {improvement:<15}")

    print()

    # Phase 5 Goals
    print("=" * 80)
    print("PHASE 5 GOALS vs ACTUAL")
    print("=" * 80)
    print()

    target_reduction = 60  # 60% faster as per plan
    actual_reduction = overall_improvement

    print(f"Target: 60% faster queries")
    print(f"Actual: {actual_reduction:.1f}% faster")
    print()

    if actual_reduction >= target_reduction:
        print("[OK] Phase 5 performance target ACHIEVED!")
    else:
        print(f"[NOTICE] Short by {target_reduction - actual_reduction:.1f}%")

    print()

    # Storage comparison
    print("=" * 80)
    print("STORAGE COMPARISON")
    print("=" * 80)
    print()

    kb_pipeline_size = sum(
        f.stat().st_size for f in Path("C:/TD_Projects/kb_pipeline").rglob("*") if f.is_file()
    ) / (1024 * 1024)

    print(f"kb_pipeline/ total: {kb_pipeline_size:.1f} MB")
    print()

    vector_db_size = sum(
        f.stat().st_size for f in Path("C:/TD_Projects/kb_pipeline/vector_db").rglob("*") if f.is_file()
    ) / (1024 * 1024)

    graph_size = sum(
        f.stat().st_size for f in Path("C:/TD_Projects/kb_pipeline/graph").rglob("*") if f.is_file()
    ) / (1024 * 1024)

    print(f"  Vector DB: {vector_db_size:.1f} MB")
    print(f"  Graph: {graph_size:.1f} MB")
    print(f"  Active storage: {vector_db_size + graph_size:.1f} MB")

    print()
    print("Target: <=250 MB (from 605 MB)")
    print(f"Actual: {vector_db_size + graph_size:.1f} MB")
    reduction = ((605 - (vector_db_size + graph_size)) / 605) * 100
    print(f"Reduction: {reduction:.1f}%")

    if vector_db_size + graph_size <= 250:
        print("[OK] Storage target ACHIEVED!")

    print()

    # Save benchmark results
    results_path = Path("C:/TD_Projects/kb_pipeline/benchmark_results.json")
    results = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'test_queries': len(test_queries),
        'systems': {
            'basic_vector_search': basic_stats,
            'enhanced_no_cache': enhanced_nocache_stats,
            'enhanced_with_cache': second_pass_stats
        },
        'cache_stats': perf_stats,
        'storage_mb': {
            'vector_db': vector_db_size,
            'graph': graph_size,
            'total_active': vector_db_size + graph_size
        }
    }

    if hybrid_stats:
        results['systems']['hybrid_search'] = hybrid_stats

    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Benchmark results saved to: {results_path}")


if __name__ == '__main__':
    run_comprehensive_benchmark()
