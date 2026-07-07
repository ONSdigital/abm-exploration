"""
Dash visualisation entry point for the Fieldworker ABM.

Open http://127.0.0.1:8050 in a browser.

Aaron Stace, 03/07/2026
"""
import dash

from fieldwork_model import FieldWorkModel
from app_layout import build_initial_figure, create_layout
from app_callbacks import init_callbacks


model = FieldWorkModel(num_field_staff=10)   # update constructor args once they are finalised

# Pre-compute the centroid of the address cloud to centre the map on load.
centre_lon = sum(model.address_lons) / len(model.address_lons)
centre_lat = sum(model.address_lats) / len(model.address_lats)

# Shared mutable state — passed into callbacks so all functions reference the
# same model instance even after a reset.
state = {
    'model': model,
    'centre_lon': centre_lon,
    'centre_lat': centre_lat,
}

initial_fig = build_initial_figure(model, centre_lon, centre_lat)

app = dash.Dash(__name__)
app.layout = create_layout(initial_fig)
init_callbacks(app, state)


if __name__ == '__main__':
    app.run(debug=True)

