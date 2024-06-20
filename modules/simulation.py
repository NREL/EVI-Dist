from abc import ABC, abstractmethod
import sys
import os
parent_directory = os.getcwd()
sys.path.append(parent_directory + "\\modules")
import lite.ev_profile_generation as evpg
import lite.baseload_profile_generation as bpg
import pandas as pd
import asyncio

class Simulation(ABC):

    def __init__(self, input_files, configs) -> None:
        super().__init__()
        """
        self.input_files['premise_report'] --> contains the file path for transformer mapping data for all feeders. Uploaded by user.
        self.input_files['ev_adoption'] --> contains the file path for ev adoption scenario dataset. Uploaded by user.

        self.configs['feeder'] --> contains the name of the selected feeder for simulation
        self.configs['controller'] --> contains the name of selected EV controller(s) ['Uncontrolled', 'TOU ASAP', 'TOU ALAP', 'TOU Random']
        self.configs['adoption'] --> contains the name of the adoption scenario, (it is 'Untitled' by default unless set by user)
        self.configs['load_profile'] --> contains the name of the selection for load profile generation ['AMI Only', 'AMI + Synthetic load']
        self.configs['ami_data_file'] --> contains the file path for AMI data
        self.confgs['month'] --> contains spesific month to run simulation for 
        """
        self.input_files = input_files
        self.configs = configs
        path = os.getcwd() + '\\data\\temp'
        if not os.path.exists(path):
            os.makedirs(path)
        self.output_directory = path

    @abstractmethod
    def _gen_load_profiles(self):
        pass

    @abstractmethod
    def run(self):
        """
        Simulation step time should serve as clock signal and the generated signals should be time-stamped based on this clock signal. 
        """
        pass 

    def _save(self, df : pd.DataFrame, filename):
        """
        Resulting time-stamped baseload and ev load profiles should be saved as .csv files in data/temp/ directory, adhering to the format of the existing files.
        (For Plus version, new files could be generated to store power flow results)
        """
        ###### FIX HERE
        df.to_csv(self.output_directory + '\\meta.csv', index=False)    


# Example simulation class for Lite version
class SimLite(Simulation):

    def __init__(self, input_files, configs) -> None:
        super().__init__(input_files, configs)

    def _gen_load_profiles(self):

        try:
            df_baseload = pd.read_csv(self.configs['ami_data_file'])
            bpg.generate_upsampled_baseload(df_baseload, self.configs['month'])
        except FileNotFoundError:
            print("File not found. Please check the file path and try again.")
        except pd.errors.EmptyDataError:
            print("The file is empty. Please provide a valid CSV file.")
        except pd.errors.ParserError:
            print("The file contains parsing errors. Please check the file format.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")          
        
    async def run(self, progress, progress_queue):
        progress[0] = 0
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print(f"Extracting EV adoption file...")

        file_path = self.input_files['ev_adoption']
        df = pd.read_csv(file_path)
        df_feeder = df[df['Feeder'] == self.configs['feeder']]
        df_feeder_month = df_feeder[df_feeder['month'] == self.configs['month']]

        progress[0] = 1
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n")    
        print(f"Seperating weekdays and weekends...")

        # Creating a new column 'day_type' based on the values in the 'dow' column
        df_feeder_month['day_type'] = df_feeder_month['dow'].apply(lambda x: 'weekend' if x in [6, 7] else 'weekday')

        progress[0] = 3
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)    
        print("Completed!\n")      
        print(f"Calculating EV rated charging rates...")

        # Modifying the values in the 'rate' column
        df_feeder_month['rate'] = df_feeder_month['rate'].replace(19.2, 9.6)

        #Create a new column called 'charging_time_seconds' with values equal to 'energy_kwh' divided by 'rate', then multiplied by 3600.
        # Creating a new column 'charging_time_seconds'
        print("Completed!\n")  
        print(f"Calculating EV charging times...")
        df_feeder_month['charging_time_seconds'] = (df_feeder_month['energy_kwh'] / df['rate']) * 3600

        progress[0] = 4
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Calculating EV charging times...")

        # Parsing the 'park_start_timestamp' and 'park_end_timestamp' columns as datetime objects
        df_feeder_month['park_start_timestamp'] = pd.to_datetime(df_feeder_month['park_start_timestamp'], format='%H:%M:%S').dt.time
        df_feeder_month['park_end_timestamp'] = pd.to_datetime(df_feeder_month['park_end_timestamp'], format='%H:%M:%S').dt.time

        progress[0] = 5
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Calculating park price scheme...")
        # Apply the revised function to the entire dataframe to update the 'park_price_scheme' column
        df_feeder_month['park_price_scheme'] = df_feeder_month.apply(lambda row: evpg.lookup_prices_optimized(row['park_start_timestamp'], 
                                                                                row['park_end_timestamp'], 
                                                                                row['dow']), axis=1)
        progress[0] = 8
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Calculating low price period...")
        df_feeder_month['low_price_period'] = df_feeder_month['park_price_scheme'].apply(evpg.count_lowest_price_periods)

        progress[0] = 11
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Calculating price periods...")
        # Also, create a new column 'price_periods' to store the periods for each price value
        df_feeder_month['price_periods'] = df_feeder_month['park_price_scheme'].apply(evpg.periods_based_on_price)

        progress[0] = 14
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Generating low price indices...")
        # Apply the function to the "price_periods" column to get the start and end indices of low price periods
        df_feeder_month['low_price_period_indices'] = df_feeder_month['price_periods'].apply(evpg.find_low_price_periods_indices)

        progress[0] = 17
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Generating low price timestamps...")
        # Apply the function to generate new timestamps
        df_feeder_month['low_price_timestamps'] = df_feeder_month.apply(evpg.generate_timestamps, axis=1)

        progress[0] = 20
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Generating total charging time...")
        # Apply the function to create the 'total_charging_time' column
        df_feeder_month['total_charging_time'] = df_feeder_month.apply(evpg.calculate_charging_time, axis=1)

        progress[0] = 23
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Calculating charge start times...")
        df_feeder_month['charge_start_time_TOU_ASAP'] = df_feeder_month.apply(evpg.calculate_charge_start_time_TOU_ASAP, axis=1)

        progress[0] = 26
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        #print(f"Progress: {progress[0]:.2f}%")
        # Apply the function to create the 'charge_start_time_ALAP' column
        df_feeder_month['charge_start_time_TOU_ALAP'] = df_feeder_month.apply(evpg.calculate_charge_start_time_TOU_ALAP, axis=1)

        progress[0] = 27
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        #print(f"Progress: {progress[0]:.2f}%")

        # Parsing the 'park_start_timestamp' and 'park_end_timestamp' columns as datetime objects
        df_feeder_month['charge_start_time_TOU_ASAP'] = pd.to_datetime(df_feeder_month['charge_start_time_TOU_ASAP'], format='%H:%M:%S').dt.time
        df_feeder_month['charge_start_time_TOU_ALAP'] = pd.to_datetime(df_feeder_month['charge_start_time_TOU_ALAP'], format='%H:%M:%S').dt.time
        # Apply the function to the DataFrame to generate the random charging start times
        df_feeder_month['charge_start_time_TOU_random'] = df_feeder_month.apply(lambda row: evpg.calculate_charge_start_time_TOU_random(row['charge_start_time_TOU_ASAP'], row['charge_start_time_TOU_ALAP']), axis=1)

        progress[0] = 30
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Saving meta data and generating final simulation variables...")
        self._save(df_feeder_month, 'meta.csv')
        
        df_feeder = pd.read_csv(self.output_directory + '\\meta.csv')
        
        df_feeder_month['park_start_timestamp'] = df_feeder_month['park_start_timestamp'].astype(str)
        df_feeder_month['charge_start_time_TOU_ASAP'] = df_feeder_month['charge_start_time_TOU_ASAP'].astype(str)
        df_feeder_month['charge_start_time_TOU_ALAP'] = df_feeder_month['charge_start_time_TOU_ALAP'].astype(str)
        df_feeder_month['charge_start_time_TOU_random'] = df_feeder_month['charge_start_time_TOU_random'].astype(str)

        df_feeder_month['park_start_timestamp'] =  pd.to_timedelta(df_feeder_month['park_start_timestamp'])
        df_feeder_month['charge_start_time_TOU_ASAP'] =  pd.to_timedelta(df_feeder_month['charge_start_time_TOU_ASAP'])
        df_feeder_month['charge_start_time_TOU_ALAP'] =  pd.to_timedelta(df_feeder_month['charge_start_time_TOU_ALAP'])
        df_feeder_month['charge_start_time_TOU_random'] =  pd.to_timedelta(df_feeder_month['charge_start_time_TOU_random'])

        progress[0] = 40
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print("Completed!\n") 
        print(f"Simulation started...")
        
        #Scenarios = ['Uncontrolled', 'TOU_ASAP', 'TOU_ALAP', 'TOU_random']
        Scenarios = self.configs['controller']

        # print(Scenarios)
        cont_count = 0
        for x in Scenarios:
            cont_count += 1
            print(f"Simulating for scenario ({cont_count}/{len(Scenarios)}): {x}")
            if x == 'Uncontrolled':
                progress[0] = 40
                EV_profiles_weekly_Uncontrolled = await evpg.Weekly_EV_Charging_Profiles_Generation(df_feeder_month, x, progress, progress_queue)
                
            if x == 'TOU ASAP':
                progress[0] = 40
                EV_profiles_weekly_TOU_ASAP = await evpg.Weekly_EV_Charging_Profiles_Generation(df_feeder_month, x, progress, progress_queue)
                
            if x == 'TOU ALAP':
                progress[0] = 40
                EV_profiles_weekly_TOU_ALAP = await evpg.Weekly_EV_Charging_Profiles_Generation(df_feeder_month, x, progress, progress_queue)
                
            if x == 'TOU Random':
                progress[0] = 40
                EV_profiles_weekly_TOU_random = await evpg.Weekly_EV_Charging_Profiles_Generation(df_feeder_month, x, progress, progress_queue)
                
        # THERE IS A PROBLEM WITH AWAIT
        if os.path.isfile(self.configs['ami_data_file']):
            try:
                self._gen_load_profiles()
            except:
                print("Invalid AMI data. Baseload profiles could not be generated.")

        progress[0] = 100
        await progress_queue.put(progress[0]) 
        await asyncio.sleep(0.01)
        print(f"Simulation completed!\n")


# Example simulation class for Lite version
class SimPlus(Simulation):

    def __init__(self, input_files, configs) -> None:
        super().__init__(input_files, configs)

    def _gen_load_profiles(self):
        pass
        
    def run(self):
        self._gen_load_profiles()
        """
        
        Execution
        
        """
        self._save()

    def _save(self):
        pass
        
    






