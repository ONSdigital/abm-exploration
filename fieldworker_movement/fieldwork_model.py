"""
The FieldWorkModel Mesa model class. Handles all Mesa-specific model 
mechanisms such as agent interaction and movement.

Aaron Stace, 03/07/2026
"""
import math
from collections import defaultdict

import mesa
import networkx as nx
from agents import FieldWorker, Household
from config import (
    ADDRESSES_FILEPATH,
    DEFAULT_INITIAL_COMPLETION_RATE,
    DEFAULT_ONGOING_COMPLETION_RATE,
    INITIAL_COMPLETION_COLUMN,
    KNOCK_RESPONSE_CHANCE,
    LSOA_CODE_COLUMN,
    LSOA_COMPLETION_FILEPATH,
    LSOAS_FILEPATH,
    ONGOING_COMPLETION_COLUMN,
    PATHS_FILEPATH,
    ROADS_FILEPATH,
    daily_hh_per_agent,
    simulation_step_seconds,
    walking_speed,
    workday_duration_hours,
    workday_start_hour,
)
from mapping import (
    build_graph_from_shapefile,
    connect_components,
    load_addresses,
    load_lsoa_completion_rates,
    load_lsoa_geojson,
    load_network_data,
    snap_addresses_to_nodes,
    to_wgs84,
)
from mesa.space import NetworkGrid


class FieldWorkModel(mesa.Model):
    """
    The model of field work operations, which includes a number of field
    workers and the geographic area they operate within.
    """

    def __init__(self, num_field_staff):
        
        super().__init__()

        self.simulation_step_seconds = simulation_step_seconds
        self.walking_speed = walking_speed
        self.hh_per_agent = daily_hh_per_agent
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
        self.current_day_interaction_seconds = 0.0
        self.daily_interaction_time_pct = {}
        self.daily_knocks_by_day = {}
        self.daily_interactions_by_day = {}
        self.prev_day_lsoa_knocks_snapshot = {}
        self.prev_day_lsoa_interactions_snapshot = {}
        self.daily_target_lsoas = []
        self._prev_day = 1  # Track day boundaries for routing trigger
        self.shortest_path_cache = {}  # Cache for road-network distances: 
                                       # (node_a, node_b) -> length

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
            'fieldwork_questionnaire_completions': 0,
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
                knock_response_chance=KNOCK_RESPONSE_CHANCE,
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

        # Build an LSOA → [Household, ...] lookup for daily route assignment.
        self.lsoa_to_households = defaultdict(list)
        for household in self.households:
            self.lsoa_to_households[household.lsoa].append(household)

        # Baseline cumulative-contact snapshots used to derive end-of-day totals.
        self.prev_day_lsoa_knocks_snapshot = {
            lsoa: 0 for lsoa in self.lsoa_stats
        }
        self.prev_day_lsoa_interactions_snapshot = {
            lsoa: 0 for lsoa in self.lsoa_stats
        }

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
        self.assign_agents_to_target_lsoas()

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
        Store the current day's lowest-completion incomplete LSOAs. Two agents 
        in each LSOA, except when odd no. of agents in which case one agent in 
        one of the LSOAs.

        Parameters
        ----------
        target_count : int or None
            Maximum number of unique LSOA codes to store. Defaults to 
            ceil(num_agents/2).

        Returns
        -------
        list[str]
            The ordered LSOA codes selected for the current day.
        """
        if target_count is None:
            target_count = math.ceil(len(self.field_staff) / 2)

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
        if characteristic not in {'initial', 'ongoing', 'fieldwork'}:
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
        colors = [
            "#00aa44" if agent.has_knocked_all_assigned_households()
            else "#0a0001"
            for agent in self.field_staff
        ]
        lons, lats = to_wgs84(eastings, northings)
        return lons, lats, colors

    def get_incomplete_nodes_for_lsoa(self, lsoa_code):
        """
        Return unique nodes in an LSOA that have at least one incomplete household.

        Parameters
        ----------
        lsoa_code : str
            The LSOA code to retrieve nodes for.

        Returns
        -------
        list[tuple]
            Unique (easting, northing) nodes with incomplete households.
        """
        nodes = []
        seen = set()
        for household in self.lsoa_to_households.get(lsoa_code, []):
            if not household.survey_completed and household.node not in seen:
                nodes.append(household.node)
                seen.add(household.node)
        return nodes

    def get_road_distance(self, node_a, node_b):
        """
        Get the road-network shortest-path distance between two nodes.
        Uses a cache to avoid recomputing the same pair.

        Parameters
        ----------
        node_a, node_b : tuple
            (easting, northing) coordinate tuples.

        Returns
        -------
        float
            The shortest-path length in metres, or float('inf') if no path exists.
        """
        # Normalize key to avoid (A, B) and (B, A) as separate entries
        key = tuple(sorted([node_a, node_b]))
        if key in self.shortest_path_cache:
            return self.shortest_path_cache[key]

        try:
            dist = nx.shortest_path_length(
                self.graph,
                node_a,
                node_b,
                weight='length'
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            dist = float('inf')

        self.shortest_path_cache[key] = dist
        return dist

    def get_incomplete_households_for_lsoa(self, lsoa_code):
        """
        Return incomplete households in an LSOA.

        Parameters
        ----------
        lsoa_code : str
            The LSOA code to retrieve households for.

        Returns
        -------
        list[Household]
            Incomplete households for the LSOA.
        """
        return [
            household for household in self.lsoa_to_households.get(lsoa_code, [])
            if not household.survey_completed
        ]

    def _build_open_tsp_route(self, start_node, stop_nodes):
        """
        Build an exact minimum-distance open TSP route from a start node
        through all stop nodes along the road network.

        Parameters
        ----------
        start_node : tuple
            Start node for the route.
        stop_nodes : list[tuple]
            Nodes that must be visited.

        Returns
        -------
        list[tuple]
            Ordered stop nodes to visit.
        """
        unique_stops = list(dict.fromkeys(stop_nodes))
        if not unique_stops:
            return []

        if len(unique_stops) == 1:
            return unique_stops

        n = len(unique_stops)
        start_to_stop = [
            self.get_road_distance(start_node, unique_stops[j])
            for j in range(n)
        ]
        stop_to_stop = [
            [self.get_road_distance(unique_stops[i], 
                                    unique_stops[j]) for j in range(n)]
            for i in range(n)
        ]

        inf = float('inf')
        dp = [[inf] * n for _ in range(1 << n)]
        parent = [[None] * n for _ in range(1 << n)]

        for j in range(n):
            dp[1 << j][j] = start_to_stop[j]

        for mask in range(1 << n):
            for last in range(n):
                cost = dp[mask][last]
                if cost == inf or not (mask & (1 << last)):
                    continue
                for nxt in range(n):
                    if mask & (1 << nxt):
                        continue
                    new_mask = mask | (1 << nxt)
                    new_cost = cost + stop_to_stop[last][nxt]
                    if new_cost < dp[new_mask][nxt]:
                        dp[new_mask][nxt] = new_cost
                        parent[new_mask][nxt] = last

        full_mask = (1 << n) - 1
        end_idx = min(range(n), key=lambda j: dp[full_mask][j])
        if dp[full_mask][end_idx] == inf:
            return unique_stops

        order_indices = []
        mask = full_mask
        current = end_idx
        while current is not None:
            order_indices.append(current)
            prev = parent[mask][current]
            mask &= ~(1 << current)
            current = prev

        order_indices.reverse()
        return [unique_stops[idx] for idx in order_indices]

    def assign_daily_households_and_routes(self, lsoa_code, agents):
        """
        For one LSOA, assign up to 10 unique households per agent for the day
        and build each agent's TSP visit order.
        """
        if not agents:
            return

        incomplete_households = self.get_incomplete_households_for_lsoa(lsoa_code)

        for agent in agents:
            agent.clear_route()
            agent.vrp_waypoint_index = 0
            agent.households_knocked = set()

        ordered_agents = list(agents)
        start_index = (self.current_day - 1) % len(ordered_agents)
        ordered_agents = ordered_agents[start_index:] + ordered_agents[:start_index]

        assigned_by_agent = {agent: [] for agent in ordered_agents}
        remaining_households = list(incomplete_households)

        # Round-robin nearest assignment so agents alternate picks fairly.
        while remaining_households:
            assigned_this_round = False

            for agent in ordered_agents:
                if len(assigned_by_agent[agent]) >= self.hh_per_agent:
                    continue

                ax, ay = agent.node
                nearest_household = min(
                    remaining_households,
                    key=lambda household: (
                        (household.node[0] - ax) ** 2
                        + (household.node[1] - ay) ** 2
                    ),
                )

                assigned_by_agent[agent].append(nearest_household)
                remaining_households.remove(nearest_household)
                assigned_this_round = True

                if not remaining_households:
                    break

            if not assigned_this_round:
                break

        for agent in agents:
            assigned_households = assigned_by_agent.get(agent, [])
            agent.daily_assigned_households = assigned_households
            target_nodes = [household.node for household in assigned_households]
            agent.vrp_waypoints = self._build_open_tsp_route(agent.node, target_nodes)

    def assign_agents_to_target_lsoas(self):
        """
        Assign field workers to target LSOAs for the current day. Agents 
        continue in the same LSOA if it remains in the target list. 
        Reassignment when LSOAs drop out of target list.

        Capacity rule: distribute agents such that each target LSOA has 2 agents,
        except when total agent count is odd, in which case exactly one target
        LSOA has 1 agent. The single-agent LSOA is chosen as the least urgent
        (highest completion ratio) among targets.

        Returns
        -------
        dict
            Per-LSOA assignment: {lsoa_code: [agent, ...]}
        """
        num_agents = len(self.field_staff)
        num_target_lsoas = len(self.daily_target_lsoas)
        single_agent_lsoa = None

        if num_agents % 2 == 1 and num_target_lsoas > 0:
            # Pick the least urgent LSOA for the single agent
            single_agent_lsoa = max(
                self.daily_target_lsoas,
                key=lambda lsoa: (
                    self.lsoa_stats[lsoa]['questionnaire_completions']
                    / max(1, self.lsoa_stats[lsoa]['total_households'])
                )
            )

        # No targets: clear all daily assignment state to avoid stale routes.
        if not self.daily_target_lsoas:
            for agent in self.field_staff:
                agent.assigned_lsoa = None
                agent.clear_route()
                agent.vrp_waypoint_index = 0
                agent.daily_assigned_households = []
                agent.households_knocked = set()
                agent.vrp_waypoints = []
            return {}

        capacity_by_lsoa = {
            lsoa: (1 if lsoa == single_agent_lsoa else 2)
            for lsoa in self.daily_target_lsoas
        }
        assignments = {lsoa: [] for lsoa in self.daily_target_lsoas}
        reassign_agents = []

        # Keep carryover agents only while each LSOA has spare capacity.
        for agent in self.field_staff:
            lsoa = agent.assigned_lsoa
            if lsoa in assignments and len(assignments[lsoa]) < capacity_by_lsoa[lsoa]:
                assignments[lsoa].append(agent)
            else:
                reassign_agents.append(agent)

        # Fill remaining capacity from unassigned agents.
        for agent in reassign_agents:
            placed = False
            for lsoa in self.daily_target_lsoas:
                if len(assignments[lsoa]) >= capacity_by_lsoa[lsoa]:
                    continue

                agent.assigned_lsoa = lsoa
                agent.assigned_day = self.current_day

                incomplete_nodes = self.get_incomplete_nodes_for_lsoa(lsoa)
                if incomplete_nodes:
                    depot_node = self.random.choice(incomplete_nodes)
                    self.grid.move_agent(agent, depot_node)
                    agent.node = depot_node

                assignments[lsoa].append(agent)
                placed = True
                break

            if not placed:
                agent.assigned_lsoa = None
                agent.clear_route()
                agent.vrp_waypoint_index = 0
                agent.daily_assigned_households = []
                agent.households_knocked = set()
                agent.vrp_waypoints = []

        # Start each day from a fresh random incomplete node for every assigned
        # agent, including carryovers that stayed in the same LSOA.
        for lsoa, agents in assignments.items():
            incomplete_nodes = self.get_incomplete_nodes_for_lsoa(lsoa)
            if not incomplete_nodes:
                continue

            for agent in agents:
                depot_node = self.random.choice(incomplete_nodes)
                self.grid.move_agent(agent, depot_node)
                agent.node = depot_node

        for lsoa, agents in assignments.items():
            self.assign_daily_households_and_routes(lsoa, agents)

        return assignments

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
        self.assign_agents_to_target_lsoas()

    def reset(self, num_field_staff, hh_per_agent=None):
        """
        Reset the model to an initial state without reloading geographic data.
        Reuses the existing graph, addresses, LSOA geometry, and household
        locations. Re-randomises household completion state, recreates field
        staff agents, and resets all time and statistics counters.

        Parameters
        ----------
        num_field_staff : int
            Number of field staff agents for the new run.
        hh_per_agent : int, optional
            Daily household target per agent. Defaults to the current value.
        """
        # Reset time / simulation state
        self.current_day = 1
        self.seconds_since_midnight = self.workday_start_seconds
        self.total_work_seconds = 0
        self.current_day_interaction_seconds = 0.0
        self.daily_interaction_time_pct = {}
        self.daily_knocks_by_day = {}
        self.daily_interactions_by_day = {}
        self.prev_day_lsoa_knocks_snapshot = {}
        self.prev_day_lsoa_interactions_snapshot = {}
        self.daily_target_lsoas = []
        self._prev_day = 1
        self.steps = 0
        self.step_history = []

        if hh_per_agent is not None:
            self.hh_per_agent = hh_per_agent

        # Refreshing stats for each LSOA
        self.lsoa_stats = defaultdict(lambda: {
            'knocks': 0,
            'interactions': 0,
            'questionnaire_completions': 0,
            'initial_questionnaire_completions': 0,
            'ongoing_questionnaire_completions': 0,
            'fieldwork_questionnaire_completions': 0,
            'remaining_households': 0,
            'total_households': 0,
        })

        # Re-randomise each household's survey completion state
        for household in self.households:
            completion_rates = self.get_lsoa_completion_rates(household.lsoa)
            survey_completed = (
                self.random.random() < completion_rates[INITIAL_COMPLETION_COLUMN]
            )
            household.survey_completed = survey_completed
            household.completion_step = 0 if survey_completed else None
            household.completion_source = 'initial' if survey_completed else None
            self.lsoa_stats[household.lsoa]['total_households'] += 1
            self.lsoa_stats[household.lsoa]['remaining_households'] += 1
            if survey_completed:
                self.register_completion(
                    household, characteristic='initial', step_number=0
                )

        self.prev_day_lsoa_knocks_snapshot = {
            lsoa: 0 for lsoa in self.lsoa_stats
        }
        self.prev_day_lsoa_interactions_snapshot = {
            lsoa: 0 for lsoa in self.lsoa_stats
        }

        # Remove existing field staff and recreate
        for agent in list(self.field_staff):
            self.grid.remove_agent(agent)
            agent.remove()

        self.field_staff = FieldWorker.create_agents(
            model=self,
            n=num_field_staff,
            node=[self.random.choice(self.node_list) for _ in range(num_field_staff)]
        )
        self.update_daily_target_lsoas()
        self.assign_agents_to_target_lsoas()

    def step(self):
        """
        One step of the model.
        """
        super().step()
        day_before_step = self.current_day

        if self.is_working_time():
            self.advance_electronic_completions()
            self.field_staff.shuffle_do('step')
        self.advance_clock()

        # Day boundary: update target LSOAs and reassign agents
        if self.current_day != self._prev_day:
            completed_day = day_before_step
            staff_capacity_seconds = (
                len(self.field_staff) * self.workday_duration_seconds
            )
            if staff_capacity_seconds > 0:
                day_pct = (
                    self.current_day_interaction_seconds
                    / staff_capacity_seconds
                ) * 100
            else:
                day_pct = 0.0

            self.daily_interaction_time_pct[completed_day] = min(
                100.0,
                max(0.0, day_pct),
            )

            daily_total_knocks = 0
            daily_total_interactions = 0
            for lsoa, stats in self.lsoa_stats.items():
                prev_knocks = self.prev_day_lsoa_knocks_snapshot.get(lsoa, 0)
                prev_interactions = self.prev_day_lsoa_interactions_snapshot.get(
                    lsoa,
                    0,
                )
                daily_total_knocks += stats['knocks'] - prev_knocks
                daily_total_interactions += (
                    stats['interactions'] - prev_interactions
                )

            self.daily_knocks_by_day[completed_day] = max(0, daily_total_knocks)
            self.daily_interactions_by_day[completed_day] = max(
                0,
                daily_total_interactions,
            )

            self.prev_day_lsoa_knocks_snapshot = {
                lsoa: stats['knocks']
                for lsoa, stats in self.lsoa_stats.items()
            }
            self.prev_day_lsoa_interactions_snapshot = {
                lsoa: stats['interactions']
                for lsoa, stats in self.lsoa_stats.items()
            }

            self.current_day_interaction_seconds = 0.0

            self.update_daily_target_lsoas()
            self.assign_agents_to_target_lsoas()
            self._prev_day = self.current_day

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
