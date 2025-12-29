# dispatch_summary.py
# Print key KPIs for a given dispatch (Business Analytics view)

import math
import db


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points in km."""
    R = 6371.0088  # mean Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def route_distance_km(dispatch_id: int) -> float:
    """Compute total route distance for this dispatch using stop coordinates."""
    sql = """
    SELECT ds.Sequence, a.Latitude, a.Longitude
    FROM wh.DispatchStop ds
    JOIN wh.Address a ON a.Address_id = ds.Address_id
    WHERE ds.Dispatch_id = ?
    ORDER BY ds.Sequence;
    """
    df = db.read(sql, [dispatch_id])
    if len(df) < 2:
        return 0.0

    dist = 0.0
    for i in range(len(df) - 1):
        r1 = df.iloc[i]
        r2 = df.iloc[i + 1]
        dist += haversine_km(r1.Latitude, r1.Longitude,
                             r2.Latitude, r2.Longitude)
    return dist


def summary(dispatch_id: int):
    # 1) Package stats: count, weight, fragile count
    pkg_sql = """
    SELECT
      COUNT(*)                            AS PackageCount,
      SUM(p.Weight_lbs)                   AS TotalWeight_lbs,
      SUM(CASE WHEN p.Fragile_flag = 1
               THEN 1 ELSE 0 END)        AS FragileCount
    FROM wh.Package p
    JOIN wh.PackageAssignment pa ON pa.Package_id = p.Package_id
    JOIN wh.DispatchStop ds      ON ds.Stop_id     = pa.Stop_id
    WHERE ds.Dispatch_id = ?;
    """
    pkg = db.read(pkg_sql, [dispatch_id]).iloc[0]

    # 2) Number of stops
    stop_sql = """
    SELECT COUNT(*) AS StopCount
    FROM wh.DispatchStop
    WHERE Dispatch_id = ?;
    """
    stop_count = int(db.read(stop_sql, [dispatch_id]).iloc[0]["StopCount"])

    # 3) Latest load plan for this dispatch (if any)
    lp_sql = """
    SELECT TOP 1 Loadplan_id, util_weight_pct, util_volume_pct
    FROM wh.LoadPlan
    WHERE Dispatch_id = ?
    ORDER BY Loadplan_id DESC;
    """
    lp_df = db.read(lp_sql, [dispatch_id])
    lp = lp_df.iloc[0] if not lp_df.empty else None

    # 4) Route distance
    dist_km = route_distance_km(dispatch_id)

    # ----- Print nicely -----
    print(f"\n=== Dispatch {dispatch_id} Summary ===")
    print(f"Stops:                 {stop_count}")
    print(f"Packages:              {int(pkg['PackageCount'])}")
    print(f"Total weight (lbs):    {pkg['TotalWeight_lbs']:.1f}")
    print(f"Fragile packages:      {int(pkg['FragileCount'])}")
    print(f"Route distance (km):   {dist_km:.2f}")

    if lp is not None:
        print(f"\nLatest LoadPlan:       {int(lp['Loadplan_id'])}")
        print(f"  Util weight (%):     {lp['util_weight_pct']:.1f}")
        print(f"  Util volume (%):     {lp['util_volume_pct']:.1f}")
    else:
        print("\nNo LoadPlan generated yet for this dispatch.")


def main():
    try:
        dispatch_id = int(input("Enter Dispatch_id to summarize: ").strip())
    except ValueError:
        print("Please enter a valid integer.")
        return
    summary(dispatch_id)


if __name__ == "__main__":
    main()
