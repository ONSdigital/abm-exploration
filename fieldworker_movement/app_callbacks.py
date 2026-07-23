"""
Dash callbacks for the Fieldworker ABM visualisation.
"""
import dash
from dash import Input, Output, State, Patch, no_update, html

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
        Input('field-staff-slider', 'value'),
        State('run-store', 'data'),
        State('step-duration-slider', 'value'),
        prevent_initial_call=True,
    )
    def handle_controls(play_clicks, pause_clicks, reset_clicks,
                        field_staff_value, store, step_duration):
        """
        Toggle running state or reset the model.
        """
        store = store or {}
        current_staff = len(state['model'].field_staff)
        store.setdefault('current_field_staff', current_staff)
        store.setdefault('pending_field_staff', current_staff)

        triggered = dash.callback_context.triggered_id

        if triggered == 'play-btn':
            store['running'] = True
        elif triggered == 'pause-btn':
            store['running'] = False
        elif triggered == 'reset-btn':
            selected_staff = int(field_staff_value or num_field_staff)
            state['model'] = FieldWorkModel(selected_staff)
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
            store['current_field_staff'] = selected_staff
            store['pending_field_staff'] = selected_staff
        elif triggered == 'field-staff-slider':
            store['pending_field_staff'] = int(
                field_staff_value or store['current_field_staff']
            )

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
        State('steps-per-tick-slider', 'value'),
        prevent_initial_call=True,
    )
    def tick(n_intervals, store, _reset_clicks, metric, choropleth_interval, 
             step_duration, steps_per_tick):
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
        store.setdefault('current_field_staff', len(model.field_staff))
        store.setdefault('pending_field_staff', store['current_field_staff'])

        if step_duration is not None:
            model.simulation_step_seconds = step_duration
            model.travel_distance_per_step = (
                model.walking_speed * model.simulation_step_seconds
            )

        steps_per_tick = int(steps_per_tick or 1)
        for _ in range(steps_per_tick):
            day_before_step = model.current_day
            model.step()

            if model.current_day != day_before_step:
                pending_staff = int(store.get('pending_field_staff', 
                                              len(model.field_staff)))
                current_staff_count = int(store.get('current_field_staff', 
                                                    len(model.field_staff)))
                if pending_staff != current_staff_count:
                    model.set_field_staff_count(pending_staff)
                store['current_field_staff'] = len(model.field_staff)

        store['step'] = model.steps

        store['current_field_staff'] = len(model.field_staff)

        staff_lons, staff_lats, staff_colors = \
                                            model.get_field_staff_positions()

        patched_fig = Patch()
        patched_fig['data'][2]['lon'] = staff_lons
        patched_fig['data'][2]['lat'] = staff_lats
        patched_fig['data'][2]['marker']['color'] = staff_colors

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

        current_staff = int(store['current_field_staff'])
        pending_staff = int(store.get('pending_field_staff', current_staff))
        if pending_staff != current_staff:
            staff_suffix = (
                f' | Staff: {current_staff} '
                f'(pending {pending_staff} next day)'
            )
        else:
            staff_suffix = f' | Staff: {current_staff}'

        return (
            patched_fig,
            f'Step: {model.steps} | {model.format_simulation_time()}'
            f'{staff_suffix}',
            store,
        )

    @app.callback(
        Output('daily-interaction-breakdown', 'children'),
        Input('interval', 'n_intervals'),
        Input('reset-btn', 'n_clicks'),
    )
    def update_daily_interaction_breakdown(_n_intervals, _reset_clicks):
        """
        Render finalized end-of-day interaction-time percentages.
        """
        day_pct = state['model'].daily_interaction_time_pct
        if not day_pct:
            return 'No completed days yet.'

        lines = []
        for day in sorted(day_pct):
            pct_value = round(day_pct[day])
            lines.append(html.Div(f'Day {day}: {pct_value}%'))
        return lines

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
