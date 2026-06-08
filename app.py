
import streamlit as st
import pandas as pd
import os
import glob
import re
import plotly.express as px

# --- Configuration --- #
SENSOR_FOLDERS = ['WMS 01', 'WMS 02', 'WMS 03', 'WMS 04', 'WMS 05']
REQUIRED_COLUMNS = [
    'GTI;solar_irradiance;Avg',
    'AlbedoDown;solar_irradiance;Avg',
    'AldedoUp;solar_irradiance;Avg'
]
DATA_DIR = '.' 

# --- Helper Functions --- #

@st.cache_data
def find_common_dates(base_dir, sensor_folders):
    all_sensor_dates = {}
    for folder in sensor_folders:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            st.warning(f"Sensor folder not found: {folder_path}")
            all_sensor_dates[folder] = set()
            continue

        # Use a wildcard to find all CSV files regardless of the prefix
        csv_files = glob.glob(os.path.join(folder_path, '*_????????_*.csv'))
        dates_in_folder = set()
        for file in csv_files:
            # Extract the 8 digits between the underscores
            match = re.search(r'_(\d{8})_', os.path.basename(file))
            if match:
                dates_in_folder.add(match.group(1))
        all_sensor_dates[folder] = dates_in_folder

    if not all_sensor_dates:
        return []

    # Find intersection: dates that exist in ALL folders
    common_dates = set.intersection(*all_sensor_dates.values())
    return sorted(list(common_dates), reverse=True)

@st.cache_data
def load_and_preprocess_data(base_dir, sensor_folders, selected_date, required_columns):
    all_data = []
    for sensor_id, folder in enumerate(sensor_folders):
        # Search for any file in the folder that contains the selected date string
        file_pattern = os.path.join(base_dir, folder, f'*_{selected_date}_*.csv')
        csv_files = glob.glob(file_pattern)

        if not csv_files:
            continue

        file_path = csv_files[0]
        try:
            df = pd.read_csv(file_path, sep=';')
            df['Sensor'] = folder
            df['Sensor_ID'] = sensor_id + 1

            for col in required_columns:
                if col not in df.columns:
                    df[col] = pd.NA
            
            df_selected = df[['Time'] + required_columns + ['Sensor', 'Sensor_ID']].copy()
            all_data.append(df_selected)
        except Exception as e:
            st.error(f"Error loading data from {file_path}: {e}")

    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        for col in required_columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')
        return combined_df
    return pd.DataFrame()

# --- Streamlit App Layout --- #
st.set_page_config(layout="wide", page_title="Weather Sensor Data Analysis")
st.title("☀️ Weather Sensor Data Analysis")

common_dates = find_common_dates(DATA_DIR, SENSOR_FOLDERS)

if not common_dates:
    st.error("No common dates found across all sensor folders.")
else:
    st.sidebar.header("Configuration")
    selected_date = st.sidebar.selectbox("Select a Date (YYYYMMDD)", common_dates)
    data_for_date = load_and_preprocess_data(DATA_DIR, SENSOR_FOLDERS, selected_date, REQUIRED_COLUMNS)

    if not data_for_date.empty:
        st.header("Interactive Plots")
        selected_parameter = st.selectbox("Choose a parameter:", REQUIRED_COLUMNS)

        if selected_parameter:
            fig_overlap = px.line(data_for_date, x='Time', y=selected_parameter, color='Sensor', title=f'Overlapping: {selected_parameter}')
            st.plotly_chart(fig_overlap, use_container_width=True)

            avg_data = data_for_date.groupby('Time')[selected_parameter].mean().reset_index()
            fig_avg = px.line(avg_data, x='Time', y=selected_parameter, title=f'Average: {selected_parameter}')
            st.plotly_chart(fig_avg, use_container_width=True)

        st.header("Pairwise Comparison")
        c1, c2 = st.columns(2)
        with c1: s1 = st.selectbox("Sensor 1", SENSOR_FOLDERS, index=0)
        with c2: s2 = st.selectbox("Sensor 2", SENSOR_FOLDERS, index=1)

        if s1 != s2:
            df_s1 = data_for_date[data_for_date['Sensor'] == s1][['Time', selected_parameter]].set_index('Time')
            df_s2 = data_for_date[data_for_date['Sensor'] == s2][['Time', selected_parameter]].set_index('Time')
            comp = pd.merge(df_s1, df_s2, left_index=True, right_index=True, suffixes=(f'_{s1}', f'_{s2}'))

            if not comp.empty:
                st.markdown("#### Statistics")
                stats = pd.DataFrame({
                    metric: [comp[f'{selected_parameter}_{s}'].mean(), comp[f'{selected_parameter}_{s}'].std(), comp[f'{selected_parameter}_{s}'].min(), comp[f'{selected_parameter}_{s}'].max(), comp[f'{selected_parameter}_{s}'].quantile(0.95)] 
                    for s in [s1, s2]
                }, index=['Mean', 'Std Dev', 'Min', 'Max', 'P95']).T
                st.dataframe(stats)
                
                pearson = comp.corr().iloc[0,1]
                rmse = ((comp.iloc[:,0] - comp.iloc[:,1])**2).mean()**0.5
                st.write(f"**Pearson's r:** {pearson:.4f} | **RMSE:** {rmse:.4f}")
