"""
Dash callbacks for the Fieldworker ABM visualisation.
"""
import dash
from app_layout import _build_route_geometry, build_initial_figure
from config import METRIC_METADATA, daily_hh_per_agent, num_field_staff
from dash import Input, Output, Patch, State, html, no_update


def _pct(model, lsoa, metric):
    """
    Calculates stats as a percentage of total households in the LSOA.
    
    Returns
    -------
    float
        Percentage of households in the LSOA that have completed the metric.
    """
    stats = model.lsoa_stats[lsoa]
    total = stats['total_households']
    if total == 0:
        return 0
    return stats[metric] / total * 100


def init_callbacks(app, state, viz_data):
    """
    Registers all Dash callbacks.

    `state` is a dict with keys:
      'model'      - the live FieldWorkModel instance
      'centre_lon' - float
      'centre_lat' - float

    Callbacks mutate `state` in place so that all functions share the same
    model instance even after a reset.
    """
    state.setdefault('last_reset_id', None)

    _last_breakdown_state = [None]

    def _apply_choropleth(patched_fig, model, metric):
        meta = METRIC_METADATA.get(metric, METRIC_METADATA['knocks'])
        patched_fig['data'][3]['z'] = [
            _pct(model, lsoa, metric) for lsoa in viz_data['lsoa_ids']
        ]
        patched_fig['data'][3]['name'] = meta['label']
        patched_fig['data'][3]['colorscale'] = meta['colorscale']
        patched_fig['data'][3]['zmin'] = 0
        patched_fig['data'][3]['zmax'] = 100

    @app.callback(
        Output('run-store', 'data'),
        Input('play-btn',  'n_clicks'),
        Input('pause-btn', 'n_clicks'),
        Input('reset-btn', 'n_clicks'),
        State('field-staff-slider', 'value'),
        State('daily-hh-per-agent-slider', 'value'),
        State('run-store', 'data'),
        State('step-duration-slider', 'value'),
        prevent_initial_call=True,
    )
    def handle_controls(play_clicks, pause_clicks, reset_clicks,
                        field_staff_value, daily_hh_value, store, step_duration):
        """
        Toggle running state or reset the model.
        """
        store = store or {}
        current_staff = len(state['model'].field_staff)
        current_daily_hh = state['model'].hh_per_agent
        store.setdefault('current_field_staff', current_staff)
        store.setdefault('pending_field_staff', current_staff)
        store.setdefault('current_daily_hh_per_agent', current_daily_hh)
        store.setdefault('pending_daily_hh_per_agent', current_daily_hh)

        triggered = dash.callback_context.triggered_id

        # Ensure reset-triggered figure rebuild is one-shot.
        if triggered != 'reset-btn':
            store.pop('reset_id', None)

        if triggered == 'play-btn':
            store['running'] = True
        elif triggered == 'pause-btn':
            store['running'] = False
        elif triggered == 'reset-btn':
            selected_staff = int(field_staff_value or num_field_staff)
            selected_daily_hh = int(daily_hh_value or daily_hh_per_agent)
            state['model'].reset(selected_staff, hh_per_agent=selected_daily_hh)
            if step_duration is not None:
                state['model'].simulation_step_seconds = step_duration
                state['model'].travel_distance_per_step = (
                    state['model'].walking_speed *
                    state['model'].simulation_step_seconds
                )
            store['running'] = False
            store['step'] = 0
            store['reset_id'] = (reset_clicks or 0)
            store['current_field_staff'] = selected_staff
            store['pending_field_staff'] = selected_staff
            store['current_daily_hh_per_agent'] = selected_daily_hh
            store['pending_daily_hh_per_agent'] = selected_daily_hh

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
        State('metric-store', 'data'),
        State('choropleth-interval-slider', 'value'),
        State('step-duration-slider', 'value'),
        State('steps-per-tick-slider', 'value'),
        State('route-toggle', 'value'),
        State('simulation-duration-slider', 'value'),
        prevent_initial_call=True,
    )
    def tick(n_intervals, store, metric, choropleth_interval,
             step_duration, steps_per_tick, route_toggle, max_days):
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
        store.setdefault('current_daily_hh_per_agent', model.hh_per_agent)
        store.setdefault('pending_daily_hh_per_agent',
                 store['current_daily_hh_per_agent'])

        if step_duration is not None:
            model.simulation_step_seconds = step_duration
            model.travel_distance_per_step = (
                model.walking_speed * model.simulation_step_seconds
            )

        steps_per_tick = int(steps_per_tick or 1)
        day_changed = False
        for _ in range(steps_per_tick):
            day_before_step = model.current_day
            model.step()

            if model.current_day != day_before_step:
                day_changed = True
                pending_staff = int(store.get('pending_field_staff', 
                                              len(model.field_staff)))
                current_staff_count = int(store.get('current_field_staff', 
                                                    len(model.field_staff)))
                pending_daily_hh = int(
                    store.get('pending_daily_hh_per_agent', model.hh_per_agent)
                )
                current_daily_hh = int(
                    store.get('current_daily_hh_per_agent', model.hh_per_agent)
                )

                # Apply pending daily household target and staff count together
                # at day rollover to keep day-level assignment changes coherent.
                model.hh_per_agent = pending_daily_hh

                if pending_staff != current_staff_count:
                    model.set_field_staff_count(pending_staff)
                elif pending_daily_hh != current_daily_hh:
                    model.update_daily_target_lsoas()
                    model.assign_agents_to_target_lsoas()

                if max_days is not None and model.current_day > int(max_days):
                    store['running'] = False
                    break

        store['step'] = model.steps

        store['current_field_staff'] = len(model.field_staff)
        store['current_daily_hh_per_agent'] = model.hh_per_agent

        staff_lons, staff_lats, staff_colors = \
                                            model.get_field_staff_positions()

        patched_fig = Patch()
        patched_fig['data'][2]['lon'] = staff_lons
        patched_fig['data'][2]['lat'] = staff_lats
        patched_fig['data'][2]['marker']['color'] = staff_colors

        interval = choropleth_interval or 1
        metric = metric or 'knocks'
        if store['step'] % interval == 0:
            _apply_choropleth(patched_fig, model, metric)

        show_routes = bool(route_toggle)
        patched_fig['data'][4]['visible'] = show_routes
        if show_routes and day_changed:
            route_lons, route_lats = _build_route_geometry(model)
            patched_fig['data'][4]['lon'] = route_lons
            patched_fig['data'][4]['lat'] = route_lats

        current_staff = int(store['current_field_staff'])
        current_daily_hh = int(store['current_daily_hh_per_agent'])
        status_suffix = f' | Staff: {current_staff} | Daily hh/agent: {current_daily_hh}'

        return (
            patched_fig,
            f'Step: {model.steps} | {model.format_simulation_time()}{status_suffix}',
            store,
        )

    @app.callback(
        Output('daily-metric-breakdown', 'children'),
        Input('interval', 'n_intervals'),
        Input('reset-btn', 'n_clicks'),
        Input('daily-metric-radio', 'value'),
    )
    def update_daily_metric_breakdown(_n_intervals, _reset_clicks, metric_type):
        """
        Render finalized end-of-day daily metrics.
        """
        metric_type = metric_type or 'interaction_time_pct'
        model = state['model']

        if metric_type == 'daily_knocks':
            data = model.daily_knocks_by_day
            formatter = lambda value: f'{int(value)} knocks'
        elif metric_type == 'daily_interactions':
            data = model.daily_interactions_by_day
            formatter = lambda value: f'{int(value)} interactions'
        else:
            data = model.daily_interaction_time_pct
            formatter = lambda value: f'{round(value)}%'

        current_state = (metric_type, model.current_day, len(data))
        if (dash.callback_context.triggered_id != 'reset-btn'
                and current_state == _last_breakdown_state[0]):
            return no_update
        _last_breakdown_state[0] = current_state

        if not data:
            return 'No completed days yet.'

        lines = []
        for day in sorted(data):
            lines.append(html.Div(f'Day {day}: {formatter(data[day])}'))
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
        patched_fig = Patch()
        _apply_choropleth(patched_fig, model, metric)
        return patched_fig

    @app.callback(
        Output('map', 'figure', allow_duplicate=True),
        Input('route-toggle', 'value'),
        prevent_initial_call=True,
    )
    def update_route_visibility(route_toggle):
        """
        Immediately show or hide agent routes when the toggle changes,
        without waiting for the next simulation tick.
        """
        patched_fig = Patch()
        show = bool(route_toggle)
        patched_fig['data'][4]['visible'] = show
        if show:
            route_lons, route_lats = _build_route_geometry(state['model'])
            patched_fig['data'][4]['lon'] = route_lons
            patched_fig['data'][4]['lat'] = route_lats
        return patched_fig

    @app.callback(
        Output('map', 'figure', allow_duplicate=True),
        Input('run-store', 'data'),
        State('route-toggle', 'value'),
        prevent_initial_call=True,
    )
    def reset_figure(store, route_toggle):
        """Return a fully rebuilt figure after a reset."""
        current_reset_id = store.get('reset_id')
        if current_reset_id is None or current_reset_id == state['last_reset_id']:
            return no_update
        state['last_reset_id'] = current_reset_id
        fig = build_initial_figure(
            state['model'], state['centre_lon'], state['centre_lat'], viz_data
        )
        if route_toggle:
            route_lons, route_lats = _build_route_geometry(state['model'])
            fig.data[4].lon = route_lons
            fig.data[4].lat = route_lats
            fig.data[4].visible = True
        return fig
