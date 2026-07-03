"""
An ABM modelling the movement of field workers around a local authority, 
visiting households.

Aaron Stace, 08/06/2026
"""
import numpy as np
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
        Placeholder for movement logic.
        """
        # Field worker should move to the next unoccupied house - check copilot
        # for advice on how to do this. 


    # Maybe not necessary to include this
    def arrive(self):
        """
        Governs the time a field worker spends between getting to an address and 
        actually knocking on the door. Could include checking address, walking
        up to the door, etc.
        """
        # This distribution should have a long tail, and a peak at about 0-20
        # seconds.
        arrival_rng = np.random.Generator
        arrival_time = arrival_rng.lognormal(mean=5, sigma=20)
        # This time is in SECONDS, might have to change later on. 
        return arrival_time

    def knock(self):
        """
        Placeholder for the logic where a field worker knocks on a household's
        door. They may or may not answer.
        """
        # Include some sort of probability of someone in the house answering
        # the door.
        # We presumably have some data regarding what proportion of people 
        # answer the door to field staff?
        # If not in, put in a postcard. Does this prompt a response? Does it 
        # annoy them? 

    def interaction(self):
        """
        Placeholder for the logic where a field worker interacts with a 
        household member.
        """
        # Longer could mean higher P of success

    def visit_household(self):
        """
        Whole process of a field worker visiting a household: knocking, waiting
        for a response, then interacting if someone opens the door.
        """
        self.arrive()
        answered = self.knock()

        if answered:
            self.interaction()

    def back_home(self):
        """
        Field staff travel back home (assign some random direction to them, or
        back to some nearby car park/train station from where they finished 
        would be very clever.
        """
        # Field worker should visit a couple of houses that didn't answer the 
        # door to them during the day on their way back. Undecided as to how
        # this should be implemented.

    def step(self):

        self.move()
        self.visit_household()


class NoOfHours(FieldWorker):
    """
    A subclass of the FieldWorker class that represents a certain number of
    hours per day that this type of field worker will do.
    """
    # Will need more than one of these eventually
    def __init__(self, model, node, hours_per_day):
        super().__init__(model, node)


class Household(mesa.Agent):
    """
    Household agents, located in the model at the nearest road/path node to 
    their actual geographical location.
    """
    # Start with one type of household. Maybe have another household class that inherits later on?
    def __init__(self, model, node, response_chance=0.5):

        super().__init__(model)

        self.node = node
        model.grid.place_agent(self, node)

        #self.hh_sentiment = hh_sentiment
        self.response_chance = response_chance
