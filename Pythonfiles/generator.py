# generator.py

import random
import datetime as dt
import db   # this is your db.py file

# ---------- TUNING KNOBS (you can change these) ----------
DAYS               = 3            # how many service days to generate
DISPATCHES_PER_DAY = 6            # trucks per day
PKGS_PER_DISPATCH  = (120, 260)   # range of packages per dispatch

# (length_cm, width_cm, height_cm, weight_lbs)
DIM_BUCKETS = [
    (30, 20, 15,  6),
    (35, 25, 20,  9),
    (40, 30, 25, 12),
    (50, 35, 25, 16),
    (60, 40, 30, 20),
    (70, 45, 35, 24),
    (80, 50, 40, 30),
]

# ---------------------------------------------------------


def ensure_truck_types_and_trucks():
    """Ensure there are some truck types and trucks in the DB."""
    # Check TruckType
    tt_count = db.scalar("SELECT COUNT(*) FROM wh.TruckType")
    if tt_count == 0:
        db.execmany("""
            INSERT INTO wh.TruckType (name, length_cm, width_cm, height_cm, max_weight_lbs)
            VALUES (?, ?, ?, ?, ?)
        """, [
            ("Small Van",  260, 160, 140,  2500),
            ("Medium Box", 400, 200, 180,  6000),
            ("Large Box",  600, 240, 240, 12000),
        ])

    # Check Truck
    t_count = db.scalar("SELECT COUNT(*) FROM wh.Truck")
    if t_count == 0:
        rows = []
        tt = db.read("SELECT Type_id, name FROM wh.TruckType ORDER BY Type_id")
        if tt.empty:
            return
        for i, row in enumerate(tt.itertuples(), start=1):
            # create 4 trucks per type
            for k in range(4):
                label = f"{row.name[:2].upper()}-{i}{k+1:02d}"
                rows.append((int(row.Type_id), label, "AVAILABLE"))
        db.execmany("""
            INSERT INTO wh.Truck (type_id, label, status)
            VALUES (?, ?, ?)
        """, rows)


def make_dispatches_and_packages():
    """Generate dispatches, stops, and packages for multiple days."""
    # We will use existing addresses.
    addr_df = db.read("""
        SELECT Address_id, City, State, Postal_code, Latitude, Longitude
        FROM wh.Address
    """)
    if addr_df.empty:
        raise RuntimeError("wh.Address has no rows; need some addresses first.")

    trucks_df = db.read("SELECT Truck_id FROM wh.Truck")
    if trucks_df.empty:
        raise RuntimeError("wh.Truck has no rows even after ensure_truck_types_and_trucks.")

    truck_ids = [int(x) for x in trucks_df["Truck_id"].tolist()]

    today = dt.date.today()

    for day_offset in range(DAYS):
        service_date = today + dt.timedelta(days=day_offset)

        for d in range(DISPATCHES_PER_DAY):
            truck_id = random.choice(truck_ids)

            # Insert a dispatch
            dispatch_id = db.scalar("""
                INSERT INTO wh.Dispatch (truck_id, service_date, status)
                OUTPUT INSERTED.Dispatch_id
                VALUES (?, ?, 'PLANNED')
            """, [truck_id, service_date.isoformat()])

            # Choose 15–45 stops for this dispatch (or fewer if we don't have that many addresses)
            max_stops = min(45, len(addr_df))
            min_stops = min(15, max_stops)
            n_stops = random.randint(min_stops, max_stops)

            addr_sample = addr_df.sample(n=n_stops, replace=False, random_state=None)

            # Insert DispatchStop
            stop_rows = []
            seq = 1
            for _, a in addr_sample.iterrows():
                stop_rows.append((int(dispatch_id), int(a["Address_id"]), seq))
                seq += 1

            db.execmany("""
                INSERT INTO wh.DispatchStop (dispatch_id, address_id, sequence)
                VALUES (?, ?, ?)
            """, stop_rows)

            # Get the Stop_ids we just created
            stops = db.read("""
                SELECT Stop_id, Address_id
                FROM wh.DispatchStop
                WHERE dispatch_id = ?
                ORDER BY sequence
            """, [int(dispatch_id)])

            # Generate packages per stop
            total_pkgs_target = random.randint(*PKGS_PER_DISPATCH)
            remaining = total_pkgs_target

            pkg_rows = []      # for wh.Package
            assign_rows = []   # for wh.PackageAssignment

            for s in stops.itertuples():
                if remaining <= 0:
                    break

                # random number of packages for this stop
                this_count = max(1, int(random.gauss(mu=4, sigma=2)))
                this_count = min(this_count, remaining)
                remaining -= this_count

                for _ in range(this_count):
                    L, W, H, wt = random.choice(DIM_BUCKETS)
                    fragile = 1 if random.random() < 0.12 else 0
                    pkg_id = f"PKG{random.randint(10000000, 99999999)}"

                    pkg_rows.append((
                        pkg_id,
                        int(s.Address_id),
                        float(wt),
                        int(L),
                        int(W),
                        int(H),
                        fragile,
                        "CREATED",
                        dt.datetime.utcnow()
                    ))

                    assign_rows.append((
                        pkg_id,
                        int(s.Stop_id),
                        dt.datetime.utcnow()
                    ))

            if pkg_rows:
                db.execmany("""
                    INSERT INTO wh.Package
                    (package_id, address_id, weight_lbs, length_cm, width_cm, height_cm,
                     fragile_flag, status, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, pkg_rows)

            if assign_rows:
                # Adjust if your PackageAssignment table does NOT have Assigned_ts
                db.execmany("""
                    INSERT INTO wh.PackageAssignment (package_id, stop_id, assigned_ts)
                    VALUES (?, ?, ?)
                """, assign_rows)


def run():
    """Entry point for script."""
    ensure_truck_types_and_trucks()
    make_dispatches_and_packages()
    return "Large dispatch + package data generated."


if __name__ == "__main__":
    print(run())
