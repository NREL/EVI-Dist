import os
import sys
import itertools
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import pandas as pd
import random
import statistics as stats
import numpy as np
import math
from datetime import datetime, date, time, timedelta
import panel as pn
import pickle
import ast
from dashboard.plots import SimpleLinePlot
from modules.data_structures import Signal
from matplotlib.figure import Figure
import asyncio


class DataOperator:
    def __init__(self, paths, configs) -> None:
        self.paths = paths
        self.res = configs['display_res']
        self.sim_len = int(1440 / self.res) * 7
        self.feeder = configs['feeder']
        self.transformer_data = pd.read_csv(self.paths['premise_report'])
        self.transformer_data = self.transformer_data[self.transformer_data['Feeder'] == self.feeder]
        itenary_data = pd.read_csv(self.paths['ev_adoption'])

        try:
            self.base_load = pd.read_csv(self.paths['baseload_profiles_S']) # This has been modified in v1.0.1 since there is now files for P and Q profiles as well
            self.base_load = self.base_load.iloc[:-1:self.res]
        except:
            self.base_load = pd.DataFrame({'date' : ['1/1/2024  0:00:00 AM']})

        self.controller = configs['controller']
        self.itenary_data_fs = itenary_data[(itenary_data['Feeder'] == self.feeder)]

        self.ev_load = dict()
        self.agg_load = dict()
        for cntrl in self.controller:
            self.ev_load[cntrl] = pd.read_csv(self.paths['ev_profiles'][cntrl])
            self.ev_load[cntrl] = self.ev_load[cntrl].iloc[::self.res]
            self.agg_load[cntrl] = pd.read_csv(self.paths['agg_profiles'][cntrl])
            self.agg_load[cntrl] = self.agg_load[cntrl].iloc[::self.res]

        with open(self.paths['mappings'], "rb") as pickle_file:
            self.mappings = pickle.load(pickle_file)


    def get_time(self, controller):
        self.ev_load[controller]['time'] = pd.to_timedelta(self.ev_load[controller]['time'])
        start_date = pd.to_datetime(self.base_load['date'].iloc[0])
        self.ev_load[controller]['datetime'] = start_date + pd.to_timedelta(self.ev_load[controller]['day'] - 1, unit='D') + self.ev_load[controller]['time']

        #return self.ev_load['time'].tolist()
        return self.ev_load[controller]['datetime'].tolist()

    def get_base_load_by_xf_id(self, xf_id):
        try:
            return np.array(self.base_load[str(xf_id)])
        except Exception as e:
            return np.zeros((self.sim_len,))

    def get_feeder_load(self):
        try:
            f = self.base_load.iloc[:,4:].sum(axis=1)
            return np.array(f)
        except:
            return np.zeros((self.sim_len,))

    def get_agg_feeder_load(self):
        # TODO: This result can be pre-calculated and stored in a variable, rather than being called every time when switched to the feeder mode
        agg_load = dict()
        for cntrl in self.controller:
            try:
                f = self.agg_load[cntrl].iloc[:,2:].sum(axis=1)
                agg_load[cntrl] =  np.array(f)
            except:
                agg_load[cntrl] = np.zeros((self.sim_len,))

        return agg_load

    def get_agg_ev_load_by_feeder(self, controller):
        return self.ev_load[controller]['power']

    def get_agg_ev_load_by_feeder_comparison(self):
        power = dict()
        for cntrl in self.controller:
            power[cntrl] = self.ev_load[cntrl]['power']
        return power

    def get_agg_xf_load_by_xf_id(self, xf_id):
        agg_load = dict()
        for cntrl in self.controller:
            agg_load[cntrl] = self.agg_load[cntrl][str(xf_id)]
        return agg_load

    def get_veh_ids_for_xf(self, xf_id):
        itenary_by_f_by_xf = self.itenary_data_fs[self.itenary_data_fs['Transformer ID'] == xf_id]
        evs_under_xf = itenary_by_f_by_xf.drop_duplicates(subset=['Veh_ID_Num'])
        veh_id_list = evs_under_xf['Veh_ID_Num'].tolist()
        return veh_id_list

    def get_each_ev_load_for_xf(self, xf_id, controller):
        veh_list = self.get_veh_ids_for_xf(xf_id)
        ev_load = dict()
        for id in veh_list:
            ev_load[id] = self.get_ev_load_by_veh_id(id, controller)
        return ev_load

    def get_ev_load_by_veh_id(self, veh_id, controller):
        try:
                # Fetch the data directly as a NumPy array
                ev_data = np.array(self.ev_load[controller][veh_id])

                # Replace NaNs with zeros using NumPy's isnan
                ev_data[np.isnan(ev_data)] = 0

                return ev_data

        except KeyError:
            # Specific error handling for missing keys (faster than general Exception)
            return np.zeros((self.sim_len,))

        except Exception as e:
            # Optional: Log other exceptions if necessary
            return np.zeros((self.sim_len,))

    def get_agg_ev_load_by_xf_id(self, xf_id, controller):
        veh_id_list = self.get_veh_ids_for_xf(xf_id)
        agg_ev_load = np.zeros((self.sim_len,))
        for ev in veh_id_list:
            agg_ev_load = agg_ev_load + self.get_ev_load_by_veh_id(ev, controller)

        return agg_ev_load

    def get_agg_ev_load_by_xf_id_comparison(self, xf_id):
        veh_id_list = self.get_veh_ids_for_xf(xf_id)
        agg_ev_load = dict()

        for cntrl in self.controller:
            agg_ev_load[cntrl] = np.zeros((self.sim_len,))
            for ev in veh_id_list:
                agg_ev_load[cntrl] = agg_ev_load[cntrl] + self.get_ev_load_by_veh_id(ev, cntrl)

        return agg_ev_load

    def get_max_combined_load_by_xf_among_controllers(self, xf_id):
        agg_ev_load = self.get_agg_ev_load_by_xf_id_comparison(xf_id)
        base_load = self.get_base_load_by_xf_id(xf_id)
        max_combined_load = 0
        for cntrl in self.controller:
            max_load_by_controller =  max(agg_ev_load[cntrl] + base_load)
            max_combined_load = max(max_combined_load, max_load_by_controller)

        return max_combined_load

    def get_table(self):
        table_df = self.transformer_data[['Transformer ID', 'Bank Size', 'OH/UG', 'Bank Configuration', 'Output Voltage', 'Longitude_X', 'Latitude_Y']].reset_index(drop=True)
        table_df = table_df.drop_duplicates(subset=['Transformer ID'])
        return table_df.reset_index(drop=True)

def get_stats(data, threshold, res=60*15):
    # We need to double check the calcualtion methods here
    # Either define res a argument to the functon or embed it into the data variable

    result = dict()
    result['max'] = np.max(data)
    result['min'] = np.min(data)
    result['avg'] = np.mean(data)

    result['dat'] = 0 # dat: duration above threshold (counts of elements/samples above a threshold * resolution of the sample, res may be required)
    result['lot'] = 0 # lot: likelihood of exceeding threshold (total count of exceeding values / total count of all values)

    result['dat'] = (np.sum(data > threshold) + 1) * res / 3600 # in hour
    result['lot'] = np.sum(data > threshold) / len(data) * 100


    info_text = f"""####################################################################\n
                    Max loading : {result['max']} kVA\n
                    Min loading : {result['min']} kVA\n
                    Average loading : {result['min']} kVA\n
                    Duration above {threshold} kVA : {result['dat']} h\n
                    Likelihood of overloading above {threshold} kVA : {result['lot']} %\n
                    ####################################################################"""

    return result

def gen_xf_mappings(file_names, progress_bar : pn.widgets.Progress=None):
    premise_report_data = pd.read_csv(file_names['premise_report'])
    charge_event_data = pd.read_csv(file_names['ev_adoption'])

    feeders = premise_report_data['Feeder'].unique()
    months = charge_event_data['month'].unique()

    xf_data = dict()
    veh_dict = dict()
    prem_dict = dict()
    prem_dict_ce = dict()
    prem_to_veh_dict = dict()
    region_dict = dict()

    num_of_feeders = len(feeders)
    count_of_feeders = 0
    progress = 0

    for feeder in feeders:

        count_of_feeders = count_of_feeders + 1
        progress = count_of_feeders/num_of_feeders * 100

        if progress_bar is not None:
            progress_bar.value = int(progress)

        data_under_same_feeder_from_premise_report = premise_report_data[premise_report_data['Feeder'] == feeder]
        data_under_same_feeder_from_charge_event = charge_event_data[charge_event_data['Feeder'] == feeder]

        xfs = data_under_same_feeder_from_premise_report['Transformer ID'].unique()

        veh_dict[feeder] = data_under_same_feeder_from_charge_event['Veh_ID_Num'].unique()
        prem_dict[feeder] = data_under_same_feeder_from_premise_report['Premise Number'].unique()
        prem_dict_ce[feeder] = data_under_same_feeder_from_charge_event['Premise Number'].unique()
        region_dict[feeder] = data_under_same_feeder_from_premise_report['Community'].unique()


        prem_to_veh_dict[feeder] = {}

        for prem in prem_dict_ce[feeder]:
            prem_to_veh_dict[feeder][int(prem)] = data_under_same_feeder_from_charge_event[data_under_same_feeder_from_charge_event['Premise Number'] == prem]['Veh_ID_Num'].unique().tolist()

        for xf in xfs:
            """
            This part requires a fix.
            'Transformer ID' column in charge_event_data is integer, however the same column in premise_report is string.
            Following solution applied, but this is ugly. We should make sure that the ID columns are always integers.
            """
            data_under_same_xf_from_charge_event = data_under_same_feeder_from_charge_event[data_under_same_feeder_from_charge_event['Transformer ID'] == int(xf)]
            data_under_same_xf_from_premise_data = data_under_same_feeder_from_premise_report[data_under_same_feeder_from_premise_report['Transformer ID'] == xf]

            vehs = data_under_same_xf_from_charge_event['Veh_ID_Num'].unique()
            prems = data_under_same_xf_from_premise_data['Premise Number'].unique()

            if feeder in xf_data:
                xf_data[feeder][xf] = {'vehicles' : vehs, 'premises' : prems}  # Add a new key-value pair to the nested dictionary
            else:
                xf_data[feeder] = {xf: {'vehicles' : vehs, 'premises' : prems}}  # Create a new nested dictionary for the feeder

    variables = {'xf_mappings' : xf_data,
                 'veh_mappings' : veh_dict,
                 'prem_mappings' : prem_dict,
                 'reg_mappings' : region_dict,
                 'prem_to_veh_mappings' : prem_to_veh_dict}

    return variables, months

def get_feeder_names(mappings):

    return [ feeder for feeder in mappings['xf_mappings']]

def convert_xfmappings_to_csv(mappings, feeder, filename):
    df = pd.DataFrame(columns=['Transformer ID','Unique_Vehicles','Num_Unique_Vehicles','Premise_Numbers','Num_Premise'])
    for xf in mappings['xf_mappings'][feeder]:
        unique_vehicles =  mappings['xf_mappings'][feeder][xf]['vehicles']
        if len(unique_vehicles) == 0:
            continue
        premise_numbers = [[int(prem)] for prem in mappings['xf_mappings'][feeder][xf]['premises']]
        new_row = {
            'Transformer ID': int(xf),
            'Unique_Vehicles': unique_vehicles,
            'Num_Unique_Vehicles': len(unique_vehicles),
            'Premise_Numbers': premise_numbers,
            'Num_Premise': len(premise_numbers)
        }
        # Append the new row to the DataFrame
        df = df.append(new_row, ignore_index=True)

    df.to_csv(filename, index=False)

class DataOperatorPlus:
    def __init__(self, paths, controller_name) -> None:
        # self.table_tabs = ["evloads", "linecurrents", "trnscurrents", "trnskva", "voltages"]
        self.cntrl_name = controller_name
        self.filenames = paths
        self.trns_list: list[Trns] = list()
        self.lines_list: list[Lines] = list()
        self.nodes_list: list[Nodes] = list()
        self.bus_list: list[Bus] = list()
        self.num_trns: int = 0
        self.num_premises: int = 0
        self.num_ev: int = 0
        self.num_charge_events: int = 0
        self.num_charge_events_completed: int = 0

        with open(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["trns_premise_ev_mapping"], 'rb') as file:
            self.trns_premise_ev_mapping: dict[str,dict[str,list[str]]] = pickle.load(file)

    async def load_data(self, progress, progress_queue):
        print("Processing simulation data...")
        self.load_trns_data()
        progress[0] += 10
        await progress_queue.put(progress[0])
        await asyncio.sleep(0.01)
        self.load_lines_data()
        progress[0] += 10
        await progress_queue.put(progress[0])
        await asyncio.sleep(0.01)
        self.load_node_voltages()
        progress[0] += 10
        await progress_queue.put(progress[0])
        await asyncio.sleep(0.01)
        self.load_bus_info()
        progress[0] += 10
        await progress_queue.put(progress[0])
        await asyncio.sleep(0.01)
        print("Simulation data processed.")


    # Example function to safely convert string to list of floats
    def safe_literal_eval(self, x):
        try:
            xnew = ast.literal_eval(x)
        except (ValueError, SyntaxError):
            xnew =  x  # Return the original value if it's not a valid Python literal
        return xnew

    def get_evloads(self):
        return pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["evloads"])

    def get_voltages(self):
        return pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["voltages"])

    def get_trnscurrents(self):
        trnscurrents_dict = dict()
        for trns in self.trns_list:
            trnscurrents_dict[trns.name] = ["{} ∠{}°".format(round(mag,3),round(ph,2)) for mag,ph in zip(trns.i_mag, trns.i_ph)]
        return pd.DataFrame(trnscurrents_dict)

    def get_trnskva(self):
        trnskva_dict = dict()
        for trns in self.trns_list:
            trnskva_dict[trns.name] = ["{} ∠{}°".format(round(mag,3),round(ph,2)) for mag,ph in zip(trns.kva_mag, trns.kva_ph)]
        return pd.DataFrame(trnskva_dict)

    def load_trns_data(self):
        #load transfomer currents
        trnscurrents: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["trnscurrents"])
        trnscurrents.iloc[:, 1:] = trnscurrents.iloc[:, 1:].applymap(self.safe_literal_eval) #don't apply map to timestamp column
        time = trnscurrents["timestamp"].to_list()
        #load transformer kva
        trnskva: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["trnskva"])
        trnskva.iloc[:, 1:]  = trnskva.iloc[:, 1:].applymap(self.safe_literal_eval) #don't apply map to timestamp column

        #load transformer ratings
        trnskva_rating: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["trnskva_ratings"])

        for idx, row in trnskva_rating.iterrows():
            trns = Trns()
            trns.name = str(row["trns"])
            trns.kva_rating = row["kva"]
            trns.phases = int(row["phases"])
            trns.premise_count = 0
            trns.ev_list = list()
            trns.kva_mag = trnskva[trns.name].to_list()
            trns.kva_mag_min = min(trns.kva_mag)
            trns.kva_mag_max = max(trns.kva_mag)
            trns.kva_mag_avg = sum(trns.kva_mag)/len(trns.kva_mag)
            trns.kva_mag_ev_single = dict()
            trns.time = time
            trns.num_charge_events = 0
            trns.num_charge_events_completed = 0
            self.trns_list.append(trns)
            self.num_trns += 1

        #now determine the number of EVs connected to the transformer and save total load
        if os.path.exists(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["evloads"]):
            ev_charge_loads: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["evloads"])
        else:
            ev_charge_loads = pd.DataFrame()
        if os.path.exists(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["ev_charge_stats"]):
            ev_charge_stats: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["ev_charge_stats"])
        else:
            ev_charge_stats = pd.DataFrame()
        time = [float(t) for t in ev_charge_loads["timestamp"]] if ("timestamp" in ev_charge_loads.columns) else [0]
        for trns in self.trns_list:
            trns.time_ev = time
            trns.kva_mag_ev = [0]*len(time)
            if trns.name in self.trns_premise_ev_mapping.keys():
                for premise, ev_list in self.trns_premise_ev_mapping[trns.name].items():
                    trns.premise_count += 1
                    self.num_premises += 1
                    for ev in ev_list:
                        if (not ev in trns.ev_list) and (ev in ev_charge_loads):
                            self.num_ev += 1
                            trns.ev_list.append(ev)
                            trns.kva_mag_ev_single[ev] = ev_charge_loads[ev]
                            trns.kva_mag_ev = [x+y for x,y in zip(trns.kva_mag_ev,ev_charge_loads[ev])]
                            charge_stats = ev_charge_stats[ev_charge_stats["ev_id"] == ev]
                            for _, row in charge_stats.iterrows():
                                if (not row["park_end_after_sim_end"]) or row["target_energy_reached"]:
                                    trns.num_charge_events += 1
                                    self.num_charge_events += 1
                                    if row["target_energy_reached"]:
                                        trns.num_charge_events_completed += 1
                                        self.num_charge_events_completed += 1


    def get_trns_kva_loading(self, kva_percent: float = 100, duration: int = 0, loading_option: str = "Consecutive Overloading Duration"):
        total_count: dict[float,int] = dict()
        kva_percent_count: dict[float,int] = dict()
        trns_df = pd.DataFrame(columns=["Name", "Rating (kVA)"])
        for trns in self.trns_list:
            if trns.kva_rating not in total_count.keys():
                total_count[trns.kva_rating] = 0
            if trns.kva_rating not in kva_percent_count.keys():
                kva_percent_count[trns.kva_rating] = 0

            total_count[trns.kva_rating] += 1

            dt = trns.time[1] - trns.time[0]
            n = math.ceil(duration/dt)
            if duration == 0: #in the background, make the "0 min duration" be equal to one timestep
                duration = dt
                n = 0

            is_overloaded = False
            if loading_option == "Consecutive Overloading Duration":
                #this approach will check whether the kva is consistantly above the threshold for the given consecutive duration
                for i in range(len(trns.kva_mag) - n):
                    window = trns.kva_mag[i:i + n] if n>0 else [trns.kva_mag[i]]
                    if all(p/trns.kva_rating*100 >= kva_percent for p in window):
                        is_overloaded = True
                        break
            else:
                #this approach will count the number of times the kva is above the threshold
                if sum([dt for p in trns.kva_mag if p/trns.kva_rating*100 >= kva_percent]) >= duration:
                    is_overloaded = True

            if is_overloaded:
                kva_percent_count[trns.kva_rating] += 1
                if len(trns_df) > 0:
                    trns_df = pd.concat([trns_df, pd.DataFrame({"Name": [trns.name], "Rating (kVA)": [trns.kva_rating]})], ignore_index=True)
                else:
                    trns_df = pd.DataFrame({"Name": [trns.name], "Rating (kVA)": [trns.kva_rating]})

        df = pd.DataFrame(columns=["Rating (kVA)", "Scenario", "Count (#)", "Order"])
        for k,v in total_count.items():
            df.loc[len(df)] = [k, "Overall Count", v, 1]

        for k,v in kva_percent_count.items():
            df.loc[len(df)] = [k, self.cntrl_name, v, 2] #TODO: change this so the label is the correct controller

        df.sort_values(by=["Order", "Rating (kVA)", "Scenario"], ascending=[True, True, True], inplace=True)
        return df, trns_df

    def get_trns_max_load_summary(self):
        return pd.DataFrame({
            "Name": [trns.name for trns in self.trns_list],
            "Rating (kVA)": [trns.kva_rating for trns in self.trns_list],
            "Max Load (%)": [trns.kva_mag_max/trns.kva_rating*100 for trns in self.trns_list],
        })

    def get_trns_tbl_df(self):
        return pd.DataFrame({
            "Name <br> (ID)": [trns.name for trns in self.trns_list],
            "Rating <br> (kVA)": [int(trns.kva_rating) for trns in self.trns_list],
            "Max Load <br> Power (pu)": [round(trns.kva_mag_max/trns.kva_rating,2) for trns in self.trns_list],
            "Avg Load <br> Power (pu)": [round(trns.kva_mag_avg/trns.kva_rating,2) for trns in self.trns_list],
            "Min Load <br> Power (pu)": [round(trns.kva_mag_min/trns.kva_rating,2) for trns in self.trns_list],
            "Phases <br> (#)": [str(trns.phases) for trns in self.trns_list],
            "Premises <br> (#)": [trns.premise_count for trns in self.trns_list],
            "EVs <br> (#)": [len(trns.ev_list) for trns in self.trns_list],
            "Charge Events <br> Completed (%)": [round(trns.num_charge_events_completed/trns.num_charge_events*100,1) if trns.num_charge_events > 0 else "-" for trns in self.trns_list],
            # "Max Load Current (A)": [trns.i_mag_max for trns in self.trns_list],
        })

    def get_trns_kva_ts(self, trns_name: str):
        trns = next(t for t in self.trns_list if t.name == trns_name)
        df_list = list()
        df_list.append(pd.DataFrame({
            "Time (hour)": [t/3600 for t in trns.time],
            "Power Magnitude (kVA)": trns.kva_mag,
            "Load": "Total",
        }))
        if len(trns.ev_list)>0:
            df_list.append(pd.DataFrame({
                "Time (hour)": [t/3600 for t in trns.time_ev],
                "Power Magnitude (kVA)": [p1-p2 for p1,p2 in zip(trns.kva_mag, trns.kva_mag_ev)],
                "Load": "Base load",
            }))
            df_list.append(pd.DataFrame({
                "Time (hour)": [t/3600 for t in trns.time_ev],
                "Power Magnitude (kVA)": trns.kva_mag_ev,
                "Load": "EV Charging",
            }))
            for ev, power in trns.kva_mag_ev_single.items():
                df_list.append(pd.DataFrame({
                "Time (hour)": [t/3600 for t in trns.time_ev],
                "Power Magnitude (kVA)": power,
                "Load": f"EV {ev}",
                }))
        df = pd.concat(df_list)
        return df


    def load_lines_data(self):
        #load transfomer currents
        linecurrents: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["linecurrents"])
        linecurrents.iloc[:, 1:] = linecurrents.iloc[:, 1:].applymap(self.safe_literal_eval) #don't apply map to timestamp column
        time = linecurrents["timestamp"].to_list()
        #load transformer ratings
        linedata: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["linedata"])

        for idx, row in linedata.iterrows():
            ln = Lines()
            ln.name = row["line"]
            ln.linecode = str(row["linecode"])
            ln.length = row["length_mi"]
            ln.phases = row["phases"]
            ln.i_mags = {}
            for i in range(ln.phases):
                ln.i_mags[ln.name + f".{i+1}"] = linecurrents[ln.name + f".{i+1}"].to_list()
            # ln.i_mag = linecurrents[ln.name].to_list()
            ln.time = time
            ln.i_mag_min = min(min(c) for c in zip(*ln.i_mags.values()))
            ln.i_mag_max = max(max(c) for c in zip(*ln.i_mags.values()))
            ln.i_mag_avg = sum(sum(c)/len(c) for c in zip(*ln.i_mags.values()))/len(time) #if len(ln.i_mags.values()) > 1 else sum(sum(c) for c in ln.i_mags.values())/len(time)
            ln.i_mag_rating = row["rating_A"]
            ln.type = row["type"]
            self.lines_list.append(ln)


    def get_lines_loading(self, loading_percent: float = 100, duration: int = 0, loading_option: str = "Consecutive Overloading Duration"):
        total_count: dict[str,int] = dict()
        loading_percent_count: dict[str,int] = dict()
        line_code_type: dict[str,str] = dict()
        line_df = pd.DataFrame(columns=["Name", "Line Code", "Rating (A)", "Type"])
        for ln in self.lines_list:
            if ln.linecode not in total_count.keys():
                total_count[ln.linecode] = 0
            if ln.linecode not in loading_percent_count.keys():
                loading_percent_count[ln.linecode] = 0
            if ln.linecode not in line_code_type.keys():
                line_code_type[ln.linecode] = ln.type

            total_count[ln.linecode] += ln.length

            dt = ln.time[1] - ln.time[0]
            n = math.ceil(duration/dt)
            if duration == 0: #in the background, make the "0 min duration" be equal to one timestep
                duration = dt
                n = 0
            is_overloaded = False

            i_mag = [min(c) for c in zip(*ln.i_mags.values())]
            if loading_option == "Consecutive Overloading Duration":
                #this approach will check whether the kva is consistantly above the threshold for the given consecutive duration
                for i in range(len(i_mag) - n):
                    window = i_mag[i:i + n]
                    if all(i/ln.i_mag_rating*100 >= loading_percent for i in window):
                        is_overloaded = True
                        break
            else:
                #this approach will count the number of times the kva is above the threshold
                if sum([dt for i in i_mag if i/ln.i_mag_rating*100 >= loading_percent]) >= duration:
                    is_overloaded = True

            if is_overloaded:
                loading_percent_count[ln.linecode] += ln.length
                if len(line_df) > 0:
                    line_df = pd.concat([line_df, pd.DataFrame({"Name": [ln.name], "Line Code": [ln.linecode], "Rating (A)": [ln.i_mag_rating], "Type": [ln.type]})], ignore_index=True)
                else:
                    line_df = pd.DataFrame({"Name": [ln.name], "Line Code": [ln.linecode], "Rating (A)": [ln.i_mag_rating], "Type": [ln.type]})

        df = pd.DataFrame(columns=["Line Code", "Scenario", "Distance (miles)", "Type", "Order"])
        for k,v in total_count.items():
            df.loc[len(df)] = [k, "Overall Distance", v, line_code_type[k], 1]

        for k,v in loading_percent_count.items():
            df.loc[len(df)] = [k, self.cntrl_name, v, line_code_type[k], 2]

        df.sort_values(by=["Order", "Line Code", "Scenario"], ascending=[True, True, True], inplace=True)
        return df, line_df

    def get_lines_max_load_summary(self):
        return pd.DataFrame({
            "Name": [ln.name for ln in self.lines_list],
            "Line Code": [ln.linecode for ln in self.lines_list],
            "Max Load (%)": [ln.i_mag_max/ln.i_mag_rating*100 for ln in self.lines_list],
        })

    def get_lines_tbl_df(self):
        return pd.DataFrame({
            "Name <br> (ID)": [ln.name for ln in self.lines_list],
            "Type <br> (str)": [ln.type for ln in self.lines_list],
            "Line Code <br> (str)": [ln.linecode for ln in self.lines_list],
            "Length <br> (kft)": [ln.length*5280 for ln in self.lines_list],
            "Phases <br> (#)": [str(ln.phases) for ln in self.lines_list],
            "Rating <br> (A)": [ln.i_mag_rating for ln in self.lines_list],
            "Max Load <br> (pu)": [round(ln.i_mag_max/ln.i_mag_rating,2) for ln in self.lines_list],
            "Avg Load <br> (pu)": [round(ln.i_mag_avg/ln.i_mag_rating,2) for ln in self.lines_list],
            "Min Load <br> (pu)": [round(ln.i_mag_min/ln.i_mag_rating,2) for ln in self.lines_list],
        })

    def get_line_i_ts(self, line_name: str):
        ln = next(l for l in self.lines_list if l.name == line_name)
        df_list = list()
        for phase, current in ln.i_mags.items():
            df_list.append(pd.DataFrame({
                "Phase": [phase for t in ln.time],
                "Time (hour)": [t/3600 for t in ln.time],
                "Current Magnitude (A)": current,
            }))
        df = pd.concat(df_list)
        return df


    def load_node_voltages(self):
        df: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["voltages"])
        time = df["timestamp"].to_list()
        for col in df.iloc[:, 1:].columns:
            node = Nodes()
            node.name = col
            node.v_mag = df[col]
            node.time = time
            node.v_mag_max = max(node.v_mag)
            node.v_mag_min = min(node.v_mag)
            node.v_mag_avg = sum(node.v_mag)/len(node.v_mag)
            self.nodes_list.append(node)

    def get_nodes_tbl_df(self):
        return pd.DataFrame({
            "Name": [node.name for node in self.nodes_list],
            "Min |V| (pu)": [node.v_mag_min for node in self.nodes_list],
            "Max |V| (pu)": [node.v_mag_max for node in self.nodes_list],
        })

    def get_node_v_ts(self, node_name: str):
        node = next(n for n in self.nodes_list if n.name == node_name)
        return pd.DataFrame({
            "node": [node.name for n in node.time],
            "Time (hour)": [t/3600 for t in node.time],
            "Voltage Magnitude (V)": node.v_mag,
        })

    def load_bus_info(self):
        df: pd.DataFrame = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + self.filenames["bus_info"])
        df['nodes'] = df['nodes'].apply(self.safe_literal_eval)
        for idx, row in df.iterrows():
            bus = Bus()
            bus.name = row["bus"]
            bus.is_pcc = row['is_pcc']
            for num in row['nodes']:
                node = next(node for node in self.nodes_list if (bus.name + "." + str(num)) == node.name)
                bus.nodes.append(node)
            self.bus_list.append(bus)

    def get_pcc_min_voltage_summary(self, voltage_cutoff: int = 0.95, duration: int = 0, loading_option: str = "Consecutive Under Voltage Duration"):
        bus_df = pd.DataFrame(columns=["PCC Bus", "Min |V| (pu)"])

        for bus in self.bus_list:
            v_mag_min = float('inf')
            # kva_mag = [min(n.v_mag[i] for n in bus.nodes) for i in range(len(bus.nodes[0].v_mag))]
            kva_mag = [min(col) for col in itertools.zip_longest(*[node.v_mag for node in bus.nodes])]

            dt = bus.nodes[0].time[1] - bus.nodes[0].time[0]
            n = math.ceil(duration/dt)
            if duration == 0: #in the background, make the "0 min duration" be equal to one timestep
                duration = dt
                n = 1

            if loading_option == "Consecutive Under Voltage Duration":
                #this approach will check whether the kva is consistantly above the threshold for the given consecutive duration
                for i in range(len(kva_mag) - n + 1):
                        window = kva_mag[i:i + n]
                        if (window[0] < v_mag_min) and all(val <= window[0] for val in window):
                            v_mag_min = window[0]
            else:
                #this approach will count the number of times the kva is above the threshold
                kva_mag.sort()
                v_mag_min = kva_mag[n-1]
                # if sum([dt for p in bus.kva_mag if p/trns.kva_rating*100 >= kva_percent]) >= duration:
                #     is_overloaded = True

            bus_df = pd.concat([bus_df, pd.DataFrame({"PCC Bus": [bus.name], "Min |V| (pu)": [v_mag_min]})])

        return bus_df

    def get_bus_tbl_df(self):
        return pd.DataFrame({
            "Bus <br> (ID)": [bus.name for bus in self.bus_list],
            "Is PCC <br> (Y/N)": ["Y" if bus.is_pcc else "N" for bus in self.bus_list],
            "Phases <br> (#)": [str(len(bus.nodes)) for bus in self.bus_list],
            "Min |V| <br> (pu)": [round(min(n.v_mag_min for n in bus.nodes),2) for bus in self.bus_list],
            "Avg |V| <br> (pu)": [round(sum(n.v_mag_avg for n in bus.nodes)/len(bus.nodes),2) for bus in self.bus_list],
            "Max |V| <br> (pu)": [round(min(n.v_mag_max for n in bus.nodes),2) for bus in self.bus_list],
        })

    def get_bus_v_ts(self, bus_name: str):
        bus = next(bus for bus in self.bus_list if (bus.name == bus_name))
        # df = pd.DataFrame()
        df_list = list()
        for node in bus.nodes:
            df_list.append(self.get_node_v_ts(node.name))
        df = pd.concat(df_list)
        return df

class Trns():
    def __init__(self) -> None:
        self.name: str
        self.kva_rating: float
        self.phases: int
        self.time: list[float]
        self.time_ev: list[float]
        self.premise_count: int
        self.ev_list: list[str]
        self.kva_mag: list[float]
        self.kva_mag_ev: list[float]
        # self.kva_ph: list[float]
        self.kva_mag_min: float
        self.kva_mag_max: float
        self.kva_mag_avg: float
        self.i_mag: list[float]
        # self.i_ph: list[float]
        self.i_mag_max: float
        self.kva_mag_ev_single: dict[str, list[float]]
        self.num_charge_events: int
        self.num_charge_events_completed: int

class Lines():
    def __init__(self) -> None:
        self.name: str
        self.linecode: str
        self.type: str
        self.phases: int
        self.length: float
        self.time: list[float]
        self.i_mags: dict[str,list[float]]
        # self.i_ph: list[float]
        self.i_mag_min: float
        self.i_mag_max: float
        self.i_mag_avg: float
        self.i_mag_rating: float

class Nodes():
    def __init__(self) -> None:
        self.name: str
        self.time: list[float]
        self.v_mag: list[float]
        self.v_mag_min: float
        self.v_mag_max: float
        self.v_mag_avg: float

class Bus():
    def __init__(self) -> None:
        self.name: str
        self.nodes: list[Nodes] = list()
        self.is_pcc: bool = False