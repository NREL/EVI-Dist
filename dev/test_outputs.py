import os
import sys
sys.path.append(os.getcwd())
from pathinit import EVIDIST_ROOT_PATH
import pandas as pd

linecurrents = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/MEAD2104_linecurrents.csv")
max_row_list = list()
for col in linecurrents.columns:
    max_row_list.append(max([str(l) for l in linecurrents[col]]))
print("linecurrents had max value of ", max(max_row_list))

trnscurrents = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/MEAD2104_trnscurrents.csv")
max_row_list = list()
for col in trnscurrents.columns:
    max_row_list.append(max([str(l) for l in trnscurrents[col]]))
print("trnscurrents had max value of ", max(max_row_list))

trnskva = pd.read_csv(EVIDIST_ROOT_PATH + "/data/temp_sim_plus/MEAD2104_trnskva.csv")
max_row_list = list()
for col in trnskva.columns:
    max_row_list.append(max([str(l) for l in trnskva[col]]))
print("trnskva had max value of ", max(max_row_list))
