# routing_opt.py
# Optimize stop sequence for a given dispatch using Latitude/Longitude.

import math
from typing import List
import pandas as pd
import db  # uses your db.py


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points (km)."""
    R = 6371.0088  # mean Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def route_length(order: List[int], coords: List[tuple]) -> float:
    """Total distance following coords in given index order."""
    dist = 0.0
    for i in range(len(order) - 1):
        a = coords[order[i]]
        b = coords[order[i + 1]]
        dist += haversine_km(a[0], a[1], b[0], b[1])
    return dist


def nearest_neighbor(coords: List[tuple], start_idx: int = 0) -> List[int]:
    """Simple nearest neighbor tour."""
    n = len(coords)
    unvisited = set(range(n))
    tour = [start_idx]
    unvisited.remove(start_idx)

    while unvisited:
        last = tour[-1]
        nxt = min(
            unvisited,
            key=lambda j: haversine_km(coords[last][0], coords[last][1],
                                       coords[j][0], coords[j][1])
        )
        tour.append(nxt)
        unvisited.remove(nxt)
    return tour


def two_opt(order: List[int], coords: List[tuple]) -> List[int]:
    """2-opt improvement heuristic."""
    improved = True

    def seg_len(i, j):
        a = coords[i]
        b = coords[j]
        return haversine_km(a[0], a[1], b[0], b[1])

    best = order[:]
    while improved:
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                a, b = best[i - 1], best[i]
                c, d = best[j], best[j + 1]
                old = seg_len(a, b) + seg_len(c, d)
                new = seg_len(a, c) + seg_len(b, d)
                if new + 1e-9 < old:
                    best[i:j + 1] = reversed(best[i:j + 1])
                    improved = True
        # loop again if improved
    return best


def recompute_dispatch_sequence(dispatch_id: int):
    """
    Load all stops for a dispatch, compute a shorter tour, and
    update wh.DispatchStop.Sequence. Uses Address.Latitude/Longitude.
    """
    df = db.read("""
        SELECT ds.Stop_id,
               ds.Sequence AS OldSequence,
               a.Latitude,
               a.Longitude
        FROM wh.DispatchStop ds
        JOIN wh.Address a ON a.Address_id = ds.Address_id
        WHERE ds.Dispatch_id = ?
        ORDER BY ds.Sequence;
    """, [dispatch_id])

    if df.empty:
        raise RuntimeError(f"No stops found for Dispatch {dispatch_id}")

    # coordinates list in current sequence order
    coords = list(zip(df["Latitude"], df["Longitude"]))

    # original order (0..n-1 in current sequence)
    orig_order = list(range(len(coords)))
    orig_dist = route_length(orig_order, coords)

    # nearest-neighbor starting from first stop, then 2-opt refine
    nn_order = nearest_neighbor(coords, start_idx=0)
    best_order = two_opt(nn_order, coords)
    new_dist = route_length(best_order, coords)

    # Build (NewSequence, Stop_id) rows
    rows = []
    for new_seq, idx in enumerate(best_order, start=1):
        stop_id = int(df.iloc[idx]["Stop_id"])
        rows.append((new_seq, stop_id))

    # Update DB
    db.execmany("UPDATE wh.DispatchStop SET Sequence = ? WHERE Stop_id = ?", rows)

    improvement_km = orig_dist - new_dist
    improvement_pct = (improvement_km / orig_dist * 100) if orig_dist > 0 else 0.0

    return {
        "dispatch_id": dispatch_id,
        "stops": len(coords),
        "orig_dist_km": orig_dist,
        "new_dist_km": new_dist,
        "improvement_km": improvement_km,
        "improvement_pct": improvement_pct,
    }


def main():
    print("Route optimizer using Latitude/Longitude\n")
    try:
        dispatch_id = int(input("Enter Dispatch_id to optimize: ").strip())
    except ValueError:
        print("Please enter a valid integer Dispatch_id.")
        return

    info = recompute_dispatch_sequence(dispatch_id)
    print("\nOptimization complete.")
    print(f"Dispatch {info['dispatch_id']}:")
    print(f"  Stops:           {info['stops']}")
    print(f"  Distance before: {info['orig_dist_km']:.2f} km")
    print(f"  Distance after:  {info['new_dist_km']:.2f} km")
    print(f"  Improvement:     {info['improvement_km']:.2f} km "
          f"({info['improvement_pct']:.1f} % shorter)")


if __name__ == "__main__":
    main()
