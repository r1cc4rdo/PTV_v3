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
    
    Why so many lines of code? Because stops IDs along opposite directions
    can be either shared or separate, and the PTV API does not make it easy
    to inquire the many-to-many relationships between routes and stops via
    directions. If we were to return only the closest stop for a route, it
    might serve only one of the directions, and subsequent API calls would
    silently fail for the opposite one. Debugging this wasn't fun (-_-)'

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
            'latitude': -37.90537,
            'longitude': 145.053925,
            'distance': 173.807861,
            'directions':
            {
                185: {'name': 'Chadstone', 'route': 15248},
                186: {'name': 'Middle Brighton', 'route': 15248}}
            }
        },
        13991:
        {
            'id': 13991,
            'name': 'Wild Cherry Rd/Leila Rd',
            'latitude': -37.90137,
            'longitude': 145.051315,
            'distance': 466.5808,
            'directions':
            {
                27: {'name': 'Elsternwick', 'route': 13027}
            }
        }
        [...]
    }
    >> print(route_db)  # indexed by route ID
    {
        15248:
        {
            'id': 15248,
            'bus': '626',
            'name': 'Middle Brighton - Chadstone via McKinnon & Carnegie',
            'directions':
            {
                185: {'name': 'Chadstone', 'stop': 13950},
                186: {'name': 'Middle Brighton', 'stop': 13950}
            }
        },
        13027:
        {
            'id': 13027,
            'bus': '625',
            'name': 'Elsternwick - Chadstone via Ormond & Oakleigh',
            'directions':
            {
                181: {'name': 'Chadstone SC', 'stop': 16942},
                27: {'name': 'Elsternwick', 'stop': 13991}
            }
        },
        [...]
    }
    """
    gps_latitude, gps_longitude = gps_coordinates
    stops_at_coordinates = ptv(f'/v3/stops/location/{gps_latitude},{gps_longitude}', route_types=2, max_distance=radius)
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
            stops_with_sequence = ptv(f'/v3/stops/route/{route_id}/route_type/2', direction_id=direction_id)['stops']
            stops_along_direction = [stop['stop_id'] for stop in stops_with_sequence if stop['stop_sequence'] != 0]
            
            for stop in stops_by_distance:
                if stop['stop_id'] in stops_along_direction:
                    direction_data['stop'] = stop['stop_id']
                    break

    closest_stops = {direction_data['stop']
                     for route_data in reachable_routes.values()
                     for direction_data in route_data['directions'].values()}

    fields = 'id name latitude longitude distance'.split()
    stops_db = {}
    for stop in stops_by_distance:
        if stop['stop_id'] in closest_stops:
            stops_db[stop['stop_id']] = dict(zip(fields, (stop['stop_' + field] for field in fields)))
            stops_db[stop['stop_id']]['name'] = stops_db[stop['stop_id']]['name'].strip()
            stops_db[stop['stop_id']]['directions'] = {direction_id: {'name': direction_data['name'], 'route': route_id}
                                                       for route_id, route_data in reachable_routes.items()
                                                       for direction_id, direction_data in route_data['directions'].items()
                                                       if direction_data['stop'] == stop['stop_id']}
    for stop in stops_by_distance:
        for route_info in stop['routes']:
            route_id = route_info['route_id']
            if route_id in reachable_routes:
                reachable_routes[route_id]['id'] = route_id
                reachable_routes[route_id]['bus'] = route_info['route_number']
                reachable_routes[route_id]['name'] = route_info['route_name'].strip()

    return stops_db, reachable_routes


if __name__ == '__main__':
    import doctest
    doctest.testmod(verbose=True)
