from datetime import datetime
from dateutil import tz


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


def routes_from_gps(ptv, gps_coordinates, radius=1500, route_types=2):
    """
    Returns all the routes that can be taken in a radius around a location.
    Parameter ptv is an instance of PTVv3 class. See example below.
    
    Why so many lines of code? We first need to talk about stops and directions.
    It's complicated. A route is composed of stops, and generally has two opposite
    directions. However the paths taken by a vehicle in each direction need not to
    be the same, so there can be stops and corresponding IDs that only appear along
    a specific direction. The opposite is also true: distinct physical stops can share
    the same ID if close enough, typical case being opposite stops on residential roads.
    The granularity seems to be at the road intersection level, i.e. ~15 meters radius.
    
    The API does not make it easy to collect all the required information. From GPS
    coordinates you can get stops, and from stops you obtain routes. But then you have
    to query each for directions of travel, and then for stop sequence numbers along each
    direction just to confirm that a bus will indeed stop at a location for your intended
    direction of travel.

    In the example below, stop #13950 is shared between directions #185 and #186,
    whereas route #13027 has separate stops for each direction of travel.
    
    >> ptv = PTVv3('your_ptv_id', 'your_ptv_key')
    >> stop_db, route_db = routes_from_gps(ptv, (-37.9055333, 145.0519582), radius=500)
    >> print(stop_db)  # indexed by stop ID
    {
        13950:
        {
            'id': 13950,
            'name': 'North Rd/Koornang Rd',
            'gps': (-37.90537, 145.053925),
            'distance': 173.807861,
            'directions':
            {
                185: {'name': 'Chadstone', 'sequence': 29, 'route': 15248},
                186: {'name': 'Middle Brighton', 'sequence': 17, 'route': 15248}
            }
        },
        13991:
        {
            'id': 13991,
            'name': 'Wild Cherry Rd/Leila Rd',
            'gps': (-37.90137, 145.051315),
            'distance': 466.5808,
            'directions':
            {
                27: {'name': 'Elsternwick', 'sequence': 22, 'route': 13027}
            }
        }
        [...]
    }
    >> print(route_db)  # indexed by route ID
    {
        15248:
        {
            'id': 15248,
            'number': '626',
            'name': 'Middle Brighton - Chadstone via McKinnon & Carnegie',
            'directions':
            {
                185: {'name': 'Chadstone', 'sequence': 29, 'stop': 13950},
                186: {'name': 'Middle Brighton', 'sequence': 17, 'stop': 13950}
            }
        },
        13027:
        {
            'id': 13027,
            'number': '625',
            'name': 'Elsternwick - Chadstone via Ormond & Oakleigh',
            'directions':
            {
                181: {'name': 'Chadstone SC', 'sequence': 28, 'stop': 16942},
                27: {'name': 'Elsternwick', 'sequence': 22, 'stop': 13991}}
            }
        },
        [...]
    }
    """
    gps_latitude, gps_longitude = gps_coordinates  # find stops and sort them by distance
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
            stops_db[stop['stop_id']] = {
                'id': stop['stop_id'],
                'name': stop['stop_name'].strip(),
                'distance': stop['stop_distance'],
                'gps': (stop['stop_latitude'], stop['stop_longitude']),
                'directions': {
                    direction_id: {
                        'name': direction_data['name'].strip(),
                        'sequence': direction_data['sequence'],
                        'route': route_id}
                    for route_id, route_data in reachable_routes.items()
                    for direction_id, direction_data in route_data['directions'].items()
                    if direction_data['stop'] == stop['stop_id']}}            
            
    for stop in stops_by_distance:  # organize routes info in a dictionary
        for route_info in stop['routes']:
            route_id = route_info['route_id']
            if route_id in reachable_routes:
                reachable_routes[route_id]['id'] = route_id
                reachable_routes[route_id]['number'] = route_info['route_number']
                reachable_routes[route_id]['name'] = route_info['route_name'].strip()

    return stops_db, reachable_routes


def filter_by_walking_distance(gmaps, gps_coordinates, minutes, stops_db, route_db):
    """
    Uses Google Maps distance matrix API to filter stops beyond a walking distance
    threshold, in minutes. Parameter gmaps is an instance of googlemaps client, found
    here: https://github.com/googlemaps/google-maps-services-python

    Returns filtered *copies* of the routes and stops' databases, but updates the
    walking times information in place. Below is an example of the updated structure,
    with 'walking' and 'address' fields added. Values for distance and duration are
    respectively expressed in meters and seconds.
    
    >> print(stops_db)
    {
        10005:
        {
            'id': 10005,
            'name': 'Oakleigh SC/Hanover St',
            'gps': (-37.9007721, 145.091919),
            'distance': 552.747742,
            'directions':
            {
                260: {'name': 'Dandenong', 'route': 8924, 'sequence': 6}
            },
            'walking':
            {
                'distance': {'text': '0.7 km', 'value': 673},
                'duration': {'text': '10 mins', 'value': 596}
            },
            'address': 'Oakleigh SC/Hanover St, Oakleigh VIC 3166, Australia'
        },
        [...]
    }    
    """
    stop_coords = [stop['gps'] for stop in stops_db.values()]
    walkings = gmaps.distance_matrix([gps_coordinates], stop_coords, mode="walking")
    for stop, address, walking in zip(stops_db, walkings['destination_addresses'], walkings['rows'][0]['elements']):
        walking.pop('status')
        stops_db[stop]['walking'] = walking
        stops_db[stop]['address'] = address
        
    stops_db = {k: v for k, v in stops_db.items() if v['walking']['duration']['value'] <= minutes*60}
    route_db = {k: v for k, v in route_db.items() if any(direction['stop'] in stops_db for direction in v['directions'].values())}
    return stops_db, route_db


def route_connections(start_routes, dest_routes):
    """
    Returns direct connections between start and destination locations.
    Parameters start_routes and dest_routes are in the 'routes' dict form
    as returned by routes_from_gps.

    Again, in the example below, we show a case in which the two directions of travel
    are not symmetric. Stops at the end of a route will not have departures.

    >> print(connections)
    {
        13067:
        {
            'route_id': 13067,
            'number': '630',
            'name': 'Elwood - Monash University via Gardenvale & Ormond & Huntingdale',
            'forward_direction': {'id': 188, 'origin': 22875, 'destination': 33430},
            'reverse_direction': {'id': 189, 'origin': 33430, 'destination': 18098}
        },
        [...]
    }
    """
    connections = {}
    for route_id in sorted(set(start_routes).intersection(set(dest_routes)), key=lambda r: start_routes[r]['number']):

        connections[route_id] = {
            'route_id': route_id,
            'name': start_routes[route_id]['name'],
            'number': start_routes[route_id]['number']}

        direction_ids = set(start_routes[route_id]['directions']).intersection(set(dest_routes[route_id]['directions']))
        assert len(direction_ids) == 2

        for direction_id in direction_ids:
            start_sequence_num = start_routes[route_id]['directions'][direction_id]['sequence']
            dest_sequence_num = dest_routes[route_id]['directions'][direction_id]['sequence']
            if start_sequence_num < dest_sequence_num:
                connections[route_id]['forward_direction'] = {
                    'id': direction_id,
                    'origin': start_routes[route_id]['directions'][direction_id]['stop'],
                    'destination': dest_routes[route_id]['directions'][direction_id]['stop']}
            else:
                connections[route_id]['reverse_direction'] = {
                    'id': direction_id,
                    'origin': dest_routes[route_id]['directions'][direction_id]['stop'],
                    'destination': start_routes[route_id]['directions'][direction_id]['stop']}
        assert 'forward_direction' in connections[route_id] and 'reverse_direction' in connections[route_id]

    return connections


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
