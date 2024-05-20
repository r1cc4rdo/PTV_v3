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
    gps_latitude, gps_longitude = gps_coordinates
    stops_at_coordinates = ptv(f'/v3/stops/location/{gps_latitude},{gps_longitude}', route_types=route_types, max_distance=radius)
    stops_by_distance = sorted(stops_at_coordinates['stops'], key=lambda s: s['stop_distance'])
    reachable_routes = {
        route_id: {
            'directions': {
                direction['direction_id']: {
                    'name': direction['direction_name'],
                    'stop': None}
                for direction in ptv(f'/v3/directions/route/{route_id}')['directions']}}
        for route_id in {route['route_id'] for stop in stops_by_distance for route in stop['routes']}}
    
    for route_id in reachable_routes:
        for direction_id, direction_data in reachable_routes[route_id]['directions'].items():
            stops_with_sequence = ptv(f'/v3/stops/route/{route_id}/route_type/{route_types}', direction_id=direction_id)['stops']
            stops_along_direction = {stop['stop_id']: stop for stop in stops_with_sequence if stop['stop_sequence'] != 0}
            
            for stop in stops_by_distance:
                if stop['stop_id'] in stops_along_direction:
                    direction_data['sequence'] = stops_along_direction[stop['stop_id']]['stop_sequence']
                    direction_data['stop'] = stop['stop_id']
                    break

    closest_stops = {direction_data['stop']
                     for route_data in reachable_routes.values()
                     for direction_data in route_data['directions'].values()}
    stops_db = {}
    for stop in stops_by_distance:
        if stop['stop_id'] in closest_stops:
            stops_db[stop['stop_id']] = {
                'id': stop['stop_id'],
                'name': stop['stop_name'].strip(),
                'distance': stop['stop_distance'],
                'gps': tuple(stop['stop_' + field] for field in ('latitude', 'longitude')),
                'directions': {
                    direction_id: {
                        'name': direction_data['name'],
                        'sequence': direction_data['sequence'],
                        'route': route_id}
                    for route_id, route_data in reachable_routes.items()
                    for direction_id, direction_data in route_data['directions'].items()
                    if direction_data['stop'] == stop['stop_id']}}            
            
    for stop in stops_by_distance:
        for route_info in stop['routes']:
            route_id = route_info['route_id']
            if route_id in reachable_routes:
                reachable_routes[route_id]['id'] = route_id
                reachable_routes[route_id]['number'] = route_info['route_number']
                reachable_routes[route_id]['name'] = route_info['route_name'].strip()

    return stops_db, reachable_routes


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
