# optimize_route.py
import math
import pandas as pd
import db  # uses your existing db helpers: get_df, exec, execmany, scalar

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two (lat, lon) in degrees."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lon1)
    p2_lat = math.radians(lat2)
    dlat = p2_lat - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2_lat) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def load_stops(dispatch_id: int) -> pd.DataFrame:
    """
    Returns one row per stop with Stop_id, Sequence, Latitude, Longitude, City, Postal_code.
    """
    sql = """
    SELECT
        ds.Stop_id,
        ds.Sequence,
        a.Latitude,
        a.Longitude,
        a.City,
        a.Postal_code
    FROM wh.DispatchStop ds
    JOIN wh.Address a
      ON a.Address_id = ds.Address_id
    WHERE ds.Dispatch_id = ?
    ORDER BY ds.Sequence;
    """
    return db.get_df(sql, [dispatch_id])

def nearest_neighbor_order(stops: pd.DataFrame) -> list[int]:
    """
    Simple nearest-neighbor heuristic.
    Returns list of Stop_id in visiting order.
    """
    if stops.empty:
        return []

    # we start at the first row as "depot"
    n = len(stops)
    remaining = list(range(n))  # row indices
    route_idx = [0]
    remaining.remove(0)

    while remaining:
        last = route_idx[-1]
        lat1 = float(stops.loc[last, "Latitude"])
        lon1 = float(stops.loc[last, "Longitude"])

        best_j = None
        best_d = 1e12
        for j in remaining:
            lat2 = float(stops.loc[j, "Latitude"])
            lon2 = float(stops.loc[j, "Longitude"])
            d = haversine_km(lat1, lon1, lat2, lon2)
            if d < best_d:
                best_d = d
                best_j = j

        route_idx.append(best_j)
        remaining.remove(best_j)

    # convert row indices to Stop_id
    return [int(stops.loc[i, "Stop_id"]) for i in route_idx]

def total_route_km(stops: pd.DataFrame, order: list[int]) -> float:
    """
    Compute total distance along the route in km for a given Stop_id order.
    """
    if len(order) < 2:
        return 0.0

    # map Stop_id -> (lat, lon)
    coord = {
        int(r.Stop_id): (float(r.Latitude), float(r.Longitude))
        for _, r in stops.iterrows()
    }

    dist = 0.0
    for i in range(len(order) - 1):
        s1 = order[i]
        s2 = order[i + 1]
        lat1, lon1 = coord[s1]
        lat2, lon2 = coord[s2]
        dist += haversine_km(lat1, lon1, lat2, lon2)
    return dist

def optimize_route(dispatch_id: int) -> float:
    """
    Main entry point:
      - Reads stops for a dispatch
      - Builds optimized visiting order using nearest neighbor
      - Safely updates wh.DispatchStop.Sequence without violating unique key
      - Optionally stores total distance on Dispatch.RouteDistance_km (if exists)
      - Returns total distance (km)
    """
    stops = load_stops(dispatch_id)
    if stops.empty or len(stops) == 1:
        return 0.0

    # 1) Build optimized order (Stop_id list)
    order_stop_ids = nearest_neighbor_order(stops)

    # 2) Phase 1: move all sequences out of 1..N range to avoid unique constraint conflicts
    db.exec(
        """
        UPDATE wh.DispatchStop
        SET Sequence = Sequence + 1000
        WHERE Dispatch_id = ?;
        """,
        [dispatch_id],
    )

    # 3) Phase 2: assign new optimized sequence values 1,2,3,...
    rows = []
    for seq, stop_id in enumerate(order_stop_ids, start=1):
        rows.append((seq, stop_id))

    db.execmany(
        """
        UPDATE wh.DispatchStop
        SET Sequence = ?
        WHERE Stop_id = ?;
        """,
        rows,
    )

    # 4) Compute final route distance with the new order
    #    (re-use the same 'stops' DataFrame; coordinates didn't change)
    dist_km = total_route_km(stops, order_stop_ids)

    # 5) (Optional) store on wh.Dispatch if RouteDistance_km column exists
    try:
        db.exec(
            """
            UPDATE wh.Dispatch
            SET RouteDistance_km = ?
            WHERE Dispatch_id = ?;
            """,
            [dist_km, dispatch_id],
        )
    except Exception:
        # if column does not exist, just ignore
        pass

    return dist_km

# Optional manual test:
if __name__ == "__main__":
    did = int(input("Dispatch_id to optimize: "))
    km = optimize_route(did)
    print(f"Optimized route distance ≈ {km:.2f} km")
