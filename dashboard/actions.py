import os
import sys
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

class DataOperator:
    def __init__(self, paths, configs) -> None:
        self.paths = paths
        self.res = configs['display_res']
        self.sim_len = int(1440 / self.res) * 7
        self.feeder = configs['feeder']
        self.transformer_data = pd.read_csv(self.paths['premise_report'])
        self.transformer_data = self.transformer_data[self.transformer_data['Feeder'] == self.feeder]
        itenary_data = pd.read_csv(self.paths['ev_adoption'])

        if os.path.isfile(configs['ami_data_file']):
            try:
                self.base_load = pd.read_csv(self.paths['baseload_profiles'])
                self.base_load = self.base_load.iloc[:-1:self.res]
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
            self.ev_load[cntrl] = pd.read_csv(self.paths['ev_profiles'][cntrl])
            self.ev_load[cntrl] = self.ev_load[cntrl].iloc[::self.res]
        
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
            return np.array(self.base_load[str(xf_id)].tolist())
        except Exception as e:
            # pn.state.notifications.error('No data available for Transformer ID = ' + str(xf_id), duration=4000)
            return np.zeros((self.sim_len,))
    
    def get_feeder_load(self):
        try:
            f = self.base_load.iloc[:,4:].sum(axis=1)
            return np.array(f.tolist())
        except:
            return np.zeros((self.sim_len,))
    
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
            return np.zeros((self.sim_len,)) # Could be none if time series is used
        
    def get_agg_ev_load_by_xf_id(self, xf_id, controller):
        veh_id_list = self.get_veh_ids_for_xf(xf_id)
        agg_ev_load = np.zeros((self.sim_len,)) # Should not be hard-coded, use time-series
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

   
    def get_table(self):
        
        table_df = self.transformer_data[['Transformer ID', 'Bank Size', 'OH/UG', 'Bank Configuration', 'Output Voltage', 'Longitude_X', 'Latitude_Y']].reset_index(drop=True)
        table_df = table_df.drop_duplicates(subset=['Transformer ID'])
        return table_df.reset_index(drop=True)

    def gen_total_load_dict(self):
        cust_lvl_premise_data=pd.DataFrame(pd.read_pickle(self.paths['ami_cust_lvl']))[:672]
        ev_premise_vehicle_dict = self.mappings['prem_to_veh_mappings'][self.feeder]
        premise_list = self.itenary_data_fs['Premise Number'].unique()
        #print(self.mappings['prem_to_veh_mappings'][self.feeder])

        total_load_dict={}
        for charging_type in self.controller:
            #print('charging_type:',charging_type)
            charging_type_formatted=charging_type
            total_load_dict[charging_type_formatted]={}
            for premise_number in cust_lvl_premise_data.columns:
                premise_s=cust_lvl_premise_data[premise_number].to_list()
                if int(premise_number) in ev_premise_vehicle_dict:
                    EV_present=True
                    vehicle_number=ev_premise_vehicle_dict[int(premise_number)]
                    #print(charging_type_formatted, vehicle_number)
                    for veh in vehicle_number:
                        if veh in self.ev_load[charging_type_formatted].columns:
                            ev_s=self.ev_load[charging_type_formatted][veh].tolist() #TODO check we can just add p to s
                            ev_s=[0 if math.isnan(x) else x for x in ev_s]
                            total_s=[a+b for a,b in zip(premise_s,ev_s)]
                            continue # TODO: This only considers a single vehicle charging at a premise. Fix needed in coordination with Erik
                else:
                    EV_present=False
                    vehicle_number=0
                    ev_s=[]
                    total_s=premise_s

                # print("Total S:", total_s)
                # print("Premise S:", premise_s)

                if max(total_s)>0 and max(premise_s)>0:
                    total_load_dict[charging_type_formatted][int(premise_number)]={
                        'premise_number':int(premise_number),
                        'EV':EV_present,
                        'vehicle_number':vehicle_number,
                        's':premise_s,
                        's_ev':total_s,
                        'total_s':total_s,
                        'peak_s':max(premise_s),
                        'peak_s_ev':max(total_s)
                    }
                else:
                    # print('premise_number:',premise_number)
                    pass

        return total_load_dict

    def do_coincidence_analysis(self, total_load_dict, fig_type="dashboard"):

        colors = ['blue', 'green', 'yellow', 'orange', 'purple', 'cyan', 'magenta', 'black']

        params1 = {
            #"""This params is for the 1st row of the coincidence plot"""
            'nrows' : 1,
            'ncols' : 3,
            'color' : ['black', 'black', 'black'],
            'label' : ['Non-coincident Peak: No EVs', 'Non-coinicdent Peak', 'No EVs'],
            'linestyle' : ['--','--','--'],
            'xlabel' : ['Customer Count', 'Customer Count', 'Transformer Rating'],
            'ylabel' : ['kVA', 'Coincidence Factor', 'Customer Count at \n100% Nameplate'],
        }

        params2 = {
            #"""This params is for the 1st row of the coincidence plot"""
            'nrows' : 1,
            'ncols' : 3,
            'color' : ['black', 'black', 'black'],
            'label' : ['Non-coincident Peak: No EVs', 'Non-coinicdent Peak', 'No EVs'],
            'linestyle' : ['--','--','--'],
            'xlabel' : ['Customer Count', 'Customer Count', 'Transformer Rating'],
            'ylabel' : ['kVA', 'Coincidence Factor', 'Customer Count at \n100% Nameplate'],
        }

        params3 = {
            #"""This params is for the 1st row of the coincidence plot"""
            'nrows' : 1,
            'ncols' : 3,
            'color' : ['black', 'black', 'black'],
            'label' : ['Non-coincident Peak: No EVs', 'Non-coinicdent Peak', 'No EVs'],
            'linestyle' : ['--','--','--'],
            'xlabel' : ['Customer Count', 'Customer Count', 'Transformer Rating'],
            'ylabel' : ['kVA', 'Coincidence Factor', 'Customer Count at \n100% Nameplate'],
        }

        slp1 = SimpleLinePlot(params1, fig_type=fig_type)
        slp2 = SimpleLinePlot(params2, fig_type=fig_type)
        slp3 = SimpleLinePlot(params3, fig_type=fig_type)

        random.seed(42)
        num_combos=100
        max_cust_count=50
        transformer_cust_counts={}
        transformer_cust_counts_evs={}
        transformer_cust_counts_all_evs={}
        bar_width=0.2
        colors=[]
        bars=[]
        bars1=[]
        bars2=[]

        for k,charging_type in enumerate(total_load_dict.keys()):
            print('charging_type:',charging_type)
            name=charging_type
            print(name)

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
                    random_premise_selection_all_evs=random.choices([key for key, value in total_load_dict[charging_type].items() if value['EV']],k=i+1)

                    non_coincident_peak_ev=sum([total_load_dict[charging_type][premise]['peak_s_ev'] for premise in ramdon_premise_selection])
                    non_coincident_peak=sum([total_load_dict[charging_type][premise]['peak_s'] for premise in ramdon_premise_selection])
                    non_coincident_peak_all_evs=sum([total_load_dict[charging_type][premise]['peak_s_ev'] for premise in random_premise_selection_all_evs])

                    coincident_peak_ev=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s_ev'] for premise in ramdon_premise_selection])])
                    coincident_peak=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s'] for premise in ramdon_premise_selection])])
                    coincident_peak_all_evs=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s_ev'] for premise in random_premise_selection_all_evs])])

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

                # ave_non_coincident_peaks_evs.append(stats.mean(non_coincident_peaks_evs))
                # ave_coincident_peaks_evs.append(stats.mean(coincident_peaks_evs))
                # ave_coincidence_factors_evs.append(stats.mean(coincidence_factors_evs))

                # ave_non_coincident_peaks.append(stats.mean(non_coincident_peaks))
                # ave_coincident_peaks.append(stats.mean(coincident_peaks))
                # ave_coincidence_factors.append(stats.mean(coincidence_factors))

                # ave_non_coincident_peaks_all_evs.append(stats.mean(non_coincident_peaks_all_evs))
                # ave_coincident_peaks_all_evs.append(stats.mean(coincident_peaks_all_evs))
                # ave_coincidence_factors_all_evs.append(stats.mean(coincidence_factors_all_evs))

                # ave_non_coincident_peaks_evs.append(max(non_coincident_peaks_evs))
                # ave_coincident_peaks_evs.append(max(coincident_peaks_evs))
                # ave_coincidence_factors_evs.append(max(coincidence_factors_evs))

                # ave_non_coincident_peaks.append(max(non_coincident_peaks))
                # ave_coincident_peaks.append(max(coincident_peaks))
                # ave_coincidence_factors.append(max(coincidence_factors))

                # ave_non_coincident_peaks_all_evs.append(max(non_coincident_peaks_all_evs))
                # ave_coincident_peaks_all_evs.append(max(coincident_peaks_all_evs))
                # ave_coincidence_factors_all_evs.append(max(coincidence_factors_all_evs))
                
                sorted_non_coincident_peaks_evs=np.sort(non_coincident_peaks_evs)
                sorted_coincident_peaks_evs=np.sort(coincident_peaks_evs)
                sorted_coincidence_factors_evs=np.sort(coincidence_factors_evs)
                ave_non_coincident_peaks_evs.append(stats.mean(sorted_non_coincident_peaks_evs[sorted_non_coincident_peaks_evs>np.percentile(sorted_non_coincident_peaks_evs,75)]))
                ave_coincident_peaks_evs.append(stats.mean(sorted_coincident_peaks_evs[sorted_coincident_peaks_evs>np.percentile(sorted_coincident_peaks_evs,75)]))
                
                sorted_non_coincident_peaks=np.sort(non_coincident_peaks)
                sorted_coincident_peaks=np.sort(coincident_peaks)
                sorted_coincidence_factors=np.sort(coincidence_factors)
                ave_non_coincident_peaks.append(stats.mean(sorted_non_coincident_peaks[sorted_non_coincident_peaks>np.percentile(sorted_non_coincident_peaks,75)]))
                ave_coincident_peaks.append(stats.mean(sorted_coincident_peaks[sorted_coincident_peaks>np.percentile(sorted_coincident_peaks,75)]))
            
                sorted_non_coincident_peaks_all_evs=np.sort(non_coincident_peaks_all_evs)
                sorted_coincident_peaks_all_evs=np.sort(coincident_peaks_all_evs)
                sorted_coincidence_factors_all_evs=np.sort(coincidence_factors_all_evs)
                ave_non_coincident_peaks_all_evs.append(stats.mean(sorted_non_coincident_peaks_all_evs[sorted_non_coincident_peaks_all_evs>np.percentile(sorted_non_coincident_peaks_all_evs,75)]))
                ave_coincident_peaks_all_evs.append(stats.mean(sorted_coincident_peaks_all_evs[sorted_coincident_peaks_all_evs>np.percentile(sorted_coincident_peaks_all_evs,75)]))

                if i >0:
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

                line = slp1.gen_plot(Signal(cust_counts, ave_non_coincident_peaks, None,  None, None), label='Non-coincident Peak: No EVs')
                line.set_color('black')
                line.set_linestyle('--')

                slp2.gen_plot(Signal(cust_counts, ave_non_coincident_peaks_evs, None,  None, None), label='Non-coinicdent Peak')
                slp3.gen_plot(Signal(cust_counts, ave_non_coincident_peaks_all_evs, None,  None, None), label='Non-coinicdent Peak')

                line = slp1.add_trace(Signal(cust_counts, ave_coincident_peaks, None,  None, None), label='Coincident Peak: No EVs')
                line.set_color('black')
                
                line = slp1.add_trace(Signal(cust_counts, ave_coincidence_factors, None,  None, None), label='Coincident Factors: No EVs', pos=1)
                line.set_color('black')
                bar_obj = slp1.add_bar(Signal(list(transformer_cust_counts[charging_type].keys()),list(transformer_cust_counts[charging_type].values()), None, None, None), label='No EVs', pos=2)
                
                for b in bar_obj:
                    b.set_color('black')  # Set color to orange                
                
                bars.extend(bar_obj)

                # axes[0].plot(cust_counts,ave_non_coincident_peaks,color='black',label='Non-coincident Peak: No EVs', linestyle='--')
                # axes2[0].plot(cust_counts,ave_non_coincident_peaks_evs,label='Non-coinicdent Peak', linestyle='--')
                # axes3[0].plot(cust_counts,ave_non_coincident_peaks_all_evs,label='Non-coinicdent Peak',  linestyle='--')

                # axes[0].plot(cust_counts,ave_coincident_peaks,color='black',label='Coincident Peak: No EVs')
                # axes[1].plot(cust_counts,ave_coincidence_factors,color='black',label='Coincident Factors: No EVs')
                # bars.extend(axes[2].bar(list(transformer_cust_counts[charging_type].keys()),list(transformer_cust_counts[charging_type].values()),color='black',label='No EVs'))

            line = slp2.add_trace(Signal(cust_counts, ave_coincident_peaks_evs, None,  None, None), label=name)
            #slp2.axis[0].set_label(name)
            line_color=line.get_color()
            colors.append(line_color)

            line = slp2.add_trace(Signal(cust_counts, ave_coincidence_factors_evs, None,  None, None), label=name, pos=1)
            #slp2.axis[1].set_label(name)
            line.set_color(line_color)

            line = slp3.gen_plot(Signal(cust_counts, ave_coincident_peaks_all_evs, None,  None, None), label=name)
            #slp3.axis[0].set_label(name)
            line.set_color(line_color)

            line = slp3.gen_plot(Signal(cust_counts, ave_coincidence_factors_all_evs, None,  None, None), label=name, pos=1)
            #slp3.axis[1].set_label(name)
            line.set_color(line_color)

            slp1.axis[0].set_ylabel('kVA',fontsize=7)
            slp2.axis[0].set_ylabel('kVA',fontsize=7)
            slp3.axis[0].set_ylabel('kVA',fontsize=7)

            slp1.axis[1].set_ylabel('Coincidence Factor',fontsize=7)
            slp2.axis[1].set_ylabel('Coincidence Factor',fontsize=7)
            slp3.axis[1].set_ylabel('Coincidence Factor',fontsize=7)

            slp1.axis[0].set_xlabel('Customer Count',fontsize=7)
            slp2.axis[0].set_xlabel('Customer Count',fontsize=7)
            slp3.axis[0].set_xlabel('Customer Count',fontsize=7)

            slp1.axis[1].set_xlabel('Customer Count',fontsize=7)
            slp2.axis[1].set_xlabel('Customer Count',fontsize=7)
            slp3.axis[1].set_xlabel('Customer Count',fontsize=7)

            slp1.axis[2].set_xlabel('Transformer 100% Nameplate',fontsize=7)
            slp2.axis[2].set_xlabel('Transformer 100% Nameplate',fontsize=7)
            slp3.axis[2].set_xlabel('Transformer 100% Nameplate',fontsize=7)


            slp1.axis[0].axhline(25, linestyle=':',color='red')#25 kVA Transformer
            slp1.axis[0].axhline(50, linestyle=':',color='red')#50 kVA Transformer
            slp1.axis[0].axhline(100, linestyle=':',color='red')#100 kVA Transformer
            slp2.axis[0].axhline(25, linestyle=':',color='red')#25 kVA Transformer
            slp2.axis[0].axhline(50, linestyle=':',color='red')#50 kVA Transformer
            slp2.axis[0].axhline(100, linestyle=':',color='red')#100 kVA Transformer
            slp3.axis[0].axhline(25, linestyle=':',color='red')#25 kVA Transformer
            slp3.axis[0].axhline(50, linestyle=':',color='red')#50 kVA Transformer
            slp3.axis[0].axhline(100, linestyle=':',color='red')#100 kVA Transformer

            slp1.axis[0].text(max_cust_count+1, 25, '25 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp1.axis[0].text(max_cust_count+1, 50, '50 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp1.axis[0].text(max_cust_count+1, 100, '100 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp2.axis[0].text(max_cust_count+1, 25, '25 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp2.axis[0].text(max_cust_count+1, 50, '50 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp2.axis[0].text(max_cust_count+1, 100, '100 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp3.axis[0].text(max_cust_count+1, 25, '25 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp3.axis[0].text(max_cust_count+1, 50, '50 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
            slp3.axis[0].text(max_cust_count+1, 100, '100 kVA Xfmr', color='red', ha='right', va='bottom', fontsize=7)
        
        categories=list(transformer_cust_counts_evs.keys())
        values_evs=np.array([list(data.values()) for data in transformer_cust_counts_evs.values()]).transpose()
        values_all_evs=np.array([list(data.values()) for data in transformer_cust_counts_all_evs.values()]).transpose()

        num_categories=3
        num_bars=values_evs.shape[1]
        indices=np.arange(num_categories)

        for i,category in zip(range(num_bars),categories):
            bars1.extend(slp2.axis[2].bar(indices + i * bar_width, values_evs[:, i], bar_width, label=category,color=colors[i]))
            bars2.extend(slp3.axis[2].bar(indices + i * bar_width, values_all_evs[:, i], bar_width, label=category,color=colors[i]))

        for bar in bars:
            height = bar.get_height()
            slp1.axis[2].text(bar.get_x() + bar.get_width() / 2.0, height, f'{height}', ha='center', va='bottom', fontsize=7)
        for bar1,bar2 in zip(bars1,bars2):
            height1 = bar1.get_height()
            height2 = bar2.get_height()
            slp2.axis[2].text(bar1.get_x() + bar1.get_width() / 2.0, height1, f'{height1}', ha='center', va='bottom', fontsize=7)
            slp3.axis[2].text(bar2.get_x() + bar2.get_width() / 2.0, height2, f'{height2}', ha='center', va='bottom', fontsize=7)

        # axes[2].set_xticks(indices + bar_width * (num_bars - 1) / 2)
        slp1.axis[0].set_xticklabels(slp1.axis[0].get_xticklabels(),fontsize=7)
        slp1.axis[0].set_yticklabels(slp1.axis[0].get_yticklabels(),fontsize=7)
        slp1.axis[1].set_xticklabels(slp1.axis[1].get_xticklabels(),fontsize=7)
        slp1.axis[1].set_yticklabels(slp1.axis[1].get_yticklabels(),fontsize=7)
        slp1.axis[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
        slp1.axis[2].set_yticklabels(slp1.axis[2].get_yticklabels(),fontsize=7)
        slp1.axis[2].set_ylabel('Customer Count',fontsize=7)

        slp2.axis[0].set_xticklabels(slp2.axis[0].get_xticklabels(),fontsize=7)
        slp2.axis[0].set_yticklabels(slp2.axis[0].get_yticklabels(),fontsize=7)
        slp2.axis[1].set_xticklabels(slp2.axis[1].get_xticklabels(),fontsize=7)
        slp2.axis[1].set_yticklabels(slp2.axis[1].get_yticklabels(),fontsize=7)
        slp2.axis[2].set_xticks(indices + bar_width * (num_bars - 1) / 2)
        slp2.axis[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
        slp2.axis[2].set_yticklabels(slp2.axis[2].get_yticklabels(),fontsize=7)
        slp2.axis[2].set_ylabel('Customer Count',fontsize=7)

        slp3.axis[0].set_xticklabels(slp3.axis[0].get_xticklabels(),fontsize=7)
        slp3.axis[0].set_yticklabels(slp3.axis[0].get_yticklabels(),fontsize=7)
        slp3.axis[1].set_xticklabels(slp3.axis[1].get_xticklabels(),fontsize=7)
        slp3.axis[1].set_yticklabels(slp3.axis[1].get_yticklabels(),fontsize=7)
        slp3.axis[2].set_xticks(indices + bar_width * (num_bars - 1) / 2)
        slp3.axis[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
        slp3.axis[2].set_yticklabels(slp3.axis[2].get_yticklabels(),fontsize=7)
        slp3.axis[2].set_ylabel('Customer Count',fontsize=7)

        slp1.axis[0].legend(fontsize=7)
        slp1.axis[1].legend(fontsize=7)
        slp1.axis[2].legend(fontsize=7)
        slp2.axis[0].legend(fontsize=7)
        slp2.axis[1].legend(fontsize=7)
        slp2.axis[2].legend(fontsize=7)
        slp3.axis[0].legend(fontsize=7)
        slp3.axis[1].legend(fontsize=7)
        slp3.axis[2].legend(fontsize=7)

        slp1.fig.suptitle(f"No EVs (Customer Loads Only) - Top Quartile Mean Across {num_combos} Random Customer Selections", fontsize=7)
        slp2.fig.suptitle(f"With EVs (2030 Mix) - Top Quartile Mean Across {num_combos} Random Customer Selections", fontsize=7)
        slp3.fig.suptitle(f"All EVs - Top Quartile Mean Across {num_combos} Random Customer Selections", fontsize=7)
            

        return [slp1, slp2, slp3]

    def do_coincidence_analysis2(self, total_load_dict, fig_type="dashboard"):
        ncols=2

        fig = Figure(figsize=(15/2,8/2))
        fig2 = Figure(figsize=(15/2,8/2))
        fig3 = Figure(figsize=(15/2,8/2))

        axes = fig.subplots(nrows=1, ncols=3)

        axes2 = fig2.subplots(nrows=1, ncols=3)

        axes3 = fig3.subplots(nrows=1, ncols=3)

        # fig,axes=plt.subplots(nrows=1, ncols=3, figsize=(18,5))
        # fig2,axes2=plt.subplots(nrows=1, ncols=3, figsize=(18,5))
        # fig3,axes3=plt.subplots(nrows=1, ncols=3, figsize=(18,5))

        axes=axes.flatten()
        axes2=axes2.flatten()
        axes3=axes3.flatten()

        random.seed(42)

        num_combos=100
        max_cust_count=50

        transformer_cust_counts={}
        transformer_cust_counts_evs={}
        transformer_cust_counts_all_evs={}
        bar_width=0.2
        colors=[]
        bars=[]
        bars1=[]
        bars2=[]
        for k,charging_type in enumerate(total_load_dict.keys()):
            print('charging_type:',charging_type)
            name=charging_type
            print(name)

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
                    random_premise_selection_all_evs=random.choices([key for key, value in total_load_dict[charging_type].items() if value['EV']],k=i+1)

                    non_coincident_peak_ev=sum([total_load_dict[charging_type][premise]['peak_s_ev'] for premise in ramdon_premise_selection])
                    non_coincident_peak=sum([total_load_dict[charging_type][premise]['peak_s'] for premise in ramdon_premise_selection])
                    non_coincident_peak_all_evs=sum([total_load_dict[charging_type][premise]['peak_s_ev'] for premise in random_premise_selection_all_evs])

                    coincident_peak_ev=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s_ev'] for premise in ramdon_premise_selection])])
                    coincident_peak=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s'] for premise in ramdon_premise_selection])])
                    coincident_peak_all_evs=max([sum(values) for values in zip(*[total_load_dict[charging_type][premise]['s_ev'] for premise in random_premise_selection_all_evs])])

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

                # ave_non_coincident_peaks_evs.append(stats.mean(non_coincident_peaks_evs))
                # ave_coincident_peaks_evs.append(stats.mean(coincident_peaks_evs))
                # ave_coincidence_factors_evs.append(stats.mean(coincidence_factors_evs))

                # ave_non_coincident_peaks.append(stats.mean(non_coincident_peaks))
                # ave_coincident_peaks.append(stats.mean(coincident_peaks))
                # ave_coincidence_factors.append(stats.mean(coincidence_factors))

                # ave_non_coincident_peaks_all_evs.append(stats.mean(non_coincident_peaks_all_evs))
                # ave_coincident_peaks_all_evs.append(stats.mean(coincident_peaks_all_evs))
                # ave_coincidence_factors_all_evs.append(stats.mean(coincidence_factors_all_evs))

                # ave_non_coincident_peaks_evs.append(max(non_coincident_peaks_evs))
                # ave_coincident_peaks_evs.append(max(coincident_peaks_evs))
                # ave_coincidence_factors_evs.append(max(coincidence_factors_evs))

                # ave_non_coincident_peaks.append(max(non_coincident_peaks))
                # ave_coincident_peaks.append(max(coincident_peaks))
                # ave_coincidence_factors.append(max(coincidence_factors))

                # ave_non_coincident_peaks_all_evs.append(max(non_coincident_peaks_all_evs))
                # ave_coincident_peaks_all_evs.append(max(coincident_peaks_all_evs))
                # ave_coincidence_factors_all_evs.append(max(coincidence_factors_all_evs))
                
                sorted_non_coincident_peaks_evs=np.sort(non_coincident_peaks_evs)
                sorted_coincident_peaks_evs=np.sort(coincident_peaks_evs)
                sorted_coincidence_factors_evs=np.sort(coincidence_factors_evs)
                ave_non_coincident_peaks_evs.append(stats.mean(sorted_non_coincident_peaks_evs[sorted_non_coincident_peaks_evs>np.percentile(sorted_non_coincident_peaks_evs,75)]))
                ave_coincident_peaks_evs.append(stats.mean(sorted_coincident_peaks_evs[sorted_coincident_peaks_evs>np.percentile(sorted_coincident_peaks_evs,75)]))
                
                sorted_non_coincident_peaks=np.sort(non_coincident_peaks)
                sorted_coincident_peaks=np.sort(coincident_peaks)
                sorted_coincidence_factors=np.sort(coincidence_factors)
                ave_non_coincident_peaks.append(stats.mean(sorted_non_coincident_peaks[sorted_non_coincident_peaks>np.percentile(sorted_non_coincident_peaks,75)]))
                ave_coincident_peaks.append(stats.mean(sorted_coincident_peaks[sorted_coincident_peaks>np.percentile(sorted_coincident_peaks,75)]))
            
                sorted_non_coincident_peaks_all_evs=np.sort(non_coincident_peaks_all_evs)
                sorted_coincident_peaks_all_evs=np.sort(coincident_peaks_all_evs)
                sorted_coincidence_factors_all_evs=np.sort(coincidence_factors_all_evs)
                ave_non_coincident_peaks_all_evs.append(stats.mean(sorted_non_coincident_peaks_all_evs[sorted_non_coincident_peaks_all_evs>np.percentile(sorted_non_coincident_peaks_all_evs,75)]))
                ave_coincident_peaks_all_evs.append(stats.mean(sorted_coincident_peaks_all_evs[sorted_coincident_peaks_all_evs>np.percentile(sorted_coincident_peaks_all_evs,75)]))

                if i >0:
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
            bars1.extend(axes2[2].bar(indices + i * bar_width, values_evs[:, i], bar_width, label=category,color=colors[i]))
            bars2.extend(axes3[2].bar(indices + i * bar_width, values_all_evs[:, i], bar_width, label=category,color=colors[i]))

        for bar in bars:
            height = bar.get_height()
            axes[2].text(bar.get_x() + bar.get_width() / 2.0, height, f'{height}', ha='center', va='bottom', fontsize=7)
        for bar1,bar2 in zip(bars1,bars2):
            height1 = bar1.get_height()
            height2 = bar2.get_height()
            axes2[2].text(bar1.get_x() + bar1.get_width() / 2.0, height1, f'{height1}', ha='center', va='bottom', fontsize=7)
            axes3[2].text(bar2.get_x() + bar2.get_width() / 2.0, height2, f'{height2}', ha='center', va='bottom', fontsize=7)

        # axes[2].set_xticks(indices + bar_width * (num_bars - 1) / 2)
        axes[0].set_xticklabels(axes[0].get_xticklabels(),fontsize=7)
        axes[0].set_yticklabels(axes[0].get_yticklabels(),fontsize=7)
        axes[1].set_xticklabels(axes[1].get_xticklabels(),fontsize=7)
        axes[1].set_yticklabels(axes[1].get_yticklabels(),fontsize=7)
        axes[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
        axes[2].set_yticklabels(axes[2].get_yticklabels(),fontsize=7)
        axes[2].set_ylabel('Customer Count at 100% Nameplate',fontsize=7)

        axes2[0].set_xticklabels(axes2[0].get_xticklabels(),fontsize=7)
        axes2[0].set_yticklabels(axes2[0].get_yticklabels(),fontsize=7)
        axes2[1].set_xticklabels(axes2[1].get_xticklabels(),fontsize=7)
        axes2[1].set_yticklabels(axes2[1].get_yticklabels(),fontsize=7)
        axes2[2].set_xticks(indices + bar_width * (num_bars - 1) / 2)
        axes2[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
        axes2[2].set_yticklabels(axes2[2].get_yticklabels(),fontsize=7)
        axes2[2].set_ylabel('Customer Count at 100% Nameplate',fontsize=7)

        axes3[0].set_xticklabels(axes3[0].get_xticklabels(),fontsize=7)
        axes3[0].set_yticklabels(axes3[0].get_yticklabels(),fontsize=7)
        axes3[1].set_xticklabels(axes3[1].get_xticklabels(),fontsize=7)
        axes3[1].set_yticklabels(axes3[1].get_yticklabels(),fontsize=7)
        axes3[2].set_xticks(indices + bar_width * (num_bars - 1) / 2)
        axes3[2].set_xticklabels(['25 kVA','50 kVA','100 kVA'],fontsize=7)
        axes3[2].set_yticklabels(axes3[2].get_yticklabels(),fontsize=7)
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
            
        # fig.show()
        # fig2.show()
        # fig3.show()

        return [fig, fig2, fig3]
        
def get_stats(data, threshold, res=60*15):
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
    prem_dict_ce = dict()
    prem_to_veh_dict = dict()
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
                 'reg_mappings' : region_dict,
                 'prem_to_veh_mappings' : prem_to_veh_dict}

    #print(months)                 
    
    return variables, months

def get_feeder_names(mappings):

    return [ feeder for feeder in mappings['xf_mappings']]
        

class DataOperatorPlus:
    def __init__(self, paths) -> None:
        self.table_tabs = ["evloads", "linecurrents", "trnscurrents", "trnskva", "voltages"]
        self.filenames = paths
        self.trns_list: list[Trns] = list()
        self.lines_list: list[Lines] = list()
        self.nodes_list: list[Nodes] = list()
        self.bus_list: list[Bus] = list()
        
        self.load_trns_data()
        self.load_lines_data()
        self.load_node_voltages()
        self.load_bus_info()
        # self.get_tables()
    
    # def get_tables(self) -> dict[str,pd.DataFrame]:
    #     tables: dict[str, pd.DataFrame] = dict()
    #     for name in self.table_tabs:
    #         match name:
    #             case "trnscurrents":
    #                 tables[name] = self.get_trnscurrents()
    #             case "trnskva":
    #                 tables[name] = self.get_trnskva()
    #             case _:
    #                 tables[name] = self.get_data(name)
    #     return tables
        
    # def get_data(self, dataname: str) -> pd.DataFrame:
    #     return pd.read_csv(self.filenames[dataname])
    
    def get_evloads(self):
        return pd.read_csv(self.filenames["evloads"])
        
    # def get_linecurrents(self):
    #     if self.linecurrents is None:
    #         lc_raw = pd.read_csv(self.filenames["linecurrents"])
    #         self.linecurrents = lc_raw.applymap(lambda x: ast.literal_eval(x))
            
    #     return self.linecurrents.applymap(lambda x: f"{round(x[2],3)} ∠ {round(x[3],3)}°")
    
    def get_voltages(self):
        return pd.read_csv(self.filenames["voltages"])
    
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
        trnscurrents: pd.DataFrame = pd.read_csv(self.filenames["trnscurrents"])
        trnscurrents = trnscurrents.applymap(lambda x: ast.literal_eval(x))
        
        #load transformer kva
        trnskva: pd.DataFrame = pd.read_csv(self.filenames["trnskva"])
        trnskva = trnskva.applymap(lambda x: ast.literal_eval(x))
        trnskva = trnskva.applymap(lambda x: [math.sqrt(x[0]**2 + x[1]**2), math.atan2(x[1],x[0])*360/2/math.pi])
        
        #load transformer ratings
        trnskva_rating: pd.DataFrame = pd.read_csv(self.filenames["trnskva_ratings"])
        
        for idx, row in trnskva_rating.iterrows():
            trns = Trns()
            trns.name = row["trns"]
            trns.kva_rating = row["kva"]
            trns.kva_mag = trnskva[trns.name].apply(lambda x: x[0]).to_list()
            trns.kva_ph = trnskva[trns.name].apply(lambda x: x[1]).to_list()
            trns.kva_mag_max = max(trns.kva_mag)
            trns.time = [t for t in range(len(trns.kva_mag))]
            trns.i_mag = trnscurrents[trns.name].apply(lambda x: x[0]).to_list()
            trns.i_ph = trnscurrents[trns.name].apply(lambda x: x[1]).to_list()
            trns.i_mag_max = max(trns.i_mag)
            self.trns_list.append(trns)
                     
    def get_trns_kva_loading(self, kva_percent: float = 100):
        total_count: dict[float,int] = dict()
        kva_percent_count: dict[float,int] = dict()
        for trns in self.trns_list:
            if trns.kva_rating not in total_count.keys():
                total_count[trns.kva_rating] = 0
            if trns.kva_rating not in kva_percent_count.keys():
                kva_percent_count[trns.kva_rating] = 0    
                
            total_count[trns.kva_rating] += 1
            
            if trns.kva_mag_max/trns.kva_rating*100 >= kva_percent:
                kva_percent_count[trns.kva_rating] += 1   
        
        df = pd.DataFrame(columns=["Rating (kVA)", "Scenario", "Count (#)"])
        for k,v in total_count.items():
            df.loc[len(df)] = [k, "Overall Count", v]
            
        for k,v in kva_percent_count.items():
            df.loc[len(df)] = [k, "TOU ASAP".format(kva_percent), v]
        
        return df
    
    def get_trns_max_load_summary(self):
        return pd.DataFrame({
            "Name": [trns.name for trns in self.trns_list],
            "Rating (kVA)": [trns.kva_rating for trns in self.trns_list],
            "Max Load (%)": [trns.kva_mag_max/trns.kva_rating*100 for trns in self.trns_list],
        })
    
    def get_trns_tbl_df(self):
        return pd.DataFrame({
            "Name": [trns.name for trns in self.trns_list],
            "Rating (kVA)": [trns.kva_rating for trns in self.trns_list],
            "Max Load Power (%)": [trns.kva_mag_max/trns.kva_rating*100 for trns in self.trns_list],
            "Max Load Current (A)": [trns.i_mag_max for trns in self.trns_list],
        })
        
    def get_trns_kva_ts(self, trns_name: str):
        trns = next(t for t in self.trns_list if t.name == trns_name)
        return pd.DataFrame({
            "Time": trns.time,
            "kva_mag": trns.kva_mag,
            "kva_ph": trns.kva_ph,
        })
        
    
    def load_lines_data(self):
        #load transfomer currents
        linecurrents: pd.DataFrame = pd.read_csv(self.filenames["linecurrents"])
        linecurrents = linecurrents.applymap(lambda x: ast.literal_eval(x))

        #load transformer ratings
        linedata: pd.DataFrame = pd.read_csv(self.filenames["linedata"])
        
        for idx, row in linedata.iterrows():
            ln = Lines()
            ln.name = row["line"]
            ln.linecode = str(row["linecode"])
            ln.length = row["length"]
            ln.i_mag = linecurrents[ln.name].apply(lambda x: x[0]).to_list()
            ln.i_ph = linecurrents[ln.name].apply(lambda x: x[1]).to_list()
            ln.time = [t for t in range(len(ln.i_mag))]
            ln.i_mag_max = max(ln.i_mag)
            self.lines_list.append(ln)
            
            
    def get_lines_loading(self, loading_percent: float = 100):
        total_count: dict[float,int] = dict()
        loading_percent_count: dict[float,int] = dict()
        for ln in self.lines_list:
            if ln.linecode not in total_count.keys():
                total_count[ln.linecode] = 0
            if ln.linecode not in loading_percent_count.keys():
                loading_percent_count[ln.linecode] = 0    
                
            total_count[ln.linecode] += ln.length
            
            if ln.i_mag_max*100 >= loading_percent:
                loading_percent_count[ln.linecode] += ln.length 
        
        df = pd.DataFrame(columns=["Line Code", "Scenario", "Distance (miles)"])
        for k,v in total_count.items():
            df.loc[len(df)] = [k, "Overall Distance", v]
            
        for k,v in loading_percent_count.items():
            df.loc[len(df)] = [k, "TOU ASAP".format(loading_percent), v]
        
        return df
    
    def get_lines_max_load_summary(self):
        return pd.DataFrame({
            "Name": [ln.name for ln in self.lines_list],
            "Line Code": [ln.linecode for ln in self.lines_list],
            "Max Load (%)": [ln.i_mag_max*100 for ln in self.lines_list],
        })
    
    def get_lines_tbl_df(self):
        return pd.DataFrame({
            "Name": [ln.name for ln in self.lines_list],
            "Line Code": [ln.linecode for ln in self.lines_list],
            "Length": [ln.length for ln in self.lines_list],
            "Max Load (%)": [ln.i_mag_max*100 for ln in self.lines_list],
        })
        
    def get_line_i_ts(self, line_name: str):
        ln = next(l for l in self.lines_list if l.name == line_name)
        return pd.DataFrame({
            "Time": ln.time,
            "i_mag": ln.i_mag,
            "i_ph": ln.i_ph,
        })
        
        
    def load_node_voltages(self):
        df: pd.DataFrame = pd.read_csv(self.filenames["voltages"])

        for col in df.columns:
            node = Nodes()
            node.name = col
            node.v_mag = df[col]
            node.time = [t for t in range(len(node.v_mag))]
            node.v_mag_max = max(node.v_mag)
            node.v_mag_min = min(node.v_mag)
            self.nodes_list.append(node)
        
    def get_nodes_tbl_df(self):
        return pd.DataFrame({
            "Name": [node.name for node in self.nodes_list],
            "V_mag_min": [node.v_mag_min for node in self.nodes_list],
            "V_mag_max": [node.v_mag_max for node in self.nodes_list],
        })
        
    def get_node_v_ts(self, node_name: str):
        node = next(n for n in self.nodes_list if n.name == node_name)
        return pd.DataFrame({
            "node": [node.name for n in node.time],
            "Time": node.time,
            "v_mag": node.v_mag,
        })
        
    def load_bus_info(self):
        df: pd.DataFrame = pd.read_csv(self.filenames["bus_info"])
        df['nodes'] = df['nodes'].apply(lambda x: ast.literal_eval(x))
        for idx, row in df.iterrows():
            bus = Bus()
            bus.name = row["bus"]
            bus.is_pcc = row['is_pcc']
            for num in row['nodes']:
                node = next(node for node in self.nodes_list if (bus.name + "." + str(num)) == node.name)
                bus.nodes.append(node)
            self.bus_list.append(bus)
            
    def get_pcc_min_voltage_summary(self):
        return pd.DataFrame({
            "PCC Bus": [bus.name for bus in self.bus_list if bus.is_pcc],
            "V_mag_min": [min([n.v_mag_min for n in bus.nodes]) for bus in self.bus_list if bus.is_pcc],
        })
    
    def get_bus_tbl_df(self):
        return pd.DataFrame({
            "Bus": [bus.name for bus in self.bus_list],
            "Is PCC": ["Y" if bus.is_pcc else "N" for bus in self.bus_list],
            "V_mag_min": [min([n.v_mag_min for n in bus.nodes]) for bus in self.bus_list],
            "V_mag_max": [min([n.v_mag_max for n in bus.nodes]) for bus in self.bus_list],
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
        self.time: list[float]
        self.kva_mag: list[float]
        self.kva_ph: list[float]
        self.kva_mag_max: float
        self.i_mag: list[float]
        self.i_ph: list[float]
        self.i_mag_max: float

class Lines():
    def __init__(self) -> None:
        self.name: str
        self.linecode: str
        self.length: float
        self.time: list[float]
        self.i_mag: list[float]
        self.i_ph: list[float]
        self.i_mag_max: float

class Nodes():
    def __init__(self) -> None:
        self.name: str
        self.time: list[float]
        self.v_mag: list[float]
        self.v_mag_min: float
        self.v_mag_max: float
        
class Bus():
    def __init__(self) -> None:
        self.name: str
        self.nodes: list[Nodes] = list()
        self.is_pcc: bool = False