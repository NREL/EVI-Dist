from dataclasses import dataclass
import numpy as np

@dataclass
class Signal:
    x : list
    y : list
    name : str
    res : int
    unit : tuple

    def __add__(self, o):
        combined = zip(self.y, o.y)
        sum = [signal[0] + signal[1] for signal in combined]
        z = Signal(self.x, np.array(sum), 'sum', self.res, self.unit)
        return z
