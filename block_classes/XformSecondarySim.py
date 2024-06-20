import pandas as pd
import helics as h

"""
This class is to hold the Distribution Secondary Transformer Simulation
It gets inputs on ev loading from the EVChargeSim
It is initialized with info on the secondary model and residential load modeling
It then figures out what the loading will do to the transformer and aggregates
total load at the secondary point to pass to the OpenDSS simulation
"""

class XformSecondarySim:
    def __init__(self, name='secondary_sim', secondary_model_dir = '.', cosim=False, helics_config_path=''):
        # add important params here
        self.secondary_model = {}
        self.secondary_model_dir = secondary_model_dir
        self.residential_load_modeling = {}
        self.ev_loads = {}
        self.aggregated_loads = {}
        self.xformer_thermals = {}
        # these are for if you want time-step based sim
        self.co_simulation = cosim
        self.controller_time = -1
        self.helics_config_path = helics_config_path
        self.fed = None
        self.publications = []
        self.subscriptions = []

    def setup_secondary_sim(self):
        # this function loads data on the secondary model and residential load

        ##### insert data loading here #####

        # if it is a co_simulation this sets up the helics federate
        if self.co_simulation:
            self.fed = h.helicsCreateCombinationFederateFromConfig(self.helics_config_path)
            h.helicsFederateSetTimeProperty(self.fed, h.helics_property_time_delta, self.timestep_sec)
            self.publications.append(h.helicsFederateGetPublication(self.fed, 'aggregated_loads'))
            self.subscriptions.append(h.helicsFederateGetSubscription(self.fed, 'ev_load'))
            h.helicsFederateEnterExecutingMode(self.fed)
        return

    def run_secondary_sim(self):
        # this function uses the profile library and setpoints to determin the actual ev loads
        xformer_thermals = {}
        aggregated_loads = {}

        ##### insert transformer thermal solver here #####


        ##### insert aggregation of loads here ######


        self.aggregated_loads = aggregated_loads
        self.xformer_thermals = xformer_thermals
        return aggregated_loads

    def output_aggregated_loads(self):
        # this function either records setpoints or 
        # for co-simulation sends them as a helics publication
        self.aggregated_loads.to_csv(f'{self.name}_aggloads.csv')
        self.xformer_thermals.to_csv(f'{self.name}_xtherm.csv')
        if self.co_simulation:
            h.helicsFederatePublish(self.publications[0], self.ev_loads)
            self.voltages = h.helicsFederateGetSubscription(self.fed, self.subscriptions)
            h.helicsFederateRequestNextStep(self.fed)
        return 
