import pandas as pd
import numpy as np
import math
from datetime import datetime, date, time, timedelta
import panel as pn
import pickle
import os


class DataOperator:
    def __init__(self, paths, configs) -> None:
        
        self.feeder = configs['feeder']
        self.transformer_data = pd.read_csv(paths['premise_report'])
        self.transformer_data = self.transformer_data[self.transformer_data['Feeder'] == self.feeder]
        itenary_data = pd.read_csv(paths['ev_adoption'])

        if os.path.isfile(configs['ami_data_file']):
            try:
                self.base_load = pd.read_csv(paths['baseload_profiles'])
            except:
                self.base_load = pd.DataFrame({'date' : ['1/1/2024  0:00:00 AM']})
        else:
            self.base_load = pd.DataFrame({'date' : ['1/1/2024  0:00:00 AM']})

        self.controller = configs['controller']
        
        #self.ev_load = pd.read_csv(os.getcwd() + "\\data\\temp\\ev_profiles_Uncontrolled.csv")
        #self.ev_load = pd.read_csv(paths['ev_profiles']['Uncontrolled'])
        self.itenary_data_fs = itenary_data[(itenary_data['Feeder'] == self.feeder)]

        self.ev_load = dict()
        for cntrl in self.controller:
            self.ev_load[cntrl] = pd.read_csv(paths['ev_profiles'][cntrl])
        
        with open(paths['mappings'], "rb") as pickle_file:
            self.mappings = pickle.load(pickle_file)

        
    def get_time(self, controller):
        self.ev_load[controller]['time'] = pd.to_timedelta(self.ev_load[controller]['time'])
        start_date = pd.to_datetime(self.base_load['date'].iloc[0])
        self.ev_load[controller]['datetime'] = start_date + pd.to_timedelta(self.ev_load[controller]['day'] - 1, unit='D') + self.ev_load[controller]['time']
        
        #return self.ev_load['time'].tolist()    
        return self.ev_load[controller]['datetime'].tolist()

    def get_base_load_by_xf_id(self, xf_id):
        try:
            return np.array(self.base_load[str(xf_id)].tolist())
        except Exception as e:
            # pn.state.notifications.error('No data available for Transformer ID = ' + str(xf_id), duration=4000)
            return np.zeros((10080,))
    
    def get_feeder_load(self):
        try:
            f = self.base_load.iloc[:,4:].sum(axis=1)
            return np.array(f.tolist())
        except:
            return np.zeros((10080,))
    
    def get_agg_ev_load_by_feeder(self, controller):
        return self.ev_load[controller]['power']

    def get_agg_ev_load_by_feeder_comparison(self):
        power = dict()
        for cntrl in self.controller:
            power[cntrl] = self.ev_load[cntrl]['power']
        return power

    def get_veh_ids_for_xf(self, xf_id):
        itenary_by_f_by_xf = self.itenary_data_fs[self.itenary_data_fs['Transformer ID'] == xf_id]
        evs_under_xf = itenary_by_f_by_xf.drop_duplicates(subset=['Veh_ID_Num'])
        veh_id_list = evs_under_xf['Veh_ID_Num'].tolist()
        return veh_id_list

    def get_ev_load_by_veh_id(self, veh_id, controller):
        try:
            ev_data = self.ev_load[controller][veh_id].tolist()
            ev_data_nans_eliminated = [0 if math.isnan(x) else x for x in ev_data]
            return np.array(ev_data_nans_eliminated)
        
        except Exception as e:
            #print(f"Err: no data found for Vehicle ID = {veh_id}")
            return np.zeros((10080,)) # Could be none if time series is used
        
    def get_agg_ev_load_by_xf_id(self, xf_id, controller):
        veh_id_list = self.get_veh_ids_for_xf(xf_id)
        agg_ev_load = np.zeros((10080,)) # Should not be hard-coded, use time-series
        for ev in veh_id_list:
            agg_ev_load = agg_ev_load + self.get_ev_load_by_veh_id(ev, controller)
            
        return agg_ev_load

    def get_agg_ev_load_by_xf_id_comparison(self, xf_id):
        veh_id_list = self.get_veh_ids_for_xf(xf_id)
        agg_ev_load = dict()
        
        for cntrl in self.controller:
            agg_ev_load[cntrl] = np.zeros((10080,)) 
            for ev in veh_id_list:
                agg_ev_load[cntrl] = agg_ev_load[cntrl] + self.get_ev_load_by_veh_id(ev, cntrl)
            
        return agg_ev_load

   
    def get_table(self):
        
        table_df = self.transformer_data[['Transformer ID', 'Bank Size', 'OH/UG', 'Bank Configuration', 'Output Voltage', 'Longitude_X', 'Latitude_Y']].reset_index(drop=True)
        table_df = table_df.drop_duplicates(subset=['Transformer ID'])
        return table_df.reset_index(drop=True)


def get_stats(data, threshold):
    # We need to double check the calcualtion methods here
    # Either define res a argument to the functon or embed it into the data variable
    
    result = dict()
    result['max'] = np.max(data)
    result['min'] = np.min(data)
    result['avg'] = np.mean(data)

    result['dat'] = 0 # dat: duration above threshold (counts of elements/samples above a threshold * resolution of the sample, res may be required)
    result['lot'] = 0 # lot: likelihood of exceeding threshold (total count of exceeding values / total count of all values)

    res = 60 # in sec

    result['dat'] = np.sum(data > threshold) * res / 3600 # in hour
    result['lot'] = np.sum(data > threshold) / len(data) * 100
    

    info_text = f"""####################################################################\n
                    Max loading : {result['max']} kVA\n
                    Min loading : {result['min']} kVA\n
                    Average loading : {result['min']} kVA\n
                    Duration above {threshold} kVA : {result['dat']} h\n
                    Likelihood of overloading above {threshold} kVA : {result['lot']} %\n
                    ####################################################################"""

    #print(info_text)
    return result

def gen_xf_mappings(file_names, progress_bar : pn.widgets.Progress=None):
    # premise_report_data = pd.read_csv( 'C:/Users/eucer/OneDrive - NREL/Desktop/NREL Work/Projects/EVI-Dist_v1/EVI-Dist/data/10_feeders_premise_report.csv')
    # charge_event_data = pd.read_csv(filename)

    premise_report_data = pd.read_csv(file_names['premise_report'])
    charge_event_data = pd.read_csv(file_names['ev_adoption'])

    feeders = premise_report_data['Feeder'].unique()
    months = charge_event_data['month'].unique()

    xf_data = dict()
    veh_dict = dict()
    prem_dict = dict()
    region_dict = dict()

    num_of_feeders = len(feeders)
    count_of_feeders = 0
    progress = 0

    for feeder in feeders:

        count_of_feeders = count_of_feeders + 1
        progress = count_of_feeders/num_of_feeders * 100

        #print(progress)
        if progress_bar is not None:
            progress_bar.value = int(progress)

        data_under_same_feeder_from_premise_report = premise_report_data[premise_report_data['Feeder'] == feeder]
        data_under_same_feeder_from_charge_event = charge_event_data[charge_event_data['Feeder'] == feeder]
        
        xfs = data_under_same_feeder_from_premise_report['Transformer ID'].unique()
        
        veh_dict[feeder] = data_under_same_feeder_from_charge_event['Veh_ID_Num'].unique()
        prem_dict[feeder] = data_under_same_feeder_from_premise_report['Premise Number'].unique()
        region_dict[feeder] = data_under_same_feeder_from_premise_report['Community'].unique()

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

            # Check if the feeder already exists in xf_data
            # if feeder in xf_data:
            #     xf_data[feeder][xf] = vehs  # Add a new key-value pair to the nested dictionary
            # else:
            #     xf_data[feeder] = {xf: vehs}  # Create a new nested dictionary for the feeder
            if feeder in xf_data:
                xf_data[feeder][xf] = {'vehicles' : vehs, 'premises' : prems}  # Add a new key-value pair to the nested dictionary
            else:
                xf_data[feeder] = {xf: {'vehicles' : vehs, 'premises' : prems}}  # Create a new nested dictionary for the feeder

    variables = {'xf_mappings' : xf_data,
                 'veh_mappings' : veh_dict,
                 'prem_mappings' : prem_dict,
                 'reg_mappings' : region_dict}

    #print(months)                 
    
    return variables, months

def get_feeder_names(mappings):

    return [ feeder for feeder in mappings['xf_mappings']]
        

            




    


