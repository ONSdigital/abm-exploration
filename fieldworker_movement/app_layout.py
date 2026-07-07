"""
Dash layout and figure builder for the Fieldworker ABM visualisation. Controls
the web page visualisation of the model.

Aaron Stace, 06/07/2026
"""
import plotly.graph_objects as go
from dash import dcc, html


def build_initial_figure(model, centre_lon, centre_lat):
    """
    Construct a Plotly figure with three traces:
      - Trace 0: static address dots (true geographic positions).
      - Trace 1: field staff positions (updated each simulation step).
      - Trace 2: LSOA choropleth (updated each N steps, coloured by metric).
    """
    staff_lons, staff_lats = model.get_field_staff_positions()

    fig = go.Figure()

    # Trace 0 — address dots (static background layer)
    fig.add_trace(go.Scattermapbox(
        lon=model.address_lons,
        lat=model.address_lats,
        mode='markers',
        marker=dict(size=4, color='grey', opacity=0.5),
        name='Addresses',
        hoverinfo='skip',
    ))

    # Trace 1 — field staff (updated via Patch each step)
    fig.add_trace(go.Scattermapbox(
        lon=staff_lons,
        lat=staff_lats,
        mode='markers',
        marker=dict(size=10, color="#0a0001"),
        name='Field staff',
    ))

    # Trace 2 — LSOA choropleth (updated via Patch every N steps)
    fig.add_trace(go.Choroplethmapbox(
        geojson=model.lsoa_geojson,
        locations=model.lsoa_ids,
        z=[0] * len(model.lsoa_ids),
        colorscale='Blues',
        zmin=0,
        zmax=50,
        marker_opacity=0.4,
        marker_line_width=0.5,
        name='Knocks per LSOA',
        showscale=True,
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
        # Controls bar
        html.Div([
            html.Button('▶ Play',  id='play-btn',  n_clicks=0,
                        style={'marginRight': '8px'}),
            html.Button('⏸ Pause', id='pause-btn', n_clicks=0,
                        style={'marginRight': '8px'}),
            html.Button('↺ Reset', id='reset-btn', n_clicks=0),
            html.Span('Step: 0', id='step-counter',
                      style={'marginLeft': '16px', 'fontFamily': 'monospace'}),

            # Metric toggle — which stat the choropleth colours by
            html.Span('  |  Choropleth metric: ', style={'marginLeft': '24px'}),
            dcc.RadioItems(
                id='metric-radio',
                options=[
                    {'label': 'Knocks',        'value': 'knocks'},
                    {'label': 'Interactions',  'value': 'interactions'},
                ],
                value='knocks',
                inline=True,
                style={'display': 'inline-block', 'marginLeft': '6px'},
            ),

            # Choropleth update frequency slider
            html.Span('  |  Update choropleth every',
                      style={'marginLeft': '24px'}),
            html.Div(
                dcc.Slider(
                    id='choropleth-interval-slider',
                    min=1, max=50, step=1, value=1,
                    marks={1: '1', 10: '10', 25: '25', 50: '50'},
                    tooltip={'placement': 'bottom', 'always_visible': False},
                ),
                style={
                    'display': 'inline-block',
                    'width': '180px',
                    'verticalAlign': 'middle',
                    'marginLeft': '6px',
                },
            ),
            html.Span('steps', style={'marginLeft': '4px'}),
            
            # Slider updating household response chance
            html.Span('  |  Household response chance: ',
                      style={'marginLeft': '24px'}),
            html.Div(
                dcc.Slider(
                    id='hh-response-chance-slider',
                    min=0.0, max=1.0, step=0.05, value=0.5,
                    marks={0: '0', 0.5: '0.5', 1: '1'},
                    tooltip={'placement': 'bottom', 'always_visible': False},
                ),
                style={
                    'display': 'inline-block',
                    'width': '180px',
                    'verticalAlign': 'middle',
                    'marginLeft': '6px',
                },
            ),

        ], style={'padding': '8px', 'background': '#f0f0f0',
                  'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),

        # Map
        dcc.Graph(
            id='map',
            figure=initial_fig,
            style={'height': 'calc(100vh - 64px)'},
            config={'scrollZoom': True},
        ),

        # Interval ticker (fires every 500 ms when running)
        dcc.Interval(id='interval', interval=500, disabled=True),

        # Store: {'running': bool, 'step': int}
        dcc.Store(id='run-store', data={'running': False, 'step': 0}),

        # Store: currently selected choropleth metric ('knocks' or 'interactions')
        dcc.Store(id='metric-store', data='knocks'),
    ])
