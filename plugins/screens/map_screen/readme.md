# Map Screen Plugin

This plugin displays a customisable map on your screen using Mapbox.
Internet connection is required but only the first time, to download and cache the maps.

## Installation

Run the following command to install the plugin:

```bash
pip install ./plugins/screens/map_screen
```

## Setup

### Step 1: Add your Mapbox API key

The map screen needs a Mapbox API key to work. If you don't already have one, you can get a free key by signing up at [Mapbox](https://console.mapbox.com/account/access-tokens).

Once you have your key, enter it in the admin panel and enable the map screen.

### Step 2: Choose a map style

Next, you'll need to set up a map style. This controls how your map looks, feature colours, labels, etc.

1. Go to [Mapbox Studio](https://console.mapbox.com/studio/) and click "New Style"
2. Either upload one of the example styles from the `styles` directory, or create your own from scratch
3. When you're happy with your style, click the three dot menu in the Mapbox console and copy the style URL
4. Paste this URL into the Style field in the admin panel

### Step 3: Set the map boundaries

Finally, you need to define which area of the map to display. The easiest way to do this is using Mapbox's static map playground:

1. Go to the [Mapbox Static Playground](https://docs.mapbox.com/playground/static/)
2. In the left panel, set the width and height to match your screen's resolution (for example, 800×480 for the Inky 7-inch display)
3. Drag and zoom the preview until your desired area fits within the overlay
4. In the left panel, switch the position selector to Bounding Box
5. Copy the four values (min lat, min lon, max lat, max lon) into the corresponding fields in the admin panel