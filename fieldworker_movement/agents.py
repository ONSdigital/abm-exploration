"""
An ABM modelling the movement of field workers around a local authority, 
visiting households.

Aaron Stace, 08/06/2026
"""
import mesa

class FieldWorker(mesa.Agent):
    """
    An agent representing a field worker. They move around the road network, 
    visiting households.
    """
    def __init__(self, model, node):
        super().__init__(model)

        self.node = node
        self.prev_node = None
        model.grid.place_agent(self, node)

    def move(self):
        """
        Move to the nearest household node (by Euclidean distance), always
        leaving the current node regardless of knock/interaction outcome.
        """
        household_nodes = [h.node for h in self.model.households if h.node != self.node]
        if not household_nodes:
            return
        nearest = min(household_nodes, key=lambda n: (n[0] - self.node[0])**2 + (n[1] - self.node[1])**2)
        self.model.grid.move_agent(self, nearest)
        self.node = nearest

    def knock(self, household):
        """
        The field worker knocks on a household's door. Records the knock against
        the household's LSOA and returns True if someone answers.
        """
        self.model.lsoa_stats[household.lsoa]['knocks'] += 1
        # We presumably have some data regarding what proportion of people 
        # answer the door to field staff?
        # If not in, put in a postcard. Does this prompt a response? Does it 
        # annoy them?
        return self.random.random() < household.response_chance

    def interaction(self, household):
        """
        The field worker interacts with a household member. Records the
        interaction against the household's LSOA.
        """
        self.model.lsoa_stats[household.lsoa]['interactions'] += 1
        # Longer could mean higher P of success
        # Change this length of time to be more realistic if data exists.
        interaction_length = self.random.normalvariate(mu=1/10, sigma=1/60)

        return interaction_length

    def visit_household(self):
        """
        Whole process of a field worker visiting a household: knocking, waiting
        for a response, then interacting if someone opens the door.
        """
        candidates = self.model.node_to_households.get(self.node, [])
        if not candidates:
            return
        household = self.random.choice(candidates)
        answered = self.knock(household)
        if answered:
            self.interaction(household)

    def step(self):

        self.move()
        self.visit_household()


class Household(mesa.Agent):
    """
    Household agents, located in the model at the nearest road/path node to 
    their actual geographical location.
    """
    # Start with one type of household. Maybe have another household class that inherits later on?
    def __init__(self, model, node, lsoa, response_chance=0.5):

        super().__init__(model)

        self.node = node
        self.lsoa = lsoa
        model.grid.place_agent(self, node)

        #self.hh_sentiment = hh_sentiment
        self.response_chance = response_chance
