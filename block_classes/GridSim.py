import pandas as pd
from opendssdirect import dss, enums
import helics as h
import json
import csv
import logging

logger = logging.getLogger(__name__)

"""
This class holds the OpenDSS simulation interaction
It allows instantiation of the GridSim object, 
initialization of the simulation,
advancement in time,
updating loads,
and outputting feedback to the controller
"""

class GridSim:
    def __init__(self, opendss_path, name='ieee_34', timestep_sec=60*5, cosim=False, helics_config_path=''):
        self.name = name
        logging.basicConfig(filename=f'{name}.log', encoding='utf-8', level=logging.DEBUG)
        self.timestep_sec = timestep_sec # how large each timestep is in seconds
        # the timestep is dependent on the resolution of the load profiles in the opendss LoadShape.dss files
        self.time = -1 # what timestep the last outputs were for in seconds
        self.loads_updated_time = 0 # what timestep are the updated loads in alignment with
        self.opendss_dir = opendss_path # directory with opendss model
        self.evse_to_load_point_dict = {'evse0': 'pev1p_810.2','evse1': 'pev1p_890.3','evse2': 'pev1p_822.1'}
        self.ev_loads = {}
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
        dss(f'Redirect {self.opendss_dir}')
        dss.Solution.Mode(enums.SolveModes.Daily)
        if self.co_simulation:
            if self.helics_config_path == '':
                fedinfo = h.helicsCreateFederateInfo()
                h.helicsFederateInfoSetCoreName(fedinfo, self.name)
                h.helicsFederateInfoSetCoreInitString(fedinfo, "--federates=1")
                self.fed = h.helicsCreateValueFederate(self.name, fedinfo)
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'voltages', h.HelicsDataType.STRING))
                self.publications.append(h.helicsFederateRegisterPublication(self.fed, 'currents', h.HelicsDataType.STRING))
                self.subscriptions.append(h.helicsFederateRegisterSubscription(self.fed, 'ev_charge_sim/ev_loads', "")) # this is a json string
            else:
                self.fed = h.helicsCreateValueFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, self.timestep_sec)
            h.helicsFederateEnterExecutingMode(self.fed)

    def update_ev_loads(self, load_timestamp):
        # this function updates the opendss loads to include the up to date aggregated loads
        # this works for a single timestep and should be used with advance_sim_time if iterating
        # if using helics you will need to get the subscriptions
        ev_loads = json.loads(h.helicsInputGetString(self.subscriptions[0]))
        if not isinstance(ev_loads, float):
            self.ev_loads = ev_loads
        else:
            logger.warning(f'recieved float for ev_loads, continuing without updating')
        for evse_name, load_value in self.ev_loads.items():
            load_name = self.evse_to_load_point_dict[evse_name]
            dss.Loads.Name(load_name)
            dss.Loads.kW(load_value)
            logger.debug(f'updated {load_name} to {load_value} at timestep {self.time}')
        with open(f'{self.name}_evloads.csv','a') as csvfile:
            csv_headings = self.ev_loads.keys()
            writer = csv.DictWriter(csvfile, fieldnames=csv_headings, lineterminator='\n')
            writer.writerow(self.ev_loads)
        self.loads_updateed_time = load_timestamp

    def advance_sim_time(self,updated_time):
        while self.time < updated_time and self.co_simulation:
            dss.Solution.Solve()
            h.helicsFederateRequestTime(self.fed, updated_time)
            self.time = self.time + self.timestep_sec
        return                

    def output_grid_values(self):
        # returns voltages, line currents, and transformer currents
        voltages = dss.Circuit.AllBusMagPu() # in per unit
        trns_currents = dss.Transformers.strWdgCurrents() #dss.Circuit.CurrentMagAngle() # need to check if this is correct synatx for all currents
        if self.co_simulation:
            h.helicsPublicationPublishString(self.publications[0], json.dumps(voltages))
            with open(f'{self.name}_voltages.csv','a') as f:
                writer = csv.writer(f, lineterminator='\n')
                writer.writerow(voltages)
            logger.debug(voltages)
            h.helicsPublicationPublishString(self.publications[1], json.dumps(trns_currents))
            with open(f'{self.name}_trnscurrents.csv','a') as f:
                writer = csv.writer(f, lineterminator='\n')
                writer.writerow(trns_currents.split(','))
            logger.debug(trns_currents)
        return voltages, trns_currents


if __name__ == "__main__":
    ieee_34_feeder = GridSim(opendss_path='../inputs/opendss_model/ieee34.dss', helics_config_path='', cosim=True)
    logger.debug('ieee_34 object created')
    ieee_34_feeder.setup_opendss_model()
    for timestep in range(1, 24*3600, 3600):
        ieee_34_feeder.output_grid_values()
        ieee_34_feeder.update_ev_loads(timestep)
        ieee_34_feeder.advance_sim_time(timestep)
        logger.info(f'ieee34 feeder federate advanced to time: {timestep}')
