
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
            all_sensor_dates[folder] = set()
            continue

        csv_files = glob.glob(os.path.join(folder_path, '*_????????_*.csv'))
        dates_in_folder = set()
        for file in csv_files:
            match = re.search(r'_(\d{8})_', os.path.basename(file))
            if match:
                dates_in_folder.add(match.group(1))
        all_sensor_dates[folder] = dates_in_folder

    if not all_sensor_dates:
        return []

    common_dates = set.intersection(*all_sensor_dates.values())
    # Sort in ascending order (earliest date first)
    return sorted(list(common_dates))

@st.cache_data
def load_and_preprocess_data(base_dir, sensor_folders, selected_date, required_columns):
    all_data = []
    for sensor_id, folder in enumerate(sensor_folders):
        file_pattern = os.path.join(base_dir, folder, f'*_{selected_date}_*.csv')
        csv_files = glob.glob(file_pattern)

        if not csv_files:
            continue

        file_path = csv_files[0]
        try:
            df = pd.read_csv(file_path, sep=';')
            df = df.rename(columns={df.columns[0]: 'Time'})
            df['Sensor'] = folder
            for col in required_columns:
                if col not in df.columns:
                    df[col] = pd.NA
            cols_to_keep = ['Time'] + [c for c in required_columns if c in df.columns] + ['Sensor']
            df_selected = df[cols_to_keep].copy()
            all_data.append(df_selected)
        except Exception as e:
            st.error(f"Error loading data from {folder}: {e}")

    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        for col in required_columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')
        return combined_df
    return pd.DataFrame()

# --- App UI ---
st.set_page_config(layout='wide', page_title='Weather Analysis')
st.title('☀️ Weather Sensor Analysis')

common_dates = find_common_dates(DATA_DIR, SENSOR_FOLDERS)

if not common_dates:
    st.error('No common dates found across all 5 sensors.')
else:
    # Display dates in order
    selected_date = st.sidebar.selectbox('Select Date (YYYYMMDD)', common_dates)
    data = load_and_preprocess_data(DATA_DIR, SENSOR_FOLDERS, selected_date, REQUIRED_COLUMNS)

    if not data.empty:
        param = st.selectbox('Choose Parameter to Analyze', REQUIRED_COLUMNS)
        
        st.subheader(f'Sensor Overlap: {param}')
        fig_line = px.line(data, x='Time', y=param, color='Sensor', hover_data=['Time'])
        st.plotly_chart(fig_line, use_container_width=True)

        st.subheader(f'Average of All 5 Sensors: {param}')
        avg_df = data.groupby('Time')[param].mean().reset_index()
        fig_avg = px.line(avg_df, x='Time', y=param)
        st.plotly_chart(fig_avg, use_container_width=True)

        st.header('Pairwise Comparison')
        c1, c2 = st.columns(2)
        with c1: s1 = st.selectbox('Select Sensor A', SENSOR_FOLDERS, index=0)
        with c2: s2 = st.selectbox('Select Sensor B', SENSOR_FOLDERS, index=1)

        if s1 != s2:
            d1 = data[data['Sensor'] == s1][['Time', param]].set_index('Time')
            d2 = data[data['Sensor'] == s2][['Time', param]].set_index('Time')
            comp = pd.merge(d1, d2, left_index=True, right_index=True, suffixes=('_A', '_B'))
            
            if not comp.empty:
                st.markdown('#### Dataset Statistics Table')
                stats_df = comp.describe().T[['mean', 'std', 'min', 'max']]
                stats_df['P95'] = [comp.iloc[:,0].quantile(0.95), comp.iloc[:,1].quantile(0.95)]
                st.dataframe(stats_df)
                
                pearson = comp.corr().iloc[0,1]
                rmse = ((comp.iloc[:,0] - comp.iloc[:,1])**2).mean()**0.5
                st.write(f'**Pearson\'s r:** {pearson:.4f} | **RMSE:** {rmse:.4f}')
            else:
                st.info('No common timestamps found between these two sensors.')
