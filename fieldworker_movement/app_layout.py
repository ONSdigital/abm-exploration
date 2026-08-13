"""
Dash layout and figure builder for the Fieldworker ABM visualisation. Controls
the web page visualisation of the model.
Aaron Stace, 06/07/2026
"""
import plotly.express as px
import plotly.graph_objects as go
from config import (
    METRIC_METADATA,
    daily_hh_per_agent,
    dash_interval_ms,
    num_field_staff,
)
from dash import dcc, html
from mapping import to_wgs84


def edge_trace_data(graph):
    filtered = [
        (s[0], s[1], e[0], e[1])
        for s, e, _ in graph.edges(data=True)
    ]

    if not filtered:
        return [], []

    start_eastings, start_northings, end_eastings, \
        end_northings = zip(*filtered)

    n = len(filtered)
    all_lons, all_lats = to_wgs84(
        start_eastings + end_eastings,
        start_northings + end_northings,
    )
    start_lons, end_lons = all_lons[:n], all_lons[n:]
    start_lats, end_lats = all_lats[:n], all_lats[n:]

    lons = [c for i in range(n) for c in (start_lons[i], end_lons[i], None)]
    lats = [c for i in range(n) for c in (start_lats[i], end_lats[i], None)]

    return lons, lats


def _build_route_geometry(model):
    """
    Build lon/lat arrays for each field staff agent's remaining planned route,
    following the road network between consecutive waypoints. Segments are
    separated by None so Plotly draws them as separate lines.

    Only the not-yet-visited portion of each agent's route is included,
    starting from the agent's current node.
    """
    all_lons, all_lats = [], []
    for agent in model.field_staff:
        waypoints = agent.vrp_waypoints
        if not waypoints:
            continue
        remaining = waypoints[agent.vrp_waypoint_index:]
        if not remaining:
            continue
        nodes = [agent.node] + remaining
        for i in range(len(nodes) - 1):
            path = model.get_road_path(nodes[i], nodes[i + 1])
            if not path:
                continue
            seg_lons, seg_lats = to_wgs84(
                [n[0] for n in path],
                [n[1] for n in path],
            )
            all_lons.extend(seg_lons)
            all_lons.append(None)
            all_lats.extend(seg_lats)
            all_lats.append(None)
    return all_lons, all_lats


def build_initial_figure(model, centre_lon, centre_lat, viz_data):
    """
    Construct a Plotly figure with four traces:
      - Trace 0: road/path network (static).
      - Trace 1: address dots (static background layer).
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
        line={'width': 1, 'color': 'blue'},
        name='Road/path network',
        hoverinfo='skip',
    ))

    # Trace 0 — address dots (static background layer)
    fig.add_trace(go.Scattermapbox(
        lon=viz_data['address_lons'],
        lat=viz_data['address_lats'],
        mode='markers',
        marker={'size': 4, 'color': 'grey', 'opacity': 0.5},
        name='Addresses',
        hoverinfo='skip',
    ))

    # Trace 2 — field staff (updated via Patch each step)
    fig.add_trace(go.Scattermapbox(
        lon=staff_lons,
        lat=staff_lats,
        mode='markers',
        marker={'size': 10, 'color': staff_colors},
        name='Field staff',
    ))

    # Trace 3 — LSOA choropleth (updated via Patch every N steps)
    _initial_meta = METRIC_METADATA['knocks']
    fig.add_trace(go.Choroplethmapbox(
        geojson=viz_data['lsoa_geojson'],
        locations=viz_data['lsoa_ids'],
        customdata=viz_data['lsoa_names'],
        z=[0] * len(viz_data['lsoa_ids']),
        colorscale=_initial_meta['colorscale'],
        zmin=0,
        zmax=100,
        marker_opacity=0.55,
        marker_line_width=0.5,
        name=_initial_meta['label'],
        showscale=True,
        hovertemplate='%{customdata}<br>%{z:.0f}%<extra></extra>',
    ))

    # Trace 4 — agent planned routes (toggled on/off, updated at day boundaries)
    fig.add_trace(go.Scattermapbox(
        lon=[],
        lat=[],
        mode='lines',
        line={'width': 2, 'color': 'red'},
        name='Agent routes',
        hoverinfo='skip',
        visible=False,
    ))

    fig.update_layout(
        mapbox={
            'style': 'open-street-map',
            'center': {'lon': centre_lon, 'lat': centre_lat},
            'zoom': 12,
        },
        # Keeping uirevision constant prevents the map resetting its zoom/pan
        # position every time the figure is patched.
        uirevision='constant',
        margin={'l': 0, 'r': 0, 't': 0, 'b': 0},
        legend={
            'bgcolor': 'rgba(255,255,255,0.7)',
            'x': 0.01,
            'y': 0.99,
        },
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
            html.Button('📊 View Results', id='view-results-btn', n_clicks=0,
                        style={'marginLeft': '8px'}),
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

            html.Span('  |  ', style={'marginLeft': '12px'}),
            dcc.Checklist(
                id='route-toggle',
                options=[{'label': ' Show agent routes', 'value': 'show'}],
                value=[],
                inline=True,
                style={'display': 'inline-block'},
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
                            min=1, max=3600, step=50, value=100,
                            marks={1: '1', 1800: '1800', 3600: '3600'},
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
                            min=1, max=50, step=1, value=num_field_staff,
                            marks={1: '1', 10: '10', 25: '25', 50: '50'},
                            tooltip={'placement': 'bottom',
                                     'always_visible': False},
                        ),
                        html.Span('(applied at start of next day)',
                                  style={'fontSize': '0.8em',
                                         'color': '#555'}),
                    ], style={'width': '220px', 'marginRight': '32px'}),

                    # Daily households-per-agent slider
                    html.Div([
                        html.Span('Daily hh per agent',
                                  style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='daily-hh-per-agent-slider',
                            min=1, max=100, step=1, value=daily_hh_per_agent,
                            marks={1: '1', 20: '20', 40: '40', 60: '60', 80: '80'},
                            tooltip={'placement': 'bottom',
                                     'always_visible': False},
                        ),
                        html.Span('(applied at start of next day)',
                                  style={'fontSize': '0.8em',
                                         'color': '#555'}),
                    ], style={'width': '220px', 'marginRight': '32px'}),

                    # Simulation duration slider
                    html.Div([
                        html.Span('Simulation duration',
                                  style={'fontWeight': 'bold'}),
                        dcc.Slider(
                            id='simulation-duration-slider',
                            min=1, max=10, step=1, value=7,
                            marks={1: '1', 5: '5', 10: '10'},
                            tooltip={'placement': 'bottom',
                                     'always_visible': False},
                        ),
                        html.Span('days',
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
                html.Summary('Daily Metrics', style={
                    'cursor': 'pointer',
                    'marginLeft': '24px',
                    'fontWeight': 'bold',
                    'userSelect': 'none',
                }),
                html.Div([
                    html.Span('Show:', style={'fontWeight': 'bold',
                                              'marginRight': '8px'}),
                    dcc.Dropdown(
                        id='daily-metric-radio',
                        options=[
                            {'label': 'Interaction Time %',
                             'value': 'interaction_time_pct'},
                            {'label': 'Households Knocked',
                             'value': 'daily_knocks'},
                            {'label': 'Households Interacted',
                             'value': 'daily_interactions'},
                        ],
                        value='interaction_time_pct',
                        clearable=False,
                        style={'width': '280px', 'display': 'inline-block',
                               'verticalAlign': 'middle'},
                    ),
                ], style={'padding': '12px 16px',
                          'background': '#e4e4e4',
                          'borderTop': '1px solid #ccc',
                          'marginTop': '4px'}),
                html.Div(
                    id='daily-metric-breakdown',
                    children='No completed days yet.',
                    style={
                        'padding': '12px 16px',
                        'background': '#e4e4e4',
                        'borderTop': '1px solid #ccc',
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

        html.Div(
            id='results-overlay',
            children=[
                html.Div([
                    html.Span('Simulation Results',
                              style={'fontWeight': 'bold', 'fontSize': '1.2em'}),
                    html.Button('✕ Close', id='close-results-btn', n_clicks=0,
                                style={'float': 'right', 'cursor': 'pointer'}),
                ], style={'marginBottom': '12px', 'overflow': 'hidden'}),
                dcc.Graph(id='interaction-time-chart',
                          style={'height': '75vh'}),
            ],
            style={
                'display': 'none',
                'position': 'fixed',
                'top': '5vh', 'left': '5vw',
                'width': '90vw', 'height': '90vh',
                'background': 'white',
                'zIndex': 1000,
                'padding': '20px',
                'boxShadow': '0 4px 24px rgba(0,0,0,0.45)',
                'overflowY': 'auto',
                'borderRadius': '8px',
            },
        ),
    ])
