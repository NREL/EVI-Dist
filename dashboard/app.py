# EVI-DiST - v0.7.1a

import panel as pn
import io
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import datetime as dt
from tkinter import Tk, filedialog
import param
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
from version_info import version_name
#import logging
import asyncio

pn.extension(template='fast')
pn.extension('tabulator')
pn.extension('plotly')
pn.extension('terminal')
pn.extension(notifications=True)
pn.extension('mathjax')

#pn.extension(design="material", sizing_mode="stretch_width")
# pn.extension('ipywidgets')

pn.state.template.param.update(header_background="black")
pn.state.template.param.update(title=f"EVI-DiST - v{version_name}")
pl = pn.pipeline.Pipeline(inherit_params=False)

info = False
markdown_file_path = "dashboard/page_info.md"

def show_info(event):
    global info
    with open(markdown_file_path, 'r') as file:
        markdown_content = file.read()

    info_page = pn.pane.Markdown(markdown_content)
    #info_page = gen_info()   
    
    if info:
        app[0] = pn.Column(pl)
    else:
        #app[0] = pn.Column(info_page)
        app[0] = pn.Column(info_page)
    
    info = not info

info_text = pn.widgets.StaticText(value="This panel was designed to help you easily interact with EVI-Dist. For more information about how to use EVI-Dist and perform specific actions, please refer to:", 
                                  align=('center','center'))

info_button = pn.widgets.Button(name='TOGGLE INFO PAGE', button_type='primary', align=('center','center'))
info_button.on_click(show_info)

pn.Row(info_text, info_button).servable()


pl.add_stage('Mode selection', pgModes, ready_parameter='ready', auto_advance=True, next_parameter='next_page')

#Lite version stages
pl.add_stage('Choose Lite mode', pgLiteModes, ready_parameter='ready', auto_advance=True, next_parameter='next_page')
pl.add_stage('Load session', pgLoadSession)
pl.add_stage('Uploading input files', pgUpload, ready_parameter='ready', auto_advance=False)
pl.add_stage('Configurations', pgConfig)
pl.add_stage('Execution', pgExecution, ready_parameter='ready', auto_advance=False)
pl.add_stage('Displaying results', pgDisplay)

#Plus version stages
pl.add_stage('Plus: choose mode', pgPlusModes, ready_parameter='ready', auto_advance=True, next_parameter='next_page')
pl.add_stage('Plus: upload DSS file', pgPlusDSSUpload, ready_parameter='ready', auto_advance=False)
pl.add_stage('Plus: load session', pgPlusLoadSession)
pl.add_stage('Plus: run simulation', pgPlusRunSim, ready_parameter='ready', auto_advance=False)
pl.add_stage('Plus: display results', pgPlusDisplay, ready_parameter='ready', auto_advance=False)


pl.define_graph({'Mode selection': ('Choose Lite mode','Plus: choose mode'),
                 'Choose Lite mode': ('Uploading input files', 'Load session'),
                 'Uploading input files': 'Configurations',
                 'Configurations': 'Execution',
                 'Execution': 'Displaying results',
                 'Load session': 'Displaying results',
                 'Plus: choose mode': ('Plus: upload DSS file', 'Plus: load session'),
                 'Plus: load session': 'Plus: display results',
                 'Plus: upload DSS file': 'Plus: run simulation',
                 'Plus: run simulation': 'Plus: display results',
                 })

pn.state.pipeline = pl

app = pn.Column(pl)
# app = pn.Column(
#     pl.title,
#     pl.network,
#     pl.stage,
#     pl.prev_button,
#     pl.next_button
#     )

app.servable()
