"""

"""
import sys
import os
sys.path.append('../')
sys.path.append(os.getcwd())
import asyncio
import time
import zipfile
import json
import io
import pickle

from pathinit import EVIDIST_ROOT_PATH
from modules.simulation_plus import SimPlus
from dashboard.actions import DataOperatorPlus

def save_session_JSON(configs, input_file_names):
        #first clear user's dir information from input file names.
        input_file_names = {k: os.path.basename(v) for k,v in input_file_names.items()}

        save_session_dict = {
            "input_file_names": dict(input_file_names),
            "output_file_names": dict(output_file_names.items()),
            "configs": dict(configs.items())
        }

        for k,v in save_session_dict.items():
            for k2,v2 in v.items():
                if k2 == "month":
                    v[k2] = str(v2)

        return save_session_dict

def get_zip_data(configs, input_file_names, output_file_names):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        # Add CSV files to ZIP
        for name, path in output_file_names.items():
            if os.path.exists(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + path):
                zip_file.write(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/" + path, arcname="sim_plus_" + name + ".csv")  # Use original file names in ZIP

        # Add JSON data to ZIP
        json_data = json.dumps(dict(save_session_JSON(configs, input_file_names).items()), indent=4).encode('utf-8')
        zip_file.writestr('session_info.json', json_data)  # Save JSON with a specific name

        # Add DataOperatorPlus pickle to ZIP
        dop_pickle = pickle.dumps(dop)
        zip_file.writestr("dop.pickle", dop_pickle)

    zip_buffer.seek(0)  # Reset buffer position for reading
    return zip_buffer


#####################################################
##SET THE DESIRED CONTROLS, FEEDER, AND SIM TIME HERE

feeder_options = ["MEAD2104", #0
                  "MEAD2059", #1
                  "MURP1210", #2
                  "MURP1312", #3
                  "BTER1341B", #4
                  "BTER1347B", #5
                  "BTER1349B", #6
                  "BTER1356B", #7
                  "SMDT1384", #8
                ]

control_options = ["TOU ASAP", #0
                   "TOU ALAP", #1
                   "TOU Random", #2
                   "Uncontrolled", #3
                   "FCFS", #4
                   "FCFS + SM50", #5
                   "EQUAL SHARING", #6
                   ]

sim_start_time = 6*3600
sim_end_time = sim_start_time + 24*3600
#####################################################


total_simulations = len(feeder_options)*len(control_options)
print("")
print("Total simulations to run: {}".format(total_simulations))

i = 0
for feeder in feeder_options:
    for control in [control_options[6]]:
        i+=1
        print("\nBeginning sim {}/{}. Feeder={}, Control={}".format(i,total_simulations,feeder,control))

        configs = dict()
        configs["feeder"] = feeder
        configs["controller"] = control
        configs["month"] = 9
        configs["day_of_week"] = 1
        configs["sim_name"] = f"{feeder}_{control}"


        input_file_names = dict()
        input_file_names["dss_main"] = EVIDIST_ROOT_PATH + f"/data/opendss_model/{feeder}/Master.dss"
        input_file_names["adoption_data"] = EVIDIST_ROOT_PATH + "/data/adoptions/2030/Xcel_Charge_Events_Home_GPS_Veh_Info_High_TRB_2030.csv"
        input_file_names["premise_report"] = EVIDIST_ROOT_PATH + "/data/premise_data/10_feeders_premise_report.csv"


        start_time = time.time()

        progress_queue = asyncio.Queue()
        progress = [0]

        sim = SimPlus(sim_name=configs["sim_name"],
                        feeder_name=configs["feeder"],
                        main_dss_file=input_file_names["dss_main"],
                        ev_adoption_file=input_file_names["adoption_data"],
                        premise_data_file=input_file_names["premise_report"],
                        controller_name=configs["controller"],
                        month=configs["month"],
                        day_of_week=configs["day_of_week"],
                        sim_start_time=sim_start_time,
                        sim_end_time=sim_end_time,
                        )

        asyncio.run(sim.run(progress, progress_queue))

        #create and process the results.
        output_file_names = dict()
        output_file_names['evloads'] = f'sim_plus_evloads.csv'
        output_file_names['linecurrents'] = f'sim_plus_linecurrents.csv'
        output_file_names['linedata'] = f'sim_plus_linedata.csv'
        output_file_names['trnscurrents'] = f'sim_plus_trnscurrents.csv'
        output_file_names['trnskva'] = f'sim_plus_trnskva.csv'
        output_file_names['trnskva_ratings'] = f'sim_plus_trnskva_ratings.csv'
        output_file_names['voltages'] = f'sim_plus_voltages.csv'
        output_file_names['bus_info'] = f'sim_plus_businfo.csv'
        output_file_names['charge_events'] = f'sim_plus_charge_event_data.csv'
        output_file_names['trns_premise_ev_mapping'] = f'sim_plus_trns_premise_ev_mapping.pkl'
        output_file_names['ev_charge_stats'] = f'sim_plus_ev_charge_stats.csv'

        dop = DataOperatorPlus(output_file_names, configs["controller"])
        asyncio.run(dop.load_data(progress, progress_queue))

        with open(EVIDIST_ROOT_PATH + f"/data/saved_sessions_plus/{configs['sim_name']}_results.zip", "wb") as f:  # Use 'wb' mode for writing binary data.
            zip_buffer = get_zip_data(configs=configs, input_file_names=input_file_names, output_file_names=output_file_names)
            f.write(zip_buffer.read())

        end_time = time.time()
        print("Sim plus executed in {} seconds".format(round(end_time-start_time,2)))
