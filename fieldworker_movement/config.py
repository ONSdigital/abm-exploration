"""
A store for file paths, constants and parameters for the field staff ABM.

Aaron Stace, 03/07/2026
"""
#-------------------------------FILE PATHS--------------------------------#

# File paths need two backslashes otherwise the code will break.
ADDRESSES_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Addresses\\Newcastle_Upon_Tyne_Addresses.csv"
ROADS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Roads\\Newcastle_Upon_Tyne_Roads.gpkg"
PATHS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Paths\\Newcastle_Upon_Tyne_Paths.gpkg"


#-----------------------------MODEL PARAMETERS----------------------------#

model_params = {
    'n_field_staff': {
        'type': 'SliderInt',
        'value': 5,
        'label': 'No. of field staff',
        'min': 1,
        'max': 20,
        'step': 1,
    },
    'hh_response_chance': {
        'type': 'SliderInt',
        'value': 0.5,
        'label': 'P(household responds to knock)',
        'min': 0,
        'max': 1,
    },
    'walking_speed': {
        'type': 'SliderInt',
        'value': 5,
        'label': 'Walking speed (m/s)',
        'min': 1,
        'max': 10,
        'step': 1,
    }
}