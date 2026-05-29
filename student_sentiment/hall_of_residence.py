"""
This agent-based model attempts to represent the spread of sentiment towards a 
census in a student hall of residence, with varying numbers of student 
ambassadors that have a positive influence on sentiment.
"""
import mesa
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


class Student(mesa.Agent):
    """
    A student, living in a university hall of residence, with an initial 
    sentiment towards the census between 0 and 1. The student can be influenced 
    by other students, and by student ambassadors, to change their sentiment.
    """
    def __init__(self, model):
        super().__init__(model)

        self.sentiment = self.random.uniform(0, 1)

    def interaction(self):
        """
        Student interacts with a random other student, and their sentiment 
        becomes the average sentiment of the two students. If the other student 
        is an ambassador, the sentiment is increased by a fixed amount.
        """
        other_person = self.random.choice(self.model.agents)
        if isinstance(other_person, Ambassador):
            self.sentiment += 0.25
        else:
            self.sentiment = (self.sentiment + other_person.sentiment) / 2



class Ambassador(mesa.Agent):
    """
    A student ambassador in a university hall of residence, with a 
    positive sentiment towards the census. The ambassador can influence other 
    students to increase their sentiment.
    """
    def __init__(self, model):
        super().__init__(model)

        self.sentiment = 0.9


class HallOfResidence(mesa.Model):
    """
    A university hall of residence, with a certain number of students and 
    ambassadors.
    """
    def __init__(self, n_students=100, n_ambassadors=1):
        super().__init__()

        self.students = Student.create_agents(model=self, n=n_students)
        self.ambassadors = Ambassador.create_agents(model=self, 
                                                    n=n_ambassadors)

    def step(self):
        for student in self.students:
            student.interaction()



for _ in range(2):

    model1 = HallOfResidence(n_students=200, n_ambassadors=1)
    model1.run_until(100)
    model2 = HallOfResidence(n_students=200, n_ambassadors=2)
    model2.run_until(100)
    model3 = HallOfResidence(n_students=200, n_ambassadors=3)
    model3.run_until(100)


print('Model variants have finished running.')

print(f'Model 1 average sentiment amongst students: {
    model1.students.agg("sentiment", np.mean)}')
print(f'Model 1 percentage of students with good sentiment (above 0.9) = {
    len(model1.students.select(lambda x: x.sentiment >= 0.9)) / 
    len(model1.students) * 100}%')

print(f'Model 2 average sentiment amongst students: {np.mean([
    student.sentiment for student in model2.students])}')
print(f'Model 2 percentage of students with good sentiment (above 0.9) = {
    len(model2.students.select(lambda x: x.sentiment >= 0.9)) / 
    len(model2.students) * 100}%')

print(f'Model 3 average sentiment amongst students: {np.mean([
    student.sentiment for student in model3.students])}')
print(f'Model 3 percentage of students with good sentiment (above 0.9) = {
    len(model3.students.select(lambda x: x.sentiment >= 0.9)) / 
    len(model3.students) * 100}%')