from dataclasses import dataclass
import numpy as np

@dataclass
class Signal:
    x : np.ndarray # was list
    y : np.ndarray # was list
    name : str
    res : int
    unit : tuple

    def __add__(self, other):
        ## Old code
        # combined = zip(self.y, o.y)
        # sum = [signal[0] + signal[1] for signal in combined]
        # z = Signal(self.x, np.array(sum), 'sum', self.res, self.unit)
        # return z
        if not isinstance(other, Signal):
            raise TypeError("Operand must be an instance of Signal")
        if len(self.y) != len(other.y):
            raise ValueError("Signals must have the same length to be added")
        
        # Use NumPy for element-wise addition
        sum_y = self.y + other.y
        return Signal(self.x, sum_y, 'sum', self.res, self.unit)