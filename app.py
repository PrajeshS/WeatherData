
import streamlit as st
import pandas as pd
import os
import glob
import re
import plotly.express as px

# --- Configuration ---
SENSOR_FOLDERS = ['WMS 01', 'WMS 02', 'WMS 03', 'WMS 04', 'WMS 05']

# Updated to match the exact hierarchy strings found in your CSV extract
REQUIRED_COLUMNS = [
    'GTI;solar_irradiance_tilted;Avg',
    'AlbedoDown;solar_irradiance;Avg',
    'AlbedoUp;solar_irradiance;Avg'
]
DATA_DIR = '.'

@st.cache_data
def find_common_dates(base_dir, sensor_folders):
    all_sensor_dates = {}
    for folder in sensor_folders:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path): continue
        csv_files = glob.glob(os.path.join(folder_path, '*_????????_*.csv'))
        dates = {re.search(r'_(\d{8})_', os.path.basename(f)).group(1) for f in csv_files if re.search(r'_(\d{8})_', os.path.basename(f))}
        all_sensor_dates[folder] = dates
    if not all_sensor_dates or len(all_sensor_dates) < len(sensor_folders):
        return []
    return sorted(list(set.intersection(*all_sensor_dates.values())))

@st.cache_data
def load_and_preprocess_data(base_dir, sensor_folders, selected_date, required_columns):
    all_data = []
    for folder in sensor_folders:
        file_pattern = os.path.join(base_dir, folder, f'*_{selected_date}_*.csv')
        csv_files = glob.glob(file_pattern)
        if not csv_files: continue
        
        try:
            # Based on your extract, the real CSV delimiter is a comma
            df = pd.read_csv(csv_files[0], sep=',', skipinitialspace=True)
            
            # Clean headers: remove quotes and strip whitespace
            df.columns = [c.strip().replace('"', '') for c in df.columns]
            
            # Map 'Date/time' (or first column) to 'Time'
            time_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), df.columns[0])
            df = df.rename(columns={time_col: 'Time'})
            
            # Convert Time to datetime objects and round for sensor alignment
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Time'] = df['Time'].dt.round('1min')
            
            df['Sensor'] = folder
            
            # Convert irradiance columns to numeric
            for col in required_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            cols_to_keep = ['Time'] + [c for c in required_columns if c in df.columns] + ['Sensor']
            all_data.append(df[cols_to_keep])
        except Exception as e:
            st.error(f"Error loading {folder}: {e}")
            
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

st.set_page_config(layout='wide', page_title='Weather Analysis')
st.title('Weather Sensor Data Analysis')

common_dates = find_common_dates(DATA_DIR, SENSOR_FOLDERS)

if not common_dates:
    st.warning('No common dates found. Please verify your data folders WMS 01-05.')
else:
    selected_date = st.sidebar.selectbox('📅 Select Date', common_dates)
    data = load_and_preprocess_data(DATA_DIR, SENSOR_FOLDERS, selected_date, REQUIRED_COLUMNS)

    if not data.empty:
        with st.expander("Data Preview & Column Check"):
            st.write("Available columns:", data.columns.tolist())
            st.dataframe(data.head())
            
        available_params = [c for c in data.columns if c not in ['Time', 'Sensor']]
        param = st.selectbox('Choose Parameter to Visualize', available_params)
        plot_data = data.dropna(subset=[param])

        if not plot_data.empty:
            st.subheader(f'Overlap Plot: {param}')
            st.plotly_chart(px.line(plot_data, x='Time', y=param, color='Sensor'), use_container_width=True)

            st.subheader(f'Average Plot: {param}')
            avg_df = plot_data.groupby('Time')[param].mean().reset_index()
            st.plotly_chart(px.line(avg_df, x='Time', y=param), use_container_width=True)

            st.divider()
            st.header('Pairwise Comparison')
            s1 = st.selectbox('Select Sensor A', SENSOR_FOLDERS, index=0)
            s2 = st.selectbox('Select Sensor B', SENSOR_FOLDERS, index=1)

            if s1 != s2:
                d1 = plot_data[plot_data['Sensor'] == s1][['Time', param]].set_index('Time')
                d2 = plot_data[plot_data['Sensor'] == s2][['Time', param]].set_index('Time')
                comp = pd.merge(d1, d2, left_index=True, right_index=True, suffixes=('_A', '_B')).dropna()
                if not comp.empty:
                    stats = comp.describe().T[['mean', 'std', 'min', 'max']]
                    stats['P95'] = [comp.iloc[:,0].quantile(0.95), comp.iloc[:,1].quantile(0.95)]
                    st.table(stats)
                    st.metric("Pearson's r", f"{comp.corr().iloc[0,1]:.4f}")
                    st.metric("RMSE", f"{((comp.iloc[:,0]-comp.iloc[:,1])**2).mean()**0.5:.4f}")
                else:
                    st.info('No overlapping timestamps found between these sensors.')
        else:
            st.error(f'No numeric data available for {param}. Check the data preview.')
    else:
        st.error('No data could be loaded for the selected date.')
