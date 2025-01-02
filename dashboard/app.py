# EVI-DiST - v1.0
import panel as pn
import io
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import datetime as dt
from tkinter import Tk, filedialog
import param
import webbrowser
import os
from tornado.web import StaticFileHandler

# Import your page modules
from page_display import pgDisplay
from page_upload import pgUpload
from page_execution import pgExecution
from page_modes import pgModes
from page_configs import pgConfig
from page_info import gen_info
from page_plus_dss_upload import pgPlusDSSUpload
from page_plus_runsim import pgPlusRunSim
from page_plus_load_session import pgPlusLoadSession
from page_plus_modes import pgPlusModes
from page_load_session import pgLoadSession
from page_lite_modes import pgLiteModes
from page_plus_display import pgPlusDisplay
from page_plus_configs import pgPlusConfig
from version_info import version_name
from pathinit import EVIDIST_ROOT_PATH
# Initialize Panel with all required extensions
pn.extension('plotly', 'tabulator', 'terminal', 'mathjax', notifications=True)

class EVIDistApp:
    def __init__(self):
        self.init_pipeline()
        self.init_info_section()
        self.init_template()
       
    def init_pipeline(self):
        """Initialize the pipeline"""
        self.pl = pn.pipeline.Pipeline(inherit_params=False)
        
        # Add pipeline stages
        self.pl.add_stage('Mode selection', pgModes, ready_parameter='ready', auto_advance=True, next_parameter='next_page')
        
        # Lite version stages
        self.pl.add_stage('Choose Lite mode', pgLiteModes, ready_parameter='ready', auto_advance=True, next_parameter='next_page')
        self.pl.add_stage('Load session', pgLoadSession, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('Uploading input files', pgUpload, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('Configurations', pgConfig, ready_parameter='ready', next_parameter='next_page')
        self.pl.add_stage('Execution', pgExecution, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('Displaying results', pgDisplay)
        
        # Plus version stages
        self.pl.add_stage('[Plus] choose mode', pgPlusModes, ready_parameter='ready', auto_advance=True, next_parameter='next_page')
        self.pl.add_stage('[Plus] upload sim files', pgPlusDSSUpload, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('[Plus] configurations', pgPlusConfig, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('[Plus] load session', pgPlusLoadSession, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('[Plus] run simulation', pgPlusRunSim, ready_parameter='ready', auto_advance=False)
        self.pl.add_stage('[Plus] display results', pgPlusDisplay, ready_parameter='ready', auto_advance=False)
        
        # Define pipeline graph
        self.pl.define_graph({
            'Mode selection': ('Choose Lite mode','[Plus] choose mode'),
            'Choose Lite mode': ('Uploading input files', 'Load session'),
            'Uploading input files': 'Configurations',
            'Configurations': 'Execution',
            'Execution': 'Displaying results',
            'Load session': 'Displaying results',
            '[Plus] choose mode': ('[Plus] upload sim files', '[Plus] load session'),
            '[Plus] load session': '[Plus] display results',
            '[Plus] upload sim files': '[Plus] configurations',
            '[Plus] configurations': '[Plus] run simulation',
            '[Plus] run simulation': '[Plus] display results',
        })
        
        pn.state.pipeline = self.pl

    def init_info_section(self):
        """Initialize the info section"""
        docs_file = 'http://localhost:5007/docs/index.html'
        
        def show_info(event):
            webbrowser.open(docs_file)
        
        info_text = pn.widgets.StaticText(
            value="This panel was designed to help you easily interact with EVI-Dist. For more information about how to use EVI-Dist and perform specific actions, please refer to:",
            align=('center','center'),
            width=600
        )
        
        info_button = pn.widgets.Button(
            name='DOCUMENTATION PAGE',
            button_type='primary',
            align=('center','center')
        )
        info_button.on_click(show_info)
        
        self.info_section = pn.Row(info_text, info_button, width=900)

    def init_template(self):
        """Initialize the template"""
        self.template = pn.template.FastListTemplate(
            title=f"EVI-DiST - v{version_name}",
            main=[self.info_section, self.pl],
            header_background="black",
        )

    def get_template(self):
        """Return the template for serving"""
        return self.template
       
app = EVIDistApp()
template = app.get_template()
template.servable()
