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


def get_times(first_time,end_time,timestep):
    
    times = [first_time]
    
    reps = int(round((end_time - first_time) / timestep,0))
    
    for x in range(0,reps,1):
        times.append(times[-1] + timestep)
        
    return times

#make sure thing is str
def check_type(item):
    if type(item) == float:
        item = str(int(item))
    elif type(item) == int:
        item = str(item)      
    return item

# new format
# 'src_taz','dest_taz','src_stop','dest_stop','first_leg','last_leg'

def run_raptor(all_trips,impedance,raptor_settings):
    print('Running raptor algorithm')
    
    #import network files
    stops_file, trips_file, stop_times_file, transfers_file, stops_dict, stoptimes_dict, footpath_dict, routes_by_stop_dict, idx_by_route_stop_dict = read_testcase(
        raptor_settings['NETWORK_NAME'])

    #print details
    print_network_details(transfers_file, trips_file, stops_file)
    
    #get list of times
    start_times = get_times(raptor_settings['first_time'],raptor_settings['end_time'],raptor_settings['timestep'])
    
    #get variables
    bike_thresh = raptor_settings['bike_thresh']
    bikespd = raptor_settings['bikespd']
    
    #turn stops file to gdf
    stops_file = gpd.GeoDataFrame(stops_file, geometry=gpd.points_from_xy(stops_file['stop_lon'], stops_file['stop_lat']), crs='epsg:4326')
    stops_file.to_crs('epsg:2240',inplace=True)
    
    #do for each start time
    for start_time in start_times:
        for trip in all_trips:
            
            #record starting time
            time_start = time.time()
            
            #import trips file
            trips = pd.read_parquet(trip)
            
            if raptor_settings['one_trip'] == True:
                start = raptor_settings['start']
                end = raptor_settings['end']
                trips = trips.loc[trips['src_taz']==start and trips['dest_taz']==end,:]
            
            if trips.shape[0] == 0:
                if raptor_settings['one_trip'] == True:
                    return
                else:
                    print(f'No trips possible from {trip}')
            else:
            
                #get start taz name
                taz_name = str(trips['src_taz'][0])
                
                #get actual first leg time
                trips['first_leg'] = pd.to_timedelta(trips['first_leg'] / 5280 / bikespd * 60 * 60, unit='s')
            
                #find actual final leg time
                trips['last_leg'] = pd.to_timedelta(trips['last_leg'] / 5280 / bikespd * 60 * 60, unit='s')
            
                #get first arrival time (needs to be actual time)
                trips['arrival_time'] = start_time + trips['first_leg']
            
                #create trip dict to put final results in
                trip_dict = {}
            
                #if trips is empty check    
                if trips.shape[0] > 0:
                    #TODO find more efficient way to do this
                    for idx, row in tqdm(trips.iterrows(),total=trips.shape[0]):
                      
                        SOURCE = int(row['src_stop'])
                        DESTINATION = int(row['dest_stop'])
                        D_TIME = row['arrival_time']
                        
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
                            
                            #get total travel time from start (fianl arrival time - departure time)
                            travel_time = pareto_optimal[-1][3] + row['last_leg'] - start_time
                            
                            #time limit of 60 mins
                            if travel_time < raptor_settings['timelimit']:
                                #toss out if two bus routes used
                                if len([x for x in edge_list if x[-1] == 'bus']) < 2:
                                    #if the key already exists, check to see if lower travel time/transfers
                                    if (row['src_taz'],row['dest_taz']) in set(trip_dict.keys()):
                                        #if lower travel time, replace
                                        if (travel_time < trip_dict[(row['src_taz'],row['dest_taz'])][2]):
                                            # #select the one with fewer transfers
                                            # if (num_transfers <= trip_dict[(row['src_taz'],row['dest_taz'])][-1]):
                                            #add a transfers requirement here
                                            trip_dict[row['src_taz'],row['dest_taz']] = (edge_list,transit_time,travel_time,SOURCE,DESTINATION,num_transfers)
                                    else:
                                        trip_dict[row['src_taz'],row['dest_taz']] = (edge_list,transit_time,travel_time,SOURCE,DESTINATION,num_transfers)
                                        
                    #get trips that aren't feasible with transit 
                    not_possible = [x for x in set(trips.dest_taz) if x not in [x[1] for x in trip_dict.keys()]]
                    
                    #get run time
                    run_time_transit = round(((time.time() - time_start)/60), 2)        
                    metadata = {'not_possible':not_possible,'run_time':run_time_transit}
                    
                    #make file name
                    time_name = f'{start_time.hour}_{start_time.minute}'
                    mode = raptor_settings['mode']
                    
                    #create new folder
                    if not os.path.exists(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{mode}_{impedance}\trip_dicts\{taz_name}'):
                        os.makedirs(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{mode}_{impedance}\trip_dicts\{taz_name}')
                    if not os.path.exists(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{mode}_{impedance}\metadata\{taz_name}'):
                        os.makedirs(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{mode}_{impedance}\metadata\{taz_name}')
                        
                    #export trip dict and metadata
                    with open(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{mode}_{impedance}\trip_dicts\{taz_name}\{time_name}.pkl','wb') as fh:
                        pickle.dump(trip_dict,fh)
                    with open(rf'C:\Users\tpassmore6\Documents\TransitSimData\Data\Outputs\{mode}_{impedance}\metadata\{taz_name}\{time_name}.pkl','wb') as fh:
                        pickle.dump(metadata,fh)
            
            # #export exclude routes
            # with open(r'C:\Users\tpassmore6\Documents\TransitSimData\Data\exclude_trips.pkl','wb') as fh:
            #     pickle.dump(exclude_routes,fh)
    
#make a one trip version
def one_trip(start_taz,end_taz,D_TIME,raptor_settings):
    

    return output
            
#%% testing

print_logo()

#get route type
route = pd.read_csv(r'GTFS/marta/route.txt')

raptor_settings = {
    'NETWORK_NAME': './marta',
    'MAX_TRANSFER': 1,
    'WALKING_FROM_SOURCE': 0,
    'CHANGE_TIME_SEC': 30,
    'PRINT_ITINERARY': 0,
    'OPTIMIZED': 0,
    'bike_thresh': 0.5 * 5280, #set initial biking threshold distance (from tcqsm page 5-20)
    'bikespd': 2.5, #set assummed avg bike speed in mph
    'first_time': datetime(2022, 11, 24, 9, 0, 0, 0), #9am
    'end_time': datetime(2022, 11, 24, 10, 15, 0, 0), #10am
    'timestep': timedelta(minutes=20), #in minutes 
    'timelimit': timedelta(hours=1), # in hours
    'impedance':'dist',
    'mode':walk,
    'one_trip':True,
    'start':'553',
    'end':'642'
    }
            
impedance = raptor_settings['impedance']
mode = raptor_settings['mode']
trips_dir = os.fspath(rf'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/{mode}_{impedance}/trips')

#selected trips
select_tazs = ['288','553','411','1071']
all_trips = [ trips_dir + rf'/{taz}.parquet' for taz in select_tazs]

run_raptor(all_trips,impedance,raptor_settings)

#%% settings

print_logo()

#get route type
route = pd.read_csv(r'GTFS/marta/route.txt')

raptor_settings = {
    'NETWORK_NAME': './marta',
    'MAX_TRANSFER': 1,
    'WALKING_FROM_SOURCE': 0,
    'CHANGE_TIME_SEC': 30,
    'PRINT_ITINERARY': 0,
    'OPTIMIZED': 0,
    'bike_thresh': 2.5 * 5280, #set initial biking threshold distance (from tcqsm page 5-20)
    'bikespd': 10, #set assummed avg bike speed in mph
    'first_time': datetime(2022, 11, 24, 9, 0, 0, 0), #9am
    'end_time': datetime(2022, 11, 24, 10, 15, 0, 0), #10am
    'timestep': timedelta(minutes=20), #in minutes 
    'timelimit': timedelta(hours=1), # in hours
    'impedance':'dist',
    'mode':'bike'
    }
            
impedance = raptor_settings['impedance']
mode = raptor_settings['mode']
trips_dir = os.fspath(rf'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/{mode}_{impedance}/trips')

#selected trips
select_tazs = ['288','553','411','1071']
all_trips = [ trips_dir + rf'/{taz}.parquet' for taz in select_tazs]

run_raptor(all_trips,impedance,raptor_settings)


#%% just walking

print_logo()

#get route type
route = pd.read_csv(r'GTFS/marta/route.txt')

raptor_settings = {
    'NETWORK_NAME': './marta',
    'MAX_TRANSFER': 1,
    'WALKING_FROM_SOURCE': 0,
    'CHANGE_TIME_SEC': 30,
    'PRINT_ITINERARY': 0,
    'OPTIMIZED': 0,
    'bike_thresh': 0.5 * 5280, #set initial biking threshold distance (from tcqsm page 5-20)
    'bikespd': 2.5, #set assummed avg bike speed in mph
    'first_time': datetime(2022, 11, 24, 9, 0, 0, 0), #9am
    'end_time': datetime(2022, 11, 24, 10, 15, 0, 0), #10am
    'timestep': timedelta(minutes=20), #in minutes 
    'timelimit': timedelta(hours=1), # in hours
    'mode': 'walk'
    }
            
# import trips
impedance = 'dist'
mode = raptor_settings['mode']
trips_dir = os.fspath(rf'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/{mode}_{impedance}/trips')


#selected trips
select_tazs = ['288','553','411','1071']#1326
all_trips = [trips_dir + rf'\{taz}.parquet' for taz in select_tazs]

run_raptor(all_trips,impedance,raptor_settings)


#%% get bikesheds
#left off here
# import pandas as pd
# import os

# impedance = 'dist'
# trips_dir = os.fspath('C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/trip_dicts')
# tazs= glob.glob(os.path.join(trips_dir,rf"{impedance}/*.pkl"))

# for taz in tqdm(tazs):
    
#     #read in trip dict
#     trip_dict = pd.read_pickle(taz)

#     #process text
#     file_path = os.path.split(taz)[-1].split('.pkl')[0]

#     #get taz name
#     start_taz = file_path.split('_')[0]
    
#     #get start time
#     start_time = file_path.split('_',1)[1]

#     #read tazs
#     tazs = gpd.read_file('C:/Users/tpassmore6/Documents/BikewaySimData/base_shapefiles/arc/Model_Traffic_Analysis_Zones_2020/Model_Traffic_Analysis_Zones_2020.shp')
#     tazs.to_crs('epsg:2240',inplace=True)
#     tazs = tazs[['FID_1','geometry']]
#     tazs['FID_1'] = tazs['FID_1'].astype(str)
    
#     #each key is a taz pair
#     end_taz = set([x[1] for x in trip_dict.keys()])
    
#     #get geo
#     end_taz = tazs[tazs['FID_1'].isin(end_taz)]
#     end_taz['start_taz'] = start_taz
#     end_taz['tup'] = list(zip(end_taz['start_taz'],end_taz['FID_1']))
    
#     #reduce dict
#     mapping_dict = { x: trip_dict[x][2] for x in trip_dict.keys()}
    
#     #add travel time
#     end_taz['transit_travel_time'] = end_taz['tup'].map(mapping_dict) 
    
#     #convert datetime to minutes
#     end_taz['transit_travel_time'] = end_taz['transit_travel_time'].apply(lambda x: x.total_seconds() / 60)
    
#     #clean up and export
#     end_taz = end_taz[['FID_1','transit_travel_time','geometry']]
#     end_taz.to_file(f'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/bikesheds/{start_taz}.gpkg',layer=f'walk_transit_{start_time}')




#%% inspect metadata



#%% imp version

# # import trips
# trips_dir = os.fspath(r'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/trips/imp_dist')

# #selected trips
# select_tazs = ['448','411','1272','225']
# all_trips = [f'C:/Users/tpassmore6/Documents/TransitSimData/Data/Outputs/trips/imp_dist\\{taz}.parquet' for taz in select_tazs]


# run_raptor(all_trips,impedance,raptor_settings)