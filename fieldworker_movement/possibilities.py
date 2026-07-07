"""
Possible pieces of code to add to the simulation that are not necessary at the
current time.
"""
# Arrive field staff agent method: simulates the delay between a field worker 
# reaching an address and them actually knocking on the door.
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


# Routing for an agent to find their way back home at the end of the day.
def back_home(self):
    """
    Field staff travel back home (assign some random direction to them, or
    back to some nearby car park/train station from where they finished 
    would be very clever.
    """
    # Field worker should visit a couple of houses that didn't answer the 
    # door to them during the day on their way back. Undecided as to how
    # this should be implemented.


# Allows number of hours worked per field worker to vary. Not necessary for now
# because we are assuming everyone does an average of 25 per week (ish).
class NoOfHours(FieldWorker):
    """
    A subclass of the FieldWorker class that represents a certain number of
    hours per day that this type of field worker will do.
    """
    # Will need more than one of these eventually
    def __init__(self, model, node, hours_per_day):
        super().__init__(model, node)