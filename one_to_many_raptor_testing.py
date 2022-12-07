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
from datetime import datetime, timedelta
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

print_logo()

#set network name
NETWORK_NAME = './marta'

#import network files
stops_file, trips_file, stop_times_file, transfers_file, stops_dict, stoptimes_dict, footpath_dict, routes_by_stop_dict, idx_by_route_stop_dict = read_testcase(
    NETWORK_NAME)

#turn stops file to gdf
stops_file = gpd.GeoDataFrame(stops_file, geometry=gpd.points_from_xy(stops_file['stop_lon'], stops_file['stop_lat']), crs='epsg:4326')
stops_file.to_crs('epsg:2240',inplace=True)
stops_file.to_file(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\stops.gpkg')

#get route type
route = pd.read_csv(r'GTFS/marta/route.txt')

#print details
print_network_details(transfers_file, trips_file, stops_file)

# Query parameters
#SOURCE, DESTINATION, DESTINATION_LIST = 36, 52, [52, 43]
#D_TIME = stop_times_file.arrival_time.sort_values().iloc[0]
MAX_TRANSFER, WALKING_FROM_SOURCE, CHANGE_TIME_SEC = 2, 0, 2
PRINT_ITINERARY, OPTIMIZED = 0, 0

#set the time that people left their house
true_start = datetime(2022, 11, 24, 8, 0, 0, 0)

#import snapped tazs and stops
with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\snapped_tazs.pkl','rb') as fh:
    snapped_tazs = pickle.load(fh)
with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\snapped_stops.pkl','rb') as fh:
    snapped_stops = pickle.load(fh)

#import bike path geo
with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\all_paths.pkl','rb') as fh:
    all_paths = pickle.load(fh)

#make sure thing is str
def check_type(item):
    if type(item) == float:
        item = str(int(item))
    elif type(item) == int:
        item = str(item)      
    return item

#%% import trips
trips_dir = os.fspath(r'C:/Users/tpassmore6/Documents/TransitSimData/Data/trips')
all_trips = glob.glob(os.path.join(trips_dir,"*.csv"))

#trips = pd.read_csv(r'C:/Users/tpassmore6/Documents/TransitSimData/Data/trips/555.csv')
run_time_transit = []

print('Running raptor algorithm')
for trip in tqdm(all_trips):
    
    #record starting time
    time_start = time.time()
    
    #import trips file
    trips = pd.read_csv(trip)
    
    #get start taz name
    taz_name = str(trips['from_TAZ'][0])
    
    # #check to see if folder already exists
    # if os.path.exists(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\mapped\{taz_name}'):    
    #     print(f'Begin routing from {taz_name} to all other TAZs')
    
    #turn these to datetime/timedelta
    trips['arrival_time'] = pd.to_datetime(trips['arrival_time'])
    trips['final_leg'] = pd.to_timedelta(trips['final_leg'])

    #create trip dict
    trip_dict = {}
    
    #bring in exclude routes if it exists
    if os.path.exists(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\exclude_routes.pkl'):
        with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\exclude_routes.pkl','rb') as fh:
            exclude_routes = pickle.load(fh)
        trips['exclude_check'] = list(zip(trips['route_id1'],trips['route_id2']))
        before = trips.shape[0]
        trips = trips[-trips['exclude_check'].isin(exclude_routes)]
        trips.drop(columns=['exclude_check'],inplace=True)
        #print(f'{before-trips.shape[0]} trips excluded')
    else:
        exclude_routes = set()

    #if trips is empty check    
    if trips.shape[0] != 0:
        #print(rf'No possible bike transit trips from {taz_name}')
    #else:
        #print(f'Begin routing from {taz_name} to all other TAZs')
        #TODO find more efficient way to do this
        for idx, row in trips.iterrows():
        # for idx, row in tqdm(trips.iterrows(),total=trips.shape[0]):
          
            SOURCE = row['from_stop']
            DESTINATION = row['to_stop']
            D_TIME = row['arrival_time']
            
            start_route = row['route_id1']
            end_route = row['route_id2']
            
            output, pareto_optimal = raptor(SOURCE, DESTINATION, D_TIME, MAX_TRANSFER, 
                            WALKING_FROM_SOURCE, CHANGE_TIME_SEC, PRINT_ITINERARY,
                            routes_by_stop_dict, stops_dict, stoptimes_dict, footpath_dict, idx_by_route_stop_dict)
            
            if pareto_optimal == None:
                exclude_routes.add((start_route,end_route))
            else:
                #get number of transfers
                num_transfers = pareto_optimal[0][0]
                
                #always take one with fewest transfers
                pareto_optimal = pareto_optimal[0][1]
            
                edge_list = []
            
                #create edge list
                for leg in pareto_optimal:
                    #format if walking edge
                    if leg[0] != 'walking':
                        #
                        tup = (leg[1],leg[2],leg[-1],leg[0],leg[3],'transit')
                    elif leg[0] == 'walking':
                        #get the arrival time
                        tup = (leg[1], leg[2], leg[-1], 'walking')
                        #tup = (leg[1],leg[2],leg[3].total_seconds(),'walking')                
                    edge_list.append(tup)
        
                #don't need last walking leg
                while edge_list[-1][-1] == 'walking':
                    edge_list = edge_list[:-1]
        
                #get total transit travel time        
                transit_time = edge_list[-1][-2] - D_TIME
                
                #get total travel time from start
                travel_time = (edge_list[-1][-2] + row[-1]) - true_start
                
                #time limit
                if travel_time < timedelta(hours=1.5):
                        
                    #if the key already exists, check to see if lower travel time
                    if (row['from_TAZ'],row['to_TAZ']) in set(trip_dict.keys()):
                        if travel_time < trip_dict[(row['from_TAZ'],row['to_TAZ'])][1]:
                            #add a transfers requirement here
                            trip_dict[row['from_TAZ'],row['to_TAZ']] = (edge_list,travel_time,SOURCE,DESTINATION,num_transfers)
                    else:
                        trip_dict[row['from_TAZ'],row['to_TAZ']] = (edge_list,travel_time,SOURCE,DESTINATION,num_transfers)
                    
        #print which trips aren't feasible with transit
        #print(f'Transit routing took {round(((time.time() - time_start)/60), 2)} minutes')
        run_time_transit.append(round(((time.time() - time_start)/60), 2))
      
        #export trip dict
        with open(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\trip_dicts\trip_dict_{taz_name}.pkl','wb') as fh:
            pickle.dump(trip_dict,fh)
        
        #export exclude routes
        with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\exclude_routes.pkl','wb') as fh:
            pickle.dump(exclude_routes,fh)
            
        # #post processing
        # #create geo for trips
        # print('Creating geo')
        # for x in tqdm(trip_dict.keys()):
        #     start_taz = check_type(x[0])
        #     end_taz = check_type(x[1])
        #     start_transit = check_type(trip_dict[x][2])
        #     end_transit = check_type(trip_dict[x][3])
        
        #     start_tazN = snapped_tazs[start_taz]
        #     end_tazN = snapped_tazs[end_taz]
        #     start_transitN = snapped_stops[start_transit]
        #     end_transitN = snapped_stops[end_transit]
        
        #     #get bike edge if available
        #     if (start_tazN,start_transitN) in all_paths.keys():
        #         bike_edge1 = all_paths[(start_tazN,start_transitN)]
        #     else:
        #         bike_edge1 = None
        #     if (end_transitN,end_tazN) in all_paths.keys():
        #         bike_edge2 = all_paths[(end_transitN,end_tazN)]
        #     else:
        #         bike_edge2 = None
                
        #     #get transit edges
        #     edge_list = trip_dict[x][0]
        
        #     transit_edges = []
        #     route_types = []
        
        #     #TODO function for getting transit shapes instead of connnecting start/end nodes
        #     for edge in edge_list:
                
        #         #get start station, end station, and tripid
        #         start = edge[0]
        #         end = edge[1]
                
        #         #get transit specific info
        #         if edge[-1] == 'transit':
        #             trip_id = check_type(edge[2])
        
        #             #extract route_id
        #             route_id = str.split(trip_id,'_')[0]
                    
        #             #get transit type
        #             route_type = route[route['new_route_id'].astype(str)==route_id]['route_type'].item()
                    
        #             route_types.append(route_type)
        #         else:
        #             route_types.append('walking')
                
        #         #get start and end stops
        #         start_point = stops_file.loc[stops_file['stop_id'] == start,'geometry'].drop_duplicates().item()
        #         end_point = stops_file.loc[stops_file['stop_id'] == end,'geometry'].drop_duplicates().item()
        
        #         #make line
        #         line = LineString([start_point,end_point])
        
        #         #replace the edge
        #         transit_edges.append(line) 
        
        
        #     if (bike_edge1 is not None) & (bike_edge2 is not None):
        #         route_types = ['bike'] + route_types + ['bike']
        #         geometry = [bike_edge1] + transit_edges + [bike_edge2]
        #     elif bike_edge1 is None:
        #         route_types = route_types + ['bike']
        #         geometry = transit_edges + [bike_edge2]
        #     elif bike_edge2 is None:
        #         route_types = ['bike'] + route_types
        #         geometry = [bike_edge1] + transit_edges
        
        #     #create gdf
        #     gdf = pd.DataFrame(data={'mode':route_types,'geometry':geometry})
        #     gdf = gpd.GeoDataFrame(gdf,geometry='geometry',crs='epsg:2240')
        
        #     #export
        #     trip_name = str(x[0]) + '_' + str(x[1])
        
        #     #create new folder
        #     if not os.path.exists(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\mapped\{start_taz}'):
        #         os.makedirs(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\mapped\{start_taz}') 
            
        #     gdf.to_file(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\mapped\{start_taz}\{trip_name}.geojson',driver='GeoJSON')
        #     #gdf.to_file(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\mapped\testing.gpkg',layer=trip_name,driver='GPKG')
          

# else:
#     print(f'Routing from {taz_name} already completed')


