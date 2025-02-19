import os
import sys
import copy
parent_directory = os.getcwd()

sys.path.append(parent_directory + "/modules")
sys.path.append(parent_directory)

from modules.data_structures import Signal
import panel as pn
from tkinter import Tk, filedialog
import param
import pandas as pd
import numpy as np
import datetime as dt
import folium
from bokeh.models.widgets.tables import NumberFormatter, BooleanFormatter
from ipyleaflet import Map as LeafletMap, Marker as LeafletMarker, MarkerCluster as LeafletCluster
from folium.plugins import MarkerCluster
from folium.map import Marker as FoliumMarker
import plotly.graph_objs as go
import plotly.express as px
from gen_text_stats import gen_text_stats
import json
import io
import zipfile
from modules.lite.coincidence_analysis import build_total_load_dict, plot_coincidence_and_transformer_sizing
import numbers
from actions import DataOperator
import matplotlib.pyplot as plt
from datetime import datetime

from plots import LinePlot, gen_plot_object
from tables import Table
from maps import Map
from collections import namedtuple

import pickle

class pgDisplay(param.Parameterized):

    file_names: param.Dict = param.Dict()
    configs: param.Dict = param.Dict()

    save_button: pn.widgets.Button = pn.widgets.Button(
        name='Save File')  # Change param.Action to pn.widgets.Button

    ready = param.Boolean(default=False)

    def __init__(self, **params):
        super().__init__(**params)

        self.paths = {}
        self.paths['premise_report'] = self.file_names['premise_report']
        self.paths['ev_adoption'] = self.file_names['ev_adoption']
        self.paths['ami_cust_lvl'] = self.file_names['ami_cust_lvl']
        self.paths['baseload_profiles_S'] = parent_directory + "/data/temp/baseload_profiles_S.csv"
        self.paths['baseload_profiles_P'] = parent_directory + "/data/temp/baseload_profiles_P.csv"
        self.paths['baseload_profiles_Q'] = parent_directory + "/data/temp/baseload_profiles_Q.csv"
        # Add baseload_profiles_P,Q,S and make sure they are also saved with correct names. 
        self.paths['ev_profiles'] = dict()
        self.paths['agg_profiles'] = dict()
        for cntl in self.configs['controller']:
            self.paths['ev_profiles'][cntl] = parent_directory + \
                "/data/temp/ev_profiles_" + cntl + ".csv"
            self.paths['agg_profiles'][cntl] = parent_directory + \
                "/data/temp/aggregated_profiles_" + cntl + ".csv"

        self.paths['mappings'] = parent_directory + \
            "/data/mappings/mappings.pkl"
        
        self.dop = DataOperator(self.paths, self.configs)
        if os.path.isfile(self.paths['ami_cust_lvl']):
            self.paths['total_load_dict'] = parent_directory + \
                "/data/temp/total_load_dict.pkl"
            if self.configs['run_selection'] == 'new':
                print("Total load dict is being generated! This may take some time.")
                pn.state.notifications.info(
                    'Coincidance analysis is now being performed after the simulations. This may take some time. Please wait until the analysis is completed and results are displayed!',
                    duration=10000)
                self.total_load_dict = build_total_load_dict(
                    ev_profiles_folder=parent_directory + '/data/temp/',
                    customer_ami_data=self.paths['ami_cust_lvl'],
                    mapping_file=parent_directory + '/data/temp/mapping.csv',
                    feeder=self.configs['feeder'],
                    conroller_types=self.configs['controller']
                )

                with open(self.paths['total_load_dict'], "wb") as file:
                    pickle.dump(self.total_load_dict, file)
            else:
                with open(self.paths['total_load_dict'], "rb") as file:
                    self.total_load_dict = pickle.load(file)

            self.figs = plot_coincidence_and_transformer_sizing(
                self.total_load_dict)
            for fig in self.figs:
                fig.tight_layout()
        else:
            self.total_load_dict = None

        self.pane_timeseries = pn.pane.Plotly()
        self.pane_comparison = pn.pane.Plotly()
        self.pane_histogram = pn.pane.Plotly()

        self.toggle_feeder_plots = pn.widgets.Switch(name='switch')
        self.select_controller = pn.widgets.Select(
            name='Select controller', options=self.configs['controller'])

        self.table = self.dop.get_table()
        self.table = self.table.rename(columns={'Bank Size': 'Bank Size (kVA)'})
        # THIS NEEDS TO BE FIXED
        self.obj_map = Map([39.638143, -104.788596], self.table)
        self.folium_pane = self.obj_map.map

        new_df = pd.DataFrame(
            columns=[
                'Num of EVs',
                'Num of Prems',
                'Max Overload (%)'])

        for i, row in self.table.iterrows():
            try:
                vehicle_count = len(
                    self.dop.mappings['xf_mappings'][self.configs['feeder']][row['Transformer ID']]['vehicles'])
                premise_count = len(
                    self.dop.mappings['xf_mappings'][self.configs['feeder']][row['Transformer ID']]['premises'])
                max_combined_load = self.dop.get_max_combined_load_by_xf_among_controllers(
                    row['Transformer ID'])
                if not (row['Bank Size (kVA)'] == 'Unknown'):
                    max_overload = round(
                        max_combined_load / int(row['Bank Size (kVA)']) * 100)
                else:
                    max_overload = np.nan

                new_row = {
                    'Num of EVs': vehicle_count,
                    'Num of Prems': premise_count,
                    'Max Overload (%)': max_overload}

                new_df = pd.concat(
                    [new_df, pd.DataFrame([new_row])], ignore_index=True)
            except Exception as e:
                # Handle the error (e.g., print the error message and continue)
                new_row = {
                    'Num of EVs': 0,
                    'Num of Prems': 0,
                    'Max Overload (%)': 0}
                new_df = pd.concat(
                    [new_df, pd.DataFrame([new_row])], ignore_index=True)
                print(f"Error transformer ID:{row['Transformer ID']}")
                # Optionally, you can continue to the next iteration
                continue

        self.table = pd.concat([self.table, new_df], axis=1)
        self.table['Max Overload (%)'] = pd.to_numeric(self.table['Max Overload (%)'], errors='coerce')
        self.table['Num of Prems'] = pd.to_numeric(self.table['Num of Prems'], errors='coerce')
        self.table['Num of EVs'] = pd.to_numeric(self.table['Num of EVs'], errors='coerce')
        self.table['Bank Size (kVA)'] = pd.to_numeric(self.table['Bank Size (kVA)'], errors='coerce')
        self.obj_table = Table(self.table.loc[:, [
                               'Transformer ID', 'Bank Size (kVA)', 'Num of Prems', 'Num of EVs', 'Max Overload (%)']])
        self.premise_table = self.obj_table.table

        self.save_button = pn.widgets.FileDownload(
            callback=self.get_zip_data,
            filename="downloaded_data.zip",
            button_type="primary",
            label="Save Sim Lite Data"
        )

        self.pane_stats = pn.Column(height=500)

        self.month_dict = {
            1: 'January',
            2: 'February',
            3: 'March',
            4: 'April',
            5: 'May',
            6: 'June',
            7: 'July',
            8: 'August',
            9: 'September',
            10: 'October',
            11: 'November',
            12: 'December'
        }

        starting_index = int()
        for index, row in self.table.iterrows():

            if str(row['Transformer ID']) in self.dop.base_load.columns:
                starting_index = index
                break
            else:
                None

        self.selected_row = self.table.iloc[[starting_index]]

    def save_session_JSON(self):
        save_session_dict = {
            "file_names": dict(self.file_names.items()),
            "configs": dict(self.configs.items())
        }

        for k, v in save_session_dict.items():
            for k2, v2 in v.items():
                if k2 == "month":
                    v[k2] = str(v2)

        return save_session_dict

    def save_file(self, event):
        file_name_input = pn.widgets.TextInput(
            name='ZIP File Name', value='saved_data.zip')

        def download_zip(event):
            # Get file name from input
            file_name = file_name_input.value

            # Create zip file in memory
            zip_buffer = self.get_zip_data()
            zip_buffer.seek(0)  # Reset the buffer position

            # Trigger the download
            return pn.io.file.download(zip_buffer, filename=file_name)

        download_button = pn.widgets.Button(
            name='Download', button_type='primary')
        download_button.on_click(download_zip)
        return pn.Column(file_name_input, download_button).servable()

    def get_zip_data(self):
        pn.state.notifications.info(
            'Data files are being saved and will be downloaded shortly.',
            duration=4000)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Add CSV files to ZIP
            for name, path in self.paths.items():
                if name == "ev_profiles":
                    for name2, path2 in path.items():
                        # Use original file names in ZIP
                        zip_file.write(
                            path2, arcname="ev_profiles_" + name2 + ".csv")
                elif name == "agg_profiles":
                    for name2, path2 in path.items():
                        # Use original file names in ZIP
                        zip_file.write(
                            path2, arcname="aggregated_profiles_" + name2 + ".csv")
                elif name == "mappings" or name == "total_load_dict":
                    zip_file.write(path, arcname=name + ".pkl")
                else:
                    if (name == 'ami_cust_lvl') and (path == ''):
                        continue
                    else:
                        # Use original file names in ZIP
                        zip_file.write(path, arcname=name + ".csv")

            # Add JSON data to ZIP
            json_data = json.dumps(
                dict(
                    self.save_session_JSON().items()),
                indent=4).encode('utf-8')
            # Save JSON with a specific name
            zip_file.writestr('session_info.json', json_data)

        zip_buffer.seek(0)  # Reset buffer position for reading

        return zip_buffer

    def get_selected_xf(self, xf_id, threshold):

        # time = np.arange(len(baseload))
        time = self.dop.get_time(self.select_controller.value)

        if self.toggle_feeder_plots.value:
            baseload = self.dop.get_feeder_load()
            agg_load = self.dop.get_agg_feeder_load()
            #ev_load = self.dop.get_agg_ev_load_by_feeder(self.select_controller.value) # No longer needed if obtained directly from ev_load_comp
            ev_load_comp = self.dop.get_agg_ev_load_by_feeder_comparison()
            title = "Feeder level"
        else:
            baseload = self.dop.get_base_load_by_xf_id(xf_id) # This now refers to "baseload_profiles_S" generated using P and Q profiles. 
            agg_load = self.dop.get_agg_xf_load_by_xf_id(xf_id)
            #ev_load = self.dop.get_agg_ev_load_by_xf_id(xf_id, self.select_controller.value) # This refers to the aggregated EV load for the selected controller.
            ev_load_comp = self.dop.get_agg_ev_load_by_xf_id_comparison(xf_id) # This refers to the aggregated EV load for all controllers. e.g., ev_load_comp['controller_name']
            # TODO: ev_load itself may be reduntant as those profiles are already included in ev_load_comp. This offers some performance improvements and freeing up RAM. 
            title = 'XF ID: ' + str(xf_id)
            each_ev_load = self.dop.get_each_ev_load_for_xf(xf_id, self.select_controller.value) # This refers to the individual EV load for the selected controller. There could exist some improvements by removing code dublication. It fetches the same data multiple times.            title = 'XF ID: ' + str(xf_id)
            signal_each_ev_load = dict()
            for key in each_ev_load.keys():
                signal_each_ev_load[key] = Signal(
                    time, each_ev_load[key], key, self.dop.res * 60, ('m', 'kW'))

        signal_base_load = Signal(
            time, baseload, 'Baseload', self.dop.res * 60, ('m', 'kW'))
        signal_ev_load = Signal(
            time, ev_load_comp[self.select_controller.value], 'EV load', self.dop.res * 60, ('m', 'kW'))

        #signal_ev_load_comp = dict()
        signal_combined_load_comp = dict()
        for cntrl in self.configs['controller']:
            signal_combined_load_comp[cntrl] = Signal(time, agg_load[cntrl], cntrl, self.dop.res * 60, ('m', 'kW'))

        #signal_combined_load = signal_base_load + signal_ev_load
        signal_combined_load = copy.copy(signal_combined_load_comp[self.select_controller.value])
        signal_combined_load.name = 'Baseload+EV'

        if not self.toggle_feeder_plots.value:
            dataset = {
                'baseload': signal_base_load.y,
                'evload': signal_ev_load.y,
                'total': signal_combined_load.y,
                'ID': str(xf_id)}
            gen_text_stats(
                self.pane_stats,
                dataset,
                self.dop,
                threshold,
                self.select_controller.value)
        else:
            # if customer level ami data uploaded, show coincidence analysis
            # plots, otherwise show nothing
            if self.total_load_dict is not None:

                mlp_pane = []
                # for i, slp in enumerate(self.slps):
                for i, fig in enumerate(self.figs):
                    # mlp_pane.append(pn.pane.Matplotlib(slp.fig, dpi=100))
                    mlp_pane.append(pn.pane.Matplotlib(fig, dpi=100))
                self.pane_stats[:] = [
                    pn.Column(
                        *mlp_pane,
                        scroll=True,
                        height=425)]
            else:
                self.pane_stats[:] = [
                    pn.Column(
                        "Toggle off **Feeder level plots** to see statistics for individual transformers.",
                        """(You can view additional feeder-level plots, such as coincidence analysis, <br/>
                                                    by uploading customer-level AMI data for the selected feeder on the **Configurations** page.)""")]

        x = float(self.selected_row['Longitude_X'])
        y = float(self.selected_row['Latitude_Y'])

        self.obj_map.m.fit_bounds(
            [[y - 0.0001, x - 0.0001], [y + 0.0001, x + 0.0001]])
        self.obj_map.m.fit_bounds(
            [[y - 0.0001, x - 0.0001], [y + 0.0001, x + 0.0001]])
        self.folium_pane.object = self.obj_map.m

        param_for_timeseries = dict()
        param_for_timeseries['type'] = 'timeseries'
        param_for_timeseries['xlabel'] = f"Time (day) in {self.month_dict[self.configs['month']]}"
        param_for_timeseries['ylabel'] = 'Power [kVA]'
        param_for_timeseries['title'] = title
        param_for_timeseries['theme'] = 'plotly_white' if pn.config.theme == 'default' else 'plotly_dark'
        param_for_timeseries['width'] = 800
        param_for_timeseries['height'] = 425
        param_for_timeseries['fontsize'] = 14

        param_for_histogram = dict()
        param_for_histogram['type'] = 'histogram'
        param_for_histogram['xlabel'] = 'Power [kVA]'
        param_for_histogram['ylabel'] = 'Counts'
        param_for_histogram['title'] = title
        param_for_histogram['theme'] = 'plotly_white' if pn.config.theme == 'default' else 'plotly_dark'
        param_for_histogram['width'] = 650
        param_for_histogram['height'] = 425
        param_for_histogram['fontsize'] = 14

        obj_timeseries = gen_plot_object(
            signal_base_load, param_for_timeseries)
        obj_timeseries.add_trace(signal_combined_load, color_seq=1)
        obj_timeseries.add_trace(signal_ev_load, color_seq=2)
        if not self.toggle_feeder_plots.value:
            for i, signal in enumerate(signal_each_ev_load.keys()):
                obj_timeseries.add_trace(
                    signal_each_ev_load[signal],
                    color_seq=3 + i,
                    dash='dashdot')
        fig_timeseries = obj_timeseries.gen_plot()

        obj_comparison = gen_plot_object(
            signal_combined_load_comp[self.configs['controller'][0]], param_for_timeseries)
        for i in range(1, len(self.configs['controller'])):
            obj_comparison.add_trace(
                signal_combined_load_comp[self.configs['controller'][i]], color_seq=i)
        fig_comparsion = obj_comparison.gen_plot()

        obj_histogram = gen_plot_object(signal_base_load, param_for_histogram)
        obj_histogram.add_trace(signal_combined_load, color_seq=1)
        obj_histogram.add_trace(signal_ev_load, color_seq=2)
        fig_histogram = obj_histogram.gen_plot()

        self.pane_timeseries.object = fig_timeseries
        self.pane_histogram.object = fig_histogram
        self.pane_comparison.object = fig_comparsion

    def panel(self):
        self.get_selected_xf(int(self.selected_row['Transformer ID']), threshold=int(
            self.selected_row['Bank Size (kVA)']))

        def click(self, event):

            self.selected_row = self.table.iloc[event.row]
            threshold = int(self.selected_row['Bank Size (kVA)'])
            xf = int(self.selected_row['Transformer ID'])
            x = self.selected_row['Longitude_X']
            y = self.selected_row['Latitude_Y']

            self.get_selected_xf(xf, threshold)

        self.premise_table.on_click(lambda event: click(self, event))

        def on_toggle(event):
            """Event action for toggling whether plots show feeder waveforms or transformer waveforms.

            Args:
                event (_type_): _description_
            """
            self.get_selected_xf(int(self.selected_row['Transformer ID']), threshold=int(
                self.selected_row['Bank Size (kVA)']))

        def on_select(event):
            """Event action for selecting the controller type.

            Args:
                event (_type_): _description_
            """
            self.get_selected_xf(int(self.selected_row['Transformer ID']), threshold=int(
                self.selected_row['Bank Size (kVA)']))
            # Update results for the selected controller

        settings1 = pn.Column(
            pn.Row(
                pn.widgets.StaticText(
                    value='Show feeder level plots'),
                self.toggle_feeder_plots,
                self.select_controller),
            self.pane_timeseries)
        settings2 = pn.Column(
            pn.Row(
                pn.widgets.StaticText(
                    value='Show feeder level plots'),
                self.toggle_feeder_plots,
                self.select_controller),
            self.pane_histogram)
        settings3 = pn.Column(
            pn.Row(
                pn.widgets.StaticText(
                    value='Show feeder level plots'),
                self.toggle_feeder_plots),
            self.pane_comparison)

        self.toggle_feeder_plots.param.watch(on_toggle, 'value')
        self.select_controller.param.watch(on_select, 'value')

        css = """
        .center-content .bk {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        """
        pn.config.raw_css.append(css)

        if self.configs['adoption'] == "":
            self.configs['adoption'] = "Untitled"

        pane_des = pn.pane.Markdown(
            f"""<span style="font-size:12pt">Feeder: <b>{self.configs['feeder']}</b>, Controller: <b>{self.configs['controller']}</b>, Adoption: <b>{self.configs['adoption']}</b>,  Load profile: <b>{self.configs['load_profile']}</b>
                                        </span>""")

        tabs = pn.Tabs(
            ('Time series', settings1),
            ('Comparison', settings3),
            ('Histogram', settings2),
            ('Stats', pn.Column(
                pn.Row(
                    pn.widgets.StaticText(value='Show feeder level plots'),
                    *([self.toggle_feeder_plots, self.select_controller] if self.toggle_feeder_plots.value else [self.toggle_feeder_plots])
                ),
                self.pane_stats
            )),
            ('Location', self.folium_pane)
        )

        left = pn.Spacer(height=500, styles={'flex': '1 1 auto'})
        middle = pn.Row(
            self.premise_table,
            tabs,
            styles={'flex': '2 1 auto'},
        )

        right = pn.Spacer(height=500, styles={'flex': '1 1 auto'})

        app = pn.Column(
            pane_des,
            pn.Row(
                self.premise_table,
                tabs),
            self.save_button)

        return app
