const ptv = new PTVv3(ptvId, ptvKey);

function formatTimeDelta(ms)
{
    const sign = ms < 0 ? '-' : '';
    ms = Math.abs(ms);
    const seconds = Math.floor(ms / 1000) % 60;
    const minutes = Math.floor(ms / 60000) % 60;
    const hours = Math.floor(ms / 3600000);

    return `${sign}${hours > 0 ? hours + ':' : ''}${minutes.toString().padStart(hours > 0 ? 2 : 1, '0')}:${seconds.toString().padStart(2, '0')}`;
}

async function checkRoutes(services, buffer=120)
{
    let currentStep = 0;
    const totalSteps = Object.keys(connections).length * 2;
    const progressBar = document.getElementById('progress-bar');
    progressBar.style.width = `0%`;

    for (const [routeId, connection] of Object.entries(connections))
    {
        const routeType = connection.type;
        const stopId = connection.forward_direction.origin;
        const directionId = connection.forward_direction.id;

        const runs = await ptv.call(`/v3/runs/route/${routeId}/route_type/${routeType}`, { expand: 'VehiclePosition' });
        progressBar.style.width = `${(++currentStep / totalSteps) * 100}%`;

        const departures = await ptv.call(`/v3/departures/route_type/${routeType}/stop/${stopId}/route/${routeId}`,
        {
            direction_id: directionId,
            max_results: 5,
            expand: 'Disruption'
        });
        progressBar.style.width = `${(++currentStep / totalSteps) * 100}%`;

        let activeRuns = {};
        if (runs.runs)
        {
            activeRuns = Object.fromEntries(runs.runs.filter(run => run.vehicle_position !== null && run.direction_id === directionId).map(run => [run.run_ref, run]));
            everActive = new Set(Object.keys(activeRuns)).union(everActive);
        }

        if (departures.departures)
        {
            for (const [index, departure] of departures.departures.entries())
            {
                const routeActive = Object.keys(activeRuns).length > 0;
                const runActive = everActive.has(departure.run_ref);
                const hasEstimated = departure.estimated_departure_utc !== null;
                const disruptions = Object.values(departures.disruptions).map(disruption => disruption.title.trim());
                const departureTime = new Date(hasEstimated ? departure.estimated_departure_utc : departure.scheduled_departure_utc);

                const walkBefore = connection.walking[connection.forward_direction.origin];
                const getGoingBy = new Date(departureTime - walkBefore * 1000 - buffer * 1000);

                const tripDuration = connection.duration.avg * 1000;
                const walkAfter = connection.walking[connection.forward_direction.destination] * 1000;
                const arriveBy = new Date(departureTime.getTime() + tripDuration + walkAfter);

                const idString = `${routeId}-${directionId}-${stopId}-${index}`
                services[idString] =
                {
                    id: idString,
                    run_ref: departure.run_ref,
                    route_id: connection.id,
                    health:
                    {
                        run_active: runActive,
                        has_estimated: hasEstimated,
                        route_active: routeActive
                    },
                    get_going_by: getGoingBy,
                    arrive_by: arriveBy,
                    disruptions: disruptions
                };
            }
        }
    }
}

async function updateTable(services, buffer=120)
{
    const tableBody = document.getElementById('serviceTable').getElementsByTagName('tbody')[0];
    tableBody.innerHTML = '';

    const sortedServices = Object.values(services).sort((a, b) => a.arrive_by - b.arrive_by);
    const legend = ['⚫', '🔴', '🟡', '🟢'];

    for (const service of sortedServices)
    {
        const td = new Date(service.get_going_by - new Date()).getTime();
        if (td < -buffer * 1000)
        {
            continue;
        }

        const row = tableBody.insertRow();
        const healthScore = Object.values(service.health).reduce((acc, val) => acc + (val ? 1 : 0), 0);
        const healthCell = row.insertCell(0);
        healthCell.textContent = legend[healthScore];
        healthCell.title = Object.keys(service.health).map(k => (service.health[k] ? '✔ ' : '✖ ') + k).join('\n\n');

        const routeCell = row.insertCell(1);
        routeCell.textContent = connections[service.route_id].number;
        routeCell.title = connections[service.route_id].name;

        const timerCell = row.insertCell(2);
        timerCell.textContent = formatTimeDelta(td);
        timerCell.title = service.id;

        const arrivalCell = row.insertCell(3);
        const midnight = new Date()
        midnight.setHours(0, 0, 0, 0);
        const days = Math.floor((service.arrive_by - midnight) / 1000 / 60 / 60 / 24);
        arrivalCell.textContent = service.arrive_by.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) + (days ? '+' + days : '');
        arrivalCell.title = service.run_ref;

        const alertsCell = row.insertCell(4);
        alertsCell.textContent = '❗'.repeat(service.disruptions.length);
        alertsCell.title = service.disruptions.join('\n\n').trim();
    }
}

let services = {};
let everActive = new Set([]);

checkRoutes(services);
setInterval(updateTable, 1000, services);
setInterval(checkRoutes, 30000, services);
