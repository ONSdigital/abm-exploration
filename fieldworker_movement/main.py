"""
Dash visualisation entry point for the Fieldworker ABM.

Open http://127.0.0.1:8050 in a browser.

Aaron Stace, 03/07/2026
"""
import dash
from dash import dcc, html, Input, Output, State, Patch, no_update
import plotly.graph_objects as go

from fieldwork_model import FieldWorkModel


model = FieldWorkModel()   # update constructor args once they are finalised

# Pre-compute the centroid of the address cloud to centre the map on load.
centre_lon = sum(model.address_lons) / len(model.address_lons)
centre_lat = sum(model.address_lats) / len(model.address_lats)


def build_initial_figure(model):
    """
    Construct a Plotly figure with two Scattermapbox traces:
      - Trace 0: static address dots (true geographic positions).
      - Trace 1: field staff positions (updated each simulation step).
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


initial_fig = build_initial_figure(model)


app = dash.Dash(__name__)

app.layout = html.Div([
    # Controls bar
    html.Div([
        html.Button('▶ Play',  id='play-btn',  n_clicks=0,
                    style={'marginRight': '8px'}),
        html.Button('⏸ Pause', id='pause-btn', n_clicks=0,
                    style={'marginRight': '8px'}),
        html.Button('↺ Reset', id='reset-btn', n_clicks=0),
        html.Span('Step: 0', id='step-counter',
                  style={'marginLeft': '16px', 'fontFamily': 'monospace'}),
    ], style={'padding': '8px', 'background': '#f0f0f0'}),

    # Map
    dcc.Graph(
        id='map',
        figure=initial_fig,
        style={'height': 'calc(100vh - 48px)'},
        config={'scrollZoom': True},
    ),

    # Interval ticker (fires every 500 ms when running)
    dcc.Interval(id='interval', interval=500, disabled=True),

    # Store: {'running': bool, 'step': int}
    dcc.Store(id='run-store', data={'running': False, 'step': 0}),
])


@app.callback(
    Output('run-store', 'data'),
    Input('play-btn',  'n_clicks'),
    Input('pause-btn', 'n_clicks'),
    Input('reset-btn', 'n_clicks'),
    State('run-store', 'data'),
    prevent_initial_call=True,
)
def handle_controls(play_clicks, pause_clicks, reset_clicks, store):
    """Toggle running state or reset the model."""
    global model, initial_fig, centre_lon, centre_lat

    triggered = dash.callback_context.triggered_id

    if triggered == 'play-btn':
        store['running'] = True
    elif triggered == 'pause-btn':
        store['running'] = False
    elif triggered == 'reset-btn':
        model = FieldWorkModel()
        centre_lon = sum(model.address_lons) / len(model.address_lons)
        centre_lat = sum(model.address_lats) / len(model.address_lats)
        store['running'] = False
        store['step'] = 0

    return store


@app.callback(
    Output('interval', 'disabled'),
    Input('run-store', 'data'),
)
def toggle_interval(store):
    return not store['running']


@app.callback(
    Output('map', 'figure'),
    Output('step-counter', 'children'),
    Output('run-store', 'data', allow_duplicate=True),
    Input('interval', 'n_intervals'),
    State('run-store', 'data'),
    State('reset-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def tick(n_intervals, store, _reset_clicks):
    """
    Advance the simulation by one step and patch only trace 1 (field staff).
    Returning a Patch object means only the changed arrays are sent to the
    browser — tiles and address dots are untouched.
    """
    if not store['running']:
        return no_update, no_update, no_update

    model.step()
    store['step'] += 1

    staff_lons, staff_lats = model.get_field_staff_positions()

    patched_fig = Patch()
    patched_fig['data'][1]['lon'] = staff_lons
    patched_fig['data'][1]['lat'] = staff_lats

    return patched_fig, f'Step: {store["step"]}', store


@app.callback(
    Output('map', 'figure', allow_duplicate=True),
    Input('reset-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def reset_figure(_n_clicks):
    """Return a fully rebuilt figure after a reset."""
    return build_initial_figure(model)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)
