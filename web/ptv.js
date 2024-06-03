/**
 * Minimal implementation of the Public Transport Victoria (PTV) v3 API.
 * Translated by ChatGPT with some human guidance from the Python original.
 * For documentation and instructions to obtain an id/key pair please visit:
 * https://www.ptv.vic.gov.au/footer/data-and-reporting/datasets/ptv-timetable-api
 * Here's an usage example:
 * 
 * const ptvId = 'your_id_here';
 * const ptvKey = 'your_key_here';
 * const ptv = new PTVv3(ptvId, ptvKey);
 * ptv.call('/v3/route_types')
 *     .then(data => {
 *         console.log('API Response:', data);
 *     })
 *     .catch(error => {
 *         console.error('API Error:', error);
 *     });
 * 
 * This file is part of the https://github.com/r1cc4rdo/PTV_v3 repository.
 */ 
class PTVv3
{
    constructor(ptvId, ptvKey, debug = false)
    {
        this.baseUrl = 'https://timetableapi.ptv.vic.gov.au';
        this.id = ptvId;
        this.key = ptvKey;
        this.debug = debug;
    }

    async call(endpoint, params = {})
    {
        params['devid'] = this.id;
        const query = new URLSearchParams(params).toString();
        const request = `${endpoint}?${query}`;
        const signature = await this.generateSignature(request);
        const url = `${this.baseUrl}${request}&signature=${signature}`;
        if (this.debug)
        {
            console.log(`Request URL: ${url}`);
        }

        const response = await fetch(url);
        if (!response.ok)
        {
            throw new Error(`Network response was not ok: ${response.statusText}`);
        }
        return response.json();
    }

    async generateSignature(request)
    {
        const encoder = new TextEncoder();
        const keyData = encoder.encode(this.key);
        const requestData = encoder.encode(request);
        const cryptoKey = await crypto.subtle.importKey('raw', keyData,
            { name: 'HMAC', hash: { name: 'SHA-1' } }, false, ['sign']);
        const signature = await crypto.subtle.sign('HMAC', cryptoKey, requestData);
        return Array.from(new Uint8Array(signature)).map(b => b.toString(16).padStart(2, '0')).join('');
    }
}
