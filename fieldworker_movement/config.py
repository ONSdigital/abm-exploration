"""
A store for file paths, constants and parameters for the field staff ABM.

Aaron Stace, 03/07/2026
"""
#-------------------------------FILE PATHS--------------------------------#

# File paths need two backslashes otherwise the code will break.
ADDRESSES_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\addresses\\Raw_Address_Data_Newcastle_April_2025.csv"
ROADS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Roads\\Newcastle_Upon_Tyne_Roads_2.gpkg"
PATHS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\Paths\\Newcastle_Upon_Tyne_Paths.gpkg"
LSOAS_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\newcastle_upon_tyne_shapefiles\\LSOAs\\LSOAs_Newcastle_Upon_Tyne.gpkg"

# Cached network GeoDataFrame written after the first neatnet.close_gaps run.
# Delete this file to force a rebuild (e.g. after updating the shapefiles).
NETWORK_CACHE_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\network_graphs\\network_cache.gpkg"
LSOA_COMPLETION_FILEPATH = "C:\\Users\\stacea\\abm-exploration\\fieldworker_movement\\addresses\\lsoa_completion_rates_low_variation.csv"


#--------------------------------ADDRESS FILE--------------------------------#

# Column name in the LSOA shapefile that holds the LSOA code.
LSOA_CODE_COLUMN = "LSOA21CD"
ADDRESSES_DELIMITER = ','
COMPLETION_DELIMITER = ','
EASTING_COLUMN = 'X_COORDINATE'
NORTHING_COLUMN = 'Y_COORDINATE'
INITIAL_COMPLETION_COLUMN = 'initial_completion_rate'
ONGOING_COMPLETION_COLUMN = 'ongoing_completion_rate'

DEFAULT_INITIAL_COMPLETION_RATE = 0.0
DEFAULT_ONGOING_COMPLETION_RATE = 0.0
KNOCK_RESPONSE_CHANCE = 0.8
KNOCK_COMPLETION_CHANCE = 0.3
INTERACTION_COMPLETION_CHANCE = 0.8


#-----------------------------MODEL PARAMETERS----------------------------#

num_field_staff = 30  # Default number of field staff agents in the model.
walking_speed = 1.4  # Average walking speed of agents in m/s
driving_speed = 13.9  # Average driving speed of agents in m/s
daily_hh_per_agent = 50 # No. of households an agent is told to visit daily

simulation_step_seconds = 30  # Default sim seconds advanced on each model step.
workday_start_hour = 9  # Simulated clock time when each workday begins.
workday_duration_hours = 5  # Fieldwork hours completed before day rollover.
dash_interval_ms = 500  # Real-time UI refresh cadence for simulation playback.

hh_interaction_mean = 300  # Mean time for hh-staff interaction in seconds (5min).
hh_interaction_std = 60  # Std of time for hh-staff interaction in seconds (1min).
daily_absence_rate = 0.2  # Probability that any given field worker is absent on a given day.
non_compliant_agent_pct = 0.10  # Fraction of field staff who ignore the planned route and use nearest-neighbour routing instead.


#---------------------------CHOROPLETH METRICS---------------------------#

# Maps each choropleth metric key to its display label and Plotly colorscale.
METRIC_METADATA = {
    'knocks': {
        'label': 'Knocks',
        'colorscale': [
            [0.0, 'rgba(8, 81, 156, 0.0)'],
            [1.0, 'rgba(8, 81, 156, 1.0)'],
        ],
    },
    'interactions': {
        'label': 'Interactions',
        'colorscale': [
            [0.0, 'rgba(35, 139, 69, 0.0)'],
            [1.0, 'rgba(35, 139, 69, 1.0)'],
        ],
    },
    'questionnaire_completions': {
        'label': 'Questionnaire Completion',
        'colorscale': [
            [0.0, 'rgb(215, 48, 39)'],
            [0.5, 'rgb(255, 255, 191)'],
            [1.0, 'rgb(26, 150, 65)'],
        ],
    },
}
