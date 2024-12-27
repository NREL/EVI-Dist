import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import pandas as pd
import opendssdirect as dss
import helics as h
import numpy as np
import json
import csv
import logging
import os.path
import pickle
import math

"""
This class holds the OpenDSS simulation interaction
It allows instantiation of the GridSim object,
initialization of the simulation,
advancement in time,
updating loads,
and outputting feedback to the controller
"""

class GridSim:
    def __init__(self, opendss_path, name, feeder_name, timestep_sec, cosim, helics_config_path, premise_report_file, sim_start_time, sim_end_time):
        self.name = name
        self.feeder_name = feeder_name
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename=EVIDIST_ROOT_PATH + f'/logs/sim_plus/{name}.log', encoding='utf-8', level=logging.DEBUG, filemode="w")
        self.timestep_sec = timestep_sec # how large each timestep is in seconds
        # the timestep is dependent on the resolution of the load profiles in the opendss LoadShape.dss files
        self.sim_start_time = sim_start_time
        self.sim_end_time = sim_end_time
        self.time = sim_start_time # what timestep the last outputs were for in seconds
        self.loads_updated_time = 0 # what timestep are the updated loads in alignment with
        self.opendss_dir = opendss_path # directory with opendss model
        self.charge_event_df = pd.read_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_charge_event_data.csv')
        with open(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_trns_premise_ev_mapping.pkl', 'rb') as file:
            self.trns_premise_ev_mapping: dict[str,dict[str,list[str]]] = pickle.load(file)
        self.evse_to_load_point_dict = self.evse_to_load_df(premise_report_file=premise_report_file, feeder_name=feeder_name, main_dss_file=opendss_path)
        self.ev_loads = {}
        self.bus_names: list[str] = []
        self.trns_names: list[str] = []
        self.trns_phases: dict[str, int] = {}
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
        #dss('clear')
        # dss.Basic.ClearAll()
        dss.Command("clear")
        dss.Command(f'Redirect "{self.opendss_dir}"')
        dss.Command("solve")
        summary = dss.Command('summary')
        # print('SUMMARY', summary)


        # dss.Solution.Mode(1)#enums.SolveModes.Daily=1)
        # dss.Solution.DblHour(1)
        #dss.Solution.StepSizeMin(self.timestep_sec/60)
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
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'trns_kva', h.HelicsDataType.STRING))
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'trns_rating', h.HelicsDataType.STRING))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, 'ev_charge_sim/ev_loads', "")) # this is a json string
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, 0.001)  #this is the minimum detectable time difference, not the timestep
            h.helicsFederateEnterExecutingMode(self.fed)

        # NOTE: this code below adds new Load objects to a csv or directly adds it to the sim
        # setup EV load nodes
        base_load_names = dss.Loads.AllNames()
        transformer_names = dss.Transformers.AllNames()
        keys_to_delete = list()
        commands = list()
        for k,v in self.evse_to_load_point_dict.items():
            load_name = v
            if load_name in base_load_names:
                #get bus information from existing load
                dss.Loads.Name(load_name)
                load_bus = dss.CktElement.BusNames()[0]
                bus_voltage = dss.Loads.kV()
                load_phases = dss.Loads.Phases()
                new_load_name = str(k)
                dss_cmd = f"New Load.{new_load_name} phases={load_phases} bus1={load_bus} kV={bus_voltage} Vminpu=0.65 Vmaxpu=1.1 model=1 kva=1.0 kw=0.00 pf=0.99"
                commands.append(dss_cmd)
                dss.Command(dss_cmd)
                self.evse_to_load_point_dict[k] = new_load_name
            elif load_name in transformer_names:
                #get bus information from LV connection of transformer
                dss.Transformers.Name(load_name)
                bus = dss.CktElement.BusNames()[1]
                load_bus = str(bus.split('.')[0] + ".1.2")
                dss.Circuit.SetActiveBus(bus)
                bus_voltage = round(dss.Bus.kVBase()*2,2) #TODO: need to determine what the correct bus voltage is if evs will be connected directly to xfmrs. Also if load should connect to .1 or .1.2
                new_load_name = str(k)
                dss_cmd = f"New Load.{new_load_name} phases={1} bus1={load_bus} kV={bus_voltage} Vminpu=0.65 Vmaxpu=1.1 model=1 kva=1.0 kw=0.00 pf=0.99"
                commands.append(dss_cmd)
                dss.Command(dss_cmd)
                self.logger.warning(f'No associated premise load object exists for EV: {k}. Load object connected directly to transformer bus {load_bus}. Associated Centroid ID is {self.evse_to_centroid[k]}. Associated Premise is {self.evse_to_premise[k]}.') #TODO: remove mention of centroid and premise after unmapped EVs issue is resolved
                self.evse_to_load_point_dict[k] = new_load_name
            else:
                self.logger.warning(f'Cannot determine bus information for EV: {k} in the charge event file. This EV will be removed from the simulation.')
                keys_to_delete.append(k)

        for k in keys_to_delete:
            del self.evse_to_load_point_dict[k]

        # clear previous outputs
        for output_data in ['evloads', 'voltages', 'linecurrents', 'trnscurrents', 'trnskva']:
            data_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_{output_data}.csv'
            if os.path.isfile(data_file):
                os.remove(data_file)

        # clear timesteps created by running Redirect above
        dss.Command('set maxcontroliter=5000')
        dss.Command('set mode=yearly')
        dss.Command('set number=1') # number of steps to run each time solve is called
        dss.Command('set stepsize=' + str(self.timestep_sec) + "s")
        dss.Command('set hour=' + str(self.sim_start_time/3600))

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


        # print("GridSim received {} total ev setpoint power at t={}".format(sum(v for v in self.ev_loads.values()), self.time))

        for evse_name, load_value in self.ev_loads.items():
            # TODO: create better mapping to include missing secondary connections
            try:
                load_name = self.evse_to_load_point_dict[str(evse_name)]
                dss.Loads.Name(load_name)
                base_load = dss.Loads.kW()
                dss.Loads.kW(load_value)
                self.logger.debug(f'updated {load_name} from {base_load} to {load_value} at timestep {self.time}')
            except:
                self.logger.warning(f'evse_name {evse_name} not in the secondary models, ignoring load in this analysis')

        evse_names = self.ev_loads.keys()
        self.loads_updated_time = load_timestamp

    def dss_solve(self):
        # print(f'running opendss for {self.time/3600} hours')
        dss.Solution.Solve()

    def advance_sim_time(self,updated_time):
        while self.time < updated_time and self.co_simulation:
            self.time = h.helicsFederateRequestTime(self.fed, updated_time)
        #self.time = self.time + self.timestep_sec
        self.logger.info(f'{self.name} feeder federate advanced to time: {updated_time}')
        return

    def output_grid_values(self):
        # returns voltages, line currents, and transformer currents
        voltages = dss.Circuit.AllBusMagPu() # in per unit
        node_names = dss.Circuit.AllNodeNames()
        dss_time = dss.Solution.DblHour()*3600 # this actually gives seconds
        # to get kva, you need to iterate through transformer powers
        trns_kva = dict()
        trns_currents = dict()
        trns_rating = dict() # kva rating
        for trns in self.trns_names:
            dss.Circuit.SetActiveElement("Transformer."+trns)
            kva = dss.CktElement.Powers()
            # phases = self.trns_phases[trns]
            if len(kva) == 12: #this is a 1-phase transformer
                trns_kva[trns]= math.sqrt(sum(kva[-2:3:-2])**2 + sum(kva[-1:3:-2])**2)
            else: #else its a 3-phase transformer
                trns_kva[trns]= math.sqrt(sum(kva[-2:7:-2])**2 + sum(kva[-1:7:-2])**2)
            current = dss.CktElement.Currents()
            if len(kva) == 12: #this is a 1-phase transformer
                trns_currents[trns]= math.sqrt(sum(current[-2:3:-2])**2 + sum(current[-1:3:-2])**2)
            else: #else its a 3-phase transformer
                trns_currents[trns]= math.sqrt(sum(current[-2:7:-2])**2 + sum(current[-1:7:-2])**2)
            dss.Transformers.Name(trns)
            trns_rating[trns]= dss.Transformers.kVA()

        # to get line currents you need to iterate through circuit elements
        line_phase_currents = {}
        for line in self.line_names:
            dss.Circuit.SetActiveElement("Line."+line)
            current = dss.CktElement.Currents()
            buses = dss.CktElement.BusNames()
            phases = int(len(current)/2/2)
            for i in range(phases):
                line_phase_currents[line + f".{i+1}"] = math.sqrt(current[i*2]**2 + current[i*2 + 1]**2)

        if self.co_simulation:
            h.helicsPublicationPublishString(self.publications[3], json.dumps(trns_rating))

            h.helicsPublicationPublishString(self.publications[0], json.dumps(voltages))
            voltage_output_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_voltages.csv'
            write_header=False
            if not os.path.isfile(voltage_output_file):
                write_header = True
            with open(voltage_output_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(['timestamp'] + node_names)
                #writer.writerow(voltages)
                writer.writerow([dss_time] + voltages)
            #self.logger.debug(f'bus voltages at t={self.time}: {voltages}')

            h.helicsPublicationPublishString(self.publications[1], json.dumps(trns_currents))
            trns_current_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_trnscurrents.csv'
            write_header=False
            if not os.path.isfile(trns_current_file):
                write_header = True
            with open(trns_current_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(['timestamp'] + self.trns_names)
                writer.writerow([dss_time] + list(trns_currents.values()))

            h.helicsPublicationPublishString(self.publications[2], json.dumps(trns_kva))
            trnskva_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_trnskva.csv'
            write_header = False
            if not os.path.isfile(trnskva_file):
                write_header=True
            with open(trnskva_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(['timestamp'] + self.trns_names)
                writer.writerow([dss_time] + list(trns_kva.values()))

            linecurrent_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_linecurrents.csv'
            write_header = False
            if not os.path.isfile(linecurrent_file):
                write_header=True
            with open(linecurrent_file,'a') as f:
                writer = csv.writer(f, lineterminator='\n')
                if write_header:
                    writer.writerow(['timestamp'] + list(line_phase_currents.keys()))
                writer.writerow([dss_time] + list(line_phase_currents.values()))

            ev_loads = dict()
            for evid in self.evse_to_load_point_dict:
                dss.Circuit.SetActiveElement("Load."+evid)
                ev_load = dss.CktElement.Powers()
                ev_loads[evid] = (math.sqrt( (ev_load[0]+ev_load[2])**2 + (ev_load[1]+ev_load[3])**2))
            evload_file = EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_evloads.csv'
            if len(self.evse_to_load_point_dict.keys()) > 0:
                write_header = False
                if not os.path.isfile(evload_file):
                    write_header = True
                with open(evload_file,'a') as f:
                    writer = csv.writer(f, lineterminator='\n')
                    if write_header:
                        writer.writerow(['timestamp'] + list(self.evse_to_load_point_dict.keys()))
                    writer.writerow([dss_time] + [ev_loads[ev] for ev in self.evse_to_load_point_dict])

        return voltages, trns_currents

    def export_grid_elements(self):
        #Line nanmes, distances
        #node names,
        #transformer names, ratings

        #get line lengths
        line_lengths = list()
        line_codes = list()
        line_ratings = list()
        line_type = list()
        line_phases = list()
        for line in self.line_names:
            dss.Lines.Name(line)
            line_ratings.append(dss.Lines.NormAmps())
            line_phases.append(dss.Lines.Phases())
            line_length = dss.Lines.Length()
            line_code = dss.Lines.LineCode()
            line_geometry = dss.Lines.Geometry()
            if line_code:
                line_codes.append(line_code)
                line_lengths.append(line_length/5280) #assume units of ft for line code
                line_type.append("Secondary") #assume secondar for line code
            elif line_geometry:
                dss.ActiveClass = 'LineGeometry'
                dss.LineGeometries.Name(line_geometry)
                line_codes.append(dss.LineGeometries.Conductors()[0])
                line_lengths.append(line_length*0.621371) #assume units of km for line geometry
                line_type.append("Primary") #assume primary for line geometry
            else:
                line_codes.append("Uncategorized")

        #save line lengths
        df_lines = pd.DataFrame({
            "line": self.line_names,
            "linecode": line_codes,
            "length_mi": line_lengths,
            "rating_A": line_ratings,
            "type": line_type,
            "phases": line_phases,
        })
        df_lines.to_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_linedata.csv', index=False)


        #get transformer ratings
        trns_kva = list()
        trns_phases = list()
        for trns in self.trns_names:
            dss.Transformers.Name(trns)
            trns_kva.append(dss.Transformers.kVA())
            trns_phases.append(len(dss.Transformers.WdgVoltages())/2)

        #save transformer ratings
        df_trns = pd.DataFrame({
            "trns": self.trns_names,
            "kva": trns_kva,
            "phases": trns_phases,
        })
        df_trns.to_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_trnskva_ratings.csv', index=False)


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
            "bus": list(bus_node_dict.keys()),
            "nodes": list(bus_node_dict.values()),
            "is_pcc": [k in pcc_bus_list for k in bus_node_dict],
        })
        df_pcc_bus.to_csv(EVIDIST_ROOT_PATH + f'/data/temp_sim_plus/sim_plus_businfo.csv', index=False)

    def evse_to_load_df(self, premise_report_file='../data/premise_data/10_feeders_premise_report.csv', feeder_name='MEAD2104', main_dss_file='inputs/opendss_model/MEAD2104/Master.dss'):
        premise_df = pd.read_csv(premise_report_file)
        premise_df = premise_df[['Feeder', 'Premise Number', 'Lot Centroid ID', 'Transformer ID']]
        premise_df = premise_df[premise_df['Feeder']==feeder_name]
        evse_to_load_df = {}
        # get all the loads from the dss file
        dss.Basic.ClearAll()
        dss.Command(f'Redirect {main_dss_file}')
        all_load_names = dss.Loads.AllNames()

        premise_df["Transformer ID"] = premise_df["Transformer ID"].apply(str)
        premise_df["Premise Number"] = premise_df["Premise Number"].apply(str)
        self.charge_event_df.sort_values("Veh_ID_Num", inplace=True)
        self.logger.debug(f'There are {len(self.charge_event_df["Veh_ID_Num"].unique())} unique EVs in the charge event file.')
        self.evse_to_centroid = dict() #TODO: remove after unmapped EVs issue is resolved
        self.evse_to_premise = dict() #TODO: remove after unmapped EVs issue is resolved
        for _, ce_row in self.charge_event_df.iterrows():
            trns_id = str(ce_row["Transformer ID"])
            premise_id = str(round(ce_row["Premise Number"]))
            ev_id = str(ce_row["Veh_ID_Num"])
            if ev_id in evse_to_load_df: #is its already been mapped, don't need to do the stuff below again
                continue
            if trns_id in premise_df["Transformer ID"].values:
                trns_rows = premise_df[premise_df["Transformer ID"] == trns_id]
                if premise_id in trns_rows["Premise Number"].values:
                    row = trns_rows[trns_rows["Premise Number"] == premise_id].iloc[0]
                    if len(trns_rows[trns_rows["Premise Number"] == premise_id]) > 1:
                        self.logger.warning(f'Multiple premises are associated with ev {ev_id}. Load assignment may not work properly.')
                    # the next line is the format if there is a secondary load model. The lines after are for if there aren't secondaries
                    load_name = f"{row['Lot Centroid ID']}_{row['Transformer ID']}"
                    self.evse_to_centroid[ev_id] = str(row['Lot Centroid ID']) #TODO: remove after unmapped EVs issue is resolved
                    self.evse_to_premise[ev_id] = premise_id #TODO: remove after unmapped EVs issue is resolved
                    # not all loads have secondary models, if they don't then the load is added to the transformer
                    if not load_name in all_load_names:
                        xfmr_name = row['Transformer ID']
                        load_name = f"{xfmr_name}"

                    evse_to_load_df[ev_id] = load_name
                else:
                    self.logger.warning(f'Premise: {premise_id} loaded from the charge event file is not found in the premise report file.')

            else:
                self.logger.warning(f'Transformer: {trns_id} loaded from the charge event file is not found in the premise report file.')

        #TODO: remove after unmapped EVs issue is resolved
        # asdf = pd.DataFrame({
        #     "Veh_ID_Num": [k for k in self.evse_to_centroid.keys()],
        #     "Lot Centroid ID": [k for k in self.evse_to_centroid.values()],
        #     "Premise Number": [k for k in self.evse_to_premise.values()],
        # })
        # asdf.to_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/unmapped_ev_list_with_premise_and_centroid.csv", sep=',', index=False)
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
        feeder_name = sys.argv[4]
    if len(sys.argv)>5:
        premise_report = sys.argv[5]
    sim_start_time = int(sys.argv[6])
    sim_end_time = int(sys.argv[7])
    feeder_fed = GridSim(name=name, feeder_name=feeder_name, timestep_sec=timestep_sec, opendss_path=opendss_path,
                         helics_config_path='', cosim=True, premise_report_file=premise_report,
                         sim_start_time=sim_start_time, sim_end_time=sim_end_time)
    feeder_fed.setup_opendss_model()
    feeder_fed.output_grid_values()
    updated_time = -10 + sim_start_time
    feeder_fed.time = -20 + sim_start_time
    while feeder_fed.time < updated_time and feeder_fed.co_simulation:
        feeder_fed.time = h.helicsFederateRequestTime(feeder_fed.fed, updated_time)
    feeder_fed.time = sim_start_time
    feeder_fed.advance_sim_time(sim_start_time)
    for timestep in range(sim_start_time, sim_end_time, timestep_sec):
        # print(f"Current opendss simulation time: {round(dss.Solution.DblHour()*3600,2)} sec, cosimtime: {timestep}")
        feeder_fed.update_ev_loads(timestep)
        feeder_fed.dss_solve()
        feeder_fed.output_grid_values()
        feeder_fed.advance_sim_time(timestep)
        # print(f"GridSim just completed time: {timestep}")

    feeder_fed.export_grid_elements()
    # release all
    h.helicsFederateDisconnect(feeder_fed.fed)
    h.helicsFederateFree(feeder_fed.fed)
    h.helicsCloseLibrary()
