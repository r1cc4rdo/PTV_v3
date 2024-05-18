import requests
import hashlib
import hmac


class PTVv3:
    """
    Minimal implementation of the Public Transport Victoria (PTV) v3 API.
    For documentation and instructions to obtain an id/key pair please visit:
    https://www.ptv.vic.gov.au/footer/data-and-reporting/datasets/ptv-timetable-api
    This file is part of the https://github.com/r1cc4rdo/PTV_v3 repository.
    """
    base_url = 'https://timetableapi.ptv.vic.gov.au'

    def __init__(self, ptv_id, ptv_key, debug=False):
        
        self.id = ptv_id
        self.key = ptv_key.encode('utf-8')
        self.debug = debug

    def __call__(self, endpoint, **params):
        """
        Signs and performs a request; throws on failure.
        Returns the JSON encoded response.
        """
        params['devid'] = self.id
        encoded = [f'{k}={v}'
                   for k, vs in params.items()
                   for v in (vs if isinstance(vs, (list, tuple)) else [vs])]
        
        request = f'{endpoint}?{"&".join(encoded)}'
        hashed = hmac.new(self.key, request.encode('utf-8'), hashlib.sha1)
        url = f'{PTVv3.base_url}{request}&signature={hashed.hexdigest()}'
        if self.debug:
            print(url)
        
        response = requests.get(url)
        response.raise_for_status()
        return response.json()


if __name__ == '__main__':
    ptv_id, ptv_key = 'your id here', 'your key here'
    ptv = PTVv3(ptv_id, ptv_key, debug=True)
    print(ptv('/v3/disruptions', route_types=2))
