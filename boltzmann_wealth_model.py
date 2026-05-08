"""
Exploring Mesa package as part of ABM discovery. This is an ABM using the 
Boltzmann Wealth Model, from a tutorial on mesa.readthedocs.io. 
"""
from mesa.time import Schedule
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import mesa

class Citizen(mesa.Agent):
    """
    An agent with fixed initial wealth and potential savings.
    """

    def __init__(self, model):
        # Passing parameters to the parent class - ensures base agent set-up 
        # happens before we set any agent behaviour.
        super().__init__(model)

        self.wealth = 10
        self.savings = 0

        
    def exchange_money(self):
        """
        Agents exchange money between each other. In this function, one agent 
        gives 1 unit of money to another.
        """
        if self.wealth > 0: 
            other_agent = self.random.choice(self.model.agents)
            other_agent.wealth += 1
            self.wealth -= 1

    def earn_interest(self):
        """
        Earns an agent interest on their savings, based on interest rate at
        that point in the simulation.
        """
        interest = int(self.savings * self.model.interest_rate)
        self.savings += interest


class CentralBankModel(mesa.Model):
    """
    An economy where monetary policy changes with events.
    """

    def __init__(self, n_citizens=50):
        
        super().__init__()

        self.interest_rate = 0.05
        self.log = []

        Citizen.create_agents(model=self, n=n_citizens)

        # Initial savings are distributed randomly among agents.
        for agent in self.agents:
            agent.savings = self.random.randint(0,20)

        # Bank reviews interest rate every 10 time units
        self.rate_review = self.schedule_recurring(
            self.review_interest_rate,
            Schedule(interval=10.0, start=10.0),
        )

        # Interest paid to agents every 5 time units
        self.schedule_recurring(
            self.pay_interest,
            Schedule(interval=5.0),
        )

        # One-off economic stimulus at t=25
        self.schedule_event(self.economic_stimulus, at=25.0)


    def review_interest_rate(self):
        """
        Adjusts interest rate based on average wealth of the agents.
        """
        
        average_wealth = self.agents.agg('wealth', np.mean)

        if average_wealth < 8:
            self.interest_rate = min(0.15, self.interest_rate + 0.02)
            action = "raised"

        if average_wealth > 12:
            self.interest_rate = max(0.01, self.interest_rate - 0.02)
            action = "lowered"

        else:
            action = "held"

        self.log.append(
            f"At t={self.time:5.1f} | Rate review: interest {action} to "
            f"{self.interest_rate:.0%} | Average wealth: {average_wealth:.1f}"
        )


    def pay_interest(self):
        """
        Pays interest to all agents
        """
        total_paid = 0

        for agent in self.agents:
            interest = int(agent.savings * self.interest_rate)
            agent.savings += interest
            total_paid += interest

        self.log.append(f"At t={self.time:5.1f} | Total interest paid: "
                        f"{total_paid}")
        

    def economic_stimulus(self):
        """
        One off stimulus in which every agent is awarded 5 units of money from
        the bank.
        """
        for agent in self.agents:
            agent.wealth += 5
        self.log.append(f"At t={self.time:5.1f} | STIMULUS: All agents receive"
                        f" 5 units of money")


    def step(self):
        """
        Regular step in the model (agents exchange money).
        """
        self.agents.shuffle_do("exchange_money")

        # Agents who have enough money save a bit of their wealth
        for agent in self.agents.select(lambda x: x.wealth > 3):
            amount_saved = agent.wealth // 4
            agent.savings += amount_saved
            agent.wealth -= amount_saved


model = CentralBankModel(n_citizens=50)
model.run_until(50)

print(" === Central Bank Model Log === \n")
for entry in model.log:
    print(f"    {entry}")

print(f"\n=== Final State (t={model.time:.0f}), step={model.steps} ===")
print(f"Interest rate: {model.interest_rate:.0%}")
print(f"Average wealth: {model.agents.agg('wealth', np.mean):.1f}")
print(f"Average savings: {model.agents.agg('savings', np.mean):.1f}")
total = sum(a.wealth + a.savings for a in model.agents)
print(f"Total money in the economy: {total}")
