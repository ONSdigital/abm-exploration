"""
The FieldWorkModel Mesa model class. Handles all Mesa-specific model 
mechanisms such as agent interaction and movement.

Aaron Stace, 03/07/2026
"""
import mesa
from mesa.space import NetworkGrid
from collections import defaultdict

from agents import FieldWorker, Household
from mapping import build_graph_from_shapefile, load_addresses, \
    snap_addresses_to_nodes, load_network_data, load_lsoa_geojson, to_wgs84, \
    load_lsoa_completion_rates, connect_components
from config import ROADS_FILEPATH, PATHS_FILEPATH, ADDRESSES_FILEPATH, \
                LSOAS_FILEPATH, LSOA_CODE_COLUMN, \
                LSOA_COMPLETION_FILEPATH, INITIAL_COMPLETION_COLUMN, \
                ONGOING_COMPLETION_COLUMN, DEFAULT_INITIAL_COMPLETION_RATE, \
                DEFAULT_ONGOING_COMPLETION_RATE, \
                DEFAULT_HOUSEHOLD_RESPONSE_CHANCE, \
                walking_speed, \
                simulation_step_seconds, workday_start_hour, \
                workday_duration_hours


class FieldWorkModel(mesa.Model):
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_field_staff):
        
        super().__init__()

        self.simulation_step_seconds = simulation_step_seconds
        self.walking_speed = walking_speed
        self.travel_distance_per_step = (
            self.walking_speed * self.simulation_step_seconds
        )
        self.workday_start_hour = workday_start_hour
        self.workday_duration_hours = workday_duration_hours
        self.workday_start_seconds = self.workday_start_hour * 60 * 60
        self.workday_duration_seconds = self.workday_duration_hours * 60 * 60
        self.current_day = 1
        self.seconds_since_midnight = self.workday_start_seconds
        self.total_work_seconds = 0
        self.daily_target_lsoas = []

        gdf = load_network_data(ROADS_FILEPATH, PATHS_FILEPATH)
        G = build_graph_from_shapefile(gdf)
        G = connect_components(G)
        gdf_addresses = load_addresses(ADDRESSES_FILEPATH)
        self.lsoa_completion_rates = load_lsoa_completion_rates(
            LSOA_COMPLETION_FILEPATH
        )

        self.grid = NetworkGrid(G)
        self.graph = G
        self.node_list = list(G.nodes())

        self.lsoa_stats = defaultdict(lambda: {
            'knocks': 0,
            'interactions': 0,
            'questionnaire_completions': 0,
            'initial_questionnaire_completions': 0,
            'ongoing_questionnaire_completions': 0,
            'remaining_households': 0,
            'total_households': 0,
        })

        address_nodes = snap_addresses_to_nodes(gdf_addresses, G)
        self.households = []
        for node, lsoa in address_nodes:
            completion_rates = self.get_lsoa_completion_rates(lsoa)
            survey_completed = (
                self.random.random() < completion_rates[INITIAL_COMPLETION_COLUMN]
            )
            household = Household(
                model=self,
                node=node,
                lsoa=lsoa,
                response_chance=DEFAULT_HOUSEHOLD_RESPONSE_CHANCE,
                initial_completion_rate=completion_rates[INITIAL_COMPLETION_COLUMN],
                ongoing_completion_rate=completion_rates[ONGOING_COMPLETION_COLUMN],
                survey_completed=survey_completed,
            )
            self.households.append(household)
            self.lsoa_stats[lsoa]['total_households'] += 1
            self.lsoa_stats[lsoa]['remaining_households'] += 1
            if survey_completed:
                self.register_completion(household, characteristic='initial', step_number=0)

        # Build a node → [Household, ...] lookup for fast access in visit_household.
        self.node_to_households = defaultdict(list)
        for household in self.households:
            self.node_to_households[household.node].append(household)

        # One entry per step: {'step': N, 'lsoa_stats': {lsoa: {knocks, interactions}}}
        self.step_history = []

        # Storing display-only true geographic positions of addresses (WGS84) 
        # for the visualisation background layer.
        self.address_lons, self.address_lats = to_wgs84(
            gdf_addresses.geometry.x, gdf_addresses.geometry.y
        )

        # LSOA polygon geometry for the live choropleth layer.
        self.lsoa_geojson, self.lsoa_ids, self.lsoa_names = load_lsoa_geojson(
            LSOAS_FILEPATH, LSOA_CODE_COLUMN
        )

        self.field_staff = FieldWorker.create_agents(
            model=self,
            n=num_field_staff,
            node=[self.random.choice(self.node_list) for _ in range(num_field_staff)]
        )
        self.update_daily_target_lsoas()

    def get_lsoa_completion_rates(self, lsoa_code):
        """
        Returns completion-rate settings for an LSOA with defaults.
        """
        return self.lsoa_completion_rates.get(str(lsoa_code), {
            INITIAL_COMPLETION_COLUMN: DEFAULT_INITIAL_COMPLETION_RATE,
            ONGOING_COMPLETION_COLUMN: DEFAULT_ONGOING_COMPLETION_RATE,
        })

    def update_daily_target_lsoas(self, target_count=None):
        """
        Store the current day's lowest-completion incomplete LSOAs. Number 
        of them is determined by number of field staff available that day.

        Parameters
        ----------
        target_count : int or None
            Maximum number of unique LSOA codes to store. Defaults to the
            current number of field staff agents.

        Returns
        -------
        list[str]
            The ordered LSOA codes selected for the current day.
        """
        if target_count is None:
            target_count = len(self.field_staff) / 2

        target_count = max(0, int(target_count))

        ranked_lsoas = sorted(
            (
                (
                    counts['questionnaire_completions'] / counts['total_households'],
                    str(lsoa),
                )
                for lsoa, counts in self.lsoa_stats.items()
                if counts['total_households'] > 0
                and counts['remaining_households'] > 0
            ),
            key=lambda item: (item[0], item[1]),
        )

        self.daily_target_lsoas = [
            lsoa for _, lsoa in ranked_lsoas[:target_count]
        ]
        return self.daily_target_lsoas

    def register_completion(self, household, characteristic, step_number):
        """
        Update LSOA completion counters when a household completes a Census
        questionnaire.

        Parameters
        ----------
        household : Household agent
            The household that has completed the Census questionnaire.
        characteristic : str
            The characteristic of the completion ('initial' or 'ongoing').
        step_number : int
            The simulation step number when the questionnaire was completed.

        Returns
        -------
        bool
            True if the completion was registered, False if it was ignored
        """
        if characteristic not in {'initial', 'ongoing'}:
            raise ValueError(f"Unknown completion source: {characteristic}")

        if not household.survey_completed:
            completed_now = household.complete_survey(step_number, characteristic)
            if not completed_now:
                return False
        elif household.completion_source != characteristic and household.completion_step != step_number:
            return False

        stats = self.lsoa_stats[household.lsoa]
        stats['questionnaire_completions'] += 1
        stats[f'{characteristic}_questionnaire_completions'] += 1
        stats['remaining_households'] -= 1
        return True

    def advance_electronic_completions(self):
        """
        Allows incomplete households to complete electronically this step.
        """
        for household in self.households:
            if household.survey_completed:
                continue
            if self.random.random() < household.ongoing_completion_rate:
                self.register_completion(
                    household,
                    characteristic='ongoing',
                    step_number=self.steps,
                )

    def format_simulation_time(self):
        """
        Return the current simulated day and clock time for display.
        """
        hours, remainder = divmod(self.seconds_since_midnight, 60 * 60)
        minutes, seconds = divmod(remainder, 60)
        return f'Day {self.current_day} | {hours:02d}:{minutes:02d}:{seconds:02d}'

    def advance_clock(self):
        """
        Rolls simulated clock straight to the next day when the field staff 
        shift ends.
        """
        self.seconds_since_midnight += self.simulation_step_seconds
        self.total_work_seconds += self.simulation_step_seconds

        elapsed_today = self.seconds_since_midnight - self.workday_start_seconds
        if elapsed_today >= self.workday_duration_seconds:
            self.current_day += 1
            self.seconds_since_midnight = self.workday_start_seconds

    def is_working_time(self):
        """
        Returns True when the current simulated day is within the active shift.
        """
        elapsed_today = self.seconds_since_midnight - self.workday_start_seconds
        return elapsed_today < self.workday_duration_seconds

    def get_field_staff_positions(self):
        """
        Return the current WGS84 positions of all field staff agents.

        Reads each agent's current node (an (easting, northing) tuple in
        EPSG:27700) and converts to longitude/latitude for the Dash map layer.

        Returns
        -------
        lons, lats : tuple of lists
        """
        display_positions = [
            getattr(agent, 'display_position', agent.node)
            for agent in self.field_staff
        ]
        eastings = [position[0] for position in display_positions]
        northings = [position[1] for position in display_positions]
        return to_wgs84(eastings, northings)

    def set_field_staff_count(self, target_count):
        """
        Rebuild the field staff agent set to match a requested count.

        This is intended to be called at controlled synchronization points
        (for example at the start of a new simulated day).
        """
        target_count = max(1, int(target_count))

        for agent in list(self.field_staff):
            self.grid.remove_agent(agent)
            agent.remove()

        self.field_staff = FieldWorker.create_agents(
            model=self,
            n=target_count,
            node=[
                self.random.choice(self.node_list)
                for _ in range(target_count)
            ],
        )
        self.update_daily_target_lsoas(target_count=target_count)

    def step(self):
        """
        One step of the model.
        """
        super().step()
        if self.is_working_time():
            self.advance_electronic_completions()
            self.field_staff.shuffle_do('step')
        self.advance_clock()
        # Snapshot cumulative LSOA stats for this step (shallow copy per LSOA).
        self.step_history.append({
            'step': self.steps,
            'day': self.current_day,
            'display_time': self.format_simulation_time(),
            'lsoa_stats': {
                lsoa: dict(counts)
                for lsoa, counts in self.lsoa_stats.items()
            }
        })
        # Could have a one-off end of day method that sends field staff back to one
        # or two houses that didn't answer
