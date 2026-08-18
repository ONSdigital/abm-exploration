"""
Dash visualisation entry point for the Fieldworker ABM.

Open http://127.0.0.1:8050 in a browser.

Aaron Stace, 03/07/2026
"""
import dash
from app_callbacks import init_callbacks
from app_layout import build_initial_figure, create_layout
from config import LSOA_CODE_COLUMN, LSOAS_FILEPATH, num_field_staff
from fieldwork_model import FieldWorkModel
from mapping import load_lsoa_geojson, to_wgs84

model = FieldWorkModel(num_field_staff=num_field_staff)

address_lons, address_lats = to_wgs84(
    model.gdf_addresses.geometry.x, model.gdf_addresses.geometry.y
)
lsoa_geojson, lsoa_ids, lsoa_names = load_lsoa_geojson(LSOAS_FILEPATH, LSOA_CODE_COLUMN)

viz_data = {
    'address_lons': address_lons,
    'address_lats': address_lats,
    'lsoa_geojson': lsoa_geojson,
    'lsoa_ids': lsoa_ids,
    'lsoa_names': lsoa_names,
}

# Pre-compute the centroid of the address cloud to centre the map on load.
centre_lon = sum(address_lons) / len(address_lons)
centre_lat = sum(address_lats) / len(address_lats)

# Shared mutable state — passed into callbacks so all functions reference the
# same model instance even after a reset.
state = {
    'model': model,
    'centre_lon': centre_lon,
    'centre_lat': centre_lat,
}

initial_fig = build_initial_figure(model, centre_lon, centre_lat, viz_data)

app = dash.Dash(__name__)
app.layout = create_layout(initial_fig)
init_callbacks(app, state, viz_data)


if __name__ == '__main__':
    app.run(debug=True)
