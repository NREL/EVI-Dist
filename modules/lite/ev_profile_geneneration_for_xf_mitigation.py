import os 
from os.path import normpath, join
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pickle
import warnings
import asyncio
warnings.filterwarnings('ignore')

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 1. Read-in the premise info and extract the transformer details
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Read-in the premise info and extract the transformer details
def get_transformer_details(premise_info_file_path, feeder_name):
    # Read the premise info excel file
    df_customers = pd.read_csv(premise_info_file_path)

    # Select the rows where the 'Feeder' column matches the feeder_name
    df_customers_feeder = df_customers[df_customers['Feeder'] == feeder_name]

    # Grouping by Transformer ID and extracting unique premise numbers for each Transformer ID
    unique_premises_per_transformer = df_customers_feeder.groupby('Transformer ID')['Premise Number'].unique()

    # Grouping by transformer-related columns and aggregating the unique premise numbers
    grouped_transformer_details = df_customers_feeder.groupby(['Transformer ID', 'Bank Size', 'Phase Designation', 'Bank Configuration', 'Output Voltage'])['Premise Number'].unique().reset_index()

    # Converting the premise numbers from list to string for better readability
    grouped_transformer_details['Premise Number'] = grouped_transformer_details['Premise Number'].apply(lambda x: ', '.join(map(str, x)))

    # Calculating the customer numbers based on the length of the premises number list for each row
    grouped_transformer_details['Customer Numbers'] = grouped_transformer_details['Premise Number'].apply(lambda x: len(x.split(', ')))

    return grouped_transformer_details

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 2. Mobility Data (EV charge events and mapping info)
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def get_feeder_charge_events(feeder_name, month_number,EV_adoption_file_path):
    # Read-in the charge events for corresponding feeder

    df_mobility = pd.read_csv(EV_adoption_file_path)
    
    # Filter for specific feeder and month
    CEs_feeder = df_mobility[df_mobility['Feeder'] == feeder_name]
    CEs_feeder_month = CEs_feeder[CEs_feeder['month'] == month_number]

    # Calculate charging time based on energy needs and charging power (unit: minutes)
    def calculate_charging_time(row):
        try:
            return int(row['energy_kwh'] / row['Max AC Power kW'] * 60)
        except (ZeroDivisionError, KeyError, TypeError):
            return None

    # Add charging time column
    CEs_feeder_month['charging_time_uncontrol'] = CEs_feeder_month.apply(calculate_charging_time, axis=1)
    
    return CEs_feeder_month

# EV mapping info: tf with EV integration:
def analyze_transformer_ev_data(CEs_feeder_day):
    # Step 1: Count the number of unique transformers
    unique_transformers_count = CEs_feeder_day['Transformer ID'].nunique()

    # Step 2: For each unique transformer, count the number of unique vehicles
    # Record the unique 'Veh_ID_Num' for each 'Transformer ID'
    unique_vehicles_per_transformer = CEs_feeder_day.groupby('Transformer ID')['Veh_ID_Num'].unique()

    # Convert the series to a DataFrame
    df_unique_vehicles_per_transformer = unique_vehicles_per_transformer.reset_index(name='Unique_Vehicles')

    # Add a new column that counts the number of unique vehicles for each transformer
    df_unique_vehicles_per_transformer['Num_Unique_Vehicles'] = df_unique_vehicles_per_transformer['Unique_Vehicles'].apply(len)

    # Extract unique 'Premise Number' for each 'Veh_ID_Num'
    premise_per_vehicle = CEs_feeder_day.groupby('Veh_ID_Num')['Premise Number'].unique()

    # Define a function to extract the 'Premise Number' for each vehicle in 'Unique_Vehicles'
    def extract_premise_numbers(vehicle_ids):
        return [premise_per_vehicle[veh_id].tolist() for veh_id in vehicle_ids]

    # Add a new column 'Premise_Numbers' to 'df_unique_vehicles_per_transformer' that stores the 'Premise Number' 
    # for each unique vehicle ID associated with a transformer
    df_unique_vehicles_per_transformer['Premise_Numbers'] = df_unique_vehicles_per_transformer['Unique_Vehicles'].apply(extract_premise_numbers)

    # Add a new column that counts the number of unique vehicles for each transformer
    df_unique_vehicles_per_transformer['Num_Premise'] = df_unique_vehicles_per_transformer['Premise_Numbers'].apply(len)

    # Total number of unique vehicles 
    Total_num_unique_vehicles = df_unique_vehicles_per_transformer['Num_Unique_Vehicles'].sum()

    # print("Total number of service transformers is:", unique_transformers_count)
    # print("Total number of unique vehicles for the feeder is:", Total_num_unique_vehicles)    
    return df_unique_vehicles_per_transformer

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 3. Transformer loading profiles
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Load the csv based transformer loading profiles:

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 4. Heuristic-based EV SCM for Transformer Overloading Mitigation (SCM Core Function)
# EV energy tracking version ( EV energy requirment known, stop charging when energy requirement is met)
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class EV:
    def __init__(self, transformer_id, ev_id, premise_id, plug_in_time, duration, start_SOC, energy_need,max_charge_rate=9.6,charging_time_uncontrol=None, event_index=None):
        # Initialize EV attributes
        self.transformer_id = transformer_id
        self.ev_id = ev_id  # Unique identifier for the electric vehicle
        self.event_index = event_index
        self.premise_id = premise_id
        self.plug_in_time = plug_in_time  # Time when the vehicle is plugged in for charging
        self.duration = duration # Total connection time in minutes
        self.allocated_power = 0  # Currently allocated charging power
        self.start_SOC = start_SOC  # State of Charge of the vehicle's battery
        self.energy_need = energy_need  # Total energy demanded by the vehicle in kWh
        self.energy_charged = 0  # Total energy charged at the current timestamp in kWh
        self.max_charge_rate = max_charge_rate  # in kW, set based on EVSE capability
        #self.actual_charging_time = 0  # New attribute to track actual charging time
        self.full_charge_flag = 0
        self.charging_time_uncontrol = charging_time_uncontrol
        
        self.managed_charging_time = None
    
    def is_connected(self, current_time):  
        # Check if the EV is connected at the current timestamp
        # Connect time (dwell period) can be longer than charging time
        return self.plug_in_time <= current_time <= (self.plug_in_time + timedelta(minutes=self.duration))

class ChargingStation:
    def __init__(self):
        self.connected_evs = []

    def add_ev(self, ev):
        self.connected_evs.append(ev)

    def remove_ev(self, ev):
        self.connected_evs.remove(ev)

class ChargingManagementSystem:
    def __init__(self, capacity_series, allocation_method='uncontrol'):
        self.station = ChargingStation()
        self.current_time = None
        self.capacity_series = capacity_series
        self.available_capacity_series = pd.Series(dtype=float, index=capacity_series.index)
        self.ev_power_series = pd.DataFrame(index=capacity_series.index)
        self.ev_energy_series = pd.DataFrame(index=capacity_series.index)
        self.allocation_method = allocation_method
        self.charging_events_evaluation = []  # New attribute to store evaluation results

    def update_time(self, new_time):
        self.current_time = new_time

    def add_ev(self, ev):
        self.station.add_ev(ev)
        
        # Use the row_index as the event_id
        event_id = f"{ev.ev_id}_{ev.event_index}"
        
        # Initialize EV power series with zeros
        if event_id not in self.ev_power_series.columns:
            self.ev_power_series[event_id] = 0
        
        # Initialize EV energy need series
        energy_need_id = f"{event_id} Energy Need"
        if energy_need_id not in self.ev_energy_series.columns:
            self.ev_energy_series[energy_need_id] = 0
        
        mask = (self.ev_energy_series.index >= ev.plug_in_time) & (self.ev_energy_series.index < ev.plug_in_time + timedelta(minutes=ev.duration))
        self.ev_energy_series.loc[mask, energy_need_id] = ev.energy_need
        
        # Initialize EV energy charged series with zeros
        energy_charged_id = f"{event_id} Energy Charged"
        if energy_charged_id not in self.ev_energy_series.columns:
            self.ev_energy_series[energy_charged_id] = 0
        
        #print(f"Added EV event: {event_id}, Plug-in Time: {ev.plug_in_time}, Duration: {ev.duration}, Energy Need: {ev.energy_need}")
    
    
    def get_ev_data(self):
        return self.ev_power_series, self.ev_energy_series
        

    def allocate_power_uncontrol(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        
        for ev in connected_evs:
            ev.allocated_power = ev.max_charge_rate


    def allocate_power_first_come_first_served(self):
        remaining_capacity = self.capacity_series[self.current_time]
        sorted_evs = sorted(self.station.connected_evs, key=lambda ev: ev.plug_in_time)
        
        for ev in sorted_evs:
            if ev.is_connected(self.current_time):
                if remaining_capacity >= 1.44:
                    allocatable_power = max(min(remaining_capacity, ev.max_charge_rate), 1.44)
                    ev.allocated_power = allocatable_power
                    remaining_capacity -= ev.allocated_power
                else:
                    ev.allocated_power = 0  # Not enough capacity to meet minimum requirement

    def allocate_power_fcfs_with_minimum(self, sm_percentage = 50):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        num_connected_evs = len(connected_evs)
        
        if num_connected_evs == 0:
            return
        
        total_capacity = self.capacity_series[self.current_time]
        min_power = 1.44  # Minimum power allocation (kW)
        average_power = sm_percentage / 100 * total_capacity / num_connected_evs
        
        # Sort EVs by plug-in time (FCFS)
        sorted_evs = sorted(connected_evs, key=lambda ev: ev.plug_in_time)
        
        # First pass: Allocate average power if it's at least the minimum power
        remaining_capacity = total_capacity
        if average_power >= min_power:
            for ev in sorted_evs:
                ev.allocated_power = min(average_power, ev.max_charge_rate)
                remaining_capacity -= ev.allocated_power
        else:
            # If average power is less than minimum, allocate no power
            for ev in sorted_evs:
                ev.allocated_power = 0
        
        # Second pass: Distribute remaining capacity
        if remaining_capacity > 0:
            for ev in sorted_evs:
                additional_power = min(remaining_capacity, ev.max_charge_rate - ev.allocated_power)
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

    def allocate_power_equal_sharing(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        if not connected_evs:
            return

        total_capacity = self.capacity_series[self.current_time]
        num_evs = len(connected_evs)
        equal_power = total_capacity / num_evs
        min_power = 1.44  # Minimum power allocation (kW)

        if equal_power >= min_power:
            # Allocate equal power to all EVs
            for ev in connected_evs:
                ev.allocated_power = min(equal_power, ev.max_charge_rate)
        else:
            # Allocate minimum power to as many EVs as possible
            evs_to_charge = int(total_capacity / min_power)
            for i, ev in enumerate(connected_evs):
                if i < evs_to_charge:
                    ev.allocated_power = min(min_power, ev.max_charge_rate)
                else:
                    ev.allocated_power = 0

        # Redistribute any remaining capacity
        remaining_capacity = total_capacity - sum(ev.allocated_power for ev in connected_evs)
        if remaining_capacity > 0:
            charging_evs = [ev for ev in connected_evs if ev.allocated_power > 0]
            additional_power = remaining_capacity / len(charging_evs)
            for ev in charging_evs:
                ev.allocated_power = min(ev.allocated_power + additional_power, ev.max_charge_rate)

            
    def allocate_power_based_on_soc(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        if connected_evs:
            remaining_capacity = self.capacity_series[self.current_time]
            total_inverse_soc = sum(1 - ev.current_soc for ev in connected_evs)
        
            # First round allocation based on SOC
            for ev in connected_evs:
                proportion = (1 - ev.current_soc) / total_inverse_soc
                allocatable_power = min(proportion * remaining_capacity, ev.max_charge_rate)
                ev.allocated_power = max(allocatable_power, 1.44) if allocatable_power >= 1.44 else 0
                remaining_capacity -= ev.allocated_power
  
            # Second round allocation
            evs_under_max_power = [ev for ev in connected_evs if ev.allocated_power < ev.max_charge_rate]
            if evs_under_max_power and remaining_capacity > 0:
                total_inverse_soc_under_max = sum(1 - ev.current_soc for ev in evs_under_max_power)
                for ev in evs_under_max_power:
                    proportion = (1 - ev.current_soc) / total_inverse_soc_under_max
                    additional_power = min(proportion * remaining_capacity, ev.max_charge_rate - ev.allocated_power)
                    ev.allocated_power += additional_power
                    remaining_capacity -= additional_power


    def allocate_power_priority_factors(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        total_priority = sum(ev.priority_factor for ev in connected_evs)
        remaining_capacity = self.capacity_series[self.current_time]
        for ev in connected_evs:
            allocatable_power = min((ev.priority_factor / total_priority) * remaining_capacity, 9.6)
            ev.allocated_power = allocatable_power

    def evaluate_charging_event(self, ev):
        energy_satisfaction_ratio = ev.energy_charged / ev.energy_need if ev.energy_need > 0 else 1.0
        
        if self.allocation_method != 'uncontrol' and ev.managed_charging_time is not None:
            charging_time_ratio = ev.managed_charging_time / ev.charging_time_uncontrol
        else:
            charging_time_ratio = 1.0  # For uncontrolled charging or if managed_charging_time is not set
        
        return {
            'ev_id': ev.ev_id,
            'event_index': ev.event_index,
            'transformer_id': ev.transformer_id,
            'full_charge_flag': ev.full_charge_flag,
            'energy_satisfaction_ratio': energy_satisfaction_ratio,
            'charging_time_ratio': charging_time_ratio,
            'allocation_method': self.allocation_method
        } 
    
    def simulate(self, start_time, end_time, time_step=timedelta(minutes=1), sm_percentage = 50):
        self.current_time = start_time
        
        while self.current_time <= end_time:
            self.update_time(self.current_time)

            if self.allocation_method == 'uncontrol':
                self.allocate_power_uncontrol()
            if self.allocation_method == 'first_come_first_served':
                self.allocate_power_first_come_first_served()
            if self.allocation_method == 'fcfs_with_minimum':
                self.allocate_power_fcfs_with_minimum(sm_percentage=sm_percentage)    
            elif self.allocation_method == 'equal_sharing':
                self.allocate_power_equal_sharing()
            elif self.allocation_method == 'soc_priority':
                self.allocate_power_based_on_soc()
            elif self.allocation_method == 'priority_factors':
                self.allocate_power_priority_factors()
            
            # if self.allocation_method == 'Uncontrolled':
            #     self.allocate_power_uncontrol()
            # if self.allocation_method == 'FCFS':
            #     self.allocate_power_first_come_first_served()
            # if self.allocation_method == 'FCFC + SM50':
            #     self.allocate_power_fcfs_with_minimum()    
            # elif self.allocation_method == 'Equal Shares':
            #     self.allocate_power_equal_sharing()
            # elif self.allocation_method == 'SOC Priority':
            #     self.allocate_power_based_on_soc()
            # elif self.allocation_method == 'Priority Factors':
            #     self.allocate_power_priority_factors()
        
            for ev in list(self.station.connected_evs):
                # Check if the EV is still connected or if this is its last time step
                if ev.is_connected(self.current_time) or self.current_time + time_step > ev.plug_in_time + timedelta(minutes=ev.duration):
                    ev.energy_charged += ev.allocated_power * (time_step.total_seconds() / 3600)  # energy = power * time (hours)
                    
                    event_id = f"{ev.ev_id}_{ev.event_index}"
                    energy_charged_id = f"{event_id} Energy Charged"

                    self.ev_power_series.at[self.current_time, event_id] = ev.allocated_power if ev.is_connected(self.current_time) else 0
                    self.ev_energy_series.at[self.current_time, energy_charged_id] = ev.energy_charged
                    
                    # Check if the EV is fully charged or if this is its last time step
                    if ev.energy_charged >= ev.energy_need or self.current_time + time_step > ev.plug_in_time + timedelta(minutes=ev.duration):
                        ev.full_charge_flag = 1 if ev.energy_charged >= ev.energy_need else 0
                        ev.managed_charging_time = (self.current_time - ev.plug_in_time).total_seconds() / 60
                        evaluation = self.evaluate_charging_event(ev)
                        self.charging_events_evaluation.append(evaluation)
                        
                        # if ev.full_charge_flag:
                        #     print(f"EV {ev.ev_id}, Charge Event Index: {ev.event_index} fully charged. Time taken: {ev.managed_charging_time:.2f} minutes, allocation method: {self.allocation_method}, Evaluated: {evaluation}")
                        # else:
                        #     print(f"EV {ev.ev_id}, Charge Event Index: {ev.event_index} did not get fully charged. Time taken: {ev.managed_charging_time:.2f} minutes, allocation method: {self.allocation_method}, Evaluated: {evaluation}")
                        
                        self.station.remove_ev(ev)

            self.current_time += time_step

    def get_charging_events_evaluation(self):
        return pd.DataFrame(self.charging_events_evaluation)
 
async def simulate_charging(Sim_start_time, Sim_end_time, method, progress_index, df_unique_vehicles_per_transformer, CEs_feeder_day, tf_capacity_available_KW, progress, progress_queue, sm_percentage=50):
    
    # Creating a capacity time series
    time_index = pd.date_range(start=Sim_start_time, end=Sim_end_time, freq='T')
    all_ev_power_profiles = pd.DataFrame(index=time_index)
    all_ev_energy_profiles = pd.DataFrame(index=time_index)
    all_charging_events_evaluation = []


    num_rows = df_unique_vehicles_per_transformer.shape[0]

    for i, (_, row) in enumerate(df_unique_vehicles_per_transformer.iterrows()):
        progress[0] = 20 + (i+1)/num_rows + progress_index
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)

        transformer_id = row['Transformer ID']
        transformer_id_str = str(transformer_id)
        ev_ids = row['Unique_Vehicles']
        
        #print(f"Processing transformer ID: {transformer_id} with {len(ev_ids)} unique vehicles")
        
        # Check if the transformer_id exists in tf_capacity_available_KW
        if transformer_id_str not in tf_capacity_available_KW.columns:
            #print(f"Warning: Transformer ID {transformer_id} not found in tf_capacity_available_KW. Skipping this transformer.")
            continue

        # Extract the available capacity time series for the corresponding transformer from the tf_capacity_available_KW
        capacity_series_monthly = tf_capacity_available_KW[transformer_id_str].to_frame(name='Capacity')
        #capacity_series_monthly.index = pd.to_datetime(capacity_series_monthly.index.tz_localize(None))
        capacity_series_monthly.index = pd.to_datetime(capacity_series_monthly.index)
        capacity_series_monthly = capacity_series_monthly.tz_localize(None)

        # capacity_series_1min = capacity_series_monthly.loc[Sim_start_time:Sim_end_time].resample('1T').ffill()
        # Ensure the capacity series covers the full simulation period
        full_index = pd.date_range(start=Sim_start_time, end=Sim_end_time, freq='1T')
        capacity_series_1min = capacity_series_monthly.reindex(full_index, method='ffill')

        management_system = ChargingManagementSystem(capacity_series_1min['Capacity'], allocation_method=method)

        for ev_id in ev_ids:
            # Extract charging event details from CEs_feeder_day
            ev_events = CEs_feeder_day[CEs_feeder_day['Veh_ID_Num'] == ev_id]
            
            for event_row_index, event in ev_events.iterrows():
                premise_id = event['Premise Number']
                park_start_time = pd.to_datetime(event['park_start_timestamp']).floor('T').time()
                park_start_timestamp = datetime.combine(Sim_start_time.date(), park_start_time)
                duration = round(event['park_time_seconds'] / 60)  # Total connection time in minutes

                energy_need = event['energy_kwh']
                start_soc = event['start_soc']
                max_charge_rate = event['Max AC Power kW']
                charging_time_uncontrol = event['charging_time_uncontrol']

                # Create EV object with event_row_index
                ev = EV(
                    transformer_id=transformer_id,
                    ev_id=ev_id,
                    premise_id=premise_id,
                    plug_in_time=park_start_timestamp,
                    duration=duration,
                    start_SOC=start_soc,
                    energy_need=energy_need,
                    max_charge_rate=max_charge_rate,
                    event_index=event_row_index,
                    charging_time_uncontrol=charging_time_uncontrol)  # Add this line
                #print(f"EV {ev.ev_id} added to the CMS list, Charge Event Index: {ev.event_index}, Transformer ID: {ev.transformer_id}, Plug-in Time: {ev.plug_in_time}, Duration: {ev.duration}, Start SOC: {ev.start_SOC}, Energy Need: {ev.energy_need}, Max Charge Rate: {ev.max_charge_rate} ")
                
                management_system.add_ev(ev)

        management_system.simulate(Sim_start_time, Sim_end_time, time_step=timedelta(minutes=1), sm_percentage=sm_percentage)  # simulation resolution 1 min
    
        ev_power_profiles, ev_energy_profiles = management_system.get_ev_data()
        charging_events_evaluation = management_system.get_charging_events_evaluation()

        # Append the results for this transformer to the overall results
        all_ev_power_profiles = pd.concat([all_ev_power_profiles, ev_power_profiles], axis=1)
        all_ev_energy_profiles = pd.concat([all_ev_energy_profiles, ev_energy_profiles], axis=1)
        all_charging_events_evaluation.append(charging_events_evaluation)
    
    #all_ev_power_profiles['Total EV Power'] = all_ev_power_profiles.sum(axis=1) 
    all_charging_events_evaluation = pd.concat(all_charging_events_evaluation, ignore_index=True)
    return all_ev_power_profiles, all_ev_energy_profiles, all_charging_events_evaluation

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 5.Weekly simulation version for EVI-Dist Lite Version
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
async def simulate_week(start_date, CEs_feeder, tf_capacity_available_KW_fillin_positive, SCMs, progress, progress_queue, sm_percentage=50):
    weekly_results = {}
    for day in range(8):  # Changed to 8 days
        current_date = start_date + timedelta(days=day)
        #print(f"Current date : f{current_date}")
        next_date = current_date + timedelta(days=1)
        #print(f"Next date : f{next_date}")
        
        #print(f"Processing day {day} of the simulation, current date: {current_date}")
        # Calculate the day of the week (1-7, where 1 is Monday and 7 is Sunday)
        dow = current_date.isoweekday()
        
        # Extract charging events for the current day
        CEs_feeder_day = CEs_feeder[CEs_feeder['dow'] == dow]
        #print(f'Charging events for the {current_date} are extracted, daily transfomer-EV mapping info:')
        df_unique_vehicles_per_transformer = analyze_transformer_ev_data(CEs_feeder_day)

        # Set simulation start and end times (48-hour period)
        Sim_start_time = datetime.combine(current_date, datetime.min.time())
        Sim_end_time = datetime.combine(next_date, datetime.max.time())

        #print(f"Sim start time: f{Sim_start_time}")
        #print(f"Sim end time: f{Sim_end_time}")
        
        # Run simulation for each SCM
        
        day_results = {}
        num_of_selected_controllers = len(SCMs)
        for ii, scm in enumerate(SCMs):
            print(f"Simulating with controller={scm} for day={day+1} ...\n")
            progress_index = day * 5 + 4 * (ii+1) / num_of_selected_controllers
            ev_power_profiles, ev_energy_profiles, charging_events_evaluation = await simulate_charging(
                Sim_start_time, Sim_end_time, scm, progress_index, df_unique_vehicles_per_transformer, 
                CEs_feeder_day, tf_capacity_available_KW_fillin_positive,
                progress, progress_queue, sm_percentage=sm_percentage
            )
            day_results[scm] = {
                'power_profiles': ev_power_profiles,
                'energy_profiles': ev_energy_profiles,
                'charging_events_evaluation': charging_events_evaluation
            }
        
        weekly_results[day] = day_results

    print(f"Aggregating simulation results to obtain weekly profiles ...\n")
    # Merge and aggregate results
    aggregated_results = await aggregate_weekly_results(weekly_results, start_date, SCMs, progress, progress_queue)
    
    return aggregated_results

async def aggregate_weekly_results(weekly_results, start_date, SCMs, progress, progress_queue):
    aggregated_results = {scm: {'power_profiles': pd.DataFrame(), 
                                'energy_profiles': pd.DataFrame(), 
                                'charging_events_evaluation': pd.DataFrame()} 
                          for scm in SCMs}
    
    progress_ = progress[0]
    for day in range(1, 8):  # Start from day 1 (second day of simulation) to day 7
        progress[0] = progress_ + (day-1)/7 * 20
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        current_date = start_date + timedelta(days=day)
        next_date = current_date + timedelta(days=1)
        
        for scm in SCMs:
            # Extract power and energy profiles for the previous and current day
            prev_day_power = weekly_results[day - 1][scm]['power_profiles']
            curr_day_power = weekly_results[day][scm]['power_profiles']
            
            prev_day_energy = weekly_results[day - 1][scm]['energy_profiles']
            curr_day_energy = weekly_results[day][scm]['energy_profiles']
            
            # Ensure the index is datetime
            prev_day_power.index = pd.to_datetime(prev_day_power.index)
            curr_day_power.index = pd.to_datetime(curr_day_power.index)
            prev_day_energy.index = pd.to_datetime(prev_day_energy.index)
            curr_day_energy.index = pd.to_datetime(curr_day_energy.index)

            # Combine the second day of previous day's profiles with first day of current day's profiles
            day_power = pd.concat([
                prev_day_power.loc[current_date:next_date - timedelta(minutes=1)],
                curr_day_power.loc[current_date:next_date - timedelta(minutes=1)]
            ], axis=1)

            day_energy = pd.concat([
                prev_day_energy.loc[current_date:next_date - timedelta(minutes=1)],
                curr_day_energy.loc[current_date:next_date - timedelta(minutes=1)]
            ], axis=1)

            # Merge with existing aggregated results
            aggregated_results[scm]['power_profiles'] = pd.concat([
                aggregated_results[scm]['power_profiles'],
                day_power
            ], axis=1)
            
            aggregated_results[scm]['energy_profiles'] = pd.concat([
                aggregated_results[scm]['energy_profiles'],
                day_energy
            ], axis=1)
            
            # Aggregate charging events evaluation
            day_evaluation = weekly_results[day][scm]['charging_events_evaluation']
            aggregated_results[scm]['charging_events_evaluation'] = pd.concat([
                aggregated_results[scm]['charging_events_evaluation'],
                day_evaluation
            ])

    # Merge identical columns (charging events spanning multiple days)
    for scm in SCMs:
        aggregated_results[scm]['power_profiles'] = aggregated_results[scm]['power_profiles'].groupby(level=0, axis=1).sum()
        aggregated_results[scm]['energy_profiles'] = aggregated_results[scm]['energy_profiles'].groupby(level=0, axis=1).last()
        # Sort and reset index for all aggregated results
        aggregated_results[scm]['power_profiles'].sort_index(inplace=True)
        aggregated_results[scm]['energy_profiles'].sort_index(inplace=True)
        aggregated_results[scm]['charging_events_evaluation'].reset_index(drop=True, inplace=True)   
    
    return aggregated_results

# #SCM lists:
#     - uncontrol
#     - first_come_first_served
#     - first_come_first_served with minimum
#     - equal_sharing

# Run the weekly simulation
# Save all the results into a single pickle file
# Power and energy profiles for all EVs under differnt SCMs
# Save the results (dict) to local pkl file for future anlaysis
# results_file_path = os.path.join(feeder_directory, 'Weekly_Transformer_overloading_mitigation_SCMs_results.pkl')
# with open(results_file_path, 'wb') as file:
#     pickle.dump(weekly_aggregated_results, file)


def create_day_time_columns(df):
    # Initialize the start time
    start_time = timedelta(days=0, hours=0, minutes=0, seconds=0)
    # Set the end time (7 days)
    end_time = timedelta(days=7)
    # Define the step (1 minute)
    step = timedelta(minutes=1)

    # Generate the list of time entries
    time_entries = []
    day = []
    current_time = start_time
    while current_time < end_time:
        # Format explicitly to include "0 days" for durations less than 1 day
        days = current_time.days
        hours, remainder = divmod(current_time.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{0} days {hours:02}:{minutes:02}:{seconds:02}"
        time_entries.append(formatted_time)
        day.append(days+1)
        current_time += step

    #updated_df = pd.DataFrame(index=df.index)
    df.insert(0, 'time', time_entries)    
    df.insert(0, 'day', day)

    return df


# Define the modified function to create a new DataFrame with aggregated profiles for each vehicle
def aggregate_vehicle_power_profiles(df):
    # Identify columns that start with "Veh" and extract unique vehicle names
    vehicle_columns = [col for col in df.columns if col.startswith("Veh")]
    vehicle_names = set(col.split("_")[1] for col in vehicle_columns)

    # Initialize an empty DataFrame for the aggregated profiles
    aggregated_df = pd.DataFrame(index=df.index)

    # Populate the new DataFrame with total power values for each unique vehicle
    for vehicle in vehicle_names:
        # Find columns associated with the current vehicle
        vehicle_event_columns = [col for col in vehicle_columns if f"Veh_{vehicle}_" in col]
        
        # Sum the power values across the event columns and add to the new DataFrame
        aggregated_df[f"Veh_{vehicle}"] = df[vehicle_event_columns].sum(axis=1)

    # Add a new column called 'Total EV Power' that sums the power for each row in the aggregated DataFrame
    aggregated_df['power'] = aggregated_df.sum(axis=1)
    aggregated_df = aggregated_df.reset_index()
    aggregated_df.drop(columns=['index'])
    column = aggregated_df.pop('power')
    aggregated_df.insert(0, 'power', column)
        
    return aggregated_df
