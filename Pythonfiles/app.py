# app.py
import datetime as dt

import pandas as pd
import streamlit as st
import pydeck as pdk
import plotly.express as px
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from db import get_df, exec as db_exec, execmany as db_execmany, scalar as db_scalar
from pack_dispatch import pack_dispatch
from optimize_route import optimize_route

# -------------------------------------------------
# Streamlit basic config
# -------------------------------------------------
st.set_page_config(
    page_title="Smart Delivery Load & Route Optimization",
    layout="wide"
)

st.title("Smart Delivery Load & Route Optimization")

# -------------------------------------------------
# Helper functions for DB access
# -------------------------------------------------

def get_dispatches_for_date(service_date: dt.date) -> pd.DataFrame:
    """
    Returns dispatches for a given service date with a nice label.
    """
    sql = """
    SELECT
        d.Dispatch_id,
        d.Service_date,
        'Truck-' + CAST(t.Truck_id AS varchar(10)) AS TruckLabel,
        'Dispatch ' + CAST(d.Dispatch_id AS varchar(10)) +
        ' — ' +
        'Truck-' + CAST(t.Truck_id AS varchar(10)) +
        ' on ' +
        CONVERT(varchar(10), d.Service_date, 120) AS Label
    FROM wh.Dispatch d
    JOIN wh.Truck t ON t.Truck_id = d.Truck_id
    WHERE CAST(d.Service_date AS date) = ?
    ORDER BY d.Dispatch_id;
    """
    return get_df(sql, params=[service_date])


def get_dispatch_summary(dispatch_id: int) -> pd.DataFrame:
    """
    KPIs for a given dispatch: number of stops, packages, weight, fragile, utilization.
    """
    sql = """
    ;WITH StopAgg AS (
        SELECT
            ds.Dispatch_id,
            COUNT(DISTINCT ds.Stop_id) AS Stops,
            COUNT(pa.Package_id) AS Packages,
            SUM(p.Weight_lbs) AS TotalWeight,
            SUM(CASE WHEN p.Fragile_flag = 1 THEN 1 ELSE 0 END) AS Fragile
        FROM wh.DispatchStop ds
        LEFT JOIN wh.PackageAssignment pa ON pa.Stop_id = ds.Stop_id
        LEFT JOIN wh.Package p ON p.Package_id = pa.Package_id
        WHERE ds.Dispatch_id = ?
        GROUP BY ds.Dispatch_id
    ),
    Util AS (
        SELECT TOP 1
            Dispatch_id,
            Util_weight_pct,
            Util_volume_pct
        FROM wh.LoadPlan
        WHERE Dispatch_id = ?
        ORDER BY Loadplan_id DESC
    )
    SELECT
        sa.Stops,
        sa.Packages,
        ISNULL(sa.TotalWeight,0) AS TotalWeight,
        ISNULL(sa.Fragile,0) AS Fragile,
        ISNULL(u.Util_weight_pct,0) AS Util_weight_pct,
        ISNULL(u.Util_volume_pct,0) AS Util_volume_pct
    FROM StopAgg sa
    LEFT JOIN Util u
      ON u.Dispatch_id = sa.Dispatch_id;
    """
    return get_df(sql, params=[dispatch_id, dispatch_id])


def get_package_search_df(selected_dispatch_id: int, kpi_date: dt.date) -> pd.DataFrame:
    """
    Returns packages with a realistic Status based on assignment / loading / date.
    NOTE: Dispatch_id is obtained via DispatchStop (not directly on PackageAssignment).
    """
    sql = """
    DECLARE @SelectedDispatchId int = ?;
    DECLARE @KpiDate date = ?;

    ;WITH LatestLoadPlan AS (
        SELECT Dispatch_id, MAX(Loadplan_id) AS Loadplan_id
        FROM wh.LoadPlan
        GROUP BY Dispatch_id
    ),
    PkgBase AS (
        SELECT
            p.Package_id,
            a.City,
            a.Postal_code,
            p.Weight_lbs,
            p.Fragile_flag,
            d.Dispatch_id,
            d.Service_date,
            lp.Loadplan_id,
            CASE
                WHEN d.Dispatch_id IS NULL THEN 'WAREHOUSE'
                WHEN lp.Loadplan_id IS NULL THEN 'ASSIGNED_ONLY'
                ELSE 'LOADED'
            END AS AssignState
        FROM wh.Package p
        LEFT JOIN wh.Address a
               ON a.Address_id = p.Address_id
        LEFT JOIN wh.PackageAssignment pa
               ON pa.Package_id = p.Package_id
        LEFT JOIN wh.DispatchStop ds
               ON ds.Stop_id = pa.Stop_id
        LEFT JOIN wh.Dispatch d
               ON d.Dispatch_id = ds.Dispatch_id
        LEFT JOIN LatestLoadPlan lp
               ON lp.Dispatch_id = d.Dispatch_id
    )
    SELECT
        pb.Package_id,
        pb.City,
        pb.Postal_code,
        pb.Weight_lbs,
        pb.Fragile_flag,
        CASE
            WHEN pb.AssignState = 'WAREHOUSE' THEN
                'AT WAREHOUSE (UNASSIGNED)'
            WHEN pb.AssignState = 'ASSIGNED_ONLY'
                 AND pb.Dispatch_id = @SelectedDispatchId THEN
                'ASSIGNED TO SELECTED DISPATCH (NOT LOADED)'
            WHEN pb.AssignState = 'ASSIGNED_ONLY'
                 AND pb.Dispatch_id <> @SelectedDispatchId THEN
                'ASSIGNED TO OTHER DISPATCH – Dispatch ' + CAST(pb.Dispatch_id AS varchar(10))
            WHEN pb.AssignState = 'LOADED'
                 AND pb.Dispatch_id = @SelectedDispatchId
                 AND pb.Service_date >= @KpiDate THEN
                'LOADED ON TRUCK – SELECTED DISPATCH'
            WHEN pb.AssignState = 'LOADED'
                 AND pb.Dispatch_id = @SelectedDispatchId
                 AND pb.Service_date < @KpiDate THEN
                'DELIVERED – SELECTED DISPATCH'
            WHEN pb.AssignState = 'LOADED'
                 AND pb.Dispatch_id <> @SelectedDispatchId
                 AND pb.Service_date < @KpiDate THEN
                'DELIVERED – DISPATCH ' + CAST(pb.Dispatch_id AS varchar(10))
            ELSE
                'LOADED ON OTHER DISPATCH – Dispatch ' + CAST(ISNULL(pb.Dispatch_id,0) AS varchar(10))
        END AS Status
    FROM PkgBase pb
    ORDER BY pb.Package_id;
    """
    return get_df(sql, params=[selected_dispatch_id, kpi_date])


def get_stop_summary_df(dispatch_id: int) -> pd.DataFrame:
    """
    Summary per stop for a dispatch.
    """
    sql = """
    SELECT
        ds.Sequence      AS StopNumber,
        a.City,
        a.Postal_code,
        COUNT(pa.Package_id)          AS NumPackages,
        SUM(p.Weight_lbs)             AS TotalWeight_lbs,
        SUM(CASE WHEN p.Fragile_flag = 1 THEN 1 ELSE 0 END) AS FragilePkgs
    FROM wh.DispatchStop ds
    JOIN wh.Address a
         ON a.Address_id = ds.Address_id
    LEFT JOIN wh.PackageAssignment pa
         ON pa.Stop_id = ds.Stop_id
    LEFT JOIN wh.Package p
         ON p.Package_id = pa.Package_id
    WHERE ds.Dispatch_id = ?
    GROUP BY ds.Sequence, a.City, a.Postal_code
    ORDER BY ds.Sequence;
    """
    return get_df(sql, params=[dispatch_id])


def get_route_stops(dispatch_id: int) -> pd.DataFrame:
    """
    Returns stops in visiting order with lat/lon for map.
    """
    sql = """
    SELECT
        ds.Sequence AS StopNumber,
        a.City,
        a.Postal_code,
        a.Latitude,
        a.Longitude
    FROM wh.DispatchStop ds
    JOIN wh.Address a
         ON a.Address_id = ds.Address_id
    WHERE ds.Dispatch_id = ?
    ORDER BY ds.Sequence;
    """
    return get_df(sql, params=[dispatch_id])


def get_utilization_for_date(service_date: dt.date) -> pd.DataFrame:
    """
    Latest load plan per dispatch for a given date (for dashboard).
    """
    sql = """
    ;WITH LatestLoad AS (
        SELECT
            Dispatch_id,
            MAX(Loadplan_id) AS Loadplan_id
        FROM wh.LoadPlan
        GROUP BY Dispatch_id
    )
    SELECT
        lp.Loadplan_id,
        lp.Dispatch_id,
        'Dispatch ' + CAST(lp.Dispatch_id AS varchar(10)) +
            ' (' + CONVERT(varchar(10), d.Service_date, 120) + ')' AS DispatchLabel,
        lp.Util_weight_pct,
        lp.Util_volume_pct
    FROM LatestLoad l
    JOIN wh.LoadPlan lp
         ON lp.Loadplan_id = l.Loadplan_id
    JOIN wh.Dispatch d
         ON d.Dispatch_id = lp.Dispatch_id
    WHERE CAST(d.Service_date AS date) = ?
    ORDER BY lp.Dispatch_id;
    """
    return get_df(sql, params=[service_date])


def get_latest_loadplan_id(dispatch_id: int) -> int | None:
    """
    Returns latest Loadplan_id for a dispatch or None.
    """
    sql = """
    SELECT TOP 1 Loadplan_id
    FROM wh.LoadPlan
    WHERE Dispatch_id = ?
    ORDER BY Loadplan_id DESC;
    """
    df = get_df(sql, params=[dispatch_id])
    if df.empty:
        return None
    return int(df.loc[0, "Loadplan_id"])


def get_placements_for_loadplan(loadplan_id: int) -> pd.DataFrame:
    """
    Returns all packages placed in a specific loadplan, with stop sequence & fragile flag.
    IMPORTANT: StopSequence is via PackageAssignment + DispatchStop, not Placement.Stop_id.
    """
    sql = """
    SELECT
        pl.Package_id,
        pl.X_cm,
        pl.Y_cm,
        pl.Z_cm,
        pl.Length_cm,
        pl.Width_cm,
        pl.Height_cm,
        p.Fragile_flag,
        ds.Sequence AS StopSequence
    FROM wh.Placement pl
    JOIN wh.Package p
         ON p.Package_id = pl.Package_id
    JOIN wh.PackageAssignment pa
         ON pa.Package_id = p.Package_id
    JOIN wh.DispatchStop ds
         ON ds.Stop_id = pa.Stop_id
    WHERE pl.Loadplan_id = ?
    ORDER BY ds.Sequence, pl.Package_id;
    """
    return get_df(sql, params=[loadplan_id])


# -------------------------------------------------
# 3D plotting helper for Load View
# -------------------------------------------------

TRUCK_L_CM = 260
TRUCK_W_CM = 160
TRUCK_H_CM = 140


def draw_box(ax, x, y, z, dx, dy, dz, face_color, edge_color="black", lw=1.0, alpha=0.95):
    """Draw a rectangular box in 3D."""
    x_c = [x, x + dx]
    y_c = [y, y + dy]
    z_c = [z, z + dz]
    verts = [
        # bottom
        [(x_c[0], y_c[0], z_c[0]), (x_c[1], y_c[0], z_c[0]),
         (x_c[1], y_c[1], z_c[0]), (x_c[0], y_c[1], z_c[0])],
        # top
        [(x_c[0], y_c[0], z_c[1]), (x_c[1], y_c[0], z_c[1]),
         (x_c[1], y_c[1], z_c[1]), (x_c[0], y_c[1], z_c[1])],
        # sides
        [(x_c[0], y_c[0], z_c[0]), (x_c[1], y_c[0], z_c[0]),
         (x_c[1], y_c[0], z_c[1]), (x_c[0], y_c[0], z_c[1])],
        [(x_c[0], y_c[1], z_c[0]), (x_c[1], y_c[1], z_c[0]),
         (x_c[1], y_c[1], z_c[1]), (x_c[0], y_c[1], z_c[1])],
        [(x_c[0], y_c[0], z_c[0]), (x_c[0], y_c[1], z_c[0]),
         (x_c[0], y_c[1], z_c[1]), (x_c[0], y_c[0], z_c[1])],
        [(x_c[1], y_c[0], z_c[0]), (x_c[1], y_c[1], z_c[0]),
         (x_c[1], y_c[1], z_c[1]), (x_c[1], y_c[0], z_c[1])]
    ]
    pc = Poly3DCollection(
        verts,
        alpha=alpha,
        facecolor=face_color,
        edgecolor=edge_color,
        linewidths=lw
    )
    ax.add_collection3d(pc)


def make_3d_figure(df: pd.DataFrame, dispatch_id: int, loadplan_id: int):
    fig = plt.figure(figsize=(8, 5))
    ax = fig.add_subplot(111, projection="3d")

    stop_vals = sorted(df["StopSequence"].unique())
    palette = px.colors.qualitative.Plotly
    color_map = {s: palette[i % len(palette)] for i, s in enumerate(stop_vals)}

    # truck
    draw_box(
        ax,
        0, 0, 0,
        TRUCK_L_CM, TRUCK_W_CM, TRUCK_H_CM,
        face_color=(1, 1, 1, 0.02),
        edge_color="black",
        lw=1.5,
        alpha=0.02
    )

    for _, row in df.iterrows():
        x = row["X_cm"]
        y = row["Y_cm"]
        z = row["Z_cm"]
        dx = row["Length_cm"]
        dy = row["Width_cm"]
        dz = row["Height_cm"]
        stop_seq = row["StopSequence"]
        fragile = bool(row["Fragile_flag"])

        face_color = color_map.get(stop_seq, "#AAAAAA")
        edge_color = "red" if fragile else "black"
        lw = 2.0 if fragile else 0.8

        draw_box(ax, x, y, z, dx, dy, dz, face_color=face_color, edge_color=edge_color, lw=lw, alpha=0.95)

    ax.set_xlabel("X (length cm)")
    ax.set_ylabel("Y (width cm)")
    ax.set_zlabel("Z (height cm)")
    ax.set_xlim(0, TRUCK_L_CM)
    ax.set_ylim(0, TRUCK_W_CM)
    ax.set_zlim(0, TRUCK_H_CM)
    ax.set_box_aspect((TRUCK_L_CM, TRUCK_W_CM, TRUCK_H_CM))

    ax.set_title(f"LoadPlan {loadplan_id} — Dispatch {dispatch_id}\n"
                 "Color = stop, red edge = fragile")

    plt.tight_layout()
    return fig


# -------------------------------------------------
# Top controls: KPI date & dispatch selector
# -------------------------------------------------

kpi_date = st.date_input("Select date for KPIs", value=dt.date.today())

dispatches_df = get_dispatches_for_date(kpi_date)

if dispatches_df.empty:
    st.warning("No dispatches for this date.")
    st.stop()

dispatch_label = st.selectbox(
    "Select a Dispatch",
    options=dispatches_df["Label"].tolist()
)

selected_dispatch_id = int(
    dispatches_df.loc[dispatches_df["Label"] == dispatch_label, "Dispatch_id"].iloc[0]
)

st.write(
    "**Truck interior (assumed demo):** L=260 cm, W=160 cm, H=140 cm | "
    "**Max weight (assumed):** 3000 lbs"
)

# -------------------------------------------------
# Tabs
# -------------------------------------------------
tabs = st.tabs(
    ["Today’s KPIs",
     "Package Search",
     "Stop Summary by Route",
     "Route Map",
     "Utilization Dashboard",
     "3D Load View"]
)

# -------------------------------------------------
# Tab 1 – Today’s KPIs
# -------------------------------------------------
with tabs[0]:
    st.subheader("Today’s KPIs for Selected Dispatch")

    summary_df = get_dispatch_summary(selected_dispatch_id)
    if summary_df.empty:
        st.info("No summary data for this dispatch.")
    else:
        row = summary_df.iloc[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Stops", int(row["Stops"]))
        c2.metric("Packages", int(row["Packages"]))
        c3.metric("Total Weight (lbs)", float(row["TotalWeight"]))
        c4.metric("Fragile packages", int(row["Fragile"]))

        c5, c6 = st.columns(2)
        c5.metric("Weight Utilization (%)", f"{float(row['Util_weight_pct']):.1f}")
        c6.metric("Volume Utilization (%)", f"{float(row['Util_volume_pct']):.1f}")

# -------------------------------------------------
# Tab 2 – Package Search
# -------------------------------------------------
with tabs[1]:
    st.subheader("Package Search")

    search_text = st.text_input(
        "Search by Package ID, city, or postal code",
        placeholder="e.g., PKG000123, Rochester, 48002..."
    )

    pkg_df = get_package_search_df(selected_dispatch_id, kpi_date)

    if search_text:
        mask = (
            pkg_df["Package_id"].astype(str).str.contains(search_text, case=False)
            | pkg_df["City"].fillna("").str.contains(search_text, case=False)
            | pkg_df["Postal_code"].astype(str).str.contains(search_text, case=False)
        )
        pkg_df = pkg_df[mask]

    st.dataframe(pkg_df, use_container_width=True)

# -------------------------------------------------
# Tab 3 – Stop Summary by Route
# -------------------------------------------------
with tabs[2]:
    st.subheader("Stop Summary by Route")

    stops_df = get_stop_summary_df(selected_dispatch_id)
    if stops_df.empty:
        st.info("No stops for this dispatch.")
    else:
        st.dataframe(stops_df, use_container_width=True)

# -------------------------------------------------
# Tab 4 – Route Map (with explicit LineLayer)
# -------------------------------------------------
with tabs[3]:
    st.subheader("Route Map")

    if st.button("Optimize Route for this Dispatch"):
        km = optimize_route(selected_dispatch_id)
        st.success(f"Route optimized – new distance ≈ {km:.2f} km")

    stops_map_df = get_route_stops(selected_dispatch_id)

    if stops_map_df.empty:
        st.info("No stops to display.")
    else:
        # Ensure sorted by stop sequence
        stops_map_df = stops_map_df.sort_values("StopNumber").reset_index(drop=True)

        # Build edges between consecutive stops
        edges = []
        for i in range(len(stops_map_df) - 1):
            row_from = stops_map_df.iloc[i]
            row_to = stops_map_df.iloc[i + 1]
            edges.append({
                "from_lon": float(row_from["Longitude"]),
                "from_lat": float(row_from["Latitude"]),
                "to_lon": float(row_to["Longitude"]),
                "to_lat": float(row_to["Latitude"]),
                "from_stop": int(row_from["StopNumber"]),
                "to_stop": int(row_to["StopNumber"])
            })
        edges_df = pd.DataFrame(edges)

        scatter_layer = pdk.Layer(
            "ScatterplotLayer",
            data=stops_map_df,
            get_position="[Longitude, Latitude]",
            get_color=[200, 30, 0],
            get_radius=150,
        )

        line_layer = pdk.Layer(
            "LineLayer",
            data=edges_df,
            get_source_position='[from_lon, from_lat]',
            get_target_position='[to_lon, to_lat]',
            get_color=[0, 120, 255],
            get_width=4,
        )

        mid_lat = stops_map_df["Latitude"].mean()
        mid_lon = stops_map_df["Longitude"].mean()

        view_state = pdk.ViewState(
            latitude=mid_lat,
            longitude=mid_lon,
            zoom=9,
            pitch=45
        )

        deck = pdk.Deck(
            layers=[line_layer, scatter_layer],
            initial_view_state=view_state,
            map_style="mapbox://styles/mapbox/light-v9"
        )

        st.pydeck_chart(deck)

# -------------------------------------------------
# Tab 5 – Utilization Dashboard
# -------------------------------------------------
with tabs[4]:
    st.subheader("Utilization Dashboard")

    util_df = get_utilization_for_date(kpi_date)
    if util_df.empty:
        st.info("No load plans for this date.")
    else:
        st.write("Latest load plan utilization per dispatch for this date.")
        st.dataframe(util_df, use_container_width=True)

        fig_u = px.bar(
            util_df,
            x="DispatchLabel",
            y=["Util_weight_pct", "Util_volume_pct"],
            barmode="group",
            labels={"value": "Utilization (%)", "variable": "Metric"},
        )
        fig_u.update_layout(xaxis_title="", legend_title="")
        st.plotly_chart(fig_u, use_container_width=True)

# -------------------------------------------------
# Tab 6 – 3D Load View
# -------------------------------------------------
with tabs[5]:
    st.subheader("3D Load View – Latest LoadPlan for Selected Dispatch")

    if st.button("Generate Load Plan for this Dispatch"):
        lp_id = pack_dispatch(selected_dispatch_id)
        st.success(f"LoadPlan {lp_id} generated.")
    else:
        lp_id = get_latest_loadplan_id(selected_dispatch_id)

    if lp_id is None:
        st.info("No load plan found yet. Click 'Generate Load Plan for this Dispatch'.")
    else:
        placements_df = get_placements_for_loadplan(lp_id)
        if placements_df.empty:
            st.info("No package placements found for this load plan.")
        else:
            fig3d = make_3d_figure(placements_df, selected_dispatch_id, lp_id)
            st.pyplot(fig3d)
