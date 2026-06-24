
import streamlit as st
import pandas as pd
import numpy as np
import os
import glob
import re
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(layout='wide', page_title='Weather Data Analysis')
st.title("☀️ Weather Forecast Data Analysis")
mode = st.sidebar.radio(
    "Mode",
    ["Single Day", "Date Range"],
    key="mode_selector"
)
# --- Configuration ---
SENSOR_FOLDERS = ['WMS 01', 'WMS 02', 'WMS 03', 'WMS 04', 'WMS 05']

# Standardized keys with flexible matching to handle naming variations and typos like 'AldedoUp'
TARGET_PARAMS = {
    'GTI Irradiance (W/m²)': ['GTI;solar_irradiance_tilted;Avg', 'GTI;solar_irradiance;Avg'],
    'Albedo Down Irradiance (W/m²)': ['AlbedoDown;solar_irradiance;Avg'],
    'Albedo Up Irradiance (W/m²)': ['AldedoUp;solar_irradiance;Avg', 'AlbedoUp;solar_irradiance;Avg'],
    'ATRHP Temperature (°C)': ['ATRHP;temperature;Avg'],
    'ATRHP Humidity (%)': ['ATRHP;humidity;Avg']
}

DATA_DIR = '.'
FORECAST_FILE = "forecast.csv"

FORECAST_MAPPING = {
    "GTI Irradiance (W/m²)": "gti",
    "Albedo Up Irradiance (W/m²)": "ghi",
    "ATRHP Temperature (°C)": "air_temp",
    "ATRHP Humidity (%)": "relative_humidity"
}

def get_data_signature(base_dir, sensor_folders):
    sig = []

    for folder in sensor_folders:
        path = os.path.join(base_dir, folder)
        files = glob.glob(os.path.join(path, "*.csv"))

        if files:
            latest_time = max(os.path.getmtime(f) for f in files)
            sig.append(f"{len(files)}_{latest_time}")
        else:
            sig.append("0_0")

    return "_".join(sig)
    
from datetime import datetime

def find_available_dates(base_dir, sensor_folders):
    all_dates = set()

    for folder in sensor_folders:
        folder_path = os.path.join(base_dir, folder)

        if not os.path.isdir(folder_path):
            continue

        csv_files = glob.glob(os.path.join(folder_path, '*_????????_*.csv'))

        for f in csv_files:
            match = re.search(r'_(\d{8})_', os.path.basename(f))
            if match:
                all_dates.add(match.group(1))

    return sorted(
        [datetime.strptime(d, "%Y%m%d").date() for d in all_dates],
        reverse=True
    )
@st.cache_data
def load_and_preprocess_data(base_dir, sensor_folders, dates_to_load, target_params, signature):
    all_data = []
    for folder in sensor_folders:
        csv_files = []
        for d in dates_to_load:
            pattern = os.path.join(base_dir, folder, f'*_{d}_*.csv')
            csv_files.extend(glob.glob(pattern))
        if not csv_files: continue

        try:
            df_list = []

            for f in csv_files:
                temp = pd.read_csv(f, sep=',', skipinitialspace=True, on_bad_lines='skip')
                df_list.append(temp)

            df = pd.concat(df_list, ignore_index=True)
            
            # Clean headers: remove non-printable chars and quotes
            df.columns = [re.sub(r'[^\x20-\x7E]', '', str(c)).strip().replace('"', '') for c in df.columns]

            # Identify Time column
            time_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), df.columns[0])
            df = df.rename(columns={time_col: 'Time'})
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Time'] = df['Time'].dt.round('1min')

            df['Sensor'] = folder

            # Map specific columns to our standardized parameter names
            found_cols = []
            for display_name, possible_names in target_params.items():
                match = next((c for c in df.columns if any(name == c or name in c for name in possible_names)), None)
                if match:
                    df[display_name] = pd.to_numeric(df[match], errors='coerce')
                    found_cols.append(display_name)

            all_data.append(df[['Time', 'Sensor'] + found_cols])
        except Exception as e:
            st.error(f"Error loading {folder}: {e}")

    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()
@st.cache_data
def load_forecast_data():
    forecast = pd.read_csv(FORECAST_FILE)

    forecast["datetime"] = pd.to_datetime(
        forecast["datetime"],
        errors="coerce"
    )

    forecast = forecast.dropna(subset=["datetime"])

    forecast["MatchKey"] = forecast["datetime"].dt.strftime("%m-%d %H:%M")

    forecast = forecast.sort_values("datetime")

    forecast = forecast.drop_duplicates(
        subset="MatchKey",
        keep="last"
    )

    return forecast
available_dates = find_available_dates(DATA_DIR, SENSOR_FOLDERS)

if not available_dates:
    st.stop()

min_d = min(available_dates)
max_d = max(available_dates)
# ensure defaults exist
start_date = None
end_date = None

if mode == "Single Day":
    selected_date = st.sidebar.date_input(
        "Select Date",
        min_value=min_d,
        max_value=max_d,
        value=max_d,
        key="single_date"
    )

    start_date = selected_date
    end_date = selected_date
    dates_to_load = [selected_date.strftime("%Y%m%d")]

else:
    start_date, end_date = st.sidebar.date_input(
        "Select Date Range",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d,
        key="range_date"
    )

    dates_to_load = pd.date_range(start_date, end_date).strftime("%Y%m%d").tolist()

# load data AFTER dates are defined
signature = get_data_signature(DATA_DIR, SENSOR_FOLDERS)
data = load_and_preprocess_data(DATA_DIR, SENSOR_FOLDERS, dates_to_load, TARGET_PARAMS, signature)

if data.empty:
    st.error("No data loaded")
    st.stop()

data["Time"] = pd.to_datetime(data["Time"])
data = data.sort_values("Time")

# SAFE FILTER (works for both modes)
filtered = data[
    (data["Time"].dt.date >= start_date) &
    (data["Time"].dt.date <= end_date)
]
# -----------------------------
# AVERAGE TABLE
# -----------------------------
avg_table = filtered.groupby(["Time"])[
    ["GTI Irradiance (W/m²)", "Albedo Down Irradiance (W/m²)", "Albedo Up Irradiance (W/m²)", "ATRHP Temperature (°C)", "ATRHP Humidity (%)"]
].mean().reset_index()

avg_table.columns = [
    "Time",
    "Avg GTI Irradiance (W/m²)",
    "Avg Albedo Down Irradiance (W/m²)",
    "Avg Albedo Up Irradiance (W/m²)",
    "Avg ATRHP Temperature (°C)",
    "Avg ATRHP Humidity (%)"
]

csv = avg_table.to_csv(index=False).encode("utf-8")

if mode == "Single Day":
    file_name = f"weather_avg_{start_date.strftime('%Y%m%d')}.csv"
else:
    file_name = f"weather_avg_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
st.download_button(
    label="📥 Download Average Data CSV",
    data=csv,
    file_name=file_name,
    mime="text/csv"
)

# -----------------------------
# CREATE AVERAGED SENSOR DATA
# -----------------------------
avg_sensor = filtered.groupby("Time")[
    [
        "GTI Irradiance (W/m²)",
        "Albedo Down Irradiance (W/m²)",
        "Albedo Up Irradiance (W/m²)",
        "ATRHP Temperature (°C)",
        "ATRHP Humidity (%)"
    ]
].mean()

avg_sensor = (
    avg_sensor
    .resample("15min")
    .mean()
    .reset_index()
)

avg_sensor["MatchKey"] = avg_sensor["Time"].dt.strftime("%m-%d %H:%M")

forecast = load_forecast_data()

DISPLAY_OPTIONS = {
    "GTI Irradiance vs gti (W/m²)": "GTI Irradiance (W/m²)",
    "Albedo Up Irradiance vs ghi (W/m²)": "Albedo Up Irradiance (W/m²)",
    "ATRHP Temperature vs air_temp (°C)": "ATRHP Temperature (°C)",
    "ATRHP Humidity vs relative_humidity (%)": "ATRHP Humidity (%)"
}

selected_display = st.selectbox(
    "Choose Parameter to Visualize",
    list(DISPLAY_OPTIONS.keys())
)

param = DISPLAY_OPTIONS[selected_display]

param = st.selectbox(
    "Choose Parameter to Visualize",
    available_params
)

forecast_col = FORECAST_MAPPING[param]

comparison = pd.merge(
    avg_sensor[
        ["Time", "MatchKey", param]
    ],
    forecast[
        ["MatchKey", forecast_col]
    ],
    on="MatchKey",
    how="inner"
)

comparison.columns = [
    "Time",
    "MatchKey",
    "Measured",
    "Forecast"
]

comparison = comparison.dropna()

if param in [
    "GTI Irradiance (W/m²)",
    "Albedo Up Irradiance (W/m²)"
]:
    comparison = comparison[
        (comparison["Measured"] > 0.5)
        &
        (comparison["Forecast"] > 0.5)
    ]

if comparison.empty:
    st.warning("No overlapping data found.")
    st.stop()
st.subheader(f"{selected_display} Comparison")
# -----------------------------
# PLOT
# -----------------------------
fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=comparison["Time"],
        y=comparison["Measured"],
        mode="lines",
        name="Measured Average"
    )
)

fig.add_trace(
    go.Scatter(
        x=comparison["Time"],
        y=comparison["Forecast"],
        mode="lines",
        name="Forecast"
    )
)

fig.update_layout(
    title=selected_display,
    height=700,
    hovermode="x unified"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

st.divider()

st.header("Forecast Comparison Statistics")

stats = comparison[
    ["Measured", "Forecast"]
].describe().T[
    ["mean", "std", "min", "max"]
]

stats["P50"] = [
    comparison["Measured"].quantile(0.50),
    comparison["Forecast"].quantile(0.50)
]

stats["P90"] = [
    comparison["Measured"].quantile(0.90),
    comparison["Forecast"].quantile(0.90)
]

stats["P95"] = [
    comparison["Measured"].quantile(0.95),
    comparison["Forecast"].quantile(0.95)
]

st.table(stats)

m1 = comparison["Measured"]
m2 = comparison["Forecast"]

rmse = np.sqrt(((m1 - m2) ** 2).mean())
mae = np.abs(m1 - m2).mean()

nrmse = (
    (rmse / m1.mean()) * 100
    if m1.mean() != 0
    else 0
)

bias = (m1 - m2).mean()

mape = (
    np.abs((m1 - m2) / m1).mean()
) * 100

row1 = st.columns(3)
row2 = st.columns(3)

row1[0].metric(
    "Pearson's r",
    f"{comparison[['Measured','Forecast']].corr().iloc[0,1]:.4f}"
)

row1[1].metric(
    "RMSE",
    f"{rmse:.2f}"
)

row1[2].metric(
    "MAE",
    f"{mae:.2f}"
)

row2[0].metric(
    "nRMSE",
    f"{nrmse:.2f}%"
)

row2[1].metric(
    "Bias",
    f"{bias:.2f}"
)

row2[2].metric(
    "MAPE",
    f"{mape:.2f}%"
)
