# viz_last_plan.py
# Visualize the latest load plan in 3D, colored by stop and red-edged if fragile.

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import pandas as pd
import db


def get_latest_plan() -> tuple[int, int]:
    df = db.read("""
        SELECT TOP 1 loadplan_id, dispatch_id
        FROM wh.LoadPlan
        ORDER BY loadplan_id DESC;
    """)
    if df.empty:
        raise RuntimeError("No LoadPlan found.")
    r = df.iloc[0]
    return int(r["loadplan_id"]), int(r["dispatch_id"])


def get_truck_dims(dispatch_id: int):
    df = db.read("""
        SELECT tt.Length_cm, tt.Width_cm, tt.Height_cm
        FROM wh.Dispatch d
        JOIN wh.Truck t      ON t.Truck_id = d.Truck_id
        JOIN wh.TruckType tt ON tt.Type_id = t.Type_id
        WHERE d.Dispatch_id = ?;
    """, [dispatch_id])
    if df.empty:
        raise RuntimeError("No truck found for dispatch.")
    r = df.iloc[0]
    return int(r["Length_cm"]), int(r["Width_cm"]), int(r["Height_cm"])


def get_placements(loadplan_id: int) -> pd.DataFrame:
    sql = """
    SELECT
      pl.Package_id,
      pl.X_cm, pl.Y_cm, pl.Z_cm,
      pl.Length_cm, pl.Width_cm, pl.Height_cm,
      p.Fragile_flag,
      ds.Sequence AS StopSequence
    FROM wh.Placement pl
    JOIN wh.Package p            ON p.Package_id = pl.Package_id
    JOIN wh.PackageAssignment pa ON pa.Package_id = p.Package_id
    JOIN wh.DispatchStop ds      ON ds.Stop_id = pa.Stop_id
    WHERE pl.Loadplan_id = ?
    ORDER BY pl.Placement_id;
    """
    return db.read(sql, [loadplan_id])


def draw_box(ax, x, y, z, L, W, H, face_color, edge_color):
    x0, y0, z0 = x, y, z
    x1, y1, z1 = x + L, y + W, z + H

    verts = [
        [(x0,y0,z0), (x1,y0,z0), (x1,y1,z0), (x0,y1,z0)],
        [(x0,y0,z1), (x1,y0,z1), (x1,y1,z1), (x0,y1,z1)],
        [(x0,y0,z0), (x1,y0,z0), (x1,y0,z1), (x0,y0,z1)],
        [(x1,y0,z0), (x1,y1,z0), (x1,y1,z1), (x1,y0,z1)],
        [(x1,y1,z0), (x0,y1,z0), (x0,y1,z1), (x1,y1,z1)],
        [(x0,y1,z0), (x0,y0,z0), (x0,y0,z1), (x0,y1,z1)],
    ]
    # IMPORTANT: no fixed alpha here; we let face_color's own alpha work
    pc = Poly3DCollection(verts)
    pc.set_facecolor(face_color)   # can include transparency (RGBA)
    pc.set_edgecolor(edge_color)
    ax.add_collection3d(pc)


def main():
    loadplan_id, dispatch_id = get_latest_plan()
    L, W, H = get_truck_dims(dispatch_id)
    df = get_placements(loadplan_id)
    if df.empty:
        print("No placements for latest load plan.")
        return

    print(f"Latest LoadPlan: {loadplan_id}, Dispatch: {dispatch_id}")
    print("Sample placements (first 10 rows):")
    print(df.head(10))

    stop_vals = sorted(df["StopSequence"].unique())
    cmap = plt.cm.get_cmap("tab10", len(stop_vals))   # bright colors
    color_map = {s: cmap(i) for i, s in enumerate(stop_vals)}

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111, projection="3d")

    # 1) Draw packages FIRST (solid colors)
    for r in df.itertuples():
        base_color = color_map[int(r.StopSequence)]
        edge = "red" if int(r.Fragile_flag) == 1 else "black"
        draw_box(
            ax,
            int(r.X_cm), int(r.Y_cm), int(r.Z_cm),
            int(r.Length_cm), int(r.Width_cm), int(r.Height_cm),
            base_color,
            edge,
        )

    # 2) Draw truck wireframe with transparent faces
    #    RGBA with very low alpha so walls are see-through
    truck_face = (1, 1, 1, 0.03)   # almost fully transparent
    draw_box(ax, 0, 0, 0, L, W, H, truck_face, "black")

    # Axes / limits
    ax.set_xlim(0, L)
    ax.set_ylim(0, W)
    ax.set_zlim(0, H)
    ax.set_xlabel("X (length cm)")
    ax.set_ylabel("Y (width cm)")
    ax.set_zlabel("Z (height cm)")
    ax.set_title(f"LoadPlan {loadplan_id} — Dispatch {dispatch_id} (color = stop, red edge = fragile)")

    # Equal aspect ratio so dimensions look correct
    ax.set_box_aspect((L, W, H))

    # Choose a decent default view angle
    ax.view_init(elev=25, azim=-60)

    # Legend for stops
    handles = [
        plt.Line2D([0],[0], marker='s', linestyle='',
                   markerfacecolor=color_map[s], markeredgecolor='black',
                   label=f"Stop {s}")
        for s in stop_vals
    ]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.02, 1.0))

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
