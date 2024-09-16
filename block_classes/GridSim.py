import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import pandas as pd
from opendssdirect import dss, enums
import helics as h
import json
import csv
import logging
import os.path

"""
This class holds the OpenDSS simulation interaction
It allows instantiation of the GridSim object, 
initialization of the simulation,
advancement in time,
updating loads,
and outputting feedback to the controller
"""

class GridSim:
    def __init__(self, opendss_path, name='ieee_34', timestep_sec=60*5, cosim=False, helics_config_path='', evse_to_load_point_dict=''):
        self.name = name
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=EVIDIST_ROOT_PATH + f'/logs/sim_plus/{name}.log', encoding='utf-8', level=logging.DEBUG)
        self.timestep_sec = timestep_sec # how large each timestep is in seconds
        # the timestep is dependent on the resolution of the load profiles in the opendss LoadShape.dss files
        self.time = 0 # what timestep the last outputs were for in seconds
        self.loads_updated_time = 0 # what timestep are the updated loads in alignment with
        self.opendss_dir = opendss_path # directory with opendss model
        if evse_to_load_point_dict == '': # have a basic default for ieee_34 system
            self.evse_to_load_point_dict = {'evse0': 'pev1p_810.2','evse1': 'pev1p_890.3','evse2': 'pev1p_822.1'}
        elif isinstance(evse_to_load_point_dict, str): # if it's a string assume it's the premise report
            self.evse_to_load_point_dict = evse_to_load_df(premise_report_file=evse_to_load_point_dict, feeder_name=name, main_dss_file=opendss_path)
        else: # if it's a dictionary assume it's already made for you
            self.evse_to_load_point_dict = evse_to_load_point_dict
        #print(f'GridSim.py line 36 {self.evse_to_load_point_dict}')
        self.ev_loads = {}
        self.bus_names: list[str] = []
        self.trns_names: list[str] = []
        self.line_names: list[str] = []
        # if there is a co-simulation then you need to pass values at each timestep
        # if not, then you need to update the full LoadShape to reflect the full day, simulate the full day, and then pass the full day's data
        self.co_simulation = cosim
        self.helics_config_path = helics_config_path
        self.fed = None
        self.publications = []
        self.subscriptions = []

    def setup_opendss_model(self):
        # this function attaches the loads to the opendss load points and 
        # runs the first timestep to make sure that the model is valid
        # if the module is run in co-simulation, it initializes a helics federate
        dss(f'Redirect "{self.opendss_dir}"')
        dss.Solution.Mode(enums.SolveModes.Daily)
        self.bus_names=dss.Circuit.AllBusNames()
        self.trns_names = dss.Transformers.AllNames()
        self.line_names = dss.Lines.AllNames()
        if self.co_simulation:
            if self.helics_config_path == '':
                fedinfo = h.helicsCreateFederateInfo()
                # h.helicsFederateInfoSetCoreName(fedinfo, self.name)
                h.helicsFederateInfoSetCoreInitString(fedinfo, "--federates=1")
                self.fed = h.helicsCreateValueFederate(self.name, fedinfo)
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'voltages', h.HelicsDataType.STRING))
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'currents', h.HelicsDataType.STRING))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, 'ev_charge_sim/ev_loads', "")) # this is a json string
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, self.timestep_sec)
            h.helicsFederateEnterExecutingMode(self.fed)

        # clear previous outputs
        for output_data in ['evloads', 'voltages', 'linecurrents', 'trnscurrents', 'trnskva']:
            data_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_{output_data}.csv'
            if os.path.isfile(data_file):
                os.remove(data_file)

    def update_ev_loads(self, load_timestamp):
        # this function updates the opendss loads to include the up to date aggregated loads
        # this works for a single timestep and should be used with advance_sim_time if iterating
        # if using helics you will need to get the subscriptions
        ev_loads = json.loads(h.helicsInputGetString(self.subscriptions[0]))
        #print(f'ev_loads: {ev_loads}')
        if not isinstance(ev_loads, float):
            self.ev_loads = ev_loads
        else:
            self.logger.warning(f'recieved float for ev_loads, continuing without updating')

        for evse_name, load_value in self.ev_loads.items():
            # TODO: create better mapping to include missing secondary connections
            try:
                load_name = self.evse_to_load_point_dict[int(evse_name)]
                dss.Loads.Name(load_name)
                base_load = dss.Loads.kvaBase()
                dss.Loads.kW(load_value+base_load)
                self.logger.debug(f'updated {load_name} to {load_value} at timestep {self.time}')
            except:
                self.logger.warning(f'evse_name {evse_name} not in the secondary models, ignoring load in this analysis')

        evse_names = self.ev_loads.keys()
        evload_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_evloads.csv'
        if len(self.ev_loads.keys()) > 0:    
            write_header = False
            if not os.path.isfile(evload_file):
                write_header = True
            with open(evload_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(['timestep'] + list(self.ev_loads.keys()))
                writer.writerow([self.time] + list(self.ev_loads.values()))
        self.loads_updated_time = load_timestamp

    def advance_sim_time(self,updated_time):
        dss.Solution.Solve()
        while self.time < updated_time and self.co_simulation:
            h.helicsFederateRequestTime(self.fed, updated_time)
            self.time = self.time + self.timestep_sec
        self.logger.info(f'ieee34 feeder federate advanced to time: {updated_time}')
        return                

    def output_grid_values(self):
        # returns voltages, line currents, and transformer currents
        voltages = dss.Circuit.AllBusMagPu() # in per unit
        node_names = dss.Circuit.AllNodeNames()
        trns_currents_str = dss.Transformers.strWdgCurrents() #dss.Circuit.CurrentMagAngle() # need to check if this is correct synatx for all currents
        #trns_currents = dss.Transformers.WdgCurrents()
        # to get kva, you need to iterate through transformer powers
        trns_kva = []
        trns_currents = []
        for trns in self.trns_names:
            dss.Circuit.SetActiveElement(trns)
            trns_kva.append(dss.CktElement.Powers())
            trns_currents.append(dss.CktElement.CurrentsMagAng())
        #print(f'trns_kva: {trns_kva}')
        # to get line currents you need to iterate through circuit elements
        line_currents = []
        for line in self.line_names:
            dss.Circuit.SetActiveElement(line)
            line_currents.append(dss.CktElement.CurrentsMagAng())

        if self.co_simulation:
            h.helicsPublicationPublishString(self.publications[0], json.dumps(voltages))
            voltage_output_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_voltages.csv'
            write_header=False
            if not os.path.isfile(voltage_output_file):
                write_header = True
            with open(voltage_output_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(node_names)
                writer.writerow(voltages)
            self.logger.debug(f'bus voltages at t={self.time}: {voltages}')
            
            h.helicsPublicationPublishString(self.publications[1], json.dumps(trns_currents))
            trns_current_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_trnscurrents.csv'
            write_header=False
            if not os.path.isfile(trns_current_file):
                write_header = True
            with open(trns_current_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(self.trns_names)
                writer.writerow(trns_currents) #.split(','))
            self.logger.debug(f'transformer currents at t={self.time}: {trns_currents_str}')

            trnskva_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_trnskva.csv'
            write_header = False
            if not os.path.isfile(trnskva_file):
                write_header=True
            with open(trnskva_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(self.trns_names)
                writer.writerow(trns_kva)
            self.logger.debug(f'transformer kva at t={self.time}: {trns_kva}')

            linecurrent_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_linecurrents.csv'
            write_header = False
            if not os.path.isfile(linecurrent_file):
                write_header=True
            with open(linecurrent_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(self.line_names)
                writer.writerow(line_currents)
            self.logger.debug(f'line currents at t={self.time}: {line_currents}')
        return voltages, trns_currents

    def export_grid_elements(self):
        #Line nanmes, distances
        #node names,
        #transformer names, ratings
        
        #get line lengths
        line_lengths = list()
        line_codes = list()
        for line in self.line_names:
            dss.Lines.Name(line)
            line_lengths.append(dss.Lines.Length())
            line_codes.append(dss.Lines.LineCode())
        
        #save line lengths    
        df_lines = pd.DataFrame({
            "line": self.line_names,
            "linecode": line_codes,
            "length": line_lengths,
        })
        df_lines.to_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_linedata.csv', index=False)
        
        
        #get transformer ratings  
        trns_kva = list()  
        for trns in self.trns_names:
            dss.Transformers.Name(trns)
            trns_kva.append(dss.Transformers.kVA())
        
        #save transformer ratings    
        df_trns = pd.DataFrame({
            "trns": self.trns_names,
            "kva": trns_kva,
        })
        df_trns.to_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_trnskva_ratings.csv', index=False)
        
        
        #get list of PCC busses
        pcc_bus_list = list()
        # pcc_node_dict: dict[str,list] = dict()
        for load in dss.Loads.AllNames():
            dss.Loads.Name(load)
            # print(dss.CktElement.BusNames()[0])
            dss.Circuit.SetActiveBus(dss.CktElement.BusNames()[0])
            if dss.Bus.LineList():
                pcc_bus=dss.Bus.Name()
                # if pcc_bus not in pcc_node_dict.keys():
                #     pcc_node_dict[pcc_bus] = dss.Bus.Nodes()
                pcc_bus_list.append(pcc_bus)
                # print(dss.Bus.Nodes())
                # load_pcc_dict[load]=pcc_bus
                
        bus_node_dict: dict[str,list] = dict()        
        for bus in dss.Circuit.AllBusNames():
            dss.Circuit.SetActiveBus(bus)
            bus_node_dict[dss.Bus.Name()] = dss.Bus.Nodes()
        # print("\n")
        # print(pcc_bus_list)
        
        #get list of all bu
        
        #save PCC bus list
        df_pcc_bus = pd.DataFrame({
            "bus": [k for k in bus_node_dict.keys()],
            "nodes": [v for v in bus_node_dict.values()],
            "is_pcc": [True if k in pcc_bus_list else False for k in bus_node_dict.keys()],
        })
        df_pcc_bus.to_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/{self.name}_businfo.csv', index=False)

def evse_to_load_df(premise_report_file='../data/premise_data/10_feeders_premise_report.csv', feeder_name='MEAD2104', main_dss_file='inputs/opendss_model/MEAD2104/Master.dss'):
    premise_df = pd.read_csv(premise_report_file)
    premise_df = premise_df[['Feeder', 'Premise Number', 'Lot Centroid ID', 'Transformer ID']]
    premise_df = premise_df[premise_df['Feeder']==feeder_name]
    evse_to_load_df = {}
    # get all the loads from the dss file
    dss.Command(f'Redirect {main_dss_file}')
    all_load_names = dss.Loads.AllNames()
    xfmr_iters = {}
    for _, row in premise_df.iterrows():
        # the next line is the format if there is a secondary load model. The lines after are for if there aren't secondaries
        load_name = f"{row['Lot Centroid ID']}_{row['Transformer ID']}"
        # not all loads have secondary models, if they don't then the load is added to the transformer, with the format: xfmr#_iterator_xfmr#
        # assumes only one evse per load point
        if not load_name in all_load_names:
            xfmr_name = row['Transformer ID']
            if xfmr_name in xfmr_iters.keys():
                xfmr_iters[xfmr_name] = xfmr_iters[xfmr_name]+1
            else:
                xfmr_iters[xfmr_name] = 0
            load_name = f"{xfmr_name}_{xfmr_iters[xfmr_name]}_{xfmr_name}"
        evse_to_load_df[row['Premise Number']] = load_name    
    return evse_to_load_df


if __name__ == "__main__":
    #TODO: make labeled inputs instead of positional
    timestep_sec = 300
    opendss_path = 'ieee34.dss'
    name = 'ieee_34'
    premise_report = 'data/premise_data/premise_report.csv'
    if len(sys.argv)>1:
        timestep_sec = int(sys.argv[1])
    if len(sys.argv)>2:
        opendss_path = sys.argv[2]
    if len(sys.argv)>3:
        name = sys.argv[3]
    if len(sys.argv)>4:
        premise_report = sys.argv[4]
    feeder_fed = GridSim(name=name, timestep_sec=timestep_sec, opendss_path=opendss_path, helics_config_path='', cosim=True, evse_to_load_point_dict=premise_report)
    #logger.debug(f'opendssfederate {feeder_fed.name} from model {feeder_fed.opendss_dir} object created')
    feeder_fed.setup_opendss_model()
    for timestep in range(0, 24*3600, 300):
        feeder_fed.output_grid_values()
        feeder_fed.update_ev_loads(timestep)
        feeder_fed.advance_sim_time(timestep)

    feeder_fed.export_grid_elements()
    # release all
    h.helicsFederateDisconnect(feeder_fed.fed)
    h.helicsFederateFree(feeder_fed.fed)
    h.helicsCloseLibrary()
