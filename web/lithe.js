/**
 * Shows how to access a limited/undocumented PTV API without an id/key pair.
 * First spotted here: https://github.com/imchlorine/PTVTimetable
 * Standard documented call do not work directly, but it should be possible
 * to modify the /v3/departures and /v3/runs endpoints in logic.js accordingly,
 * avoiding having to expose the key in the source. Send a pull request?
 */

const baseURL = "https://www.ptv.vic.gov.au/lithe";

async function getToken()
{
    let url = "https://www.ptv.vic.gov.au";
    let response = await fetch(url);
    let result = await response.text();
    let token = result.match(/"fetch-key" value="([^"]+)"/)[1];
    return token;
}

async function apiRequest(uri)
{
    let encodedUri = encodeURI(uri);
    let url = baseURL + encodedUri + `__tok=${token}`;
    let response = await fetch(url);
    let jsonResult = await response.json();
    return jsonResult;
}

async function getRoutes(routeType=2)
{
    let uri = `/routes?route_type=${routeType}&`;
    result = await apiRequest(uri);
    return result["routes"]
}

const token = await getToken()

console.log(token)
console.log(getRoutes())
