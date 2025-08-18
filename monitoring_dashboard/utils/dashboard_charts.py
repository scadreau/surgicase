# Created: 2025-08-14 17:38:38
# Last Modified: 2025-08-18 14:30:24
# Author: Scott Cadreau

"""
Dashboard Chart Utilities

This module provides chart creation functions for the monitoring dashboard.
It handles visualization of EC2 monitoring metrics using Plotly charts.
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd
from decimal import Decimal

# Color scheme for consistent dashboard appearance
COLORS = {
    'primary': '#1f77b4',
    'success': '#2ca02c',
    'warning': '#ff7f0e',
    'danger': '#d62728',
    'info': '#17a2b8',
    'secondary': '#6c757d',
    'background': '#f8f9fa'
}

# Threshold values
CPU_WARNING_THRESHOLD = 70
CPU_CRITICAL_THRESHOLD = 80
MEMORY_WARNING_THRESHOLD = 70
MEMORY_CRITICAL_THRESHOLD = 80

def convert_decimal_to_float(value):
    """Convert Decimal or any numeric value to float, handling None values."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value) if value is not None else None

def prepare_chart_data(data: List[Dict]) -> pd.DataFrame:
    """
    Prepare data for charts by converting Decimal types to float and handling timestamps.
    
    Args:
        data: List of monitoring records
        
    Returns:
        pd.DataFrame: Prepared dataframe with proper data types
    """
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Convert all numeric columns from Decimal to float
    numeric_columns = [
        'cpu_utilization_percent', 'memory_utilization_percent',
        'network_in_bytes', 'network_out_bytes',
        'disk_read_bytes', 'disk_write_bytes'
    ]
    
    for col in numeric_columns:
        if col in df.columns:
            df[col] = df[col].apply(convert_decimal_to_float)
    
    return df

def create_cpu_timeline_chart(data: List[Dict], title: str = "CPU Utilization Over Time") -> go.Figure:
    """
    Create a timeline chart for CPU utilization with threshold lines.
    
    Args:
        data: List of monitoring records with timestamp and cpu_utilization_percent
        title: Chart title (default: "CPU Utilization Over Time")
        
    Returns:
        plotly.graph_objects.Figure: Interactive CPU timeline chart
    """
    # Prepare data with Decimal conversion
    df = prepare_chart_data(data)
    
    if df.empty or 'cpu_utilization_percent' not in df.columns:
        # Return empty chart with message
        fig = go.Figure()
        fig.add_annotation(
            text="No CPU data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    # Create figure
    fig = go.Figure()
    
    # Add CPU line
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['cpu_utilization_percent'],
        mode='lines+markers',
        name='CPU Usage (%)',
        line=dict(color=COLORS['primary'], width=2),
        marker=dict(size=4),
        hovertemplate='<b>%{y:.1f}%</b><br>%{x}<extra></extra>'
    ))
    
    # Add threshold lines
    fig.add_hline(
        y=CPU_WARNING_THRESHOLD,
        line_dash="dash",
        line_color=COLORS['warning'],
        annotation_text=f"Warning ({CPU_WARNING_THRESHOLD}%)",
        annotation_position="bottom right"
    )
    
    fig.add_hline(
        y=CPU_CRITICAL_THRESHOLD,
        line_dash="dash",
        line_color=COLORS['danger'],
        annotation_text=f"Critical ({CPU_CRITICAL_THRESHOLD}%)",
        annotation_position="top right"
    )
    
    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="CPU Utilization (%)",
        height=400,
        showlegend=True,
        hovermode='x unified',
        yaxis=dict(range=[0, max(100, df['cpu_utilization_percent'].max() * 1.1)])
    )
    
    return fig

def create_memory_timeline_chart(data: List[Dict], title: str = "Memory Utilization Over Time") -> go.Figure:
    """
    Create a timeline chart for memory utilization with threshold lines.
    
    Args:
        data: List of monitoring records with timestamp and memory_utilization_percent
        title: Chart title (default: "Memory Utilization Over Time")
        
    Returns:
        plotly.graph_objects.Figure: Interactive memory timeline chart
    """
    # Prepare data with Decimal conversion
    df = prepare_chart_data(data)
    
    if df.empty or 'memory_utilization_percent' not in df.columns:
        # Return empty chart with message
        fig = go.Figure()
        fig.add_annotation(
            text="No memory data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    # Filter out null memory values
    df_memory = df[df['memory_utilization_percent'].notna()]
    
    if df_memory.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No memory data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    # Create figure
    fig = go.Figure()
    
    # Add memory area chart
    fig.add_trace(go.Scatter(
        x=df_memory['timestamp'],
        y=df_memory['memory_utilization_percent'],
        mode='lines',
        fill='tonexty',
        name='Memory Usage (%)',
        line=dict(color=COLORS['success'], width=2),
        fillcolor=f"rgba(44, 160, 44, 0.3)",
        hovertemplate='<b>%{y:.1f}%</b><br>%{x}<extra></extra>'
    ))
    
    # Add threshold lines
    fig.add_hline(
        y=MEMORY_WARNING_THRESHOLD,
        line_dash="dash",
        line_color=COLORS['warning'],
        annotation_text=f"Warning ({MEMORY_WARNING_THRESHOLD}%)",
        annotation_position="bottom right"
    )
    
    fig.add_hline(
        y=MEMORY_CRITICAL_THRESHOLD,
        line_dash="dash",
        line_color=COLORS['danger'],
        annotation_text=f"Critical ({MEMORY_CRITICAL_THRESHOLD}%)",
        annotation_position="top right"
    )
    
    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Memory Utilization (%)",
        height=400,
        showlegend=True,
        hovermode='x unified',
        yaxis=dict(range=[0, max(100, df_memory['memory_utilization_percent'].max() * 1.1)])
    )
    
    return fig

def create_network_io_chart(data: List[Dict], title: str = "Network I/O Over Time") -> go.Figure:
    """
    Create a dual-axis chart for network input/output traffic.
    
    Args:
        data: List of monitoring records with network_in_bytes and network_out_bytes
        title: Chart title (default: "Network I/O Over Time")
        
    Returns:
        plotly.graph_objects.Figure: Interactive network I/O chart
    """
    # Prepare data with Decimal conversion
    df = prepare_chart_data(data)
    
    if df.empty or 'network_in_bytes' not in df.columns or 'network_out_bytes' not in df.columns:
        # Return empty chart with message
        fig = go.Figure()
        fig.add_annotation(
            text="No network data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    # Convert bytes to KB for better readability
    df['network_in_kb'] = df['network_in_bytes'] / 1024
    df['network_out_kb'] = df['network_out_bytes'] / 1024
    
    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Add network in
    fig.add_trace(
        go.Scatter(
            x=df['timestamp'],
            y=df['network_in_kb'],
            mode='lines',
            name='Network In (KB)',
            line=dict(color=COLORS['info'], width=2),
            hovertemplate='<b>In: %{y:,.0f} KB</b><br>%{x}<extra></extra>'
        ),
        secondary_y=False
    )
    
    # Add network out
    fig.add_trace(
        go.Scatter(
            x=df['timestamp'],
            y=df['network_out_kb'],
            mode='lines',
            name='Network Out (KB)',
            line=dict(color=COLORS['warning'], width=2),
            hovertemplate='<b>Out: %{y:,.0f} KB</b><br>%{x}<extra></extra>'
        ),
        secondary_y=True
    )
    
    # Update layout
    fig.update_layout(
        title=title,
        height=400,
        hovermode='x unified'
    )
    
    # Set y-axes titles
    fig.update_yaxes(title_text="Network In (KB)", secondary_y=False)
    fig.update_yaxes(title_text="Network Out (KB)", secondary_y=True)
    
    return fig

def create_disk_io_chart(data: List[Dict], title: str = "Disk I/O Over Time") -> go.Figure:
    """
    Create a chart for disk read/write activity.
    
    Args:
        data: List of monitoring records with disk_read_bytes and disk_write_bytes
        title: Chart title (default: "Disk I/O Over Time")
        
    Returns:
        plotly.graph_objects.Figure: Interactive disk I/O chart
    """
    # Prepare data with Decimal conversion
    df = prepare_chart_data(data)
    
    if df.empty or 'disk_read_bytes' not in df.columns or 'disk_write_bytes' not in df.columns:
        # Return empty chart with message
        fig = go.Figure()
        fig.add_annotation(
            text="No disk data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    # Filter out null values and convert to GB for better readability
    df_disk = df[(df['disk_read_bytes'].notna()) & (df['disk_write_bytes'].notna())]
    
    if df_disk.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No disk I/O data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    df_disk['disk_read_gb'] = df_disk['disk_read_bytes'] / (1024**3)
    df_disk['disk_write_gb'] = df_disk['disk_write_bytes'] / (1024**3)
    
    # Create figure
    fig = go.Figure()
    
    # Add disk read
    fig.add_trace(go.Scatter(
        x=df_disk['timestamp'],
        y=df_disk['disk_read_gb'],
        mode='lines',
        name='Disk Read (GB)',
        line=dict(color=COLORS['primary'], width=2),
        hovertemplate='<b>Read: %{y:.2f} GB</b><br>%{x}<extra></extra>'
    ))
    
    # Add disk write
    fig.add_trace(go.Scatter(
        x=df_disk['timestamp'],
        y=df_disk['disk_write_gb'],
        mode='lines',
        name='Disk Write (GB)',
        line=dict(color=COLORS['danger'], width=2),
        hovertemplate='<b>Write: %{y:.2f} GB</b><br>%{x}<extra></extra>'
    ))
    
    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Disk I/O (GB)",
        height=400,
        showlegend=True,
        hovermode='x unified'
    )
    
    return fig

def create_system_overview_chart(current_data: Dict) -> go.Figure:
    """
    Create a gauge chart showing current system metrics overview.
    
    Args:
        current_data: Latest monitoring data with CPU and memory percentages
        
    Returns:
        plotly.graph_objects.Figure: Gauge chart with system metrics
    """
    if not current_data:
        fig = go.Figure()
        fig.add_annotation(
            text="No current data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title="System Overview", height=300)
        return fig
    
    cpu_value = current_data.get('cpu_utilization_percent', 0) or 0
    memory_value = current_data.get('memory_utilization_percent', 0) or 0
    
    # Create subplot with 2 gauges
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}]],
        subplot_titles=("", "")
    )
    
    # CPU gauge
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=cpu_value,
        domain={'x': [0, 0.5], 'y': [0, 0.85]},
        title={'text': "CPU (%)"},
        gauge={
            'axis': {'range': [None, 100]},
            'bar': {'color': "#4169E1"},
            'steps': [
                {'range': [0, 50], 'color': "lightgray"},
                {'range': [50, 80], 'color': "yellow"},
                {'range': [80, 100], 'color': "red"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 80
            }
        }
    ), row=1, col=1)
    
    # Memory gauge
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=memory_value,
        domain={'x': [0.5, 1], 'y': [0, 0.85]},
        title={'text': "Memory (%)"},
        gauge={
            'axis': {'range': [None, 100]},
            'bar': {'color': "darkgreen"},
            'steps': [
                {'range': [0, 50], 'color': "lightgray"},
                {'range': [50, 80], 'color': "yellow"},
                {'range': [80, 100], 'color': "red"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 80
            }
        }
    ), row=1, col=2)
    
    fig.update_layout(
        title="Current System Metrics",
        height=300,
        font={'color': "#87CEEB", 'family': "Arial"}
    )
    
    return fig

def create_combined_metrics_chart(data: List[Dict], title: str = "Combined System Metrics") -> go.Figure:
    """
    Create a combined chart showing CPU, memory, and network metrics on one chart.
    
    Args:
        data: List of monitoring records with all metrics
        title: Chart title (default: "Combined System Metrics")
        
    Returns:
        plotly.graph_objects.Figure: Combined metrics chart
    """
    # Prepare data with Decimal conversion
    df = prepare_chart_data(data)
    
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(title=title, height=400)
        return fig
    
    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Add CPU line
    fig.add_trace(
        go.Scatter(
            x=df['timestamp'],
            y=df['cpu_utilization_percent'],
            mode='lines',
            name='CPU (%)',
            line=dict(color=COLORS['primary'], width=2),
            hovertemplate='<b>CPU: %{y:.1f}%</b><br>%{x}<extra></extra>'
        ),
        secondary_y=False
    )
    
    # Add memory line (only where data exists)
    df_memory = df[df['memory_utilization_percent'].notna()]
    if not df_memory.empty:
        fig.add_trace(
            go.Scatter(
                x=df_memory['timestamp'],
                y=df_memory['memory_utilization_percent'],
                mode='lines',
                name='Memory (%)',
                line=dict(color=COLORS['success'], width=2),
                hovertemplate='<b>Memory: %{y:.1f}%</b><br>%{x}<extra></extra>'
            ),
            secondary_y=False
        )
    
    # Add network throughput (simplified)
    df['network_total_mb'] = (df['network_in_bytes'] + df['network_out_bytes']) / (1024**2)
    fig.add_trace(
        go.Scatter(
            x=df['timestamp'],
            y=df['network_total_mb'],
            mode='lines',
            name='Network (MB)',
            line=dict(color=COLORS['warning'], width=1, dash='dot'),
            hovertemplate='<b>Network: %{y:.1f} MB</b><br>%{x}<extra></extra>'
        ),
        secondary_y=True
    )
    
    # Update layout
    fig.update_layout(
        title=title,
        height=400,
        hovermode='x unified'
    )
    
    # Set y-axes titles
    fig.update_yaxes(title_text="CPU & Memory (%)", secondary_y=False)
    fig.update_yaxes(title_text="Network Total (MB)", secondary_y=True)
    
    return fig
