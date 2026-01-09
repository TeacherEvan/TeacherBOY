"""
Measure startup performance before/after modularization.
Run this to verify lazy loading improvements.
"""

import time
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def measure_import_time(module_name: str) -> float:
    """Measure time to import a module in milliseconds."""
    # Clear module from cache if exists
    if module_name in sys.modules:
        del sys.modules[module_name]

    start = time.perf_counter()
    try:
        __import__(module_name)
        end = time.perf_counter()
        return (end - start) * 1000  # Convert to ms
    except Exception as e:
        print(f"  ❌ Error importing {module_name}: {e}")
        return -1


def get_module_count() -> int:
    """Get number of loaded modules."""
    return len(sys.modules)


def main():
    print("📊 TeacherBOY Startup Performance Metrics")
    print("=" * 70)

    baseline_modules = get_module_count()
    print(f"Baseline modules loaded: {baseline_modules}")
    print()

    # Measure config
    print("⏱️  Measuring module import times...")
    print("-" * 70)

    config_time = measure_import_time("src.config")
    config_modules = get_module_count()
    print(f"src.config: {config_time:>8.2f}ms  (Δ {config_modules - baseline_modules} modules)")

    # Measure agent factory (should be very fast)
    factory_time = measure_import_time("src.agents.agent_factory")
    factory_modules = get_module_count()
    print(
        f"src.agents.agent_factory: {factory_time:>8.2f}ms  (Δ {factory_modules - config_modules} modules)"
    )

    # Measure agent router
    router_time = measure_import_time("src.agents.agent_router")
    router_modules = get_module_count()
    print(
        f"src.agents.agent_router: {router_time:>8.2f}ms  (Δ {router_modules - factory_modules} modules)"
    )

    # Measure main app (this will trigger agent registration but NOT instantiation)
    main_time = measure_import_time("src.main")
    main_modules = get_module_count()
    print(f"src.main: {main_time:>8.2f}ms  (Δ {main_modules - router_modules} modules)")

    print("-" * 70)
    total_time = config_time + factory_time + router_time + main_time
    total_modules = main_modules - baseline_modules

    print()
    print("📈 Summary")
    print("=" * 70)
    print(f"Total startup time: {total_time:>8.2f}ms")
    print(f"Total modules loaded: {total_modules}")
    print()

    # Check if agents are actually instantiated
    from src.agents.agent_factory import AgentFactory

    print(f"Registered agents: {len(AgentFactory._registry)}")
    print(f"Instantiated agents: {len(AgentFactory._instances)}")
    print()

    if len(AgentFactory._instances) == 0:
        print("✅ SUCCESS: Lazy loading working! No agents instantiated at startup.")
    else:
        print(f"⚠️  WARNING: {len(AgentFactory._instances)} agents instantiated early.")

    print("=" * 70)

    # Optional: Trigger lazy loading and measure
    print()
    print("🔧 Testing lazy instantiation...")
    print("-" * 70)

    start = time.perf_counter()
    agents = AgentFactory.get_all_agents()
    end = time.perf_counter()
    lazy_time = (end - start) * 1000

    print(f"Lazy instantiation of {len(agents)} agents: {lazy_time:.2f}ms")
    print(f"Total modules after lazy load: {get_module_count()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
