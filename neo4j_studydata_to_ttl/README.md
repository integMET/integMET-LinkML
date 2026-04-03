# Neo4j JSON to RDF Converter

## Overview

This repository contains a Python script that converts Neo4j-derived JSON data into RDF and generates a matching ontology file.

The script reads a JSON graph exported from Neo4j and writes RDF in the following formats:

- Turtle (`.ttl`)
- N-Triples (`.nt`)
- JSON-LD (`.jsonld`)

It also generates a corresponding ontology file in Turtle format.

## Files

- `neo4j_study_json_to_rdf_with_ontology.py`  
  A Python script that converts Neo4j-derived JSON data into RDF and generates an ontology file.

- `neo4j_query_table_data_2026-4-3.json`  
  Input JSON data used by the script.

## Input JSON

The input JSON was generated from the IntegMet Neo4j data using the Cypher query described in `neo4j_study_json_to_rdf.cypher`.

The JSON has a top-level `graph_json` object containing:

- `nodes`
- `relationships`

The data includes `Study` nodes and related information such as species metadata, MeSH annotations, GO annotations, analysis groups, and analysis types.

## What the script does

The script reads the Neo4j JSON graph and converts `Study`-centered data into RDF resources.

In particular, it:

- identifies `Study` nodes and creates RDF resources for them
- uses `Study` or `Nodeid` as the primary study identifier
- adds LLM-derived text fields such as summaries, observations, and findings
- adds category information such as branch, category, and subcategory
- links studies to external resources such as MeSH, GO, NCBI Gene, and OMIM
- adds organism annotations
- adds analysis group information and file names
- maps analysis types such as `LC-MS`, `GC-MS`, and `CE-MS` to RDF terms

## Output files

The script generates the following files from the specified output base name:

- `<output_base>.ttl`
- `<output_base>.nt`
- `<output_base>.jsonld`
- `<output_base>_ontology.ttl`

## Requirements

- Python 3
- `rdflib`

Install the dependency with:

    pip install rdflib

## Usage

In the current implementation, you need to specify the source JSON data and the output file name in the code.

Run the script with:

    python neo4j_study_json_to_rdf_with_ontology.py

## Current default settings

The current code uses the following default values:

- Input JSON: `neo4j_query_table_data_2026-4-3.json`
- Output base name: `integmet_study_rdf`

With these settings, the script generates:

- `integmet_study_rdf.ttl`
- `integmet_study_rdf.nt`
- `integmet_study_rdf.jsonld`
- `integmet_study_rdf_ontology.ttl`

## Notes

Some namespace URIs in the script are marked with comments such as `need to change` or `need to check`.

Before publishing or reusing this code, you should review and update these URIs as needed.