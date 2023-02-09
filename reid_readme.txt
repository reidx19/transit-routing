transit_raptor_routing.py - script for running raptor algorithm. Needs marta gtfs data and tranfers. The script takes trip parquet files made in the find_candidate_stops.py script in the TransitSimDev repository and outputs the optimal transit routes (if possible given the constraints) as python dictionaries saved as pickles.

transitsim_raptor_mapping.py - script for mapping trips. Can be used to examine specific trips in GIS. Each trip is turned into a GeoJSON file composed of multiple linestrings for each segment of the trip (bike/walk, transit mode)
