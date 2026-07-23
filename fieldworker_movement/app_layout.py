"""
Dash layout and figure builder for the Fieldworker ABM visualisation. Controls
the web page visualisation of the model.

Aaron Stace, 06/07/2026
"""
import plotly.graph_objects as go
from dash import dcc, html

from config import METRIC_METADATA, dash_interval_ms
from mapping import to_wgs84


def edge_trace_data(graph, edge_type=None):
    lons = []
    lats = []

    for start, end, data in graph.edges(data=True):
        if edge_type is not None and data.get('type') != edge_type:
            continue
        start_lon, start_lat = to_wgs84([start[0]], [start[1]])
        end_lon, end_lat = to_wgs84([end[0]], [end[1]])
        lons.extend([start_lon[0], end_lon[0], None])
        lats.extend([start_lat[0], end_lat[0], None])

    return lons, lats


def build_initial_figure(model, centre_lon, centre_lat):
    """
    Construct a Plotly figure with three traces:
      - Trace 0: static address dots (true geographic positions).
      - Trace 2: field staff positions (updated each simulation step).
      - Trace 3: LSOA choropleth (updated each N steps, coloured by metric).
    """
    staff_lons, staff_lats, staff_colors = model.get_field_staff_positions()

    fig = go.Figure()

    network_lons, network_lats = edge_trace_data(model.graph)
    fig.add_trace(go.Scattermapbox(
        lon=network_lons,
        lat=network_lats,
        mode='lines',
        line=dict(width=1, color='blue'),
        name='Road/path network',
        hoverinfo='skip',
    ))

    # Trace 0 — address dots (static background layer)
    fig.add_trace(go.Scattermapbox(
        lon=model.address_lons,
        lat=model.address_lats,
        mode='markers',
        marker=dict(size=4, color='grey', opacity=0.5),
        name='Addresses',
        hoverinfo='skip',
    ))

    # Trace 2 — field staff (updated via Patch each step)
    fig.add_trace(go.Scattermapbox(
        lon=staff_lons,
        lat=staff_lats,
        mode='markers',
        marker=dict(size=10, color=staff_colors),
        name='Field staff',
    ))

    # Trace 3 — LSOA choropleth (updated via Patch every N steps)
    _initial_meta = METRIC_METADATA['knocks']
    fig.add_trace(go.Choroplethmapbox(
        geojson=model.lsoa_geojson,
        locations=model.lsoa_ids,
        customdata=model.lsoa_names,
        z=[0] * len(model.lsoa_ids),
        colorscale=_initial_meta['colorscale'],
        zmin=0,
        zmax=100,
        marker_opacity=0.55,
        marker_line_width=0.5,
        name=_initial_meta['label'],
        showscale=True,
        hovertemplate='%{customdata}<br>%{z:.0f}%<extra></extra>',
    ))

    fig.update_layout(
        mapbox=dict(
            style='open-street-map',
            center=dict(lon=centre_lon, lat=centre_lat),
            zoom=12,
        ),
        # Keeping uirevision constant prevents the map resetting its zoom/pan
        # position every time the figure is patched.
        uirevision='constant',
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            bgcolor='rgba(255,255,255,0.7)',
            x=0.01,
            y=0.99,
        ),
    )
    return fig


def create_layout(initial_fig):
    return html.Div([
        # Controls bar — row 1: buttons, step counter, metric radio
        html.Div([
            html.Button('▶ Play',  id='play-btn',  n_clicks=0,
                        style={'marginRight': '8px'}),
            html.Button('⏸ Pause', id='pause-btn', n_clicks=0,
                        style={'marginRight': '8px'}),
            html.Button('↺ Reset', id='reset-btn', n_clicks=0),
            html.Span('Step: 0 | Day 1 | 09:00:00', id='step-counter',
                      style={'marginLeft': '16px', 'fontFamily': 'monospace'}),

            # Metric toggle — which stat the choropleth colours by
            html.Span('  |  Choropleth metric: ', style={'marginLeft': '24px'}),
            dcc.RadioItems(
                id='metric-radio',
                options=[
                    {'label': 'Knocks',        'value': 'knocks'},
                    {'label': 'Interactions',  'value': 'interactions'},
                    {'label': 'Questionnaire Completion',
                     'value': 'questionnaire_completions'},
                ],
                value='knocks',
                inline=True,
                style={'display': 'inline-block', 'marginLeft': '6px'},
            ),

            # Settings dropdown — sliders
            html.Details([
                html.Summary('⚙ Settings', style={
                    'cursor': 'pointer',
                    'marginLeft': '24px',
                    'fontWeight': 'bold',
                    'userSelect': 'none',
                }),
                html.Div([
                    # Choropleth update frequency slider
                    html.Div([
                        html.Span('Update choropleth every',
                                  style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='choropleth-interval-slider',
                            min=1, max=50, step=1, value=1,
                            marks={1: '1', 10: '10', 25: '25', 50: '50'},
                            tooltip={'placement': 'bottom',
                                     'always_visible': False},
                        ),
                        html.Span('steps',
                                  style={'fontSize': '0.8em',
                                         'color': '#555'}),
                    ], style={'width': '220px', 'marginRight': '32px'}),

                    html.Div([
                        html.Span('Steps per tick', 
                                  style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='steps-per-tick-slider',
                            min=1, max=1000, step=5, value=100,
                            marks={1: '1', 100: '100', 500: '500', 1000: '1000'},
                            tooltip={'placement': 'bottom', 
                                     'always_visible': False},
                        ),
                        html.Span('(higher = faster, same fidelity)',
                                style={'fontSize': '0.8em', 'color': '#555'}),
                    ], style={'width': '220px', 'marginRight': '32px'}),

                    # Seconds per simulation step slider
                    html.Div([
                        html.Span('Seconds per step',
                                  style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='step-duration-slider',
                            min=1, max=30, step=1, value=1,
                            marks={1: '1', 15: '15', 30: '30'},
                            tooltip={'placement': 'bottom',
                                     'always_visible': False},
                        ),
                        html.Span('(higher = loss of fidelity)',
                                  style={'fontSize': '0.8em', 'color': '#555'}),
                    ], style={'width': '220px', 'marginRight': '32px'}),

                    # Number of field staff slider
                    html.Div([
                        html.Span('Field staff',
                                  style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='field-staff-slider',
                            min=1, max=50, step=1, value=10,
                            marks={1: '1', 10: '10', 25: '25', 50: '50'},
                            tooltip={'placement': 'bottom',
                                     'always_visible': False},
                        ),
                        html.Span('(applied at start of next day)',
                                  style={'fontSize': '0.8em',
                                         'color': '#555'}),
                    ], style={'width': '220px'}),

                ], style={
                    'display': 'flex',
                    'flexDirection': 'row',
                    'alignItems': 'flex-start',
                    'padding': '12px 16px',
                    'background': '#e4e4e4',
                    'borderTop': '1px solid #ccc',
                    'marginTop': '4px',
                }),
            ], style={'marginLeft': '16px'}),

            html.Details([
                html.Summary('Daily Interaction Time %', style={
                    'cursor': 'pointer',
                    'marginLeft': '24px',
                    'fontWeight': 'bold',
                    'userSelect': 'none',
                }),
                html.Div(
                    id='daily-interaction-breakdown',
                    children='No completed days yet.',
                    style={
                        'padding': '12px 16px',
                        'background': '#e4e4e4',
                        'borderTop': '1px solid #ccc',
                        'marginTop': '4px',
                        'fontFamily': 'monospace',
                    },
                ),
            ], style={'marginLeft': '16px'}),

        ], style={'padding': '8px', 'background': '#f0f0f0',
                  'display': 'flex', 'alignItems': 'center',
                  'flexWrap': 'wrap'}),

        # Map
        dcc.Graph(
            id='map',
            figure=initial_fig,
            style={'height': 'calc(100vh - 64px)'},
            config={'scrollZoom': True},
        ),

        # Interval ticker (fires every 500 ms when running)
        dcc.Interval(id='interval', interval=dash_interval_ms, disabled=True),

        # Store: {'running': bool, 'step': int}
        dcc.Store(id='run-store', data={'running': False, 'step': 0}),

        # Store: currently selected choropleth metric ('knocks' or 'interactions')
        dcc.Store(id='metric-store', data='knocks'),
    ])
