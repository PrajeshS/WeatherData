
import streamlit as st
import pandas as pd
import numpy as np
import os
import glob
import re
import plotly.express as px

# --- Configuration ---
SENSOR_FOLDERS = ['WMS 01', 'WMS 02', 'WMS 03', 'WMS 04', 'WMS 05']

# Standardized keys with flexible matching to handle naming variations and typos like 'AldedoUp'
TARGET_PARAMS = {
    'GTI Irradiance': ['GTI;solar_irradiance_tilted;Avg', 'GTI;solar_irradiance;Avg'],
    'Albedo Down': ['AlbedoDown;solar_irradiance;Avg'],
    'Albedo Up': ['AldedoUp;solar_irradiance;Avg', 'AlbedoUp;solar_irradiance;Avg']
}

DATA_DIR = '.'

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
            df = pd.read_csv(csv_files[0], sep=',', skipinitialspace=True, on_bad_lines='skip')
            
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

st.set_page_config(layout='wide', page_title='Weather Data Analysis')
st.title('☀️ Weather Sensor Data Analysis')
mode = st.sidebar.radio(
    "Mode",
    ["Single Day", "Date Range"],
    key="mode_selector"
)
available_dates = find_available_dates(DATA_DIR, SENSOR_FOLDERS)

if not available_dates:
    st.warning("No available dates found")
    st.stop()

min_d = min(available_dates)
max_d = max(available_dates)

if mode == "Single Day":
    selected_date = st.sidebar.date_input(
        "Select Date",
        value=max_d,
        min_value=min_d,
        max_value=max_d,
        key="single_date"
    )

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
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)

    signature = get_data_signature(DATA_DIR, SENSOR_FOLDERS)

    data = load_and_preprocess_data(
    DATA_DIR,
    SENSOR_FOLDERS,
    dates_to_load,
    TARGET_PARAMS,
    signature
    )

if data.empty:
    st.error("No data loaded")
    st.stop()

data["Time"] = pd.to_datetime(data["Time"])
data = data.sort_values("Time")

# -----------------------------
# FILTER (safe for both modes)
# -----------------------------
if mode == "Date Range":
    filtered = data[
        (data["Time"].dt.date >= start_date.date()) &
        (data["Time"].dt.date <= end_date.date())
    ]
else:
    filtered = data.copy()

# -----------------------------
# AVERAGE TABLE
# -----------------------------
avg_table = (
    filtered
    .groupby("Time")[["GTI Irradiance", "Albedo Down", "Albedo Up"]]
    .mean()
    .reset_index()
)

avg_table.columns = [
    "Time",
    "Avg GTI Irradiance",
    "Avg Albedo Down",
    "Avg Albedo Up"
]

csv = avg_table.to_csv(index=False).encode("utf-8")

st.download_button(
    label="📥 Download Average Data CSV",
    data=csv,
    file_name="weather_avg.csv",
    mime="text/csv"
)

# --------------------------
# MAIN VISUALIZATION BLOCK
# --------------------------
if not data.empty:
    available_params = [c for c in data.columns if c not in ['Time', 'Sensor']]

    if available_params:
        param = st.selectbox('Choose Parameter to Visualize', available_params)
        plot_data = data.dropna(subset=[param])

        st.subheader(f'Overlap Plot: {param}')
        st.plotly_chart(px.line(plot_data, x='Time', y=param, color='Sensor'), use_container_width=True)

        st.subheader(f'Average Plot: {param}')
        avg_df = plot_data.groupby('Time')[param].mean().reset_index()
        st.plotly_chart(px.line(avg_df, x='Time', y=param), use_container_width=True)

        st.divider()
        st.header('Pairwise Comparison (Filtered for Daytime > 0.5 W/m²)')

        col1, col2 = st.columns(2)

        with col1:
            s1 = st.selectbox('Sensor A', SENSOR_FOLDERS, index=0)

        with col2:
            s2 = st.selectbox('Sensor B', SENSOR_FOLDERS, index=1)

        if s1 != s2:
            d1 = plot_data[plot_data['Sensor'] == s1][['Time', param]].set_index('Time')
            d2 = plot_data[plot_data['Sensor'] == s2][['Time', param]].set_index('Time')

            comp = pd.merge(d1, d2, left_index=True, right_index=True, suffixes=('_A', '_B'))

            comp = comp[(comp.iloc[:, 0] > 0.5) & (comp.iloc[:, 1] > 0.5)].dropna()

            if not comp.empty:
                stats = comp.describe().T[['mean', 'std', 'min', 'max']]
                stats['P50'] = [comp.iloc[:, 0].quantile(0.50), comp.iloc[:, 1].quantile(0.50)]
                stats['P90'] = [comp.iloc[:, 0].quantile(0.90), comp.iloc[:, 1].quantile(0.90)]
                stats['P95'] = [comp.iloc[:, 0].quantile(0.95), comp.iloc[:, 1].quantile(0.95)]
                st.table(stats)

                m1, m2 = comp.iloc[:, 0], comp.iloc[:, 1]

                rmse = np.sqrt(((m1 - m2) ** 2).mean())
                mae = np.abs(m1 - m2).mean()
                nrmse = (rmse / m1.mean()) * 100 if m1.mean() != 0 else 0
                bias = (m1 - m2).mean()
                mape = (np.abs((m1 - m2) / m1).mean()) * 100

                row1 = st.columns(3)
                row2 = st.columns(3)

                row1[0].metric("Pearson's r", f"{comp.corr().iloc[0,1]:.4f}")
                row1[1].metric("RMSE", f"{rmse:.2f}")
                row1[2].metric("MAE", f"{mae:.2f}")

                row2[0].metric("nRMSE", f"{nrmse:.2f}%")
                row2[1].metric("Bias", f"{bias:.2f}")
                row2[2].metric("MAPE", f"{mape:.2f}%")

            else:
                st.info("No values above 0.5 found in overlap.")

    else:
        st.error("Parameters not found.")

else:
    st.error("No data loaded.")
