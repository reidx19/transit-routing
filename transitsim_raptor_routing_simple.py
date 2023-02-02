"""
Runs the query algorithm
"""
import os
from pathlib import Path
user_directory = os.fspath(Path.home())
file_directory = r"\Documents\GitHub\transit-routing" #directory of bikewaysim outputs
homeDir = user_directory+file_directory
os.chdir(homeDir)

#%%

from RAPTOR.hypraptor import hypraptor
from RAPTOR.one_to_many_rraptor import onetomany_rraptor
from RAPTOR.rraptor import rraptor
from RAPTOR.std_raptor import raptor
from TBTR.hyptbtr import hyptbtr
from TBTR.one_many_tbtr import onetomany_rtbtr
from TBTR.rtbtr import rtbtr
from TBTR.tbtr import tbtr
from miscellaneous_func import *

#post processing specific
from datetime import datetime, timedelta, date
from shapely.ops import LineString, MultiLineString
import geopandas as gpd
import pandas as pd
import pickle
from tqdm import tqdm
import time
import glob

#suppress error message
import warnings
from shapely.errors import ShapelyDeprecationWarning
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning) 
warnings.filterwarnings("ignore", category=FutureWarning)

print_logo()

#get route type
route = pd.read_csv(r'GTFS/marta/route.txt')

raptor_settings = {
    'NETWORK_NAME': './marta',
    'MAX_TRANSFER': 2,
    'WALKING_FROM_SOURCE': 0,
    'CHANGE_TIME_SEC': 30,
    'PRINT_ITINERARY': 0,
    'OPTIMIZED': 0,
    'bike_thresh': 1 * 5280, #set initial biking threshold distance (from tcqsm page 5-20)
    'bikespd': 10, #set assummed avg bike speed in mph
    'first_time': datetime(2022, 11, 24, 9, 0, 0, 0), #9am
    'end_time': datetime(2022, 11, 24, 10, 15, 0, 0), #10am
    'timestep': timedelta(minutes=20), #in minutes 
    'timelimit': timedelta(hours=2), # in hours
    'impedance':'dist',
    'mode':'walk'
    }
            
impedance = raptor_settings['impedance']
mode = raptor_settings['mode']
trips_dir = os.fspath(rf'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/{mode}_{impedance}/trips')

#import network files
stops_file, trips_file, stop_times_file, transfers_file, stops_dict, stoptimes_dict, footpath_dict, routes_by_stop_dict, idx_by_route_stop_dict = read_testcase(
    raptor_settings['NETWORK_NAME'])

#print details
print_network_details(transfers_file, trips_file, stops_file)

#get variables
bike_thresh = raptor_settings['bike_thresh']
bikespd = raptor_settings['bikespd']

#turn stops file to gdf
stops_file = gpd.GeoDataFrame(stops_file, geometry=gpd.points_from_xy(stops_file['stop_lon'], stops_file['stop_lat']), crs='epsg:4326')
stops_file.to_crs('epsg:2240',inplace=True)
#stops_file.to_file('stops.geojson')

SOURCE = 3597
DESTINATION = 2952
D_TIME = datetime(2022, 11, 24, 9, 0, 0, 0)

output, pareto_optimal = raptor(SOURCE, DESTINATION, D_TIME, raptor_settings['MAX_TRANSFER'], 
                raptor_settings['WALKING_FROM_SOURCE'], raptor_settings['CHANGE_TIME_SEC'], raptor_settings['PRINT_ITINERARY'],
                routes_by_stop_dict, stops_dict, stoptimes_dict, footpath_dict, idx_by_route_stop_dict)

if pareto_optimal != None:
    #get number of transfers
    num_transfers = pareto_optimal[0][0]
    
    #always take one with fewest transfers
    pareto_optimal = pareto_optimal[0][1]

    #initialize edge list
    edge_list = []

    #create edge list
    #structure
    #leg[0] : walking or the boarding time if transit
    #leg[1] : starting transit stop
    #leg[2] : ending transit stop
    #leg[3] : if walking = travel time and if transit = egress time
    #leg[4] : only for transit = route and trip number
    
    #get rid of last walking leg
    while pareto_optimal[-1][0] == 'walking':
        pareto_optimal = pareto_optimal[:-1]
    
    for leg in pareto_optimal:
        #format if walking edge
        if leg[0] != 'walking':
            #create transit edge
            #lookup transit mode from route

            #extract route_id
            route_id = str.split(leg[4],'_')[0]
            
            #get transit type
            route_type = route[route['new_route_id'].astype(str)==route_id]['route_type'].item()        
            
            if (route_type == 1) | (route_type == '1'):
                tup = (leg[1],leg[2],leg[3]-leg[0],leg[4],'rail')
            elif (route_type == 3) | (route_type == '3'):
                tup = (leg[1],leg[2],leg[3]-leg[0],leg[4],'bus')
                
        else:
            #get the arrival time
            tup = (leg[1], leg[2], leg[3], 'walking')
            #tup = (leg[1],leg[2],leg[3].total_seconds(),'walking')                
        edge_list.append(tup)

    #get total transit travel time (final egress - first arrival)        
    transit_time = pareto_optimal[-1][3] - D_TIME
    
    output = (edge_list,transit_time,SOURCE,DESTINATION,num_transfers)

else:
    print('Not possible')