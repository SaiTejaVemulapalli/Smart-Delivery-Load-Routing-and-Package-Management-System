# pack_dispatch.py
# Core packing engine for Dispatch → LoadPlan

import datetime as dt
import pandas as pd
import db


# -------------------------------------------------
# Helper: load all packages for a dispatch
# -------------------------------------------------
def load_packages(dispatch_id: int) -> pd.DataFrame:
    sql = """
    SELECT
      p.Package_id,
      p.Weight_lbs,
      p.Length_cm,
      p.Width_cm,
      p.Height_cm,
      p.Fragile_flag,
      ds.Sequence AS StopSequence
    FROM wh.Package p
    JOIN wh.PackageAssignment pa ON pa.Package_id = p.Package_id
    JOIN wh.DispatchStop ds ON ds.Stop_id = pa.Stop_id
    WHERE ds.Dispatch_id = ?
    ORDER BY ds.Sequence DESC, p.Weight_lbs DESC;
    """
    return db.read(sql, [dispatch_id])


# -------------------------------------------------
# Helper: get truck dimensions for the dispatch
# -------------------------------------------------
def get_truck(dispatch_id: int):
    sql = """
    SELECT
      tt.Length_cm,
      tt.Width_cm,
      tt.Height_cm,
      tt.Max_weight_lbs
    FROM wh.Dispatch d
    JOIN wh.Truck t ON t.Truck_id = d.Truck_id
    JOIN wh.TruckType tt ON tt.Type_id = t.Type_id
    WHERE d.Dispatch_id = ?;
    """
    row = db.read(sql, [dispatch_id]).iloc[0]
    return (
        int(row.Length_cm),
        int(row.Width_cm),
        int(row.Height_cm),
        float(row.Max_weight_lbs),
    )


# -------------------------------------------------
# Simple greedy 3D packer
# -------------------------------------------------
def pack(dispatch_id: int):
    """
    Returns (loadplan_id, placed_list).
    placed_list is a list of dictionaries with coordinates etc.
    """
    packages = load_packages(dispatch_id)
    L, W, H, max_weight = get_truck(dispatch_id)

    x = y = z = 0
    row_depth = 0
    layer_height = 0

    placed = []
    total_weight = 0.0

    for _, r in packages.iterrows():
        # weight constraint
        if total_weight + r.Weight_lbs > max_weight:
            continue

        # move across X
        if x + r.Length_cm > L:
            x = 0
            y += row_depth
            row_depth = 0

        # new row in Y
        if y + r.Width_cm > W:
            x = 0
            y = 0
            z += layer_height
            layer_height = 0

        # no more vertical space
        if z + r.Height_cm > H:
            continue

        placed.append({
            "Package_id": r.Package_id,
            "X_cm": int(x),
            "Y_cm": int(y),
            "Z_cm": int(z),
            "Length_cm": int(r.Length_cm),
            "Width_cm": int(r.Width_cm),
            "Height_cm": int(r.Height_cm),
            "Fragile_flag": bool(r.Fragile_flag),
            "StopSequence": int(r.StopSequence),
        })

        total_weight += float(r.Weight_lbs)
        x += int(r.Length_cm)
        row_depth = max(row_depth, int(r.Width_cm))
        layer_height = max(layer_height, int(r.Height_cm))

    # utilization metrics
    util_weight = round((total_weight / max_weight) * 100, 1) if max_weight > 0 else 0.0
    used_volume = sum(
        p["Length_cm"] * p["Width_cm"] * p["Height_cm"] for p in placed
    )
    truck_volume = L * W * H
    util_volume = round((used_volume / truck_volume) * 100, 1) if truck_volume > 0 else 0.0

    # insert LoadPlan and get new id
    lp_sql = """
    INSERT INTO wh.LoadPlan
      (Dispatch_id, Generated_ts, Algorithm_version,
       Util_weight_pct, Util_volume_pct)
    OUTPUT INSERTED.Loadplan_id
    VALUES (?, ?, ?, ?, ?);
    """
    loadplan_id = db.scalar(lp_sql, [
        dispatch_id,
        dt.datetime.utcnow(),
        "proto-frontend-1.0",
        util_weight,
        util_volume
    ])

    # insert Placements
    rows = [
        (
            loadplan_id,
            p["Package_id"],
            p["X_cm"], p["Y_cm"], p["Z_cm"],
            p["Length_cm"], p["Width_cm"], p["Height_cm"],
            0,  # Rotated_base_flag
            0,  # Layer_index (simple version)
        )
        for p in placed
    ]

    if rows:
        db.execmany("""
        INSERT INTO wh.Placement
          (Loadplan_id, Package_id,
           X_cm, Y_cm, Z_cm,
           Length_cm, Width_cm, Height_cm,
           Rotated_base_flag, Layer_index)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, rows)

    return int(loadplan_id), placed


# -------------------------------------------------
# Public function used by Streamlit frontend
# -------------------------------------------------
def pack_dispatch(dispatch_id: int) -> int:
    """
    Called from app.py.
    Creates a new LoadPlan and Placements for the given dispatch.
    Returns Loadplan_id.
    """
    loadplan_id, _ = pack(dispatch_id)
    return loadplan_id


# -------------------------------------------------
# CLI entry point (optional)
# -------------------------------------------------
def main():
    print("=== Dispatch Load Planner ===")
    dispatch_id = int(input("Enter Dispatch_id to pack: "))
    lp_id = pack_dispatch(dispatch_id)
    print(f"LoadPlan {lp_id} created successfully.")


if __name__ == "__main__":
    main()
