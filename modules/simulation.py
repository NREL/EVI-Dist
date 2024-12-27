from abc import ABC, abstractmethod
import sys
import os
import numpy as np
from datetime import datetime, timedelta
from pathinit import EVIDIST_ROOT_PATH
#parent_directory = os.getcwd()
parent_directory = EVIDIST_ROOT_PATH
sys.path.append(parent_directory + "/modules")
import lite.ev_profile_generation as evpg
import lite.baseload_profile_generation as bpg
import lite.ev_profile_geneneration_for_xf_mitigation as evpg_tfm
import pandas as pd
import asyncio
import pickle
from dashboard.actions import convert_xfmappings_to_csv

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
        path = os.getcwd() + '/data/temp'
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
        df.to_csv(self.output_directory + '/meta.csv', index=False)    


# Example simulation class for Lite version
class SimLite(Simulation):

    def __init__(self, input_files, configs) -> None:
        super().__init__(input_files, configs)
        price_based_controllers = ['Uncontrolled', 'TOU ASAP', 'TOU ALAP' , 'TOU Random']
        xf_mitigation_controllers = ['FCFS' , 'FCFS + SM' , 'Equal Shares']
        self.xf_mit_control_mapping = {'first_come_first_served' : 'FCFS', 'fcfs_with_minimum' : 'FCFS + SM', 'equal_sharing' : 'Equal Shares'}
        self.is_any_price_based_cont_selected = any(key in self.configs['controller'] for key in ['Uncontrolled', 'TOU ASAP', 'TOU ALAP' , 'TOU Random'])
        self.is_any_xf_ol_mi_cont_selected = any(key in self.configs['controller'] for key in xf_mitigation_controllers)
        self.price_based_selected_controllers = [key for key in price_based_controllers if key in self.configs['controller']]
        self.xf_ol_mi_selected_controllers = [key for key in xf_mitigation_controllers if key in self.configs['controller']]
        if self.is_any_xf_ol_mi_cont_selected:
            self.df_baseload_P = pd.read_csv(self.configs['ami_data_file_P'])
            self.df_baseload_Q = pd.read_csv(self.configs['ami_data_file_Q'])
        with open(os.getcwd() + "/data/mappings/mappings.pkl", "rb") as pickle_file:
            self.mappings = pickle.load(pickle_file)

    def _gen_load_profiles(self):
        try:
            df_baseload = pd.read_csv(self.configs['ami_data_file'])
            #if ('FCFS' in self.configs['controller']) or ('FCFS + SM50' in self.configs['controller']) or ('Equal Shares' in self.configs['controller']):
            # if self.is_any_xf_ol_mi_cont_selected:
            #     bpg.generate_upsampled_baseload(self.df_baseload_P, self.configs['month'], "baseload_profiles_P")
            #     bpg.generate_upsampled_baseload(self.df_baseload_Q, self.configs['month'], "baseload_profiles_Q")
            bpg.generate_upsampled_baseload(df_baseload, self.configs['month'], "baseload_profiles", self.configs['timezone'])
        except FileNotFoundError:
            print("File not found. Please check the file path and try again.")
        except pd.errors.EmptyDataError:
            print("The file is empty. Please provide a valid CSV file.")
        except pd.errors.ParserError:
            print("The file contains parsing errors. Please check the file format.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")          
        
    async def run(self, progress, progress_queue):

        if self.is_any_price_based_cont_selected:
            
            progress[0] = 0
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)
            print(f"Extracting EV adoption file...")

            #file_path = self.input_files['ev_adoption']
            df = pd.read_csv(self.input_files['ev_adoption'])
            df_feeder = df[df['Feeder'] == self.configs['feeder']]
            df_feeder_month = df_feeder[df_feeder['month'] == self.configs['month']]
            df_feeder_month['max_charge_rate'] = df_feeder_month.apply(lambda row: min(row['rate'], row['Max AC Power kW']), axis=1)

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
            
            df_feeder = pd.read_csv(self.output_directory + '/meta.csv')
            
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
            #Scenarios = self.configs['controller']
            Scenarios = self.price_based_selected_controllers

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
                    
        if self.is_any_xf_ol_mi_cont_selected:
            progress[0] = 0
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            print("\nFCFS-based controls are being run. These controller simulations might take some time to complete..!\n")
            print(f"Selected controllers: {self.xf_ol_mi_selected_controllers}")

            feeder_name = self.configs['feeder']
            month_number = self.configs['month']

            premise_info_file_path = self.input_files['premise_report']
            EV_adoption_file_path = self.input_files['ev_adoption']

            #SCMs = ['uncontrol', 'first_come_first_served', 'fcfs_with_minimum', 'equal_sharing']
            #SCMs = ['first_come_first_served']

            SCMs = self.xf_ol_mi_selected_controllers.copy()
            for index, scm in enumerate(SCMs):
                if scm == 'FCFS':
                    SCMs[index] = 'first_come_first_served'
                elif scm == 'FCFS + SM':
                    SCMs[index] = 'fcfs_with_minimum'
                elif scm == 'Equal Shares':
                    SCMs[index] = 'equal_sharing'

            print(f"Controllers: {SCMs}\n")
            
            # Set the start date for the week
            #year = datetime.strptime(self.df_baseload_P['time'].iloc[0], "%m/%d/%Y %H:%M").year 
            year = pd.to_datetime(self.df_baseload_P['time'].iloc[0]).year
            first_day = datetime(year=year, month=self.configs['month'], day=1)
            start_date = first_day + timedelta(days=(7 - first_day.weekday()) % 7) - timedelta(days=1)
            if start_date.month < self.configs['month']:
                start_date += timedelta(weeks=1)

            grouped_transformer_details = evpg_tfm.get_transformer_details(premise_info_file_path, feeder_name)
            print('Step 1: Premise info and transformer details are extracted.\n')

            progress[0] = 2
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            CEs_feeder_month = evpg_tfm.get_feeder_charge_events(feeder_name, month_number, EV_adoption_file_path)
            # # Call the function and display the result for a whole week

            progress[0] = 5
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            df_unique_vehicles_per_transformer = evpg_tfm.analyze_transformer_ev_data(CEs_feeder_month)
            progress[0] = 8
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            print('Step 2: EV mapping info are extracted.\n')

            
            self.df_baseload_P['time'] = pd.to_datetime(self.df_baseload_P['time']).dt.tz_localize('UTC').dt.tz_convert(self.configs['timezone'])
            self.df_baseload_Q['time'] = pd.to_datetime(self.df_baseload_Q['time']).dt.tz_localize('UTC').dt.tz_convert(self.configs['timezone'])

            self.df_baseload_P = self.df_baseload_P.set_index('time')
            self.df_baseload_Q = self.df_baseload_Q.set_index('time')

            # drop non-numeric columns

            columns_to_drop = ['Month', 'Hour', 'Day_of_the_Week', 'Is_Holiday', 'total_power', 'Timestamp']
            for col in columns_to_drop:
                if col in self.df_baseload_P.columns:
                    self.df_baseload_P = self.df_baseload_P.drop(columns=col)
                if col in self.df_baseload_Q.columns:
                    self.df_baseload_Q = self.df_baseload_Q.drop(columns=col)
                
            tf_loading_KW_numeric = self.df_baseload_P #tf_loading_KW.copy().drop(columns=columns_to_drop)
            tf_loading_KVAR_numeric = self.df_baseload_Q #tf_loading_KVAR.copy().drop(columns=columns_to_drop)

            tf_loading_KVA = np.sqrt(np.square(tf_loading_KW_numeric) + np.square(tf_loading_KVAR_numeric))

            ## Calculate the avaible capacity (KW) for EV charging
            # Step 1: Create a dictionary mapping transformer SIDs to their Bank Sizes
            tf_capacity_dict = dict(zip(grouped_transformer_details['Transformer ID'], grouped_transformer_details['Bank Size']))

            # # Step 2: Filter columns in tf_loading_KVA_month to include only numerical transformer IDs
            # # Identify columns with numerical names
            numerical_columns = [col for col in tf_loading_KVA.columns if str(col).isdigit()]
            tf_loading_KVA_month_numeric = tf_loading_KVA[numerical_columns]

            # # Step 3: Initialize a new dataframe with the same index as tf_loading_KVA_month_numeric
            tf_capacity_available = pd.DataFrame(index=tf_loading_KVA_month_numeric.index)

            progress[0] = 12
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            # Step 4: Iterate through the numeric columns in tf_loading_KVA_month_numeric
            for column in tf_loading_KVA_month_numeric.columns:
                #print(column)
                
                if int(column) in tf_capacity_dict:
                    # Get the nameplate capacity for this transformer
                    # print(tf_loading_KVA_month_numeric[column])
                    capacity = tf_capacity_dict[int(column)]
                    if capacity == 'Unknown':
                        continue
                    # print(capacity)

                    # print(tf_loading_KVA_month_numeric[column].dtype)
                    # print(tf_loading_KVA_month_numeric[column].isnull().sum())  # Check for any NaN values
                    # print(type(capacity))
                    
                    # Calculate the available capacity
                    available_capacity = int(float(capacity)) - tf_loading_KVA_month_numeric[column]
                    
                    # Add this series to the new dataframe with integer column name
                    tf_capacity_available[column] = available_capacity

            progress[0] = 16
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            # Step 5: Calculate the avaible capacity (KW) for EV charging
            # Get the column names from tf_capacity_available
            available_columns = tf_capacity_available.columns

            # Filter tf_loading_KVAR and tf_loading_KW to include only the matching columns
            tf_loading_KVAR_filtered = self.df_baseload_Q[available_columns]
            tf_loading_KW_filtered = self.df_baseload_P[available_columns]

            # Calculate tf_capacity_available_KW using the filtered dataframes
            tf_capacity_available_KW = np.sqrt(np.square(tf_capacity_available) - np.square(tf_loading_KVAR_filtered)) - tf_loading_KW_filtered

            # Step 6:Data processing for fill in the missing data
            # After creating tf_capacity_available_KW, add this line:
            tf_capacity_available_KW_fillin = tf_capacity_available_KW.interpolate()

            # Replace any value in tf_capacity_available_KW_fillin that is less than 0 with 0.
            # After creating tf_capacity_available_KW_fillin, add this line:
            tf_capacity_available_KW_fillin_positive = tf_capacity_available_KW_fillin.clip(lower=0)
            print('Step 3: Transformer loading profiles are extracted and the available capacity for EV charging are calculated.\n')

            progress[0] = 20
            await progress_queue.put(progress[0]) 
            #await asyncio.sleep(0.01)

            print("Start simulation...!\n")
            sm_percentage = self.configs['sm_percentage']
            weekly_aggregated_results = await evpg_tfm.simulate_week(start_date, CEs_feeder_month, tf_capacity_available_KW_fillin_positive, SCMs, progress, progress_queue, sm_percentage=sm_percentage)
            print('Step 4: Feeder-level weekly simulation for the service transformer overloading mitigation is completed.\n')

            # Extract results for each SCM
            weekly_results = {}
            for scm in SCMs:
                weekly_results[scm] = {
                    'power_profiles': weekly_aggregated_results[scm]['power_profiles'],
                    'energy_profiles': weekly_aggregated_results[scm]['energy_profiles'],
                    'charging_events_evaluation': weekly_aggregated_results[scm]['charging_events_evaluation']
                }


            # Extract and save the power profiles for each SCM
            ev_profiles = {}
            for scm in SCMs:
                ev_profiles[scm] = weekly_results[scm]['power_profiles']
                #ev_profiles[scm] = epg.aggregate_vehicle_power_profiles(ev_profiles[scm])
                aggraged_df = evpg_tfm.aggregate_vehicle_power_profiles(ev_profiles[scm])
                updated_df = evpg_tfm.create_day_time_columns(aggraged_df)
                ev_profiles[scm] = updated_df.iloc[:-1:1]
                ev_profiles[scm].to_csv(parent_directory + "/data/temp/" + f'ev_profiles_{self.xf_mit_control_mapping[scm]}.csv', index=True)

            progress[0] = 95
            await progress_queue.put(progress[0]) 
            await asyncio.sleep(0.01)

            print('Step 5: EV power profiles are extracted and saved as csv files.\n')

        # THERE IS A PROBLEM WITH AWAIT
        if os.path.isfile(self.configs['ami_data_file']):
            try:
                self._gen_load_profiles()
            except:
                print("Invalid AMI data. Baseload profiles could not be generated.")

        print("Generating mapping file...")
        convert_xfmappings_to_csv(self.mappings, self.configs['feeder'],  parent_directory + r"/data/temp/mapping.csv")

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
        
    






