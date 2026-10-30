# Weather enrichment

Kinetiqo can add historical, hourly weather to eligible outdoor activities
during synchronization. It uses the Visual Crossing Timeline Weather API and
requires the server environment variable:

```text
VISUAL_CROSSING_API_KEY=your-key
```

The API key is used only by the server and is never shown in the web interface,
stored in activity weather data, or written to logs.

## Enabling weather

Enable **Weather data** in Settings to use it by default for Fast Sync. On the
sync page, **Fetch weather data** enables it for that run and **Resync weather**
replaces saved weather for the selected sync scope.

Full Sync does not fetch weather unless it is explicitly enabled. Weather is
never fetched by the browser or when viewing an activity, chart, chat response,
or MCP tool result.

When weather is enabled, each activity is processed in a single ordered pass:
Kinetiqo saves the activity and streams, fetches missing weather, then updates
the Strava description. Weather placeholders therefore use the newly saved
weather during that same sync. When weather is disabled, Kinetiqo makes no
weather-provider request; a description requiring unavailable weather is
deferred until a weather-enabled sync.

## What is stored

For each eligible activity, Kinetiqo samples the GPS route at hourly intervals
and requests the matching historical weather. Short or sparse routes use the
nearest recorded GPS point in the overlapping provider hour when a midpoint
cannot be interpolated. A stationary route still receives weather, although
headwind is omitted when no travel bearing is available. Saved data can include:

- temperature and apparent temperature;
- provider condition text and source;
- rain, snow, wind direction, wind speed, and gusts;
- calculated route bearing and headwind component.

Weather is an hourly estimate, not a sensor measurement made on the athlete.
Conditions can vary over short distances and terrain. Route coordinates are
sent to Visual Crossing only for the lookup; they are not saved in the weather
payload or returned by AI/MCP tools.

Weather is retained when activities are deleted from the Kinetiqo interface.
If the same Strava activity is synchronized again, its saved weather can be
reused without another provider request.

Indoor activities and activities without a usable GPS route are skipped. A
temporary provider or network failure leaves the activity available for a later
retry.

## Visual Crossing rate limits

Visual Crossing reports the remaining daily quota in the
`X-RateLimit-Remaining` HTTP response header. When the API reports `0`,
Kinetiqo stops making further weather requests in that server process until the
next midnight UTC. HTTP 429 has the same effect.

Kinetiqo does not maintain a separate database quota counter. The stop state is
best effort: Gunicorn workers and a restarted server do not share in-memory
state. If another worker makes a request after the limit is exhausted, Visual
Crossing returns its current limit information and that worker stops too.

When the provider limit is reached, activity synchronization still completes.
Kinetiqo displays a warning that only weather enrichment stopped.

## Attribution

Weather data is provided by [Visual Crossing](https://www.visualcrossing.com/).
Use of the service remains subject to your Visual Crossing plan, terms, and
current quota allowance.
