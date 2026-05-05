import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from app.config import settings

def _get_sync_engine():
    url = settings.DATABASE_URL
    if "sqlite+aiosqlite" in url:
        url = url.replace("sqlite+aiosqlite", "sqlite")
    elif "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    return create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})

def generate_hotspot_report() -> dict:
    engine = _get_sync_engine()
    try:
        df = pd.read_sql("""
            SELECT latitude AS lat, longitude AS lon, g_force_peak,
                   triggered_at, response_minutes
            FROM emergency_logs
            WHERE status != 'cancelled'
        """, engine)
    except Exception as e:
        return {"message": f"No data yet: {str(e)}", "total_incidents": 0}

    if df.empty:
        return {"message": "No incidents recorded yet", "total_incidents": 0}

    df["lat_bin"] = (df["lat"] * 200).round() / 200
    df["lon_bin"] = (df["lon"] * 200).round() / 200

    hotspots = df.groupby(["lat_bin", "lon_bin"]).agg(
        incident_count=("g_force_peak", "count"),
        avg_g_force=("g_force_peak", "mean"),
        avg_response_min=("response_minutes", "mean")
    ).reset_index().sort_values("incident_count", ascending=False)

    os.makedirs("static/reports", exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), facecolor="#0f172a")
    for ax in axes:
        ax.set_facecolor("#1e293b")

    pivot = hotspots.pivot_table(values="incident_count", index="lat_bin", columns="lon_bin", fill_value=0)
    sns.heatmap(pivot, ax=axes[0], cmap="YlOrRd", cbar_kws={"label": "Incidents"})
    axes[0].set_title("Accident Hotspots", color="white", fontsize=14)
    axes[0].tick_params(colors="white")

    top10 = hotspots.head(10).copy()
    top10["zone"] = top10["lat_bin"].astype(str) + "," + top10["lon_bin"].astype(str)
    sns.barplot(data=top10, x="incident_count", y="zone", ax=axes[1], palette="Reds_r")
    axes[1].set_title("Top Danger Zones", color="white", fontsize=14)
    axes[1].tick_params(colors="white")

    plt.tight_layout()
    plt.savefig("static/reports/hotspots.png", dpi=150, facecolor="#0f172a")
    plt.close()

    return {
        "total_incidents": int(len(df)),
        "avg_response_minutes": round(float(df["response_minutes"].dropna().mean()), 2) if df["response_minutes"].notna().any() else 0,
        "top_hotspots": hotspots.head(5).to_dict(orient="records"),
        "report_url": "/static/reports/hotspots.png"
    }

def generate_response_time_report() -> dict:
    engine = _get_sync_engine()
    try:
        df = pd.read_sql("""
            SELECT triggered_at, response_minutes
            FROM emergency_logs WHERE status = 'responded'
        """, engine)
    except Exception:
        return {"message": "No data"}
    if df.empty:
        return {"message": "No response data yet"}
    return {"avg_response_minutes": round(float(df["response_minutes"].mean()), 2)}
