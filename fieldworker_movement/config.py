"""
A store for file paths, constants and parameters for the field staff ABM.

Aaron Stace, 03/07/2026
"""
#-------------------------------FILE PATHS--------------------------------#

# File paths need two backslashes otherwise the code will break.
ADDRESSES_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\addresses\\Raw_Address_Data_Newcastle_April_2025.csv"
ROADS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Roads\\Newcastle_Upon_Tyne_Roads.gpkg"
PATHS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Paths\\Newcastle_Upon_Tyne_Paths.gpkg"
LSOAS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\LSOAs\\LSOAs_Newcastle_Upon_Tyne.gpkg"

# Cached network GeoDataFrame written after the first neatnet.close_gaps run.
# Delete this file to force a rebuild (e.g. after updating the shapefiles).
NETWORK_CACHE_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\network_graphs\\network_cache.gpkg"


#--------------------------------ADDRESS FILE--------------------------------#

# Column name in the LSOA shapefile that holds the LSOA code.
LSOA_CODE_COLUMN = "LSOA21CD"
ADDRESSES_DELIMITER = ','
EASTING_COLUMN = 'X_COORDINATE'
NORTHING_COLUMN = 'Y_COORDINATE'

#-----------------------------MODEL PARAMETERS----------------------------#

num_field_staff = 10  # Default number of field staff agents in the model.

model_params = {
    'n_field_staff': {
        'type': 'SliderInt',
        'value': 5,
        'label': 'No. of field staff',
        'min': 1,
        'max': 20,
        'step': 1,
    },
    'walking_speed': {
        'type': 'SliderInt',
        'value': 5,
        'label': 'Walking speed (m/s)',
        'min': 1,
        'max': 10,
        'step': 1,
    },
    'answer_prob': {
        'type': 'SliderInt',
        'value': 0.5,
        'label': 'P(household responds to knock)',
        'min': 0,
        'max': 1,
    },
    'hh_response_chance': {
        'type': 'SliderInt',
        'value': 0.75,
        'label': 'Chance of household completing Census',
        'min': 0,
        'max': 1,
        'step': 0.05,
    },
}