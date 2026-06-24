import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import base64
from datetime import datetime, timedelta

# --- Config ---
REPO_PATH = "PrajeshS/WeatherData"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "") # Add to streamlit secrets or use local env
FORECAST_FILE = "forecast.csv"
SENSORS = ['WMS 01', 'WMS 02', 'WMS 03', 'WMS 04', 'WMS 05']

@st.cache_data
def load_forecast_data():
    df = pd.read_csv(FORECAST_FILE)
    df['datetime'] = pd.to_datetime(df['datetime'])
    return df

def get_github_file(path):
    url = f"https://api.github.com/repos/{REPO_PATH}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        content = base64.b64decode(resp.json()['content']).decode('utf-8')
        return pd.read_csv(pd.compat.StringIO(content), sep=';', engine='python')
    return None

@st.cache_data
def get_actual_data_range(start_date, end_date):
    all_days_data = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y%m%d')
        daily_sensor_data = []
        for sensor in SENSORS:
            # Filename pattern based on previous logic
            path = f"{sensor}/G254070_{date_str}_0000.csv" # Note: Using placeholder serial logic
            df = get_github_file(path)
            if df is not None:
                df['datetime'] = pd.to_datetime(df.iloc[:,0], errors='coerce')
                val_col = [c for c in df.columns if 'GTI' in c][0]
                df = df.rename(columns={val_col: 'Actual'})
                daily_sensor_data.append(df[['datetime', 'Actual']])
        
        if daily_sensor_data:
            combined = pd.concat(daily_sensor_data)
            # Average 5 sensors, then resample to 15min
            daily_avg = combined.groupby('datetime')['Actual'].mean().resample('15min').mean().reset_index()
            all_days_data.append(daily_avg)
        current_date += timedelta(days=1)
    
    return pd.concat(all_days_data) if all_days_data else pd.DataFrame()

st.set_page_config(layout='wide', page_title='Forecast vs Actual')
st.title("📊 Forecast vs Actual Weather Analysis")

# Sidebar selection
start_default = datetime(2026, 5, 18)
end_default = datetime.now() - timedelta(days=1)

st.sidebar.header("Selection")
date_range = st.sidebar.date_input("Select Date Range", [start_default, end_default], min_value=start_default)

if len(date_range) == 2:
    start_dt, end_dt = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    
    with st.spinner("Fetching and processing data..."):
        forecast_df = load_forecast_data()
        actual_df = get_actual_data_range(start_dt, end_dt)

    if not actual_df.empty:
        # Merge
        merged = pd.merge(forecast_df, actual_df, on='datetime', how='inner').dropna()
        
        # Plotting
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=merged['datetime'], y=merged['Actual'], name='Actual (15m Avg)', line=dict(color='blue')))
        fig.add_trace(go.Scatter(x=merged['datetime'], y=merged['forecast'], name='Forecast', line=dict(color='orange', dash='dot')))
        st.plotly_chart(fig, use_container_width=True)

        # Statistics
        st.header("Statistical Comparison")
        y_true, y_pred = merged['Actual'], merged['forecast']
        
        def calculate_metrics(actual, forecast):
            diff = forecast - actual
            metrics = {
                "Mean": [actual.mean(), forecast.mean()],
                "Std": [actual.std(), forecast.std()],
                "Min": [actual.min(), forecast.min()],
                "Max": [actual.max(), forecast.max()],
                "P50": [actual.median(), forecast.median()],
                "P90": [actual.quantile(0.9), forecast.quantile(0.9)],
                "P95": [actual.quantile(0.95), forecast.quantile(0.95)],
            }
            stats_df = pd.DataFrame(metrics, index=['Actual', 'Forecast']).T
            
            # Pairwise
            r = np.corrcoef(actual, forecast)[0,1]
            rmse = np.sqrt(((diff)**2).mean())
            mae = np.abs(diff).mean()
            nrmse = (rmse / actual.mean()) * 100 if actual.mean() != 0 else 0
            bias = diff.mean()
            mape = (np.abs(diff / actual).mean()) * 100 if (actual != 0).all() else np.nan
            
            return stats_df, r, rmse, mae, nrmse, bias, mape

        stats_df, r, rmse, mae, nrmse, bias, mape = calculate_metrics(y_true, y_pred)
        
        col1, col2 = st.columns([1, 2])
        with col1: st.table(stats_df)
        with col2:
            m_col1, m_col2, m_col3 = st.columns(3)
            m_col1.metric("Pearson's r", f"{r:.4f}")
            m_col2.metric("RMSE", f"{rmse:.2f}")
            m_col3.metric("MAE", f"{mae:.2f}")
            m_col1.metric("nRMSE %", f"{nrmse:.2f}%")
            m_col2.metric("Bias", f"{bias:.2f}")
            m_col3.metric("MAPE %", f"{mape:.2f}%" if not np.isnan(mape) else "N/A")
    else:
        st.error("No actual data found for the selected range in GitHub.")
