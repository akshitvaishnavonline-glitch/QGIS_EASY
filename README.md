# QGIS_EASY
Making QGIS simple and easy to use by automating repetitive GIS tasks, such as calculating road lengths, extracting road networks, and generating district-wise statistics using Python.
# QGIS_EASY

Making QGIS simple and easy to use through Python automation.

## About

QGIS_EASY is a collection of simple Python tools designed to automate repetitive GIS tasks in QGIS.

## Current Tool: Road Length Automation

This tool helps users:
- Extract specific road types, such as National Highways and State Highways.
- Calculate road-segment lengths in kilometres.
- Calculate total road length.
- Generate district-wise road-length statistics.

## Requirements

- QGIS
- A road network vector layer with line geometry
- A road-type or reference field
- A district attribute for district-wise statistics

## Usage

1. Open QGIS and the Processing Toolbox.
2. Load the Python script into the QGIS Processing Scripts section.
3. Select the road network layer.
4. Specify the road field and road type.
5. Select the district field and output destinations.
6. Run the tool to generate the road-length and district statistics outputs.

## Project Status

Under development. Contributions and suggestions are welcome.
