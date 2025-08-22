# Created: 2025-08-14 17:39:43
# Last Modified: 2025-08-22 06:01:41
# Author: Scott Cadreau

"""
EC2 Monitoring Dashboard

This is the main Streamlit application for monitoring EC2 instance performance.
It provides real-time visualization of CPU, memory, network, and disk metrics
for the SurgiCase primary API server during user onboarding periods.

Usage:
    streamlit run dashboard.py --server.port 8501

Features:
    - Real-time system metrics display
    - Interactive time-series charts
    - System health scoring
    - Alert monitoring
    - Auto-refresh capabilities
    - Historical data analysis
"""

import streamlit as st
import sys
import os
from datetime import datetime, timedelta
import time
import logging

# Add utils directory to path
utils_path = os.path.join(os.path.dirname(__file__), 'utils')
sys.path.insert(0, utils_path)

# Import dashboard utilities
try:
    from dashboard_db import (
        get_latest_monitoring_data,
        get_monitoring_data_by_hours,
        get_monitoring_summary_stats,
        get_recent_alerts,
        get_hourly_aggregated_data,
        get_system_health_score
    )
    from dashboard_charts import (
        create_cpu_timeline_chart,
        create_memory_timeline_chart,
        create_network_io_chart,
        create_disk_io_chart,
        create_system_overview_chart,
        create_combined_metrics_chart
    )
except ImportError as e:
    st.error(f"Failed to import dashboard utilities: {e}")
    st.error("Please ensure you're running the dashboard from the correct directory.")
    st.stop()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="EC2 Monitoring Dashboard",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
EC2_INSTANCE_ID = "i-099fb57644b0c33ba"
INSTANCE_TYPE = "m8g.8xlarge"
INSTANCE_SPECS = "32 vCPUs, 128GB RAM"

def format_bytes(bytes_value):
    """Format bytes into human readable format."""
    if bytes_value is None:
        return "N/A"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"

def get_status_emoji(value, warning_threshold=70, critical_threshold=80):
    """Get status emoji based on metric value and thresholds."""
    if value is None:
        return "⚪"
    elif value < warning_threshold:
        return "🟢"
    elif value < critical_threshold:
        return "🟡"
    else:
        return "🔴"

def display_header():
    """Display the dashboard header with instance information."""
    st.title("🖥️ EC2 Instance Monitoring Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Instance ID", EC2_INSTANCE_ID)
    
    with col2:
        st.metric("Instance Type", INSTANCE_TYPE)
    
    with col3:
        st.metric("Specifications", INSTANCE_SPECS)
    
    with col4:
        # System health score
        try:
            health_score, health_status = get_system_health_score()
            health_color = "🟢" if health_score >= 75 else "🟡" if health_score >= 50 else "🔴"
            st.metric("Health Score", f"{health_score}/100 {health_color}", health_status)
        except Exception as e:
            st.metric("Health Score", "Error", "Unable to calculate")
            logger.error(f"Health score display error: {str(e)}")

def display_current_metrics():
    """Display current system metrics in a card layout."""
    st.subheader("📊 Current System Status")
    
    current_data = get_latest_monitoring_data()
    
    if not current_data:
        st.error("No current monitoring data available")
        return
    
    # Last update time
    last_update = current_data['timestamp']
    time_diff = datetime.now() - last_update
    minutes_ago = int(time_diff.total_seconds() / 60)
    
    st.caption(f"Last updated: {last_update.strftime('%Y-%m-%d %H:%M:%S')} ({minutes_ago} minutes ago)")
    
    # Current metrics cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cpu_value = float(current_data['cpu_utilization_percent']) if current_data['cpu_utilization_percent'] else 0
        cpu_emoji = get_status_emoji(cpu_value)
        st.metric(
            "CPU Usage", 
            f"{cpu_value:.1f}%", 
            help=f"Current CPU utilization {cpu_emoji}"
        )
    
    with col2:
        memory_value = float(current_data['memory_utilization_percent']) if current_data['memory_utilization_percent'] else 0
        memory_emoji = get_status_emoji(memory_value)
        memory_gb = (memory_value / 100) * 32  # 32GB total
        st.metric(
            "Memory Usage", 
            f"{memory_value:.1f}%", 
            f"{memory_gb:.1f}GB / 32GB",
            help=f"Current memory utilization {memory_emoji}"
        )
    
    with col3:
        network_in = current_data['network_in_bytes'] or 0
        network_out = current_data['network_out_bytes'] or 0
        st.metric(
            "Network In", 
            format_bytes(network_in),
            help="Cumulative network input"
        )
    
    with col4:
        st.metric(
            "Network Out", 
            format_bytes(network_out),
            help="Cumulative network output"
        )

def display_alerts_section():
    """Display recent alerts and warnings."""
    st.subheader("🚨 Recent Alerts")
    
    alerts = get_recent_alerts(5)
    
    if not alerts:
        st.success("✅ No recent alerts - System running smoothly")
    else:
        for alert in alerts:
            severity_color = {
                'info': 'blue',
                'warning': 'orange', 
                'error': 'red'
            }.get(alert['severity'], 'gray')
            
            with st.container():
                st.markdown(f"**{alert['timestamp'].strftime('%H:%M:%S')}** - :{severity_color}[{alert['message']}]")

def display_time_series_charts(time_range_hours):
    """Display interactive time series charts."""
    st.subheader("📈 Performance Trends")
    
    # Get data based on time range
    if time_range_hours <= 6:
        # Use detailed data for short time ranges
        chart_data = get_monitoring_data_by_hours(time_range_hours)
    else:
        # Use aggregated data for longer time ranges
        chart_data = get_hourly_aggregated_data(time_range_hours)
        # Convert aggregated data format for charts
        if chart_data:
            for record in chart_data:
                record['timestamp'] = record['hour']
                record['cpu_utilization_percent'] = record['avg_cpu']
                record['memory_utilization_percent'] = record['avg_memory']
                record['network_in_bytes'] = record['avg_network_in']
                record['network_out_bytes'] = record['avg_network_out']
    
    if not chart_data:
        st.warning(f"No data available for the last {time_range_hours} hours")
        return
    
    # Display charts in tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "CPU", "Memory", "Network", "Disk I/O"])
    
    with tab1:
        # Combined metrics chart
        combined_chart = create_combined_metrics_chart(chart_data)
        st.plotly_chart(combined_chart, use_container_width=True)
        
        # System overview gauges
        current_data = get_latest_monitoring_data()
        if current_data:
            overview_chart = create_system_overview_chart(current_data)
            st.plotly_chart(overview_chart, use_container_width=True)
    
    with tab2:
        cpu_chart = create_cpu_timeline_chart(chart_data)
        st.plotly_chart(cpu_chart, use_container_width=True)
    
    with tab3:
        memory_chart = create_memory_timeline_chart(chart_data)
        st.plotly_chart(memory_chart, use_container_width=True)
    
    with tab4:
        network_chart = create_network_io_chart(chart_data)
        st.plotly_chart(network_chart, use_container_width=True)
    
    with tab5:
        disk_chart = create_disk_io_chart(chart_data)
        st.plotly_chart(disk_chart, use_container_width=True)

def display_summary_stats(time_range_hours):
    """Display summary statistics for the selected time period."""
    st.subheader("📋 Summary Statistics")
    
    stats = get_monitoring_summary_stats(time_range_hours)
    
    if not stats:
        st.warning(f"No statistics available for the last {time_range_hours} hours")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Avg CPU", f"{stats.get('avg_cpu', 0):.1f}%")
        st.metric("Max CPU", f"{stats.get('max_cpu', 0):.1f}%")
    
    with col2:
        st.metric("Avg Memory", f"{stats.get('avg_memory', 0):.1f}%")
        st.metric("Max Memory", f"{stats.get('max_memory', 0):.1f}%")
    
    with col3:
        st.metric("Data Points", f"{stats.get('total_records', 0):,}")
        st.metric("Alert Count", stats.get('alert_count', 0))
    
    with col4:
        # Calculate uptime percentage (assuming 1 record per minute)
        expected_records = time_range_hours * 60
        actual_records = stats.get('total_records', 0)
        uptime_pct = min(100, (actual_records / expected_records * 100)) if expected_records > 0 else 0
        st.metric("Data Coverage", f"{uptime_pct:.1f}%")
        
        # System load assessment
        avg_cpu = stats.get('avg_cpu', 0)
        avg_memory = stats.get('avg_memory', 0)
        load_status = "Light" if avg_cpu < 30 and avg_memory < 50 else "Moderate" if avg_cpu < 70 and avg_memory < 80 else "Heavy"
        st.metric("System Load", load_status)

def display_sidebar():
    """Display sidebar controls and information."""
    with st.sidebar:
        st.header("⚙️ Dashboard Controls")
        
        # Time range selector
        time_range_options = {
            "Last Hour": 1,
            "Last 6 Hours": 6,
            "Last 24 Hours": 24,
            "Last 3 Days": 72,
            "Last Week": 168
        }
        
        selected_range = st.selectbox(
            "📅 Time Range",
            options=list(time_range_options.keys()),
            index=1,  # Default to 6 hours
            help="Select the time period for chart display"
        )
        
        time_range_hours = time_range_options[selected_range]
        
        # Auto-refresh settings
        st.header("🔄 Auto Refresh")
        
        auto_refresh = st.checkbox(
            "Enable Auto Refresh",
            value=False,
            help="Automatically refresh dashboard every 60 seconds"
        )
        
        if auto_refresh:
            refresh_interval = st.slider(
                "Refresh Interval (seconds)",
                min_value=30,
                max_value=300,
                value=60,
                step=30
            )
            
            # Display countdown
            placeholder = st.empty()
            
        # Manual refresh button
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()
        
        # System information
        st.header("ℹ️ System Info")
        st.info(f"""
        **Instance**: {EC2_INSTANCE_ID}
        **Type**: {INSTANCE_TYPE}
        **Specs**: {INSTANCE_SPECS}
        **Purpose**: Primary API Server
        **Monitoring**: Every minute
        """)
        
        # Capacity planning info
        st.header("📊 Capacity Planning")
        current_data = get_latest_monitoring_data()
        if current_data:
            cpu_value = float(current_data['cpu_utilization_percent']) if current_data['cpu_utilization_percent'] else 0
            memory_value = float(current_data['memory_utilization_percent']) if current_data['memory_utilization_percent'] else 0
            
            cpu_headroom = 80 - cpu_value  # Assuming 80% as warning threshold
            memory_headroom = 80 - memory_value
            
            st.success(f"CPU Headroom: {max(0, cpu_headroom):.1f}%")
            st.success(f"Memory Headroom: {max(0, memory_headroom):.1f}%")
            
            if cpu_value < 30 and memory_value < 50:
                st.success("✅ Ready for user onboarding!")
            elif cpu_value < 70 and memory_value < 80:
                st.warning("⚠️ Monitor during heavy load")
            else:
                st.error("🚨 Consider scaling resources")
        
        return time_range_hours, auto_refresh, locals().get('refresh_interval', 60)

def main():
    """Main dashboard application function."""
    try:
        # Display sidebar and get settings
        time_range_hours, auto_refresh, refresh_interval = display_sidebar()
        
        # Main dashboard content
        display_header()
        
        st.markdown("---")
        
        # Current metrics section
        display_current_metrics()
        
        st.markdown("---")
        
        # Alerts section
        display_alerts_section()
        
        st.markdown("---")
        
        # Time series charts
        display_time_series_charts(time_range_hours)
        
        st.markdown("---")
        
        # Summary statistics
        display_summary_stats(time_range_hours)
        
        # Footer
        st.markdown("---")
        st.caption(f"Dashboard last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.caption("📋 Monitoring data collected every minute | 🔄 Log rotation every 6 hours | 🗑️ Data retention: 2 days")
        
        # Auto-refresh logic
        if auto_refresh:
            time.sleep(refresh_interval)
            st.rerun()
            
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        st.error(f"Dashboard error: {str(e)}")
        st.error("Please check the database connection and monitoring system status.")

if __name__ == "__main__":
    main()
