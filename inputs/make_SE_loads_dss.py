# this script creates an SE_loads.dss file from the
# Xcel_Charge_Events_Home_GPS_Veh_Info_High.csv 
# which lists the transformer the charger is connected to 
# and uses that to connect to one of the lv buses on the downstream
# side of the transformer 
import pandas as pd


def get_ce_transformers(charge_events_file, feeder_name = 'all'):
    ce_df = pd.read_csv(charge_events_file)
    # select only the desired feeder
    if not feeder_name == 'all':
        ce_df = ce_df[ce_df['Feeder']==feeder_name]
    
    # only pull uniqe ce locations
    # this assumes only home charging so far
    premise_numbers = ce_df['Premise Number'].unique()
    se_list = []
    for pn in premise_numbers:
        se_list.append(ce_df[ce_df['Premise Number'] == pn].iloc[0])
    return se_list


def get_transformer_buses(transformer_dss_file):
    # not needed given standard format of transformers
    return True


def write_se_loads_dss(se_list):
    # all transformers with ce should be low voltage, single phase, so can assume
    # bus syntax to be like: trans_#########_lv_connection.1.0 and trans_#########_lv_connection.2.0
    # spread the chargers evenly between the two connections
    dss_file_lines = []
    conn_num = 1
    for se in se_list:
        se_id = se['Premise Number']
        trans_id = se['Transformer ID']
        max_power_kw = se['Max AC Power kW']
        new_line = f"New Load.EV_{se_id} phases=1 bus=trans_{trans_id}_lv_connection.{conn_num}.0 kV=0.24 Vminpu=0.65 Vmaxpu=1.1 kw={max_power_kw} kvar=3.25 numcust=1\n"
        dss_file_lines.append(new_line)
        # alternate connection numbers
        if conn_num == 1:
            conn_num = 2
        else:
            conn_num = 1

    #write the file
    with open('SE_Loads.dss', 'w') as se_file:
        se_file.writelines(dss_file_lines)



if __name__ == "__main__":
    charge_events_file = sys.argv[1] # this should be a csv of charge events with the premise number, transformer id, max AC power. It can be the charge events list for the transport team
    feeder_name = sys.argv[2] # this is just a string of feeder name in case you want to make loads for only one feeder
    
    charger_transformer_df = get_ce_transformers(charge_events_file, feeder_name)
    write_se_loads_dss(charger_transformer_df)
    print('Wrote SE_loads.dss')