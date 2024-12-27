import os
import pandas as pd
import ast
import matplotlib.pyplot as plt
import random
import statistics as stats
import numpy as np
import pdb
from pathinit import EVIDIST_ROOT_PATH
from matplotlib.figure import Figure

def build_total_load_dict(
        ev_profiles_folder:str, # This is a directory
        customer_ami_data:str, # This can be a pkl or csv file
        mapping_file:str, # This is a csv file
        feeder:str, # This is the selected feeder name
        conroller_types: list()
        ): 

    print('Performing coincidence analysis...')
    EV_dataframes = {}
    ev_xfmr_dataframe=pd.DataFrame()
    print('Getting', feeder, 'EV profiles')
    # for filename in os.listdir(ev_profiles_folder):
    #     if filename.startswith('ev'):
    for ctrl_type in conroller_types:
        #READ IN EV CHARGING PROFILES FOR ALL FEEDERS AND CREATE DICT OF DATAFRAMES
        #WITH CHARGING STRATEGIES AS KEYS
        #filepath = os.path.join(ev_profiles_folder, filename)
        filepath = os.path.join(ev_profiles_folder, "ev_profiles_" + ctrl_type + ".csv")
        #df_name = os.path.splitext(filename)[0].split('ev_profiles_')[1]
        df_name = ctrl_type
        df=pd.read_csv(filepath) #this is in 1min resolution
        columns_to_drop=['Unnamed: 0.1', 'Unnamed: 0', 'day', 'time', 'power']
        columns_to_drop_filt=[label for label in columns_to_drop if label in df.columns]
        df=df.drop(columns_to_drop_filt,axis=1)
        df.index=pd.date_range(start='2023-09-01 00:00', periods=len(df), freq='T')
        df=df.resample('15T').max() #convert to 15 min max values (1 week of data)
        if df_name not in EV_dataframes:
            EV_dataframes[df_name] = df.fillna(0) 
        else:
            EV_dataframes[df_name]=pd.concat([EV_dataframes[df_name],df.fillna(0)],axis=1)

    #GET VEHICLE TO PREMISE MAPPING FOR ALL FEEDERS AND CREATE DATAFRAME
    df=pd.read_csv(mapping_file).set_index('Transformer ID')
    if ev_xfmr_dataframe.empty:
        ev_xfmr_dataframe=df
    else:
        ev_xfmr_dataframe=pd.concat([ev_xfmr_dataframe,df],axis=0)

    #GET AMI DATA FOR ALL METERS WE HAVE ACROSS ALL TEN FEEDERS
    print(f"Getting {feeder} customer level AMI data")
    ami_start='2023-09-01 00:00:00' # TODO: needs to be date agnostic
    ami_end='2023-09-07 23:45:00'

    if os.path.splitext(customer_ami_data)[1] == '.pkl':
        Customer_load_dataframe=pd.DataFrame(pd.read_pickle(customer_ami_data)) #1-month of data
    elif os.path.splitext(customer_ami_data)[1] == '.csv':
        Customer_load_dataframe=pd.read_csv(customer_ami_data) #1-month of data
    Customer_load_dataframe['Total']=Customer_load_dataframe.sum(axis=1)
    Customer_load_dataframe.fillna(0,inplace=True)

    if Customer_load_dataframe['Total'].idxmax() in Customer_load_dataframe[ami_start:ami_end].index:
        Customer_load_dataframe=Customer_load_dataframe[ami_start:ami_end] #take first week
        Customer_load_dataframe.drop('Total',axis=1,inplace=True)
    else:
        plt.plot(Customer_load_dataframe.index,Customer_load_dataframe.sum(axis=1))
        plt.show()
        raise ValueError(f"Peak occurs on {Customer_load_dataframe['Total'].idxmax()}: re-adjust start and end dates to include peak load day")
    
    #MAP EV VEHICLE NUMBERS TO PREMISES AND CREATE A DICT
    print('Mapping EVS to premises')
    ev_premise_vehicle_dict={}

    for transformer in ev_xfmr_dataframe.index:
        raw_EV_premises=ev_xfmr_dataframe.loc[transformer]['Premise_Numbers']
        if type(raw_EV_premises) != float: #nan is float
            EV_premises=[int(item[0]) for item in ast.literal_eval(raw_EV_premises)]
            EV_vehicle_numbers=ev_xfmr_dataframe[ev_xfmr_dataframe.index==float(transformer)]['Unique_Vehicles'].values[0].strip("[]").replace("'", "").strip().split()
            for prem,veh in zip(EV_premises,EV_vehicle_numbers):
                if prem not in ev_premise_vehicle_dict:
                    ev_premise_vehicle_dict[prem]=[veh] 
                else:
                    ev_premise_vehicle_dict[prem].append(veh)
    # # #############################################################
    # COMBINE EV PROFILES AND AMI DATA INTO total_load_dict
    print('Creating load dictionary')
    missing_EVs=[]
    
    total_load_dict={}

    print("Length of EV_dataframes:", len(EV_dataframes.keys()))

    for charging_type in EV_dataframes.keys():
        print('\tCharging type: ',charging_type)
        zero_load_premises=[]
        # charging_type_formatted=charging_type.split('EV_profiles_weekly_')[1]
        charging_type_formatted=charging_type
        total_load_dict[charging_type_formatted]={}
        for premise_number in Customer_load_dataframe.columns:
            premise_s=Customer_load_dataframe[premise_number].to_list()
            if int(premise_number) in ev_premise_vehicle_dict:
                EV_present=True
                vehicle_numbers=ev_premise_vehicle_dict[int(premise_number)]
                if all([veh in EV_dataframes[charging_type_formatted].columns for veh in vehicle_numbers]):
                    ev_s=EV_dataframes[charging_type_formatted][vehicle_numbers].sum(axis=1).tolist()
                else:
                    ev_s=[0]*len(premise_s)
                    for veh in vehicle_numbers:
                        if veh not in EV_dataframes[charging_type_formatted].columns:
                            missing_EVs.append(veh)
                        else:
                            ev_s=[a+b for a,b in zip(ev_s,EV_dataframes[charging_type_formatted][veh].to_list())]
                total_s=[a+b for a,b in zip(premise_s,ev_s)]
            else:
                EV_present=False
                vehicle_numbers=[0]
                ev_s=[0]*len(premise_s)
                total_s=premise_s
            if max(total_s)>0 and max(premise_s)>0:
                total_load_dict[charging_type_formatted][int(premise_number)]={
                    'premise_number':int(premise_number),
                    'EV':EV_present,
                    'vehicle_number':vehicle_numbers,
                    's':premise_s,
                    's_ev':ev_s,
                    'total_s':total_s,
                    'peak_s':max(premise_s),
                    'peak_s_ev':max(total_s)
                }
                if max(premise_s)>max(total_s):
                    print('here')
            else:
                zero_load_premises.append(premise_number)
                # print('\t\tZero load on premise:',premise_number,'--> EXCLUDING PREMISE' )
                pass
    print(f"{len(zero_load_premises)} premises with zero load per AMI. Excluding these from total_load_dict.")
    EV_count=len([key for key, value in total_load_dict['Uncontrolled'].items() if value['EV']])
    total_premise_count=len(total_load_dict['Uncontrolled'])
    print(f"{EV_count}/{total_premise_count} ({round(100*EV_count/total_premise_count,2)}%) of premises with EVs on {feeder}")
    return total_load_dict

def plot_coincidence_and_transformer_sizing(
        total_load_dict:dict,
        ):

    fig = Figure(figsize=(15/2,8/2))
    fig2 = Figure(figsize=(15/2,8/2))
    fig3 = Figure(figsize=(15/2,8/2))

    axes = fig.subplots(nrows=1, ncols=3)
    axes2 = fig2.subplots(nrows=1, ncols=3)
    axes3 = fig3.subplots(nrows=1, ncols=3)

    axes=axes.flatten()
    axes2=axes2.flatten()
    axes3=axes3.flatten()

    random.seed(42)

    num_combos=100
    max_cust_count=60

    transformer_cust_counts={}
    transformer_cust_counts_evs={}
    transformer_cust_counts_all_evs={}
    bar_width=0.2
    colors=[]
    bars=[]
    bars1=[]
    bars2=[]
    for k,charging_type in enumerate(total_load_dict.keys()):
        # name=charging_type.split('weekly_')[1]
        name=charging_type
        cust_counts=[]

        ave_non_coincident_peaks_evs=[]
        ave_coincident_peaks_evs=[]
        ave_coincidence_factors_evs=[]

        ave_non_coincident_peaks=[]
        ave_coincident_peaks=[]
        ave_coincidence_factors=[]

        ave_non_coincident_peaks_all_evs=[]
        ave_coincident_peaks_all_evs=[]
        ave_coincidence_factors_all_evs=[]

        transformer_cust_counts[charging_type]={
            '25':0,
            '50':0,
            '100':0
            }
        transformer_cust_counts_evs[charging_type]={
            '25_evs':0,
            '50_evs':0,
            '100_evs':0
            }
        transformer_cust_counts_all_evs[charging_type]={
            '25_all_evs':0,
            '50_all_evs':0,
            '100_all_evs':0
            }

        for i in range(max_cust_count):

            cust_counts.append(i+1)

            non_coincident_peaks_evs=[]
            coincident_peaks_evs=[]
            coincidence_factors_evs=[]

            non_coincident_peaks=[]
            coincident_peaks=[]
            coincidence_factors=[]

            non_coincident_peaks_all_evs=[]
            coincident_peaks_all_evs=[]
            coincidence_factors_all_evs=[]

            for j in range(num_combos):
                ramdon_premise_selection=random.choices(list(total_load_dict[charging_type].keys()),k=i+1)
                # print([key for key, value in total_load_dict[charging_type].items() if value['EV'] and key in ramdon_premise_selection])

                random_premise_selection_all_evs=random.choices([key for key, value in total_load_dict[charging_type].items() if value['EV']],k=i+1)

                non_coincident_peak_ev=sum([total_load_dict[charging_type][premise]['peak_s_ev'] for premise in ramdon_premise_selection])
                non_coincident_peak=sum([total_load_dict[charging_type][premise]['peak_s'] for premise in ramdon_premise_selection])
                non_coincident_peak_all_evs=sum([total_load_dict[charging_type][premise]['peak_s_ev'] for premise in random_premise_selection_all_evs])

                coincident_peak_ev=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['total_s'] for premise in ramdon_premise_selection])])
                coincident_peak=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s'] for premise in ramdon_premise_selection])])
                coincident_peak_all_evs=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['total_s'] for premise in random_premise_selection_all_evs])])

                coincidence_factor_ev=coincident_peak_ev/non_coincident_peak_ev
                coincidence_factor=coincident_peak/non_coincident_peak
                coincidence_factor_all_evs=coincident_peak_all_evs/non_coincident_peak_all_evs

                non_coincident_peaks_evs.append(non_coincident_peak_ev)
                coincident_peaks_evs.append(coincident_peak_ev)

                non_coincident_peaks.append(non_coincident_peak)
                coincident_peaks.append(coincident_peak)

                non_coincident_peaks_all_evs.append(non_coincident_peak_all_evs)
                coincident_peaks_all_evs.append(coincident_peak_all_evs)

                coincidence_factors_evs.append(coincidence_factor_ev)
                coincidence_factors.append(coincidence_factor)
                coincidence_factors_all_evs.append(coincidence_factor_all_evs)
            
            sorted_non_coincident_peaks_evs=np.sort(non_coincident_peaks_evs)
            sorted_coincident_peaks_evs=np.sort(coincident_peaks_evs)
            sorted_coincidence_factors_evs=np.sort(coincidence_factors_evs)
            ave_non_coincident_peaks_evs.append(stats.mean(sorted_non_coincident_peaks_evs[sorted_non_coincident_peaks_evs>=np.percentile(sorted_non_coincident_peaks_evs,75)]))
            ave_coincident_peaks_evs.append(stats.mean(sorted_coincident_peaks_evs[sorted_coincident_peaks_evs>=np.percentile(sorted_coincident_peaks_evs,75)]))
            
            sorted_non_coincident_peaks=np.sort(non_coincident_peaks)
            sorted_coincident_peaks=np.sort(coincident_peaks)
            sorted_coincidence_factors=np.sort(coincidence_factors)
            ave_non_coincident_peaks.append(stats.mean(sorted_non_coincident_peaks[sorted_non_coincident_peaks>=np.percentile(sorted_non_coincident_peaks,75)]))
            ave_coincident_peaks.append(stats.mean(sorted_coincident_peaks[sorted_coincident_peaks>=np.percentile(sorted_coincident_peaks,75)]))
        
            sorted_non_coincident_peaks_all_evs=np.sort(non_coincident_peaks_all_evs)
            sorted_coincident_peaks_all_evs=np.sort(coincident_peaks_all_evs)
            sorted_coincidence_factors_all_evs=np.sort(coincidence_factors_all_evs)
            ave_non_coincident_peaks_all_evs.append(stats.mean(sorted_non_coincident_peaks_all_evs[sorted_non_coincident_peaks_all_evs>=np.percentile(sorted_non_coincident_peaks_all_evs,75)]))
            ave_coincident_peaks_all_evs.append(stats.mean(sorted_coincident_peaks_all_evs[sorted_coincident_peaks_all_evs>=np.percentile(sorted_coincident_peaks_all_evs,75)]))

            if i>0:
                ave_coincidence_factors_evs.append(stats.mean(sorted_coincidence_factors_evs[sorted_coincidence_factors_evs>np.percentile(sorted_coincidence_factors_evs,75)]))
                ave_coincidence_factors.append(stats.mean(sorted_coincidence_factors[sorted_coincidence_factors>np.percentile(sorted_coincidence_factors,75)]))
                ave_coincidence_factors_all_evs.append(stats.mean(sorted_coincidence_factors_all_evs[sorted_coincidence_factors_all_evs>np.percentile(sorted_coincidence_factors_all_evs,75)]))
            else:
                ave_coincidence_factors_evs.append(1)
                ave_coincidence_factors.append(1)
                ave_coincidence_factors_all_evs.append(1)

        for index,(peak_no_evs, peak_evs, peak_all_evs) in enumerate(zip(ave_coincident_peaks,ave_coincident_peaks_evs,ave_coincident_peaks_all_evs)):
            if peak_no_evs>=25 and transformer_cust_counts[charging_type]['25']==0:
                transformer_cust_counts[charging_type]['25']=cust_counts[index]
            if peak_no_evs>=50 and transformer_cust_counts[charging_type]['50']==0:
                transformer_cust_counts[charging_type]['50']=cust_counts[index]
            if peak_no_evs>=100 and transformer_cust_counts[charging_type]['100']==0:
                transformer_cust_counts[charging_type]['100']=cust_counts[index]

            if peak_evs>=25 and transformer_cust_counts_evs[charging_type]['25_evs']==0:
                transformer_cust_counts_evs[charging_type]['25_evs']=cust_counts[index]
            if peak_evs>=50 and transformer_cust_counts_evs[charging_type]['50_evs']==0:
                transformer_cust_counts_evs[charging_type]['50_evs']=cust_counts[index]
            if peak_evs>=100 and transformer_cust_counts_evs[charging_type]['100_evs']==0:
                transformer_cust_counts_evs[charging_type]['100_evs']=cust_counts[index]

            if peak_all_evs>=25 and transformer_cust_counts_all_evs[charging_type]['25_all_evs']==0:
                transformer_cust_counts_all_evs[charging_type]['25_all_evs']=cust_counts[index]
            if peak_all_evs>=50 and transformer_cust_counts_all_evs[charging_type]['50_all_evs']==0:
                transformer_cust_counts_all_evs[charging_type]['50_all_evs']=cust_counts[index]
            if peak_all_evs>=100 and transformer_cust_counts_all_evs[charging_type]['100_all_evs']==0:
                transformer_cust_counts_all_evs[charging_type]['100_all_evs']=cust_counts[index]
        
        if k==0:
            axes[0].plot(cust_counts,ave_non_coincident_peaks,color='black',label='Non-coincident Peak: No EVs', linestyle='--')
            axes2[0].plot(cust_counts,ave_non_coincident_peaks_evs,label='Non-coinicdent Peak', linestyle='--')
            axes3[0].plot(cust_counts,ave_non_coincident_peaks_all_evs,label='Non-coinicdent Peak',  linestyle='--')

            axes[0].plot(cust_counts,ave_coincident_peaks,color='black',label='Coincident Peak: No EVs')
            axes[1].plot(cust_counts,ave_coincidence_factors,color='black',label='Coincident Factors: No EVs')
            bars.extend(axes[2].bar(list(transformer_cust_counts[charging_type].keys()),list(transformer_cust_counts[charging_type].values()),color='black',label='No EVs'))

        line,=axes2[0].plot(cust_counts,ave_coincident_peaks_evs,label=name)
        line_color=line.get_color()
        colors.append(line_color)
        axes2[1].plot(cust_counts,ave_coincidence_factors_evs,label=name,color=line_color)
        axes3[0].plot(cust_counts,ave_coincident_peaks_all_evs,label=name, color=line_color)
        axes3[1].plot(cust_counts,ave_coincidence_factors_all_evs,label=name, color=line_color)

        axes[0].set_ylabel('kVA',fontsize=7)
        axes2[0].set_ylabel('kVA',fontsize=7)
        axes3[0].set_ylabel('kVA',fontsize=7)

        axes[1].set_ylabel('Coincidence Factor',fontsize=7)
        axes2[1].set_ylabel('Coincidence Factor',fontsize=7)
        axes3[1].set_ylabel('Coincidence Factor',fontsize=7)

        axes[0].set_xlabel('Customer Count',fontsize=7)
        axes2[0].set_xlabel('Customer Count',fontsize=7)
        axes3[0].set_xlabel('Customer Count',fontsize=7)

        axes[1].set_xlabel('Customer Count',fontsize=7)
        axes2[1].set_xlabel('Customer Count',fontsize=7)
        axes3[1].set_xlabel('Customer Count',fontsize=7)

        axes[0].axhline(25, linestyle=':',color='red')#25 kVA Transformer
        axes[0].axhline(50, linestyle=':',color='red')#50 kVA Transformer
        axes[0].axhline(100, linestyle=':',color='red')#100 kVA Transformer
        axes2[0].axhline(25, linestyle=':',color='red')#25 kVA Transformer
        axes2[0].axhline(50, linestyle=':',color='red')#50 kVA Transformer
        axes2[0].axhline(100, linestyle=':',color='red')#100 kVA Transformer
        axes3[0].axhline(25, linestyle=':',color='red')#25 kVA Transformer
        axes3[0].axhline(50, linestyle=':',color='red')#50 kVA Transformer
        axes3[0].axhline(100, linestyle=':',color='red')#100 kVA Transformer

        axes[0].text(max_cust_count+1, 25, '25 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes[0].text(max_cust_count+1, 50, '50 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes[0].text(max_cust_count+1, 100, '100 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes2[0].text(max_cust_count+1, 25, '25 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes2[0].text(max_cust_count+1, 50, '50 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes2[0].text(max_cust_count+1, 100, '100 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes3[0].text(max_cust_count+1, 25, '25 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes3[0].text(max_cust_count+1, 50, '50 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        axes3[0].text(max_cust_count+1, 100, '100 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)


    categories=list(transformer_cust_counts_evs.keys())
    values_evs=np.array([list(data.values()) for data in transformer_cust_counts_evs.values()]).transpose()
    values_all_evs=np.array([list(data.values()) for data in transformer_cust_counts_all_evs.values()]).transpose()

    num_categories=3
    num_bars=values_evs.shape[1]
    indices=np.arange(num_categories)


    for i,category in zip(range(num_bars),categories):
        cat=category
        bars1.extend(axes2[2].bar(indices + i * bar_width, values_evs[:, i], bar_width, label=cat,color=colors[i]))
        bars2.extend(axes3[2].bar(indices + i * bar_width, values_all_evs[:, i], bar_width, label=cat,color=colors[i]))

    for bar in bars:
        height = bar.get_height()
        axes[2].text(bar.get_x() + bar.get_width() / 2.0, height, f'{height}', ha='center', va='bottom', fontsize=7)
    for bar1,bar2 in zip(bars1,bars2):
        height1 = bar1.get_height()
        height2 = bar2.get_height()
        axes2[2].text(bar1.get_x() + bar1.get_width() / 2.0, height1, f'{height1}', ha='center', va='bottom', fontsize=7)
        axes3[2].text(bar2.get_x() + bar2.get_width() / 2.0, height2, f'{height2}', ha='center', va='bottom', fontsize=7)

    
    axes[0].tick_params(axis='x', labelsize=7)
    axes[0].tick_params(axis='y', labelsize=7)
    axes[1].tick_params(axis='x', labelsize=7)
    axes[1].tick_params(axis='y', labelsize=7)

    axes[2].set_xticks(indices)
    axes[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
    axes[2].tick_params(axis='y', labelsize=7)
    axes[2].set_ylabel('Customer Count at 100% Nameplate',fontsize=7)

    axes2[0].tick_params(axis='x', labelsize=7)
    axes2[0].tick_params(axis='y', labelsize=7)
    axes2[1].tick_params(axis='x', labelsize=7)
    axes2[1].tick_params(axis='y', labelsize=7)
    axes2[2].set_xticks(indices + ((num_bars/2)-0.5) * bar_width)
    axes2[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
    axes2[2].tick_params(axis='y', labelsize=7)
    axes2[2].set_ylabel('Customer Count at 100% Nameplate',fontsize=7)

    axes3[0].tick_params(axis='x', labelsize=7)
    axes3[0].tick_params(axis='y', labelsize=7)
    axes3[1].tick_params(axis='x', labelsize=7)
    axes3[1].tick_params(axis='y', labelsize=7)
    axes3[2].set_xticks(indices + ((num_bars/2)-0.5) * bar_width)
    axes3[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
    axes3[2].tick_params(axis='y', labelsize=7)
    axes3[2].set_ylabel('Customer Count at 100% Nameplate',fontsize=7)

    axes[0].legend(fontsize=7)
    axes[1].legend(fontsize=7)
    axes[2].legend(fontsize=7)
    axes2[0].legend(fontsize=7)
    axes2[1].legend(fontsize=7)
    axes2[2].legend(fontsize=7)
    axes3[0].legend(fontsize=7)
    axes3[1].legend(fontsize=7)
    axes3[2].legend(fontsize=7)

    fig.suptitle(f"No EVs (Customer Loads Only) - Top Quartile Mean Across {num_combos} Random Customer Selections", fontsize=7)
    fig2.suptitle(f"With EVs (2030 Mix) - Top Quartile Mean Across {num_combos} Random Customer Selections", fontsize=7)
    fig3.suptitle(f"All EVs - Top Quartile Mean Across {num_combos} Random Customer Selections", fontsize=7)

    fig.tight_layout()
    fig2.tight_layout()
    fig3.tight_layout()   

    return [fig, fig2, fig3]
