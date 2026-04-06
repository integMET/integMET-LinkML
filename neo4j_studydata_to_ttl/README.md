# Neo4j JSON to RDF Converter and TTL to RDF-config YAML Generator

## Neo4j JSON to RDF Converter Overview

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

## RDF-config YAML Generator Overview 

This tool is intended for cases such as the following:

- You want to generate RDF-config files from existing RDF/Turtle data.
- You want a practical first draft of `model.yaml` based on both ontology definitions and actual instance data.
- You want regenerated YAML to follow updates to `@prefix` aliases or namespace declarations in the source TTL files.
- You want an initial `description.yaml` draft derived from ontology metadata such as `rdfs:label` and `rdfs:comment`.

The purpose of this script is not to produce a perfect final configuration with no review. Instead, it is designed to generate a stable, reviewable first draft that is easy to refine.

## Output Logic

### 1. Prefix extraction

- Both ontology TTL and data TTL are loaded.
- The script tries to preserve the declaration order of `@prefix` statements.
- If multiple prefixes point to the same namespace URI, the alias found in the data TTL is preferred.
- If a namespace is used but not explicitly declared, the script falls back to namespace information available through `rdflib`.

### 2. Subject discovery

- `owl:Class` resources defined in the ontology are detected.
- The script checks which classes actually appear in the data TTL through `rdf:type`.
- Classes in the ontology namespace that are used in the data are adopted as modeled subjects.
- Subject names are generated in CamelCase from class local names.

### 3. Predicate and object generation

- For each class, the script collects predicates actually used by its instances.
- If an object refers to another typed resource, the target class is inferred.
- Object names are generated automatically in snake_case while avoiding duplicates.

### 4. Cardinality inference

Predicate cardinality is inferred from occurrence counts observed in the data TTL.

- `?` : 0 or 1
- `*` : 0 or more
- `+` : 1 or more, with multiple values observed
- `{n}` : always exactly `n`
- `{n,m}` : between `n` and `m`

This cardinality is an empirical estimate based on the supplied data TTL. It is not a formal ontology guarantee.

### 5. Description generation

`description.yaml` descriptions are generated with the following priority:

1. `rdfs:comment`
2. `rdfs:label`
3. fallback wording derived from local names

---
## Usage

Edit the configuration block at the top of `ttl_to_rdfconfig.py`.

```python
ONTOLOGY_TTL_PATH = Path("/path/to/integmet_study_rdf_ontology.ttl")
DATA_TTL_PATH = Path("/path/to/integmet_study_rdf.ttl")
OUTPUT_DIR = Path("/path/to/output")
EXAMPLES_PER_CLASS = 3
```

Meaning of each setting:

- `ONTOLOGY_TTL_PATH`: path to the ontology TTL file
- `DATA_TTL_PATH`: path to the instance/data TTL file
- `OUTPUT_DIR`: output directory for generated YAML files
- `EXAMPLES_PER_CLASS`: number of example instances to include in each `model.yaml` subject header

After editing the settings, run:

```bash
python ttl_to_rdfconfig.py
```

---
