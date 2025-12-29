# Smart Delivery Load, Truck Space, and Route Optimization System

This project presents an end-to-end logistics decision-support system designed to improve truck loading efficiency, fragile package handling, package lifecycle tracking, and delivery route visualization.

## Project Overview
Modern logistics operations require intelligent coordination between warehouse loading, delivery routing, and operational tracking. This system integrates database-driven planning, automated truck loading logic, and interactive visual dashboards to support real-world delivery operations.

## Key Features
- Automated truck loading based on package dimensions, weight, and fragility
- Truck space utilization analysis (weight and volume)
- Package lifecycle tracking (warehouse → loaded → delivered)
- Route map visualization using geographic coordinates
- 3D truck load visualization
- Manager-friendly Streamlit frontend

## Technology Stack
- Python
- SQL Server
- Streamlit
- Pandas / NumPy
- Matplotlib & PyDeck

## System Architecture
The system consists of a relational database backend, Python-based analytics and optimization logic, and a Streamlit frontend that presents dashboards and visualizations for non-technical users.

## How to Run
1. Configure database connection in `db.py`
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
## Run the application:

bash
streamlit run app.py
