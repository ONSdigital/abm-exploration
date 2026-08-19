"""
Dash callbacks for the Fieldworker ABM visualisation.
"""
import dash
import plotly.graph_objects as go
from app_layout import _build_route_geometry, build_initial_figure
from config import METRIC_METADATA, daily_hh_per_agent, num_field_staff
from dash import Input, Output, Patch, State, no_update


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
        State('absence-toggle', 'value'),
        State('route-compliance-toggle', 'value'),
        prevent_initial_call=True,
    )
    def handle_controls(play_clicks, pause_clicks, reset_clicks,
                        field_staff_value, daily_hh_value, store,
                        step_duration, absence_toggle,
                        route_compliance_toggle):
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
            apply_daily_absences = bool(absence_toggle)
            apply_route_non_compliance = bool(route_compliance_toggle)
            state['model'].reset(
                selected_staff,
                hh_per_agent=selected_daily_hh,
                apply_daily_absences=apply_daily_absences,
                apply_route_non_compliance=apply_route_non_compliance,
            )
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
        State('field-staff-slider', 'value'),
        State('daily-hh-per-agent-slider', 'value'),
        prevent_initial_call=True,
    )
    def tick(n_intervals, store, metric, choropleth_interval,
             step_duration, steps_per_tick, route_toggle, max_days,
             field_staff_slider_value, daily_hh_slider_value):
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

        # Guard against the Dash race condition where the interval fires again
        # before the browser receives and processes the updated run-store that
        # a previous tick returned with running=False.
        if max_days is not None and model.current_day > int(max_days):
            store['running'] = False
            return no_update, no_update, store

        store.setdefault('current_field_staff', len(model.field_staff))
        store.setdefault('current_daily_hh_per_agent', model.hh_per_agent)

        if step_duration is not None:
            model.simulation_step_seconds = step_duration
            model.travel_distance_per_step = (
                model.walking_speed * model.simulation_step_seconds
            )

        steps_per_tick = int(steps_per_tick or 1)
        day_changed = False
        for _ in range(steps_per_tick):
            if max_days is not None and model.current_day > int(max_days):
                store['running'] = False
                break
            day_before_step = model.current_day
            model.step()

            if model.current_day != day_before_step:
                day_changed = True
                pending_staff = int(field_staff_slider_value or \
                                    len(model.field_staff))
                current_staff_count = len(model.field_staff)
                pending_daily_hh = int(daily_hh_slider_value or \
                                       model.hh_per_agent)
                current_daily_hh = model.hh_per_agent

                # Apply pending daily household target and staff count together
                # at day rollover to keep day-level assignment changes coherent.
                model.hh_per_agent = pending_daily_hh

                if pending_staff != current_staff_count:
                    model.set_field_staff_count(pending_staff)
                elif pending_daily_hh != current_daily_hh:
                    model.update_daily_target_lsoas()
                    model.assign_agents_to_target_lsoas()

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
        Output('results-overlay', 'style'),
        Output('interaction-time-chart', 'figure'),
        Output('knocks-interactions-chart', 'figure'),
        Output('cumulative-chart', 'figure'),
        Output('questionnaire-completion-chart', 'figure'),
        Output('attendance-chart', 'figure'),
        Input('view-results-btn', 'n_clicks'),
        Input('close-results-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_results_overlay(open_clicks, close_clicks):
        """
        Opens/closes the results overlay and populates the charts.
        """
        _overlay_visible = {
            'display': 'block',
            'position': 'fixed',
            'top': '5vh', 'left': '5vw',
            'width': '90vw', 'height': '90vh',
            'background': 'white',
            'zIndex': 1000,
            'padding': '20px',
            'boxShadow': '0 4px 24px rgba(0,0,0,0.45)',
            'overflowY': 'auto',
            'borderRadius': '8px',
        }
        _overlay_hidden = dict(_overlay_visible, display='none')

        if dash.callback_context.triggered_id == 'close-results-btn':
            return _overlay_hidden, no_update, no_update, no_update, \
                no_update, no_update

        model = state['model']
        data = model.daily_interaction_time_pct
        if not data:
            empty_fig = go.Figure()
            empty_fig.update_layout(
                title='No completed days yet.',
                xaxis_title='Day',
                yaxis_title='Interaction time (%)',
            )
            return _overlay_visible, empty_fig, go.Figure(), go.Figure(), \
                    go.Figure(), go.Figure()

        days = sorted(data.keys())
        pcts = [data[d] for d in days]
        fig_time = go.Figure(go.Bar(
            x=[f'Day {d}' for d in days],
            y=pcts,
            marker_color='orangered',
            hovertemplate='%{x}: %{y:.1f}%<extra></extra>',
        ))
        fig_time.update_layout(
            title='Field staff interaction time by day',
            xaxis_title='Day',
            yaxis_title='Interaction time (%)',
            yaxis={
                'range': [40, 100],
                'showgrid': True,
                'gridcolor': 'rgba(200, 200, 200, 0.4)',
                'showline': True,
                'linecolor': 'black',
            },
            xaxis={
                'showgrid': False,
                'showline': True,
                'linecolor': 'black',
            },
            plot_bgcolor='white',
            bargap=0.3,
        )

        knocks_data = model.daily_knocks_by_day
        interactions_data = model.daily_interactions_by_day
        knocks = [knocks_data.get(d, 0) for d in days]
        interactions = [interactions_data.get(d, 0) for d in days]
        day_labels = [f'Day {d}' for d in days]
        fig_contacts = go.Figure()
        fig_contacts.add_trace(go.Bar(
            x=day_labels,
            y=knocks,
            name='Households visited',
            marker_color='blue',
            hovertemplate='%{x}<br>Visits: %{y}<extra></extra>',
        ))
        fig_contacts.add_trace(go.Bar(
            x=day_labels,
            y=interactions,
            name='Interactions',
            marker_color='lightblue',
            hovertemplate='%{x}<br>Interactions: %{y}<extra></extra>',
        ))
        fig_contacts.update_layout(
            title='Household visits and interactions by day',
            xaxis_title='Day',
            yaxis_title='Households',
            yaxis={
                'showgrid': True,
                'gridcolor': 'rgba(200, 200, 200, 0.4)',
                'showline': True,
                'linecolor': 'black',
            },
            xaxis={
                'showgrid': False,
                'showline': True,
                'linecolor': 'black',
            },
            barmode='overlay',
            plot_bgcolor='white',
            bargap=0.3,
            legend={'orientation': 'h', 'y': -0.2},
        )
        cumulative_knocks = []
        cumulative_interactions = []
        running_knocks = 0
        running_interactions = 0
        for d in days:
            running_knocks += knocks_data.get(d, 0)
            running_interactions += interactions_data.get(d, 0)
            cumulative_knocks.append(running_knocks)
            cumulative_interactions.append(running_interactions)
        fig_cumulative = go.Figure()
        fig_cumulative.add_trace(go.Scatter(
            x=day_labels,
            y=cumulative_knocks,
            mode='lines+markers',
            name='Cumulative households visited',
            line={'color': 'blue'},
            hovertemplate='%{x}<br>Total visits: %{y}<extra></extra>',
        ))
        fig_cumulative.add_trace(go.Scatter(
            x=day_labels,
            y=cumulative_interactions,
            mode='lines+markers',
            name='Cumulative interactions',
            line={'color': 'lightblue'},
            hovertemplate='%{x}<br>Total interactions: %{y}<extra></extra>',
        ))
        fig_cumulative.update_layout(
            title='Cumulative household visits and interactions',
            xaxis_title='Day',
            yaxis_title='Households (cumulative)',
            yaxis={
                'showgrid': True,
                'gridcolor': 'rgba(200, 200, 200, 0.4)',
                'showline': True,
                'linecolor': 'black',
            },
            xaxis={
                'showgrid': False,
                'showline': True,
                'linecolor': 'black',
            },
            plot_bgcolor='white',
            legend={'orientation': 'h', 'y': -0.2},
        )

        completion_pct_data = model.daily_questionnaire_completion_pct
        completion_pcts = [completion_pct_data.get(d, 0) for d in days]
        fig_completion = go.Figure(go.Scatter(
            x=day_labels,
            y=completion_pcts,
            mode='lines+markers',
            line={'color': 'green'},
            hovertemplate='%{x}<br>Completion: %{y:.1f}%<extra></extra>',
        ))
        fig_completion.update_layout(
            title='Questionnaire completion rate',
            xaxis_title='Day',
            yaxis_title='% households completed',
            yaxis={'range': [0, 100],
                   'showgrid': True,
                   'gridcolor': 'rgba(200, 200, 200, 0.4)',
                   'showline': True,
                   'linecolor': 'black',
            },
            xaxis={'showgrid': False,
                   'showline': True,
                   'linecolor': 'black',
            },
            plot_bgcolor='white',
            showlegend=False,
        )

        attendance_data = model.daily_attendance_pct
        attendance_pcts = [attendance_data.get(d, 0) for d in days]
        fig_attendance = go.Figure(go.Scatter(
            x=day_labels,
            y=attendance_pcts,
            mode='lines+markers',
            line={'color': 'steelblue'},
            hovertemplate='%{x}<br>Attendance: %{y:.1f}%<extra></extra>',
        ))
        fig_attendance.update_layout(
            title='Field staff attendance by day',
            xaxis_title='Day',
            yaxis_title='% staff present',
            yaxis={
                'range': [0, 100],
                'showgrid': True,
                'gridcolor': 'rgba(200, 200, 200, 0.4)',
                'showline': True,
                'linecolor': 'black',
            },
            xaxis={
                'showgrid': False,
                'showline': True,
                'linecolor': 'black',
            },
            plot_bgcolor='white',
            showlegend=False,
        )

        return _overlay_visible, fig_time, fig_contacts, fig_cumulative, \
            fig_completion, fig_attendance

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
