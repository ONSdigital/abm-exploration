"""
Dash callbacks for the Fieldworker ABM visualisation.
"""
import dash
from dash import Input, Output, State, Patch, no_update

from config import num_field_staff, METRIC_METADATA

from fieldwork_model import FieldWorkModel
from app_layout import build_initial_figure


def _pct(model, lsoa, metric):
    """
    Calculates stats as a percentage of total households in the LSOA.
    
    Returns
    -------
    float
        Percentage of households in the LSOA that have completed the metric.
    """
    total = model.lsoa_stats[lsoa]['total_households']
    if total == 0:
        return 0
    return model.lsoa_stats[lsoa][metric] / total * 100


def init_callbacks(app, state):
    """
    Registers all Dash callbacks.

    `state` is a dict with keys:
      'model'      - the live FieldWorkModel instance
      'centre_lon' - float
      'centre_lat' - float

    Callbacks mutate `state` in place so that all functions share the same
    model instance even after a reset.
    """

    @app.callback(
        Output('run-store', 'data'),
        Input('play-btn',  'n_clicks'),
        Input('pause-btn', 'n_clicks'),
        Input('reset-btn', 'n_clicks'),
        State('run-store', 'data'),
        State('step-duration-slider', 'value'),
        prevent_initial_call=True,
    )
    def handle_controls(play_clicks, pause_clicks, reset_clicks, store,
                        step_duration):
        """Toggle running state or reset the model."""
        triggered = dash.callback_context.triggered_id

        if triggered == 'play-btn':
            store['running'] = True
        elif triggered == 'pause-btn':
            store['running'] = False
        elif triggered == 'reset-btn':
            state['model'] = FieldWorkModel(num_field_staff)
            if step_duration is not None:
                state['model'].simulation_step_seconds = step_duration
                state['model'].travel_distance_per_step = (
                    state['model'].walking_speed *
                    state['model'].simulation_step_seconds
                )
            state['centre_lon'] = sum(state['model'].address_lons) / len(state['model'].address_lons)
            state['centre_lat'] = sum(state['model'].address_lats) / len(state['model'].address_lats)
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
        Output('metric-store', 'data'),
        Input('metric-radio', 'value'),
    )
    def update_metric_store(value):
        """Mirror RadioItems selection into metric-store."""
        return value

    @app.callback(
        Output('map', 'figure'),
        Output('step-counter', 'children'),
        Output('run-store', 'data', allow_duplicate=True),
        Input('interval', 'n_intervals'),
        State('run-store', 'data'),
        State('reset-btn', 'n_clicks'),
        State('metric-store', 'data'),
        State('choropleth-interval-slider', 'value'),
        State('step-duration-slider', 'value'),
        prevent_initial_call=True,
    )
    def tick(n_intervals, store, _reset_clicks, metric, choropleth_interval, 
             step_duration):
        """
        Advance the simulation by one step and patch:
          - Trace 1 (field staff) every step.
          - Trace 2 (LSOA choropleth) every `choropleth_interval` steps.
        Returning a Patch object means only the changed arrays are sent to the
        browser — tiles and address dots are untouched.
        """
        if not store['running']:
            return no_update, no_update, no_update

        model = state['model']
        model.simulation_step_seconds = step_duration
        model.travel_distance_per_step = (
            model.walking_speed * model.simulation_step_seconds
        )
        model.step()
        store['step'] = model.steps

        staff_lons, staff_lats = model.get_field_staff_positions()

        patched_fig = Patch()
        patched_fig['data'][2]['lon'] = staff_lons
        patched_fig['data'][2]['lat'] = staff_lats

        interval = choropleth_interval or 1
        metric = metric or 'knocks'
        if store['step'] % interval == 0:
            meta = METRIC_METADATA.get(metric, METRIC_METADATA['knocks'])
            patched_fig['data'][3]['z'] = [
                _pct(model, lsoa, metric) for lsoa in model.lsoa_ids
            ]
            patched_fig['data'][3]['name'] = meta['label']
            patched_fig['data'][3]['colorscale'] = meta['colorscale']
            patched_fig['data'][3]['zmin'] = 0
            patched_fig['data'][3]['zmax'] = 100

        return (
            patched_fig,
            f'Step: {model.steps} | {model.format_simulation_time()}',
            store,
        )

    @app.callback(
        Output('map', 'figure', allow_duplicate=True),
        Input('metric-store', 'data'),
        State('run-store', 'data'),
        prevent_initial_call=True,
    )
    def update_choropleth_on_metric_change(metric, store):
        """
        When the metric toggle changes while the simulation is paused, immediately
        repaint the choropleth without waiting for the next tick.
        """
        if store['running']:
            return no_update

        metric = metric or 'knocks'
        model = state['model']
        meta = METRIC_METADATA.get(metric, METRIC_METADATA['knocks'])
        patched_fig = Patch()
        patched_fig['data'][3]['z'] = [
            _pct(model, lsoa, metric) for lsoa in model.lsoa_ids
        ]
        patched_fig['data'][3]['name'] = meta['label']
        patched_fig['data'][3]['colorscale'] = meta['colorscale']
        patched_fig['data'][3]['zmin'] = 0
        patched_fig['data'][3]['zmax'] = 100
        return patched_fig

    @app.callback(
        Output('map', 'figure', allow_duplicate=True),
        Input('reset-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_figure(_n_clicks):
        """Return a fully rebuilt figure after a reset."""
        return build_initial_figure(
            state['model'], state['centre_lon'], state['centre_lat']
        )
