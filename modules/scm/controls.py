
from datetime import datetime, timedelta
import pandas as pd


# EV energy tracking version ( EV energy requirment known, stop charging when energy requirement is met)
class EV:
    def __init__(self, transformer_id, ev_id, premise_id, plug_in_time, duration, start_SOC, energy_need, energy_capacity,max_charge_rate=9.6, event_index=None):
        # Initialize EV attributes
        self.transformer_id = transformer_id
        self.ev_id = ev_id  # Unique identifier for the electric vehicle
        self.event_index = event_index
        self.premise_id = premise_id
        self.plug_in_time = plug_in_time  # Time when the vehicle is plugged in for charging
        self.duration = duration # Total connection time in minutes
        self.allocated_power = 0  # Currently allocated charging power
        self.start_SOC = start_SOC  # State of Charge of the vehicle's battery
        self.current_soc = start_SOC
        self.energy_need = energy_need  # Total energy demanded by the vehicle in kWh
        self.energy_charged = 0  # Total energy charged at the current timestamp in kWh
        self.energy_capacity = energy_capacity
        self.max_charge_rate = max_charge_rate  # in kW, set based on EVSE capability
        self.actual_charging_time = 0  # New attribute to track actual charging time

    def is_connected(self, current_time):
        # Check if the EV is connected at the current timestamp
        # Connect time (dwell period) can be longer than charging time
        return self.plug_in_time <= current_time < (self.plug_in_time + timedelta(minutes=self.duration))

    def power_limit_from_max_charge(self, time_step_sec):
        return max((self.energy_need - self.energy_charged)*3600/time_step_sec, 0) #kW

class ChargingStation:
    def __init__(self):
        self.connected_evs: list[EV] = []

    def add_ev(self, ev):
        self.connected_evs.append(ev)

    def remove_ev(self, ev: EV):
        # ev.allocated_power = 0
        self.connected_evs.remove(ev)

class ChargingManagementSystem:
    def __init__(self, allocation_method, time_step_sec):
        self.station = ChargingStation()
        self.trns_id = ""
        self.current_time = None
        self.capacity_rated = 0 #setting to zero but it should get overwritten immediately. But it should be easy to catch if it doesn't
        self.previous_time_step_total_load = 0
        self.previous_time_step_ev_load = 0
        self.allocation_method = allocation_method
        self.time_step_sec = time_step_sec #TODO: let this get inherited instead of default setting

    def update_time(self, new_time):
        self.current_time = new_time

    def add_ev(self, ev: EV):
        self.station.add_ev(ev)

    def allocate_power_uncontrol(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]

        for ev in connected_evs:
            ev.allocated_power = ev.max_charge_rate


    def allocate_power_first_come_first_served(self, remaining_capacity):
        sorted_evs = sorted(self.station.connected_evs, key=lambda ev: ev.plug_in_time)

        for ev in sorted_evs:
            if ev.is_connected(self.current_time):
                if remaining_capacity >= 1.44:
                    allocatable_power = min(max(min(remaining_capacity, ev.max_charge_rate), 1.44), ev.power_limit_from_max_charge(self.time_step_sec))
                    ev.allocated_power = allocatable_power
                    remaining_capacity -= ev.allocated_power
                else:
                    ev.allocated_power = 0  # Not enough capacity to meet minimum requirement

    def allocate_power_fcfs_with_minimum(self, remaining_capacity):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        num_connected_evs = len(connected_evs)

        if num_connected_evs == 0:
            return

        total_capacity = remaining_capacity
        min_power = 1.44  # Minimum power allocation (kW)
        average_power = 0.5 * total_capacity / num_connected_evs

        # Sort EVs by plug-in time (FCFS)
        sorted_evs = sorted(connected_evs, key=lambda ev: ev.plug_in_time)

        # First pass: Allocate average power if it's at least the minimum power
        remaining_capacity = total_capacity
        if average_power >= min_power:
            for ev in sorted_evs:
                ev.allocated_power = min(average_power, ev.max_charge_rate, ev.power_limit_from_max_charge(self.time_step_sec))
                remaining_capacity -= ev.allocated_power
        else:
            # If average power is less than minimum, allocate no power
            for ev in sorted_evs:
                ev.allocated_power = 0

        # Second pass: Distribute remaining capacity
        if remaining_capacity > 0:
            for ev in sorted_evs:
                additional_power = min(remaining_capacity, min(ev.max_charge_rate, ev.power_limit_from_max_charge(self.time_step_sec)) - ev.allocated_power)
                ev.allocated_power += additional_power
                remaining_capacity -= additional_power

                if remaining_capacity <= 0:
                    break

        # Final check: If any EV got less than minimum power, set it to 0
        for ev in connected_evs:
            if 0 < ev.allocated_power < min_power:
                ev.allocated_power = 0

    # Calculates the equal power share for all connected EVs.
    # If the equal share is above the minimum power, it allocates this share to all EVs (limited by their max charge rate).
    # If the equal share is below the minimum power, it allocates the minimum power to as many EVs as possible.
    # It then redistributes any remaining capacity among the EVs that received power.
    # This approach maintains the principle of equal sharing while being more computationally efficient. It ensures that:
    # When capacity is sufficient, all EVs receive an equal share.
    # When capacity is insufficient for all EVs to receive the minimum power, it allocates power to as many as possible.
    # Any remaining capacity is distributed equally among charging EVs.

    def allocate_power_equal_sharing(self, remaining_capacity):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        if not connected_evs:
            return

        total_capacity = remaining_capacity
        num_evs = len(connected_evs)
        equal_power = total_capacity / num_evs
        min_power = 1.44  # Minimum power allocation (kW) #TODO: this should maybe be replaced with min(1.44, ev.power_limit_from_max_charge(self.time_step_sec)) to allow the charging power to be below 1.44kW for the timestep that the ev is finishing up. Technically still valid if you consider the allocated power to be the average power for the timestep.

        if equal_power >= min_power:
            # Allocate equal power to all EVs
            for ev in connected_evs:
                ev.allocated_power = min(equal_power, ev.max_charge_rate, ev.power_limit_from_max_charge(self.time_step_sec))
        else:
            # Allocate minimum power to as many EVs as possible
            evs_to_charge = int(total_capacity / min_power)
            for i, ev in enumerate(connected_evs):
                if i < evs_to_charge:
                    ev.allocated_power = min(min_power, ev.max_charge_rate, ev.power_limit_from_max_charge(self.time_step_sec))
                else:
                    ev.allocated_power = 0

        # Redistribute any remaining capacity
        remaining_capacity = total_capacity - sum(ev.allocated_power for ev in connected_evs)
        if remaining_capacity > 0:
            charging_evs = [ev for ev in connected_evs if ev.allocated_power > 0]
            if len(charging_evs) > 0:
                additional_power = remaining_capacity / len(charging_evs)
                for ev in charging_evs:
                    ev.allocated_power = min(ev.allocated_power + additional_power, ev.max_charge_rate, ev.power_limit_from_max_charge(self.time_step_sec))

    def get_ev_allocated_power(self) -> dict[str,float]:
        return {ev.ev_id: ev.allocated_power for ev in self.station.connected_evs if ev.is_connected(self.current_time)}

    def simulate_step(self, time_step: timedelta):
        remaining_capacity = max(min(self.capacity_rated - self.previous_time_step_total_load + self.previous_time_step_ev_load, self.capacity_rated), 0)

        #reset ev loads to zero
        for ev in self.station.connected_evs:
            ev.allocated_power = 0

        # if self.allocation_method == 'UNCONTROL':
        #     self.allocate_power_uncontrol()
        if self.allocation_method == 'FCFS':
            self.allocate_power_first_come_first_served(remaining_capacity)
        elif self.allocation_method == 'FCFS + SM50':
            self.allocate_power_fcfs_with_minimum(remaining_capacity)
        elif self.allocation_method == 'EQUAL SHARES':
            self.allocate_power_equal_sharing(remaining_capacity)

        ev_allocated_powers = self.get_ev_allocated_power()
        self.previous_time_step_ev_load = sum(v for v in ev_allocated_powers.values())

        for ev in list(self.station.connected_evs):
            if ev.is_connected(self.current_time):
                ev.energy_charged += ev.allocated_power * (time_step.total_seconds() / 3600)  # energy = power * time (hours)

                if ev.energy_charged >= ev.energy_need:
                    # print(f"EV {ev.ev_id}, Charge Event Index: {ev.event_index} removed from the CMS list: (Fully charged, Power Allocation method: {self.allocation_method}) ")
                    ev.allocated_power = 0
                    self.station.remove_ev(ev)

        return ev_allocated_powers
