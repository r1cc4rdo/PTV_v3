from datetime import datetime, timedelta
from dateutil import tz

ptv = None  # Public Transport Victoria API
gmaps = None  # Google Maps API


def setup_ptv(ptv_object):
    global ptv
    ptv = ptv_object
    return ptv


def setup_gmaps(gmaps_object):
    global gmaps
    gmaps = gmaps_object
    return gmaps


def parse_utc(utc_string):
    """
    Allows for parsing UTC strings either without fractional seconds digits,
    or with them, regardless of their lenght (Python/C does consider malformed
    anything with more than 6 digits after the dot).

    >>> parse_utc('2024-05-17T01:00:27Z')
    datetime.datetime(2024, 5, 17, 1, 0, 27, tzinfo=tzutc())
    
    >>> parse_utc('2024-05-17T01:02:36.240509912Z')
    datetime.datetime(2024, 5, 17, 1, 2, 36, 240509, tzinfo=tzutc())
    """
    assert utc_string.endswith('Z')
    utc_string = utc_string[:-1]
    utc_format = '%Y-%m-%dT%H:%M:%S'
    
    if '.' in utc_string:  # parse fractional seconds for estimated times
        utc_format += '.%f'
    if len(utc_string) > 26:  # truncate to 6 fractional digits
        utc_string = utc_string[:26]
        
    return datetime.strptime(utc_string, utc_format).replace(tzinfo=tz.tzutc())


def find_routes_and_stops(location, radius=1500, route_types=2):
    """
    Returns all the routes that can be taken in a radius around a location.
    A location is a dict of the form {'gps': (-37.9057, 145.0927)}, optionally with
    an additional "walking_radius" field measured in minutes, which we progressively
    add to in place with more and more information as it is collected.
    
    Why so many lines of code? We first need to talk about stops and directions.
    It's complicated. A route is composed of stops, and generally has two opposite
    directions. However the paths taken by a vehicle in each direction need not to
    be the same, so there can be stops and corresponding IDs that only appear along
    a specific direction. The opposite is also true: distinct physical stops can share
    the same ID if close enough, typical case being opposite stops on residential roads.
    The granularity seems to be at the road intersection level, i.e. ~15 meters radius.
    Even more confusingly, different routes can have the same direction, so there can
    also be a many-to-one mapping between routes and directions for a stop.
    
    Back to "why so many lines of code": reality is messy, and the API doesn't do much to
    improve on the situation. In fact, the API does not make it easy to collect all the
    required information. From GPS coordinates you can get stops, which however need to be
    checked for departures. From stops you obtain routes, but then you have to query each
    for directions of travel, and then for stop sequence numbers along each direction just
    to confirm that a bus will indeed stop at a location for your intended direction of travel.

    Given a stop, its sequence number is: 
    sequence_number = location['stops'][stop_id]['routes'][route_id][direction_id]

    Given a route, its sequence number is recorded for convenience as:
    sequence_number = location['routes'][route_id]['directions'][direction_id]['sequences']
    
    In the example below, stop #13950 is shared between directions #185 and #186,
    whereas route #13027 has separate stops for each direction of travel.

    >> setup_ptv(PTVv3('your_ptv_id', 'your_ptv_key'))
    >> location = {'gps': (-37.905457, 145.051951)}
    >> find_routes_and_stops(location, radius=500)
    >> print(location['stops'])  # indexed by stop ID
    {
        13950:
        {
            'id': 13950,
            'name': 'North Rd/Koornang Rd',
            'gps': (-37.90537, 145.053925),
            'distance': 173.1222,
            'routes':
            {
                15248:
                {
                    185: 29,
                    186: 17
                }
            }
        },
        13991:
        {
            'id': 13991,
            'name': 'Wild Cherry Rd/Leila Rd',
            'gps': (-37.90137, 145.051315),
            'distance': 458.153137,
            'routes':
            {
                13027:
                {
                    27: 22
                }
            }
        }
        [...]
    }
    >> print(location['routes'])  # indexed by route ID
    {
        15248:
        {
            'id': 15248,
            'type': 2,
            'number': '626',
            'name': 'Middle Brighton - Chadstone via McKinnon & Carnegie',
            'directions':
            {
                185: {'name': 'Chadstone', 'stop': 13950, 'sequence': 29},
                186: {'name': 'Middle Brighton', 'stop': 13950, 'sequence': 17}
            }
        },
        13027:
        {
            'id': 13027,
            'type': 2,
            'number': '625',
            'name': 'Elsternwick - Chadstone via Ormond & Oakleigh',
            'directions':
            {
                181: {'name': 'Chadstone SC', 'stop': 16942, 'sequence': 28},
                27: {'name': 'Elsternwick', 'stop': 13991, 'sequence': 22}
            }
        },
        [...]
    }
    """
    assert ptv, 'You need to initialize the ptv object with setup_ptv'

    gps_latitude, gps_longitude = location['gps']  # find stops and sort them by distance
    stops_at_coordinates = ptv(f'/v3/stops/location/{gps_latitude},{gps_longitude}', route_types=route_types, max_distance=radius)
    stops_by_distance = sorted(stops_at_coordinates['stops'], key=lambda s: s['stop_distance'])

    reachable_routes = {  # find routes associated with stops and their direction of travel
        route_id: {
            'directions': {
                direction['direction_id']: {
                    'name': direction['direction_name'],
                    'stop': None}
                for direction in ptv(f'/v3/directions/route/{route_id}')['directions']}}
        for route_id in {route['route_id'] for stop in stops_by_distance for route in stop['routes']}}
    
    for route_id in reachable_routes:  # find sequence numbers of stops along a direction
        for direction_id, direction_data in reachable_routes[route_id]['directions'].items():
            stops_with_sequence = ptv(f'/v3/stops/route/{route_id}/route_type/{route_types}', direction_id=direction_id)['stops']
            stops_along_direction = {stop['stop_id']: stop for stop in stops_with_sequence if stop['stop_sequence'] != 0}
            
            for stop in stops_by_distance:  # find closest stop for a direction
                if stop['stop_id'] in stops_along_direction:
                    direction_data['sequence'] = stops_along_direction[stop['stop_id']]['stop_sequence']
                    direction_data['stop'] = stop['stop_id']
                    break

    closest_stops = {direction_data['stop']
                     for route_data in reachable_routes.values()
                     for direction_data in route_data['directions'].values()}
    stops_db = {}
    for stop in stops_by_distance:  # organize stops info in a dictionary
        if stop['stop_id'] in closest_stops:

            routes = {
                route_id: {
                    direction_id: direction_data['sequence']
                    for direction_id, direction_data in route_data['directions'].items()
                    if direction_data['stop'] == stop['stop_id']}
                for route_id, route_data in reachable_routes.items()}
            
            stops_db[stop['stop_id']] = {
                'id': stop['stop_id'],
                'name': stop['stop_name'].strip(),
                'distance': stop['stop_distance'],
                'gps': (stop['stop_latitude'], stop['stop_longitude']),
                'routes': {k: v for k, v in routes.items() if v}}
            
    for stop in stops_by_distance:  # organize routes info in a dictionary
        for route in stop['routes']:
            route_id = route['route_id']
            if route_id in reachable_routes:
                reachable_routes[route_id]['id'] = route_id
                reachable_routes[route_id]['type'] = route['route_type']
                reachable_routes[route_id]['number'] = route['route_number']
                reachable_routes[route_id]['name'] = route['route_name'].strip()

    location['stops'] = stops_db
    location['routes'] = reachable_routes
    return location


def filter_by_walking_distance(location):
    """
    Uses Google Maps distance matrix API to filter stops beyond a walking distance
    threshold, in minutes. Parameter gmaps is an instance of googlemaps client,
    found here: https://github.com/googlemaps/google-maps-services-python

    Adds the walking times information and filters the location data, both in place.
    See below an example of the updated structure, with 'walking' and 'address' fields
    added. Values for distance and duration are respectively expressed in meters and seconds.
    
    >> print(location['stops'])
    {
        10005:
        {
            'id': 10005,
            'name': 'Oakleigh SC/Hanover St',
            'gps': (-37.9007721, 145.091919),
            'distance': 552.747742,
            'routes':
            {
                8922: {260: 6},
                8924: {260: 6},
                8934: {260: 6},
                13820: {260: 6}
            },
            'walking':
            {
                'distance': {'text': '0.7 km', 'value': 660},
                'duration': {'text': '10 mins', 'value': 588}
            },
            'address': 'Oakleigh SC/Hanover St, Oakleigh VIC 3166, Australia'
        },
        [...]
    }
    >> print(location['routes'])
    {
        8922:
        {
            'id': 8922,
            'type': 2,
            'number': '862',
            'name': 'Dandenong - Chadstone via North Dandenong & Oakleigh',
            'directions':
            {
                260: {'name': 'Dandenong', 'sequence': 6, 'stop': 10005}
            }
        },
        8924:
        {
            'id': 8924,
            'type': 2,
            'number': '802',
            'name': 'Dandenong - Chadstone via Mulgrave & Oakleigh',
            'directions':
            {
                260: {'name': 'Dandenong', 'sequence': 6, 'stop': 10005}
            }
        },
        [...]
    }
    """
    assert gmaps, 'You need to initialize the gmaps object with setup_gmaps'
    
    stops_db = location['stops']
    if not stops_db:
        return
    
    stop_coords = [stop['gps'] for stop in stops_db.values()]
    walkings = gmaps.distance_matrix([location['gps']], stop_coords, mode="walking")
    for stop, address, walking in zip(stops_db, walkings['destination_addresses'], walkings['rows'][0]['elements']):
        walking.pop('status')
        stops_db[stop]['walking'] = walking
        stops_db[stop]['address'] = address

    location['stops'] = {  # drop unreachable stops
        stop_id: stop_data
        for stop_id, stop_data in location['stops'].items()
        if stop_data['walking']['duration']['value'] <= location['walking_radius'] * 60}

    for route_data in location['routes'].values():  # drop unreachable directions
        route_data['directions'] = {
            direction_id: direction_data
            for direction_id, direction_data in route_data['directions'].items()
            if direction_data['stop'] in location['stops']}
            
    location['routes'] = {  # drop unreachable routes
        route_id: route_data
        for route_id, route_data in location['routes'].items()
        if route_data['directions']}
            
    return location


def find_connecting_routes(start_location, dest_location):
    """
    Returns direct connecting routes between start and destination locations.
    Locations must already contain information about routes and stops, collected above.

    Again, in the example below, we show a case in which the two directions of travel
    are not symmetric. Stops at the end of a route do not have any departures. 'walking'
    gives the time required, in seconds, to reach a given stop on foot from its reference
    location.

    connections = find_routes(oakleigh, monash)
    >> print(connections)
    {
        13067:
        {
            'route_id': 13067,
            'number': '630',
            'name': 'Elwood - Monash University via Gardenvale & Ormond & Huntingdale',
            'forward_direction': {'id': 188, 'origin': 22875, 'destination': 33430},
            'reverse_direction': {'id': 189, 'origin': 33430, 'destination': 18098},
            'walking': {22875: 571, 33430: 430, 18098: 617}
        },
        [...]
    }
    """
    assert ptv, 'You need to initialize the ptv object with setup_ptv'
    
    start_routes = start_location['routes']
    dest_routes = dest_location['routes']

    connections = {}
    for route_id in sorted(set(start_routes).intersection(set(dest_routes)), key=lambda r: start_routes[r]['number']):

        direction_ids = set(start_routes[route_id]['directions']).intersection(set(dest_routes[route_id]['directions']))
        if not direction_ids:
            continue

        connection = {
            'id': route_id,
            'type': start_routes[route_id]['type'],
            'name': start_routes[route_id]['name'],
            'number': start_routes[route_id]['number']}

        for direction_id in direction_ids:
            start_sequence_num = start_routes[route_id]['directions'][direction_id]['sequence']
            dest_sequence_num = dest_routes[route_id]['directions'][direction_id]['sequence']
            if start_sequence_num < dest_sequence_num:
                connection['forward_direction'] = {
                    'id': direction_id,
                    'origin': start_routes[route_id]['directions'][direction_id]['stop'],
                    'destination': dest_routes[route_id]['directions'][direction_id]['stop']}
            else:
                connection['reverse_direction'] = {
                    'id': direction_id,
                    'origin': dest_routes[route_id]['directions'][direction_id]['stop'],
                    'destination': start_routes[route_id]['directions'][direction_id]['stop']}

        if not 'forward_direction' in connection:
            continue

        route = connection['forward_direction']
        connection['walking'] = {
            route[side]: location['stops'][route[side]]['walking']['duration']['value']
            for side, location in (('origin', start_location), ('destination', dest_location))}

        if 'reverse_direction' in connection:  # reverse can be absent if stops for direction are too far away
            route = connection['reverse_direction']
            for side, location in (('origin', dest_location), ('destination', start_location)):
                connection['walking'][route[side]] = location['stops'][route[side]]['walking']['duration']['value']
                
        connections[route_id] = connection
        
    return connections


def compute_travel_time(connections):
    """
    Uses expected departure times to compute the expected trip duration.
    Interestingly, the projected trip length varies throughout the day.
    We report the average, minimum and maximum duration in seconds.

    Terminus stations do not have departures when used as destinations.
    We counteract the problem when it happens by computing the duration
    for the reverse trip. No provision is made in the present code for
    trips where both origin and destination are terminus stops. My best
    bet would be to compute the duration of the trip from origin to the
    stop before terminus, and extrapolate by multiplying with N / (N-1)
    where N is the total number of stops. Send a pull request ;)

    This function updates the connections database in place and returns it.
    """
    assert ptv, 'You need to nitialize the ptv object with setup_ptv'

    for connection in connections.values():

        for direction in ('forward_direction', 'reverse_direction'):

            origin_departures = ptv(  # for some stops, no results are returned if not given a max_results parameter (wtf?!)
                f'/v3/departures/route_type/{connection["type"]}/stop/{connection[direction]["origin"]}/route/{connection["id"]}',
                expand='All', include_geopath='false', direction_id=connection[direction]['id'], max_results=1000)
            dest_departures = ptv(
                f'/v3/departures/route_type/{connection["type"]}/stop/{connection[direction]["destination"]}/route/{connection["id"]}',
                expand='All', include_geopath='false', direction_id=connection[direction]['id'], max_results=1000)

            if origin_departures['departures'] and dest_departures['departures']:
                break

        else:  # no departures from terminus stations, and if here both origin and destination are. Giving up.
            connection['duration'] = {'min': None, 'max': None, 'avg': None}
            continue
    
        runrefs_origin = {departure['run_ref']: departure for departure in origin_departures['departures']}
        runrefs_dest = {departure['run_ref']: departure for departure in dest_departures['departures']}
        common_refs = sorted(set(runrefs_origin).intersection(set(runrefs_dest)))
    
        travel_times = []
        for ref in common_refs:
            start_time = parse_utc(runrefs_origin[ref]['scheduled_departure_utc'])
            end_time = parse_utc(runrefs_dest[ref]['scheduled_departure_utc'])
            travel_time = (end_time - start_time).total_seconds()
            travel_times.append(travel_time % (60 * 60 * 24))

        connection['duration'] = {
            'min': int(min(travel_times)),
            'max': int(max(travel_times)),
            'avg': int(round(sum(travel_times) / len(travel_times)))}

    return connections


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
