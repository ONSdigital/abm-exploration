"""
Headless scenario runner for the FieldWorker ABM.

Runs each scenario for a fixed number of simulated days, then writes:
  - scenario_results.xlsx  — one sheet per scenario, one row per completed day
  - scenario_<label>.png   — 7-panel results chart per scenario (same layout as
                             the Dash results overlay)

Aaron Stace, 26/08/2026
"""
import os
import time

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from config import num_field_staff, revisit_buffer_days
from fieldwork_model import FieldWorkModel
from plotly.subplots import make_subplots

# ── Configuration — edit these ────────────────────────────────────────────────

SEED = 42
NUM_DAYS = 10
OUTPUT_DIR = r"C:\Users\stacea\abm-exploration\fieldworker_movement\model_outputs"

# Safety cap: if a scenario hasn't finished after this many steps, stop early
# and warn. Prevents infinite loops from unexpected model states.
MAX_STEPS_GUARD = 5_000_000

SCENARIOS = [
    {
        'label': 'Baseline',
        'apply_daily_absences':       False,
        'apply_route_non_compliance': False,
        'apply_homeward_revisits':    False,
        'revisit_buffer_days':        revisit_buffer_days,
    },
]

# ─────────────────────────────────────────────────────────────────────────────


def run_scenario(scenario, seed, num_days):
    """
    Initialise a FieldWorkModel for the given scenario config and step it
    until `num_days` completed days have been recorded.

    Returns the model after the run completes.
    """
    label = scenario['label']
    print(f"\n{'=' * 60}")
    print(f"  Scenario : {label}")
    print(f"  Seed={seed} | Days={num_days}")
    print(f"{'=' * 60}")

    model = FieldWorkModel(
        num_field_staff=scenario.get('num_field_staff', num_field_staff),
        apply_daily_absences=scenario.get('apply_daily_absences', True),
        apply_route_non_compliance=scenario.get('apply_route_non_compliance', True),
        apply_homeward_revisits=scenario.get('apply_homeward_revisits', True),
        revisit_buffer_days=scenario.get('revisit_buffer_days', revisit_buffer_days),
        seed=seed,
    )
    if 'hh_per_agent' in scenario:
        model.hh_per_agent = scenario['hh_per_agent']

    print(f"  Model initialised. "
          f"{len(model.households):,} households | "
          f"{len(model.field_staff)} field staff")
    print("  Stepping model...")

    t_start  = time.time()
    steps    = 0
    last_day = 0

    while len(model.daily_knocks_by_day) < num_days:
        model.step()
        steps += 1

        if model.current_day != last_day:
            last_day  = model.current_day
            days_done = len(model.daily_knocks_by_day)
            elapsed   = time.time() - t_start
            knocks    = model.daily_knocks_by_day.get(days_done, 0)
            print(f"    Day {days_done:>2}/{num_days} complete | "
                  f"knocks: {knocks:>5} | "
                  f"steps so far: {steps:>9,} | "
                  f"elapsed: {elapsed:.1f}s")

        if steps >= MAX_STEPS_GUARD:
            print(f"  [WARNING] Step guard reached ({MAX_STEPS_GUARD:,} steps). "
                  f"Stopping early — only {len(model.daily_knocks_by_day)} "
                  f"day(s) recorded.")
            break

    total = time.time() - t_start
    print(f"  Finished. {steps:,} total steps in {total:.1f}s")
    return model


def extract_rows(model):
    """
    Build a list of per-day result dicts from a completed model run.
    Cumulative knock/interaction totals are computed here.
    """
    days = sorted(model.daily_knocks_by_day.keys())
    cumulative_knocks              = 0
    cumulative_interactions        = 0
    cumulative_cross_day_revisits  = 0
    rows = []
    for day in days:
        knocks             = model.daily_knocks_by_day.get(day, 0)
        interactions       = model.daily_interactions_by_day.get(day, 0)
        cross_day_revisits = model.daily_cross_day_revisits_by_day.get(day, 0)
        cumulative_knocks             += knocks
        cumulative_interactions       += interactions
        cumulative_cross_day_revisits += cross_day_revisits
        rows.append({
            'day':                           day,
            'knocks':                        knocks,
            'interactions':                  interactions,
            'cumulative_knocks':             cumulative_knocks,
            'cumulative_interactions':       cumulative_interactions,
            'questionnaire_completion_pct':  round(
                model.daily_questionnaire_completion_pct.get(day, 0.0), 2
            ),
            'attendance_pct': round(
                model.daily_attendance_pct.get(day, 0.0), 2
            ),
            'interaction_time_pct': round(
                model.daily_interaction_time_pct.get(day, 0.0), 2
            ),
            'multi_visits':                  model.daily_multi_visits_by_day.get(day, 0),
            'cross_day_revisits':            cross_day_revisits,
            'cumulative_cross_day_revisits': cumulative_cross_day_revisits,
        })
    return rows


def save_excel(all_results, output_path):
    """
    Write all scenario results to a single .xlsx file, one sheet per scenario.
    Sheet names are truncated to Excel's 31-character limit.
    """
    print(f"\nWriting Excel results → {output_path}")
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for label, rows in all_results.items():
            sheet_name = label[:31]
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  Sheet written : '{sheet_name}'")
    print("  Done.")


def save_png(label, rows, output_path):
    """
    Produce an 8-panel PNG chart for a single scenario (4 rows x 2 cols),
    matching the layout of the Dash results overlay:
      Row 1: interaction time %          |  knocks & interactions by day
      Row 2: cumulative totals           |  questionnaire completion %
      Row 3: staff attendance %          |  same-day multi-visits by day
      Row 4: cross-day revisits          |  (blank)
    """
    day_labels = [f"Day {r['day']}" for r in rows]

    fig = make_subplots(
        rows=4, cols=2,
        subplot_titles=(
            'Field staff interaction time (%)',
            'Household visits and interactions by day',
            'Cumulative visits and interactions',
            'Questionnaire completion (%)',
            'Staff attendance (%)',
            'Same-day multi-visits by day',
            'Cross-day revisits',
            '',
        ),
        vertical_spacing=0.10,
        horizontal_spacing=0.10,
    )

    # Row 1, Col 1 — interaction time %
    fig.add_trace(go.Bar(
        x=day_labels,
        y=[r['interaction_time_pct'] for r in rows],
        marker_color='orangered',
        showlegend=False,
        hovertemplate='%{x}: %{y:.1f}%<extra></extra>',
    ), row=1, col=1)

    # Row 1, Col 2 — knocks and interactions (overlaid bars)
    fig.add_trace(go.Bar(
        x=day_labels,
        y=[r['knocks'] for r in rows],
        name='Knocks',
        marker_color='steelblue',
        hovertemplate='%{x}<br>Knocks: %{y}<extra></extra>',
    ), row=1, col=2)
    fig.add_trace(go.Bar(
        x=day_labels,
        y=[r['interactions'] for r in rows],
        name='Interactions',
        marker_color='lightblue',
        hovertemplate='%{x}<br>Interactions: %{y}<extra></extra>',
    ), row=1, col=2)

    # Row 2, Col 1 — cumulative knocks & interactions
    fig.add_trace(go.Scatter(
        x=day_labels,
        y=[r['cumulative_knocks'] for r in rows],
        name='Cumulative knocks',
        mode='lines+markers',
        line={'color': 'steelblue'},
        hovertemplate='%{x}<br>Total knocks: %{y}<extra></extra>',
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=day_labels,
        y=[r['cumulative_interactions'] for r in rows],
        name='Cumulative interactions',
        mode='lines+markers',
        line={'color': 'lightblue'},
        hovertemplate='%{x}<br>Total interactions: %{y}<extra></extra>',
    ), row=2, col=1)

    # Row 2, Col 2 — questionnaire completion %
    fig.add_trace(go.Scatter(
        x=day_labels,
        y=[r['questionnaire_completion_pct'] for r in rows],
        mode='lines+markers',
        line={'color': 'seagreen'},
        showlegend=False,
        hovertemplate='%{x}: %{y:.1f}%<extra></extra>',
    ), row=2, col=2)

    # Row 3, Col 1 — attendance %
    fig.add_trace(go.Bar(
        x=day_labels,
        y=[r['attendance_pct'] for r in rows],
        marker_color='mediumpurple',
        showlegend=False,
        hovertemplate='%{x}: %{y:.1f}%<extra></extra>',
    ), row=3, col=1)

    # Row 3, Col 2 — same-day multi-visits
    fig.add_trace(go.Bar(
        x=day_labels,
        y=[r['multi_visits'] for r in rows],
        marker_color='darkorange',
        showlegend=False,
        hovertemplate='%{x}: %{y}<extra></extra>',
    ), row=3, col=2)

    # Row 4, Col 1 — cross-day revisits: per-day bar + cumulative line
    fig.add_trace(go.Bar(
        x=day_labels,
        y=[r['cross_day_revisits'] for r in rows],
        name='Cross-day revisits (daily)',
        marker_color='crimson',
        opacity=0.6,
        hovertemplate='%{x}<br>Revisits: %{y}<extra></extra>',
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=day_labels,
        y=[r['cumulative_cross_day_revisits'] for r in rows],
        name='Cumulative cross-day revisits',
        mode='lines+markers',
        line={'color': 'darkred'},
        hovertemplate='%{x}<br>Total revisits: %{y}<extra></extra>',
    ), row=4, col=1)

    # Fix y-axes to [0, 100] for percentage panels
    for (r, c) in [(1, 1), (2, 2), (3, 1)]:
        fig.update_yaxes(range=[0, 100], row=r, col=c)

    fig.update_layout(
        title_text=f'Scenario results: {label}',
        title_font_size=16,
        barmode='overlay',
        height=1600,
        width=1400,
        plot_bgcolor='white',
        legend={
            'orientation': 'h',
            'y': -0.03,
            'x': 0.5,
            'xanchor': 'center',
        },
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor='black')
    fig.update_yaxes(
        showgrid=True,
        gridcolor='rgba(200,200,200,0.4)',
        showline=True,
        linecolor='black',
    )

    pio.write_image(fig, output_path, format='png', scale=2)
    print(f"  PNG saved    → {output_path}")


if __name__ == '__main__':
    print("FieldWorker ABM — Headless Scenario Runner")
    print(f"Seed: {SEED} | Days per scenario: {NUM_DAYS} | "
          f"Scenarios: {len(SCENARIOS)}")

    all_results = {}
    for i, scenario in enumerate(SCENARIOS, start=1):
        print(f"\n[{i}/{len(SCENARIOS)}] Starting scenario: {scenario['label']}")
        model = run_scenario(scenario, SEED, NUM_DAYS)
        rows  = extract_rows(model)
        label = scenario['label']
        all_results[label] = rows

        safe_label = label.replace(' ', '_').replace('/', '-').replace('+', 'and')
        png_path   = os.path.join(OUTPUT_DIR, f'scenario_{safe_label}.png')
        print("  Generating PNG...")
        save_png(label, rows, png_path)

    xlsx_path = os.path.join(OUTPUT_DIR, 'scenario_results.xlsx')
    save_excel(all_results, xlsx_path)

    print(f"\n{'=' * 60}")
    print(f"All {len(SCENARIOS)} scenario(s) complete.")
    print(f"Outputs written to: {OUTPUT_DIR}")
    print(f"{'=' * 60}")
