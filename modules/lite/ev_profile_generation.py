import os
from os.path import normpath, join
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pickle
import random
import math
import json
import itertools
import ast
from datetime import datetime, date, timedelta
import asyncio

import warnings
warnings.filterwarnings('ignore')

def lookup_prices_optimized(start_time, end_time, dow):
    """
    Further optimized function to return price values based on a start time, end time, and day of the week 
    in minute resolution. Adjusted to handle special scenarios where the parking duration crosses midnight 
    from Friday to Saturday or Sunday to Monday.
    
    Parameters:
    - start_time: datetime.time object representing the start time.
    - end_time: datetime.time object representing the end time.
    - dow: Integer representing day of the week (1 to 7).
    
    Returns:
    - List of price values for each minute within the given time range.
    """
    
    # Predefine certain times for comparison
    time_13_00 = datetime.strptime("13:00:00", '%H:%M:%S').time()
    time_15_00 = datetime.strptime("15:00:00", '%H:%M:%S').time()
    time_19_00 = datetime.strptime("19:00:00", '%H:%M:%S').time()
    
    # Convert times to datetime objects for easier manipulation
    start_datetime = datetime.combine(date.today(), start_time)
    end_datetime = datetime.combine(date.today(), end_time)
    
    # If end_time is before start_time, adjust the end_datetime
    if end_time < start_time:
        end_datetime += pd.Timedelta(days=1)
    
    total_minutes = int((end_datetime - start_datetime).total_seconds() / 60)
    current_datetime = start_datetime
    prices = []
    
    for _ in range(total_minutes):
        current_time = current_datetime.time()
        
        # If the parking started on Friday and has crossed to Saturday
        if dow == 5 and current_datetime.date() != start_datetime.date():
            day_type = "weekend"
        # If the parking started on Sunday and has crossed to Monday
        elif dow == 7 and current_datetime.date() != start_datetime.date():
            day_type = "weekday"
        else:
            day_type = "weekend" if dow in [6, 7] else "weekday"
        
        # Weekday pricing
        if day_type == "weekday":
            if time_13_00 <= current_time <= time_15_00:
                prices.append(0.2)
            elif time_15_00 < current_time <= time_19_00:
                prices.append(0.29)
            else:
                prices.append(0.12)
        # Weekend pricing
        else:
            prices.append(0.12)
        
        # Move to the next minute
        current_datetime += pd.Timedelta(minutes=1)
    
    return prices

def periods_based_on_price(period_prices):
  # Check if the input is already a list
    if isinstance(period_prices, list):
        prices_list = period_prices
    else:
        # Convert the string representation of a list to an actual list of floats
        prices_list = eval(period_prices)
    
    min_price = min(prices_list)
    
    # Define periods based on the price value
    periods = []
    for price in prices_list:
        if price == min_price:
            periods.append('low') # summer 0.12
        elif price == (min_price + 0.10):  # Assuming a threshold of 0.10 above the minimum as 'medium'  Sumemr: 0.2
            periods.append('medium')
        else:
            periods.append('high') #summer: 0.29
    
    return periods

def count_lowest_price_periods(period_prices):
    periods = periods_based_on_price(period_prices)
    # Return the count of 'low' periods
    return periods.count('low')

def find_low_price_periods_indices(price_periods):
    # Find the indices of 'low' periods
    low_indices = [i for i, value in enumerate(price_periods) if value == 'low']
    
    # If there are no 'low' periods, return None
    if not low_indices:
        return None
    
    # Extract continuous ranges of indices
    ranges = []
    start = low_indices[0]
    end = low_indices[0]
    for idx in low_indices[1:]:
        if idx == end + 1:  # Check if indices are consecutive
            end = idx
        else:
            ranges.append((start, end))
            start = idx
            end = idx
    ranges.append((start, end))  # Add the last range
    
    return ranges

def generate_timestamps(row):
    start_time = row['park_start_timestamp']
    
    # Convert to datetime object if it's a string
    if isinstance(start_time, str):
        start_time = datetime.strptime(start_time, '%H:%M:%S')
    
    # Convert times to datetime objects for easier manipulation
    start_datetime = datetime.combine(date.today(), start_time)

    indices = row['low_price_period_indices']
    
    # Generate new timestamps based on the indices
    new_timestamps = []
    if indices:
        for start_idx, end_idx in indices:
            new_start_time = start_datetime + timedelta(minutes=start_idx)
            new_end_time = start_datetime + timedelta(minutes=end_idx)
            new_timestamps.append((new_start_time.time(), new_end_time.time()))
    
    return new_timestamps

def calculate_charging_time(row):
    try:
        return int(row['energy_kwh'] / row['rate'] * 60)
    except (ZeroDivisionError, KeyError, TypeError):
        return None
    
def calculate_charge_start_time_TOU_ASAP(row):
    #row = df.iloc[1723]
    total_charging_time = row['total_charging_time']
    low_price_period = row['low_price_period']
    low_price_timestamps = row['low_price_timestamps']
    
    # park_start_timestamp = datetime.strptime(row['park_start_timestamp'], '%H:%M:%S').time() 
    # park_end_timestamp = datetime.strptime(row['park_end_timestamp'], '%H:%M:%S').time() 

    park_start_timestamp = row['park_start_timestamp']
    park_end_timestamp = row['park_end_timestamp'] 
    
    # Check if low_price_timestamps is not empty and has at least one tuple
    if low_price_timestamps and len(low_price_timestamps[0]) == 2:
        start_low_price, end_low_price = low_price_timestamps[0]
        
        # Condition 1: total_charging_time <= low_price_period
        if total_charging_time <= low_price_period:
            return start_low_price
        
        # Condition 2: total_charging_time > low_price_period
        else:
            charging_start_time_ASAP = (datetime.combine(date.today(), end_low_price) - timedelta(minutes=int(total_charging_time))).time()
            charging_start_time_ALAP = (datetime.combine(date.today(), park_end_timestamp) - timedelta(minutes=int(total_charging_time))).time()

            charge_start_time_early = max(charging_start_time_ASAP, park_start_timestamp) #  Charing only plu-in            
            charge_start_time = min(charge_start_time_early, charging_start_time_ALAP) # Make sure fullly charged before plug-out
           
            return charge_start_time       
        
        # # For both conditions, the action is the same
        # return start_low_price
    return None

def calculate_charge_start_time_TOU_ALAP(row):
    total_charging_time = row['total_charging_time']
    low_price_period = row['low_price_period']
    low_price_timestamps = row['low_price_timestamps']
    
    # park_start_timestamp = datetime.strptime(row['park_start_timestamp'], '%H:%M:%S').time() 
    # park_end_timestamp = datetime.strptime(row['park_end_timestamp'], '%H:%M:%S').time() 

    park_start_timestamp = row['park_start_timestamp']
    park_end_timestamp = row['park_end_timestamp'] 

    # Check if low_price_timestamps is not empty and has at least one tuple
    if low_price_timestamps and len(low_price_timestamps[0]) == 2:
        start_low_price, end_low_price = low_price_timestamps[0]
        
        # Condition 1: total_charging_time <= low_price_period
        if total_charging_time <= low_price_period:
        # For both conditions, the action is the same
            return (datetime.combine(datetime.today(), end_low_price) - timedelta(minutes=total_charging_time)).time()
        
        # Condition 2: total_charging_time > low_price_period # explot all low price periods to minimize the cost
        else:
            charging_start_time_ALAP = (datetime.combine(date.today(), park_end_timestamp) - timedelta(minutes=int(total_charging_time))).time()            
            charge_start_time_early = min(start_low_price, charging_start_time_ALAP) # Make sure fullly charged before plug-out            
            charge_start_time = max(charge_start_time_early, park_start_timestamp) #  Charing only plug-in  
            
            return charge_start_time
    
    return None

def calculate_charge_start_time_TOU_random(start_time, end_time):
    """
    Generate a random timestamp between start_time and end_time, considering intraday scenarios.
    This function also handles if start_time and end_time are already datetime.time objects.
    """
    # Convert the start and end times to datetime objects, if they are strings
    if isinstance(start_time, str):
        start = datetime.strptime(start_time, '%H:%M:%S')
    else:
        start = datetime.combine(datetime.today(), start_time)
        
    if isinstance(end_time, str):
        end = datetime.strptime(end_time, '%H:%M:%S')
    else:
        end = datetime.combine(datetime.today(), end_time)
        
    
    if start <= end:
        # Direct scenario
        random_time = start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))
    else:
        # Intraday scenario
        end_of_day = datetime.strptime('23:59:59', '%H:%M:%S')
        start_of_day = datetime.strptime('00:00:00', '%H:%M:%S')
        
        total_seconds_first_day = (end_of_day - start).total_seconds() + 1
        total_seconds_second_day = (end - start_of_day).total_seconds()
        
        total_seconds = total_seconds_first_day + total_seconds_second_day
        random_seconds = random.randint(0, int(total_seconds))
        
        if random_seconds <= total_seconds_first_day:
            random_time = start + timedelta(seconds=random_seconds)
        else:
            random_time = start_of_day + timedelta(seconds=(random_seconds - total_seconds_first_day))
    
    # Return the timestamp in the desired format
    return random_time.time().strftime('%H:%M:%S')

async def Weekly_EV_Charging_Profiles_Generation(df_feeder_month, SCM_scenario, progress, progress_queue):
    # Create a list to save the daily EV charging profiles

    df_list = [] 
    
    progress_ = progress[0]
    for idx in range(1,8):
        progress[0] = progress_ + (idx-1)/7 * 60
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        #print(f"Progress: {progress[0]:.2f}%")
        #idx = 1
        if idx == 1:
            day_previous = 7
        else:
            day_previous = idx - 1

        df_tmp_previous = df_feeder_month[df_feeder_month ['dow'] == day_previous]
        df_tmp_current = df_feeder_month[df_feeder_month ['dow'] == idx]


        time_min_term = np.timedelta64(0,'m')
        timedelta_list = [time_min_term + np.timedelta64(i,'m') for i in range(1440)]

        df_charging_power_profile = pd.DataFrame({'day':idx,'time':timedelta_list,'power':[0]*len(timedelta_list)})
    
        df_EV_charging_profiles = pd.DataFrame(columns=df_feeder_month ['Veh_ID_Num'].unique())

        #df_charging_power_profile_combined =  pd.concat([df_charging_power_profile, df_EV_charging_profiles], axis=1)
        df_charging_power_profile = pd.concat([df_charging_power_profile, df_EV_charging_profiles], axis=1)
        
        df_sample_previous = df_tmp_previous.reset_index()  # make sure indexes pair with number of rows
        df_sample_current = df_tmp_current.reset_index()  # make sure indexes pair with number of rows

        # Generate the load profiels for EV charging loads that lasting cross the day: from previous day to the current day

        total_rows = int(df_sample_previous.shape[0]) + int(df_sample_current.shape[0])
        count = 0 
        progress__ = progress[0]
        for index, row in df_sample_previous.iterrows():
            count += 1
            progress_increment = (count/total_rows) * 1/7 * 0.6
            progress[0] = progress__ + progress_increment * 100
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)
            #print(f"Progress: {progress[0]:.2f}%")
            #row = df_sample_previous.iloc[1]
            Veh_ID_Num = row['Veh_ID_Num']

            if SCM_scenario == 'Uncontrolled':
                charge_start_time = row['park_start_timestamp']
            if SCM_scenario == 'TOU ASAP':
                charge_start_time = row['charge_start_time_TOU_ASAP']
            if SCM_scenario == 'TOU ALAP':
                charge_start_time = row['charge_start_time_TOU_ALAP']
            if SCM_scenario == 'TOU Random':
                charge_start_time = row['charge_start_time_TOU_random']

  
            charge_time_minute = int(row['energy_kwh']/row['rate'] * 60)

            charge_end_time = charge_start_time + np.timedelta64(charge_time_minute,'m')          

            # Only for scenario that the charging process pass the midnight to the second day, if the charging finished in the previous day, it's considered as the current day case!
            # Only the charging periods within the seconday day are considered
            if charge_end_time > np.timedelta64(24,'h'): 
                if charge_start_time > np.timedelta64(24,'h'): # 这个if 感觉没什么作用!
                    charge_start_time = charge_start_time - np.timedelta64(24,'h')
                    charge_end_time = charge_end_time - np.timedelta64(24,'h')
                else:
                    charge_start_time = np.timedelta64(0,'h') # Only considering this day, the time start as 0:00:00
                    charge_end_time = charge_end_time - np.timedelta64(24,'h')
                    
                df_charging_power_profile.loc[(df_charging_power_profile.time>=charge_start_time)&\
                                                (df_charging_power_profile.time<charge_end_time),'power'] += row['rate']
                df_charging_power_profile.loc[(df_charging_power_profile.time>=charge_start_time)&\
                                                (df_charging_power_profile.time<charge_end_time), Veh_ID_Num] = row['rate']    
                    
        for index, row in df_sample_current.iterrows():
            
            count += 1
            progress_increment = (count/total_rows) * 1/7 * 0.6
            progress[0] = progress__ + progress_increment * 100
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)
            #print(f"Progress: {progress[0]:.2f}%")
            #row = df_sample_previous.iloc[2]
            Veh_ID_Num = row['Veh_ID_Num']

            if SCM_scenario == 'Uncontrolled':
                charge_start_time = row['park_start_timestamp']
            if SCM_scenario == 'TOU ASAP':
                charge_start_time = row['charge_start_time_TOU_ASAP']
            if SCM_scenario == 'TOU ALAP':
                charge_start_time = row['charge_start_time_TOU_ALAP']
            if SCM_scenario == 'TOU Random':
                charge_start_time = row['charge_start_time_TOU_random']

            charge_time_minute = int(row['energy_kwh']/row['rate'] * 60)
            charge_end_time = charge_start_time + np.timedelta64(charge_time_minute,'m')

            if charge_start_time < np.timedelta64(24,'h'): 
                if charge_end_time > np.timedelta64(24,'h'):
                    charge_end_time = np.timedelta64(24,'h') # only consider the charging periods that are still within the day! 
                    
                df_charging_power_profile.loc[(df_charging_power_profile.time>=charge_start_time)&\
                                                (df_charging_power_profile.time<charge_end_time),'power'] += row['rate']
                df_charging_power_profile.loc[(df_charging_power_profile.time>=charge_start_time)&\
                                                (df_charging_power_profile.time<charge_end_time), Veh_ID_Num] = row['rate']
                    

        df_list.append(df_charging_power_profile) # Save daily power profiles into a csv files

    # Concatenate the DataFrames to form a single DataFrame and save to local CSV file
    combined_weekly_profile_df = pd.concat(df_list, ignore_index=True)
    path = os.getcwd() + '\\data\\temp\\'
    file_name = path + 'ev_profiles_' + SCM_scenario + '.csv'
    #combined_weekly_profile_df.to_csv('C:\\Users\\eucer\\OneDrive - NREL\\Desktop\\NREL Work\\Projects\\EVI-Dist_v1\\EVI-Dist\\data\\temp\\EV_profiles_weekly_' + SCM_scenario + '.csv')
    combined_weekly_profile_df.to_csv(file_name)
    print('EV charging profiles generated and saved to local CSV file successfully!')

    return combined_weekly_profile_df

