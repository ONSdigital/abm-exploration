"""
Exploring Mesa package as part of ABM discovery. This is an ABM using the 
Boltzmann Wealth Model, from a tutorial on mesa.readthedocs.io. 
"""
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import mesa

# Creating the agent. Mesa automatically assigns agents an integer to act as a
# unique_id.

class MoneyAgent(mesa.Agent):
    """
    An agent with fixed initial wealth.
    """

    def __init__(self, model):
        # Passing parameters to the parent class - ensures base agent set-up 
        # happens before we set any agent behaviour.
        super().__init__(model)

        # Creating an agent's variable and setting its initial value
        self.wealth = 1

    def say_wealth(self):
        """
        Agent does something. In this case, it's saying hello.
        """
        print(f"Hi, I'm an agent, ID {self.unique_id}. My wealth is "
              f"{self.wealth}.")
        
    def exchange_money(self):
        """
        """
        # First, verifying that the agent has any wealth to exchange.
        if self.wealth > 0: 
            other_agent = self.random.choice(self.model.agents)
            if other_agent is not None:
                other_agent.wealth += 1
                self.wealth -= 1


class MoneyModel(mesa.Model):
    """
    A model with some number of agents. Creates a subclass of the model class
    from mesa. 
    """

    def __init__(self, n, seed=None):
        
        super().__init__(seed=seed)
        # Setting a seed means the model will do the same thing every time 
        # you run it.
        self.num_agents = n

        #Creating agents
        MoneyAgent.create_agents(model=self, n=n)

    def step(self):
        """
        Advances the model by one step (a step is the smallest time period
        in the model, also called a tick)
        """
        # Randomly shuffles the list of agents, then iterates through, calling
        # the function passed as the parameter.
        self.agents.shuffle_do("exchange_money")
        #self.agents.do("say_wealth") # Can also just made them do something 
                                      # without shuffling. 


model = MoneyModel(n=12)

for _ in range(30):         # Sim will run for 30 steps. Underscore is 
    model.step()            # convention for a variable that is not used.


# Creating a histogram to see the wealth distribution after 30 steps.
agent_wealth = [agent.wealth for agent in model.agents]

graph = sns.histplot(agent_wealth, discrete=True)
graph.set(
        title="Wealth Distribution", xlabel="Wealth", ylabel="Number of Agents"
)
plt.show()